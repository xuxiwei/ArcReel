"""Aliyun OSS backend for ``lib.object_storage.client.ObjectStorageClient``.

Upstream ships TOS only and drives the TOS SDK through a handful of calls
(``head_bucket`` / ``put_object`` / ``put_object_from_file`` / ``get_object`` / ``head_object`` / ``delete_object`` /
``pre_signed_url``, each with ``bucket=`` and keyword arguments). :class:`OssSdkShim` offers the
same calls on top of ``oss2`` so the client, formal objects, relay copies and disposal keep
working unchanged. Failures are raised as :class:`ObjectStorageError` with the same kinds the UI
already maps.

Connection fields for OSS:

- ``endpoint``: ``oss-cn-hangzhou.aliyuncs.com`` (or the ``-internal`` endpoint when the server runs
  on ECS in the same region — uploads/downloads then cost no public traffic);
- ``region``: ``cn-hangzhou`` (``oss-cn-hangzhou`` is accepted too);
- ``bucket``, AccessKey ID / Secret of a RAM user limited to that bucket.

Signed download URLs must be reachable by browsers and media providers, so they are never signed
for an ``-internal`` endpoint: ``ARCREEL_OSS_PUBLIC_ENDPOINT`` (a public endpoint or a bound custom
domain / CDN host) wins, otherwise ``-internal`` is dropped from the connection endpoint.

Secrets are only used to build the SDK objects; they never reach logs or error text.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from lib.object_storage.client import ObjectStorageConfig, ObjectStorageError, ObjectStorageErrorKind

PUBLIC_ENDPOINT_ENV = "ARCREEL_OSS_PUBLIC_ENDPOINT"
_AUTH_CODES = frozenset(
    {"InvalidAccessKeyId", "SignatureDoesNotMatch", "SecurityTokenExpired", "InvalidSecurityToken", "AccessKeyDisabled"}
)
_CONNECT_TIMEOUT_SEC = 10
# OSS V4 signatures are valid for at most 7 days.
_MAX_PRESIGN_SECONDS = 7 * 24 * 3600


def is_oss_endpoint(endpoint: str) -> bool:
    return _host(endpoint).endswith(".aliyuncs.com")


def _host(endpoint: str) -> str:
    host = endpoint.strip().lower()
    for scheme in ("https://", "http://"):
        host = host.removeprefix(scheme)
    return host.split("/", 1)[0]


def _https(endpoint: str) -> str:
    endpoint = endpoint.strip().rstrip("/")
    if endpoint.lower().startswith(("http://", "https://")):
        return endpoint
    return f"https://{endpoint}"


def _region(region: str) -> str:
    return region.strip().lower().removeprefix("oss-")


def public_endpoint(endpoint: str) -> tuple[str, bool]:
    """Endpoint used for signed URLs and whether it is a custom domain (CNAME)."""
    override = os.environ.get(PUBLIC_ENDPOINT_ENV, "").strip()
    if override:
        return _https(override), not is_oss_endpoint(override)
    return _https(endpoint.replace("-internal.aliyuncs.com", ".aliyuncs.com")), False


def _classify(exc: Exception) -> ObjectStorageError:
    from oss2 import exceptions as oss_exc

    if isinstance(exc, oss_exc.RequestError):
        return ObjectStorageError("network", message=type(exc).__name__)
    if isinstance(exc, oss_exc.OssError):
        status = getattr(exc, "status", None)
        code = str(getattr(exc, "code", "") or "")
        message = str(getattr(exc, "message", "") or "")
        if status is not None and status < 0:
            return ObjectStorageError("network", code=code, message=type(exc).__name__)
        if code in _AUTH_CODES:
            kind: ObjectStorageErrorKind = "auth"
        elif status == 404:
            kind = "not_found"
        elif status == 403:
            kind = "denied"
        else:
            kind = "provider"
        return ObjectStorageError(kind, code=code, message=message, status_code=status)
    return ObjectStorageError("provider", message=type(exc).__name__)


@dataclass(frozen=True)
class _PutResult:
    etag: str


@dataclass(frozen=True)
class _HeadResult:
    content_length: int
    etag: str
    content_type: str | None


@dataclass(frozen=True)
class _SignedUrl:
    signed_url: str


class OssSdkShim:
    """The subset of the TOS SDK surface ``ObjectStorageClient`` uses, implemented with ``oss2``."""

    def __init__(self, config: ObjectStorageConfig) -> None:
        import oss2

        self._oss2 = oss2
        self._bucket_name = config.bucket.strip()
        self._region = _region(config.region)
        ak, sk = config.access_key_id.strip(), config.secret_access_key.strip()
        auth_v4 = getattr(oss2, "AuthV4", None)
        self._auth = auth_v4(ak, sk) if auth_v4 is not None else oss2.Auth(ak, sk)
        self._bucket = self._make_bucket(_https(config.endpoint), is_cname=False)
        signing_endpoint, is_cname = public_endpoint(config.endpoint)
        self._signing_bucket = (
            self._bucket
            if signing_endpoint == _https(config.endpoint) and not is_cname
            else self._make_bucket(signing_endpoint, is_cname=is_cname)
        )

    def _make_bucket(self, endpoint: str, *, is_cname: bool) -> Any:
        kwargs: dict[str, Any] = {"connect_timeout": _CONNECT_TIMEOUT_SEC, "is_cname": is_cname}
        if getattr(self._oss2, "AuthV4", None) is not None:
            kwargs["region"] = self._region
        return self._oss2.Bucket(self._auth, endpoint, self._bucket_name, **kwargs)

    def _check_bucket(self, bucket: str) -> None:
        if bucket.strip() != self._bucket_name:
            raise ObjectStorageError("invalid_config", code="BucketMismatch")

    def _guard(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ObjectStorageError:
            raise
        except Exception as exc:
            raise _classify(exc) from exc

    def head_bucket(self, *, bucket: str) -> None:
        """Credentials valid, bucket exists and is readable.

        ``GetBucketInfo`` first; a RAM user scoped to objects may be denied that, so fall back to a
        HEAD on a key that does not exist: 404 ``NoSuchKey`` proves access, ``NoSuchBucket`` does not.
        """
        self._check_bucket(bucket)
        try:
            self._guard(self._bucket.get_bucket_info)
            return
        except ObjectStorageError as exc:
            if exc.kind != "denied":
                raise
        try:
            self._guard(self._bucket.head_object, ".arcreel-connection-check")
        except ObjectStorageError as exc:
            if exc.kind == "not_found" and exc.code != "NoSuchBucket":
                return
            raise

    def put_object(self, *, bucket: str, key: str, content: bytes, content_type: str | None = None) -> _PutResult:
        self._check_bucket(bucket)
        headers = {"Content-Type": content_type} if content_type else None
        result = self._guard(self._bucket.put_object, key, content, headers=headers)
        return _PutResult(etag=str(getattr(result, "etag", "") or ""))

    def put_object_from_file(
        self, *, bucket: str, key: str, file_path: str, content_type: str | None = None
    ) -> _PutResult:
        self._check_bucket(bucket)
        headers = {"Content-Type": content_type} if content_type else None
        result = self._guard(self._bucket.put_object_from_file, key, file_path, headers=headers)
        return _PutResult(etag=str(getattr(result, "etag", "") or ""))

    def get_object(self, *, bucket: str, key: str) -> Any:
        self._check_bucket(bucket)
        return _GuardedStream(self._guard(self._bucket.get_object, key))

    def head_object(self, *, bucket: str, key: str) -> _HeadResult:
        self._check_bucket(bucket)
        result = self._guard(self._bucket.head_object, key)
        headers = getattr(result, "headers", None) or {}
        return _HeadResult(
            content_length=int(getattr(result, "content_length", 0) or 0),
            etag=str(getattr(result, "etag", "") or ""),
            content_type=headers.get("Content-Type") or getattr(result, "content_type", None),
        )

    def delete_object(self, *, bucket: str, key: str) -> None:
        self._check_bucket(bucket)
        self._guard(self._bucket.delete_object, key)

    def pre_signed_url(self, *, bucket: str, http_method: Any, key: str, expires: int) -> _SignedUrl:
        self._check_bucket(bucket)
        method = str(getattr(http_method, "value", http_method) or "GET").upper()
        if not method.endswith("GET"):
            raise ObjectStorageError("invalid_config", code="UnsupportedPresignMethod")
        seconds = max(1, min(int(expires), _MAX_PRESIGN_SECONDS))
        url = self._guard(self._signing_bucket.sign_url, "GET", key, seconds, slash_safe=True)
        return _SignedUrl(signed_url=str(url))


class _GuardedStream:
    """Body of ``get_object``; read errors are classified like every other call."""

    def __init__(self, result: Any) -> None:
        self._result = result

    def read(self) -> bytes:
        try:
            return self._result.read()
        except Exception as exc:
            raise _classify(exc) from exc


def create_oss_client(config: ObjectStorageConfig) -> OssSdkShim:
    return OssSdkShim(config)
