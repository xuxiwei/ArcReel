"""Object-storage key prefixes: org/<org_id>/user/<user_id>/ …"""

from __future__ import annotations

import logging

from saas.adapter.billing_context import get_billing_identity
from saas.adapter.mode import is_saas
from saas.isolation.paths import safe_org_segment

logger = logging.getLogger(__name__)


# SaaS keys built without a tenant land here instead of the shared namespace, so
# they can never collide with (or be read as) another tenant's objects.
UNSCOPED_PREFIX = "org/_unscoped/"


def tenant_object_prefix() -> str:
    """Self-hosted → ''. SaaS → ``org/<org>/user/<user>/``, or the quarantine prefix without a tenant."""
    if not is_saas():
        return ""
    identity = get_billing_identity()
    if identity is None:
        logger.error("saas object key built without billing identity; using %s", UNSCOPED_PREFIX)
        return UNSCOPED_PREFIX
    try:
        org = safe_org_segment(identity.org_id)
        user = safe_org_segment(identity.user_id.replace(":", "_"))
    except ValueError:
        logger.error("saas object key: invalid tenant ids org=%r user=%r", identity.org_id, identity.user_id)
        return UNSCOPED_PREFIX
    return f"org/{org}/user/{user}/"


def apply_tenant_prefix(key_without_bucket_prefix: str) -> str:
    """Prefix a relative object key (after FORMAL_/RELAY_ prefix) when SaaS."""
    prefix = tenant_object_prefix()
    if not prefix:
        return key_without_bucket_prefix
    return f"{prefix}{key_without_bucket_prefix.lstrip('/')}"
