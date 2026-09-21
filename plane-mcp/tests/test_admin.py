## fork-custom
"""Unit tests for plane_mcp.tools.admin."""

from __future__ import annotations

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken
from key_value.aio.stores.memory import MemoryStore

from plane_mcp.auth import admin_guard
from plane_mcp.tools import admin as admin_module


def _make_token(token: str = "pat-admin") -> AccessToken:
    return AccessToken(
        token=token,
        client_id="test",
        scopes=["read", "write"],
        expires_at=None,
        claims={"auth_method": "api_key_header", "workspace_slug": "ws"},
    )


def _patch_http(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return original(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _get_tool(mcp: FastMCP, name: str):
    return mcp._tool_manager._tools[name]


@pytest.fixture
def admin_mcp(monkeypatch):
    admin_guard._reset_store_for_tests()
    monkeypatch.setattr(admin_guard, "_get_store", lambda: MemoryStore(default_collection="mcp_admin_guard"))
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())
    monkeypatch.setattr(admin_module, "get_access_token", lambda: _make_token())
    server = FastMCP("test")
    admin_module.register_admin_tools(server)
    yield server
    admin_guard._reset_store_for_tests()


def _plane_admin_true_handler(extra):
    """Return an httpx handler that always reports admin=True for /api/v1/users/me/
    and delegates every other request to ``extra``."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/users/me/":
            return httpx.Response(200, json={"id": "u1", "is_instance_admin": True})
        return extra(request)

    return handler


@pytest.mark.asyncio
async def test_get_instance_info_returns_fields(admin_mcp, monkeypatch):
    def extra(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/instances/":
            return httpx.Response(
                200,
                json={
                    "id": "inst-1",
                    "version": "0.23",
                    "workspaces_count": 3,
                    "users_count": 10,
                    "is_setup_done": True,
                },
            )
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, _plane_admin_true_handler(extra))

    tool = _get_tool(admin_mcp, "get_instance_info")
    result = await tool.fn()
    assert result.instance_id == "inst-1"
    assert result.version == "0.23"
    assert result.workspace_count == 3
    assert result.user_count == 10
    assert result.is_setup_done is True


@pytest.mark.asyncio
async def test_get_instance_info_degrades_on_404(admin_mcp, monkeypatch):
    def extra(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/instances/":
            return httpx.Response(404)
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, _plane_admin_true_handler(extra))

    tool = _get_tool(admin_mcp, "get_instance_info")
    result = await tool.fn()
    assert result.instance_id is None
    assert result.version is None


@pytest.mark.asyncio
async def test_list_workspace_health_counts(admin_mcp, monkeypatch):
    def extra(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/workspaces/":
            return httpx.Response(200, json=[
                {"id": "w1", "slug": "alpha", "name": "Alpha", "updated_at": "2026-04-01T00:00:00Z"},
                {"id": "w2", "slug": "beta", "name": "Beta", "updated_at": "2026-04-02T00:00:00Z"},
            ])
        if path == "/api/workspaces/alpha/members/":
            return httpx.Response(200, json=[{}, {}, {}])  # 3 members
        if path == "/api/workspaces/alpha/projects/":
            return httpx.Response(200, json=[{}, {}])  # 2 projects
        if path == "/api/workspaces/beta/members/":
            return httpx.Response(403)
        if path == "/api/workspaces/beta/projects/":
            return httpx.Response(200, json=[{}])
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, _plane_admin_true_handler(extra))

    tool = _get_tool(admin_mcp, "list_workspace_health")
    result = await tool.fn(limit=5)
    assert result.total == 2
    alpha = next(w for w in result.workspaces if w.slug == "alpha")
    assert alpha.member_count == 3
    assert alpha.project_count == 2
    assert alpha.issue_count is None
    beta = next(w for w in result.workspaces if w.slug == "beta")
    assert beta.member_count is None  # 403 → skipped silently
    assert beta.project_count == 1


@pytest.mark.asyncio
async def test_list_workspace_health_limit_validation(admin_mcp, monkeypatch):
    _patch_http(monkeypatch, _plane_admin_true_handler(lambda r: httpx.Response(200, json=[])))
    tool = _get_tool(admin_mcp, "list_workspace_health")
    with pytest.raises(ToolError, match="limit must be"):
        await tool.fn(limit=0)


@pytest.mark.asyncio
async def test_get_recent_ipban_events_wraps_reader(admin_mcp, monkeypatch, tmp_path):
    log = tmp_path / "stdout.log"
    log.write_text(
        "2026-04-19 22:09:44.1454|WARN|IPBan|Banning ip address: 1.2.3.4, "
        "user name: alice, config blacklisted: False, count: 6, "
        "extra info: , duration: 1.00:00:00\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PLANE_MCP_IPBAN_LOG", str(log))

    def extra(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, _plane_admin_true_handler(extra))

    tool = _get_tool(admin_mcp, "get_recent_ipban_events")
    result = await tool.fn(limit=5)
    assert len(result.events) == 1
    assert result.events[0]["ip"] == "1.2.3.4"
    assert result.warning is None


@pytest.mark.asyncio
async def test_get_recent_ipban_events_warns_when_unset(admin_mcp, monkeypatch):
    monkeypatch.delenv("PLANE_MCP_IPBAN_LOG", raising=False)

    def extra(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, _plane_admin_true_handler(extra))

    tool = _get_tool(admin_mcp, "get_recent_ipban_events")
    result = await tool.fn()
    assert result.events == []
    assert result.warning is not None


@pytest.mark.asyncio
async def test_trigger_backup_now_success(admin_mcp, monkeypatch):
    def extra(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/instances/admin/backup/" and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "task_name": "PlaneBackup",
                    "started_at": "2026-04-24T09:15:32+00:00",
                    "pid": None,
                },
            )
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, _plane_admin_true_handler(extra))

    tool = _get_tool(admin_mcp, "trigger_backup_now")
    result = await tool.fn()
    assert result["task_name"] == "PlaneBackup"
    assert result["pid"] is None
    assert "started_at" in result


@pytest.mark.asyncio
async def test_trigger_backup_now_plane_error(admin_mcp, monkeypatch):
    def extra(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/instances/admin/backup/":
            return httpx.Response(500, json={"detail": "Failed to start PlaneBackup task: denied"})
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, _plane_admin_true_handler(extra))

    tool = _get_tool(admin_mcp, "trigger_backup_now")
    with pytest.raises(ToolError, match="plane api error: 500"):
        await tool.fn()


@pytest.mark.asyncio
async def test_non_admin_blocked_across_all_tools(admin_mcp, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/users/me/":
            return httpx.Response(200, json={"id": "u2", "is_instance_admin": False})
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token("pat-user"))

    for name in ("get_instance_info", "list_workspace_health", "get_recent_ipban_events", "trigger_backup_now"):
        tool = _get_tool(admin_mcp, name)
        with pytest.raises(ToolError, match="requires instance admin"):
            await tool.fn()


@pytest.mark.asyncio
async def test_all_four_tools_registered(admin_mcp):
    names = set(admin_mcp._tool_manager._tools.keys())
    assert {"get_instance_info", "list_workspace_health", "get_recent_ipban_events", "trigger_backup_now"} <= names
