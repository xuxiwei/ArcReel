"""Object-storage key prefixes: org/<org_id>/user/<user_id>/ …"""

from __future__ import annotations

from saas.adapter.billing_context import get_billing_identity
from saas.adapter.mode import is_saas
from saas.isolation.paths import safe_org_segment


def tenant_object_prefix() -> str:
    """Return '' when self-hosted or billing identity missing."""
    if not is_saas():
        return ""
    identity = get_billing_identity()
    if identity is None:
        return ""
    try:
        org = safe_org_segment(identity.org_id)
        user = safe_org_segment(identity.user_id.replace(":", "_"))
    except ValueError:
        return ""
    return f"org/{org}/user/{user}/"


def apply_tenant_prefix(key_without_bucket_prefix: str) -> str:
    """Prefix a relative object key (after FORMAL_/RELAY_ prefix) when SaaS."""
    prefix = tenant_object_prefix()
    if not prefix:
        return key_without_bucket_prefix
    return f"{prefix}{key_without_bucket_prefix.lstrip('/')}"
