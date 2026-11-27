"""SaaS hardening of the Agent's Bash sandbox: secrets env + cross-tenant / host denyRead."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from saas.isolation.agent_sandbox import (
    blank_secret_env,
    configured_deny_read,
    saas_extra_deny_read,
    saas_secret_env_keys,
    sibling_paths_along,
)


def _mk(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def data_tree(tmp_path: Path) -> dict[str, Path]:
    projects = tmp_path / "data" / "projects"
    mine = _mk(projects / "org" / "org-a" / "my-film")
    _mk(projects / "org" / "org-a" / "my-other-film")
    _mk(projects / "org" / "org-b" / "their-film")
    _mk(projects / "legacy-flat-project")
    (projects / "org" / "org-a" / "stray.txt").write_text("x")
    return {"projects": projects, "mine": mine}


def test_secret_env_names_cover_saas_settings() -> None:
    env = {
        "CONTROL_PLANE_JWT_SECRET": "s",
        "CONTROL_PLANE_INTERNAL_TOKEN": "t",
        "CONTROL_PLANE_URL": "http://127.0.0.1:8100",
        "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
        "AUTH_PASSWORD": "p",
        "AUTH_TOKEN_SECRET": "s",
        "SENTRY_DSN": "https://k@sentry",
        "ARCREEL_API_TOKEN": "keep-me",
        "ARCREEL_API_BASE": "http://127.0.0.1:1241/api/v1",
        "PATH": "/usr/bin",
        "HOME": "/var/lib/arcreel",
    }
    keys = saas_secret_env_keys(env)
    assert keys == sorted(
        [
            "AUTH_PASSWORD",
            "AUTH_TOKEN_SECRET",
            "CONTROL_PLANE_INTERNAL_TOKEN",
            "CONTROL_PLANE_JWT_SECRET",
            "CONTROL_PLANE_URL",
            "DATABASE_URL",
            "SENTRY_DSN",
        ]
    )
    assert "ARCREEL_API_TOKEN" not in keys
    assert "PATH" not in keys


def test_blank_secret_env_keeps_explicit_values() -> None:
    environ = {"CONTROL_PLANE_JWT_SECRET": "s", "DATABASE_URL": "x", "PATH": "/bin"}
    agent_env = {"DATABASE_URL": "explicit"}
    blanked = blank_secret_env(agent_env, environ)
    assert blanked == ["CONTROL_PLANE_JWT_SECRET"]
    assert agent_env == {"DATABASE_URL": "explicit", "CONTROL_PLANE_JWT_SECRET": ""}


def test_sibling_paths_hide_other_tenants_and_projects(data_tree: dict[str, Path]) -> None:
    projects, mine = data_tree["projects"], data_tree["mine"]
    denied = {p.relative_to(projects.resolve()).as_posix() for p in sibling_paths_along(projects, mine)}
    assert denied == {
        "legacy-flat-project",
        "org/org-b",
        "org/org-a/my-other-film",
        "org/org-a/stray.txt",
    }


def test_sibling_paths_outside_root_is_empty(tmp_path: Path, data_tree: dict[str, Path]) -> None:
    assert sibling_paths_along(data_tree["projects"], _mk(tmp_path / "elsewhere")) == []


def test_configured_deny_read_keeps_existing_paths_only(tmp_path: Path) -> None:
    present = _mk(tmp_path / "control-plane")
    environ = {"ARCREEL_AGENT_DENY_READ": os.pathsep.join([str(present), str(tmp_path / "missing"), " "])}
    assert configured_deny_read(environ) == [present.resolve()]


def test_extra_deny_read_covers_projects_sdk_dirs_and_host_paths(tmp_path: Path, data_tree: dict[str, Path]) -> None:
    sdk_projects = _mk(tmp_path / "home" / ".claude" / "projects")
    own = "-data-projects-org-org-a-my-film"
    _mk(sdk_projects / own)
    _mk(sdk_projects / "-data-projects-org-org-b-their-film")
    (sdk_projects.parent / "history.jsonl").write_text("{}")
    host = _mk(tmp_path / "opt" / "arcreel-control-plane")

    deny = saas_extra_deny_read(
        projects_dir=data_tree["projects"],
        project_cwd=data_tree["mine"],
        sdk_projects_dir=sdk_projects,
        sdk_project_dir_name=own,
        environ={"ARCREEL_AGENT_DENY_READ": str(host)},
    )
    assert str((data_tree["projects"] / "org" / "org-b").resolve()) in deny
    assert str((sdk_projects / "-data-projects-org-org-b-their-film").resolve()) in deny
    assert str((sdk_projects.parent / "history.jsonl").resolve()) in deny
    assert str(host.resolve()) in deny
    assert str(data_tree["mine"].resolve()) not in deny
    assert str((sdk_projects / own).resolve()) not in deny
    assert len(deny) == len(set(deny))


def test_policy_wires_saas_hardening(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data_tree: dict[str, Path]) -> None:
    from server.agent_runtime.agent_access_policy import AgentAccessPolicy

    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("CONTROL_PLANE_JWT_SECRET", "s" * 40)
    AgentAccessPolicy._collect_env_keys_to_scrub.cache_clear()
    AgentAccessPolicy._env_scrub_wrap_prefix.cache_clear()
    try:
        repo = _mk(tmp_path / "repo")
        profile = _mk(tmp_path / "profile")
        policy = AgentAccessPolicy(
            project_root=repo,
            data_root=data_tree["projects"].parent,
            agent_profile_root=profile,
            sandbox_enabled=True,
            claude_projects_dir=_mk(tmp_path / "home" / ".claude" / "projects"),
        )
        settings = policy.build_sandbox_settings(data_tree["mine"])
        deny_read = settings["filesystem"]["denyRead"]
        assert str((data_tree["projects"] / "org" / "org-b").resolve()) in deny_read
        assert "-u CONTROL_PLANE_JWT_SECRET" in policy.wrap_bash_command_for_env_scrub("env")
    finally:
        AgentAccessPolicy._collect_env_keys_to_scrub.cache_clear()
        AgentAccessPolicy._env_scrub_wrap_prefix.cache_clear()


def test_self_hosted_policy_is_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data_tree: dict[str, Path]) -> None:
    from server.agent_runtime.agent_access_policy import AgentAccessPolicy

    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    policy = AgentAccessPolicy(
        project_root=_mk(tmp_path / "repo"),
        data_root=data_tree["projects"].parent,
        agent_profile_root=_mk(tmp_path / "profile"),
        sandbox_enabled=True,
        claude_projects_dir=_mk(tmp_path / "home" / ".claude" / "projects"),
    )
    deny_read = policy.build_sandbox_settings(data_tree["mine"])["filesystem"]["denyRead"]
    assert str((data_tree["projects"] / "org" / "org-b").resolve()) not in deny_read
