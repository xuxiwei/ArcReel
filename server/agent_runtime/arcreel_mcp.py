"""ArcReel Agent 会话的 in-process MCP server。

工具 handler 跑在服务端主进程（不在 Agent sandbox 内），因此能读 ArcReel 数据库、调用供应商 HTTP，
而不必在 ``filesystem.denyRead`` / 网络白名单上开口子。每个会话以自己的项目建一个 server；工具全部来自
Agent 工具集声明，由内嵌 adapter 暴露。
"""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import McpSdkServerConfig

from lib.db.base import DEFAULT_USER_ID
from lib.generation.generation_queue_client import batch_enqueue_and_wait
from lib.project.project_manager import ProjectManager, get_project_manager
from server.agent_toolset.embedded import embedded_server
from server.agent_toolset.toolset import AGENT_TOOLSET
from server.tool_runtime import CallerContext, ProjectScope, Services


def _resolve_mcp_projects(data_root: Path) -> ProjectManager:
    """Resolve the ProjectManager used by the session MCP tool surface.

    Self-hosted (upstream): reuse the :func:`get_project_manager` singleton when it
    serves ``data_root``, otherwise build one for that root (tests / custom roots).

    SaaS: the tools must see the org-scoped tree ``projects/org/<org_id>/`` that the
    Agent cwd and HTTP routes use. Without a bound billing identity there is no
    tenant to scope to, so refuse instead of falling back to the shared root.
    """
    from saas.adapter.billing_context import get_billing_identity
    from saas.adapter.mode import is_saas

    if is_saas():
        if get_billing_identity() is None:
            raise RuntimeError("SaaS MCP server requires a bound billing identity")
        return get_project_manager()
    projects = get_project_manager()
    if projects.data_root.resolve() != data_root.resolve():
        projects = ProjectManager(data_root)
    return projects


def build_arcreel_mcp_server(
    *,
    project_name: str,
    data_root: Path,
    user_id: str = DEFAULT_USER_ID,
) -> McpSdkServerConfig:
    """以会话项目构建暴露全部 ArcReel 工具的 in-process MCP server；生成类工具等到批次终态再返回。"""
    projects = _resolve_mcp_projects(data_root)
    return embedded_server(
        AGENT_TOOLSET,
        name="arcreel",
        version="1.0.0",
        scope=ProjectScope(project_name=project_name, data_root=projects.data_root),
        caller=CallerContext(user_id=user_id, source="embedded", batch_waiter=batch_enqueue_and_wait),
        services=Services.defaults(projects),
    )


__all__ = ["build_arcreel_mcp_server"]
