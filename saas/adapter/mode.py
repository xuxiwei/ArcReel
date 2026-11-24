"""Deployment mode switch. Default preserves upstream self-hosted behavior."""

from __future__ import annotations

import os
from typing import Literal

DeploymentMode = Literal["self_hosted", "saas"]

_SAAS_VALUES = frozenset({"saas", "cloud"})


def get_deployment_mode() -> DeploymentMode:
    raw = os.environ.get("DEPLOYMENT_MODE", "self_hosted").strip().lower()
    if raw in _SAAS_VALUES:
        return "saas"
    return "self_hosted"


def is_saas() -> bool:
    return get_deployment_mode() == "saas"
