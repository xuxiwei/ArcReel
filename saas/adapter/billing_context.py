"""Request/worker billing identity for SaaS credit holds."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True, slots=True)
class BillingIdentity:
    user_id: str
    org_id: str


_billing_identity: ContextVar[BillingIdentity | None] = ContextVar(
    "saas_billing_identity", default=None
)


def get_billing_identity() -> BillingIdentity | None:
    return _billing_identity.get()


def set_billing_identity(identity: BillingIdentity | None) -> Token[BillingIdentity | None]:
    return _billing_identity.set(identity)


def reset_billing_identity(token: Token[BillingIdentity | None]) -> None:
    _billing_identity.reset(token)


@contextmanager
def bind_billing_identity(identity: BillingIdentity | None) -> Iterator[None]:
    token = set_billing_identity(identity)
    try:
        yield
    finally:
        reset_billing_identity(token)


def identity_from_task_payload(payload: dict | None, *, user_id: str | None) -> BillingIdentity | None:
    """Restore org/user stamped into a generation task payload at enqueue time."""
    if not payload or not user_id:
        return None
    saas = payload.get("_saas")
    if not isinstance(saas, dict):
        return None
    org_id = saas.get("org_id")
    if not org_id:
        return None
    return BillingIdentity(user_id=str(user_id), org_id=str(org_id))


def stamp_task_payload(payload: dict | None, identity: BillingIdentity | None) -> dict | None:
    """Attach SaaS org to a task payload (shallow copy when needed)."""
    if identity is None:
        return payload
    base = dict(payload or {})
    base["_saas"] = {"org_id": identity.org_id}
    return base
