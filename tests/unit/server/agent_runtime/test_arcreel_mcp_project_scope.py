"""Unit tests for in-process MCP ProjectManager scoping (WB-10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp import types

from lib.infra.data_root_layout import DataRootLayout
from saas.adapter.billing_context import BillingIdentity, bind_billing_identity
from saas.isolation.paths import TenantDataRootLayout
from server.agent_runtime.arcreel_mcp import _resolve_mcp_projects, build_arcreel_mcp_server


def test_resolve_mcp_projects_uses_saas_org_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """WB-10: with SaaS billing identity, MCP uses projects/org/<org_id>/."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    data_root = tmp_path / "data"
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
    from lib.infra.app_data_dir import reset_for_tests
    from lib.project.project_manager import reset_project_manager_for_tests

    reset_for_tests()
    reset_project_manager_for_tests()

    org_id = "org-wb10-test"
    org_projects = TenantDataRootLayout(root=data_root, org_id=org_id).projects_dir
    org_projects.mkdir(parents=True, exist_ok=True)
    DataRootLayout(data_root).projects_dir.mkdir(parents=True, exist_ok=True)

    with bind_billing_identity(BillingIdentity(user_id="user-1", org_id=org_id)):
        projects = _resolve_mcp_projects(data_root)

    assert projects.projects_dir.resolve() == org_projects.resolve()
    assert "org" in projects.projects_dir.parts
    assert org_id in projects.projects_dir.parts
    reset_project_manager_for_tests()
    reset_for_tests()


def test_resolve_mcp_projects_non_saas_keeps_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without SaaS identity, MCP keeps the session data_root ProjectManager."""
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
    data_root = tmp_path / "data"
    data_root.mkdir()

    projects = _resolve_mcp_projects(data_root)
    assert projects.data_root.resolve() == data_root.resolve()
    assert projects.projects_dir.resolve() == DataRootLayout(data_root).projects_dir.resolve()


async def _call(server, name: str, arguments: dict) -> types.CallToolResult:
    request = types.CallToolRequest(params=types.CallToolRequestParams(name=name, arguments=arguments))
    result = (await server.request_handlers[types.CallToolRequest](request)).root
    assert isinstance(result, types.CallToolResult)
    return result


@pytest.mark.asyncio
async def test_mcp_get_source_text_reads_org_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WB-10: MCP file tools resolve under the org tree, not the global projects dir."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    data_root = tmp_path / "data"
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_root))
    from lib.infra.app_data_dir import reset_for_tests
    from lib.project.project_manager import reset_project_manager_for_tests

    reset_for_tests()
    reset_project_manager_for_tests()

    org_id = "org-wb10-read"
    project_name = "proj-org"
    org_project = TenantDataRootLayout(root=data_root, org_id=org_id).projects_dir / project_name
    org_project.mkdir(parents=True)
    (org_project / "project.json").write_text(
        json.dumps({"name": project_name, "title": "Org"}, ensure_ascii=False),
        encoding="utf-8",
    )
    source_dir = org_project / "source"
    source_dir.mkdir()
    (source_dir / "novel.txt").write_text("org-source-body", encoding="utf-8")

    # Same-named global project must not be used.
    global_project = DataRootLayout(data_root).projects_dir / project_name
    global_project.mkdir(parents=True)
    (global_project / "project.json").write_text("{}", encoding="utf-8")
    (global_project / "source").mkdir()
    (global_project / "source" / "novel.txt").write_text("global-source-body", encoding="utf-8")

    with bind_billing_identity(BillingIdentity(user_id="user-1", org_id=org_id)):
        server = build_arcreel_mcp_server(project_name=project_name, data_root=data_root)["instance"]
        listed = await _call(server, "list_source_files", {})
        got = await _call(server, "get_source_text", {"path": "source/novel.txt"})

    assert listed.isError is False
    assert got.isError is False
    assert isinstance(got.content[-1], types.TextContent)
    payload = json.loads(got.content[-1].text)
    assert payload["source_text"]["text"] == "org-source-body"

    reset_project_manager_for_tests()
    reset_for_tests()
