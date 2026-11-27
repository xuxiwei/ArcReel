"""SaaS: Aliyun OSS behind ObjectStorageClient (oss2 replaced by an in-memory fake)."""

import sys
import types

import pytest

from lib.object_storage.client import ObjectStorageClient, ObjectStorageConfig, ObjectStorageError


class _OssError(Exception):
    def __init__(self, status: int, code: str = "", message: str = "") -> None:
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


class _RequestError(_OssError):
    def __init__(self) -> None:
        super().__init__(-2, "", "connection reset")


class _Result:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Bucket:
    instances: list["_Bucket"] = []
    objects: dict[str, tuple[bytes, str | None]] = {}
    bucket_info_error: Exception | None = None
    missing_bucket = False

    def __init__(self, auth, endpoint, name, **kwargs) -> None:
        self.auth, self.endpoint, self.name, self.kwargs = auth, endpoint, name, kwargs
        _Bucket.instances.append(self)

    def get_bucket_info(self):
        if _Bucket.bucket_info_error:
            raise _Bucket.bucket_info_error
        return _Result()

    def put_object(self, key, data, headers=None):
        _Bucket.objects[key] = (data, (headers or {}).get("Content-Type"))
        return _Result(etag="ETAG1")

    def put_object_from_file(self, key, filename, headers=None):
        with open(filename, "rb") as handle:
            return self.put_object(key, handle.read(), headers=headers)

    def get_object(self, key):
        if key not in _Bucket.objects:
            raise _OssError(404, "NoSuchKey")
        data = _Bucket.objects[key][0]
        return _Result(read=lambda: data)

    def head_object(self, key):
        if _Bucket.missing_bucket:
            raise _OssError(404, "NoSuchBucket")
        if key not in _Bucket.objects:
            raise _OssError(404, "NoSuchKey")
        data, ctype = _Bucket.objects[key]
        return _Result(content_length=len(data), etag="ETAG1", headers={"Content-Type": ctype})

    def delete_object(self, key):
        _Bucket.objects.pop(key, None)

    def sign_url(self, method, key, expires, slash_safe=False):
        return f"{self.endpoint}/{key}?m={method}&e={expires}&cname={self.kwargs.get('is_cname')}"


@pytest.fixture(autouse=True)
def fake_oss2(monkeypatch: pytest.MonkeyPatch):
    mod = types.ModuleType("oss2")
    exc = types.ModuleType("oss2.exceptions")
    exc.OssError, exc.RequestError = _OssError, _RequestError
    mod.exceptions = exc
    mod.AuthV4 = lambda ak, sk: ("v4", ak, sk)
    mod.Auth = lambda ak, sk: ("v1", ak, sk)
    mod.Bucket = _Bucket
    monkeypatch.setitem(sys.modules, "oss2", mod)
    monkeypatch.setitem(sys.modules, "oss2.exceptions", exc)
    monkeypatch.delenv("ARCREEL_OSS_PUBLIC_ENDPOINT", raising=False)
    _Bucket.instances, _Bucket.objects = [], {}
    _Bucket.bucket_info_error, _Bucket.missing_bucket = None, False
    yield


def _client(endpoint: str = "oss-cn-hangzhou.aliyuncs.com", region: str = "cn-hangzhou") -> ObjectStorageClient:
    return ObjectStorageClient(ObjectStorageConfig("oss", region, endpoint, "media", " AK ", " SK "))


async def test_round_trip_and_https_v4() -> None:
    client = _client(region="oss-cn-hangzhou")
    assert await client.put_bytes("a/b.png", b"img", content_type="image/png") == "ETAG1"
    assert await client.get_bytes("a/b.png") == b"img"
    info = await client.head("a/b.png")
    assert (info.size, info.content_type) == (3, "image/png")
    assert client.head_sync("a/b.png").size == 3
    await client.delete("a/b.png")
    assert "a/b.png" not in _Bucket.objects
    bucket = _Bucket.instances[0]
    assert bucket.endpoint == "https://oss-cn-hangzhou.aliyuncs.com"
    assert bucket.auth == ("v4", "AK", "SK")
    assert bucket.kwargs["region"] == "cn-hangzhou"


def test_put_file_uses_streaming_upload(tmp_path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    assert _client().put_file_sync("v.mp4", video, content_type="video/mp4") == "ETAG1"
    assert _Bucket.objects["v.mp4"] == (b"video", "video/mp4")


async def test_presign_never_uses_internal_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    url = await _client("oss-cn-hangzhou-internal.aliyuncs.com").presign_get("k.png", expires_seconds=600)
    assert url.startswith("https://oss-cn-hangzhou.aliyuncs.com/k.png?m=GET&e=600")

    monkeypatch.setenv("ARCREEL_OSS_PUBLIC_ENDPOINT", "media.example.com")
    url = await _client("oss-cn-hangzhou-internal.aliyuncs.com").presign_get("k.png", expires_seconds=10**9)
    assert url.startswith("https://media.example.com/k.png?m=GET&e=604800&cname=True")


async def test_errors_are_classified() -> None:
    client = _client()
    with pytest.raises(ObjectStorageError) as err:
        await client.get_bytes("missing")
    assert err.value.kind == "not_found"

    _Bucket.bucket_info_error = _OssError(403, "InvalidAccessKeyId", "bad key")
    with pytest.raises(ObjectStorageError) as err:
        await client.check()
    assert (err.value.kind, err.value.code) == ("auth", "InvalidAccessKeyId")

    _Bucket.bucket_info_error = _RequestError()
    with pytest.raises(ObjectStorageError) as err:
        await client.check()
    assert err.value.kind == "network"


async def test_check_falls_back_when_bucket_info_denied() -> None:
    _Bucket.bucket_info_error = _OssError(403, "AccessDenied")
    await _client().check()  # NoSuchKey on the probe proves access

    _Bucket.missing_bucket = True
    with pytest.raises(ObjectStorageError) as err:
        await _client().check()
    assert (err.value.kind, err.value.code) == ("not_found", "NoSuchBucket")


def test_unknown_kind_still_rejected() -> None:
    with pytest.raises(ObjectStorageError):
        ObjectStorageClient(ObjectStorageConfig("s3", "r", "e", "b", "a", "s"))


def test_router_infers_kind_from_endpoint() -> None:
    from server.routers.object_storage import SaveObjectStorageConnectionRequest

    def body(endpoint: str, **kw):
        return SaveObjectStorageConnectionRequest(region="cn-hangzhou", endpoint=endpoint, bucket="b", **kw)

    assert body("oss-cn-hangzhou.aliyuncs.com").kind == "oss"
    assert body("https://oss-cn-hangzhou-internal.aliyuncs.com").kind == "oss"
    assert body("tos-cn-beijing.volces.com").kind == "tos"
    assert body("oss-cn-hangzhou.aliyuncs.com", kind="tos").kind == "tos"
