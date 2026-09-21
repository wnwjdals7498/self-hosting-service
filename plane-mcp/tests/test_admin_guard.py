## fork-custom
"""Unit tests for plane_mcp.auth.admin_guard."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken
from key_value.aio.stores.memory import MemoryStore

from plane_mcp.auth import admin_guard


def _make_token(token: str = "pat-xyz") -> AccessToken:
    return AccessToken(
        token=token,
        client_id="test",
        scopes=["read", "write"],
        expires_at=None,
        claims={"auth_method": "api_key_header", "workspace_slug": "ws"},
    )


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch):
    store = MemoryStore(default_collection="mcp_admin_guard")
    admin_guard._reset_store_for_tests()
    monkeypatch.setattr(admin_guard, "_get_store", lambda: store)
    yield store
    admin_guard._reset_store_for_tests()


def _make_httpx_mock(status_code: int, body: dict[str, Any] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.call_count += 1
        return httpx.Response(status_code, json=body or {})

    handler.call_count = 0
    return handler


def _patch_async_client(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return original(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_admin_passes_through(monkeypatch):
    handler = _make_httpx_mock(200, {"id": "u1", "is_instance_admin": True})
    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())

    @admin_guard.require_instance_admin
    def tool() -> str:
        return "ok"

    assert await tool() == "ok"
    assert handler.call_count == 1


@pytest.mark.asyncio
async def test_non_admin_blocked(monkeypatch):
    handler = _make_httpx_mock(200, {"id": "u1", "is_instance_admin": False})
    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())
    calls = []

    @admin_guard.require_instance_admin
    def tool() -> str:
        calls.append("called")
        return "ok"

    with pytest.raises(ToolError, match="requires instance admin"):
        await tool()
    assert calls == []


@pytest.mark.asyncio
async def test_cache_hit_avoids_second_api_call(monkeypatch):
    handler = _make_httpx_mock(200, {"id": "u1", "is_instance_admin": True})
    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())

    @admin_guard.require_instance_admin
    def tool() -> str:
        return "ok"

    assert await tool() == "ok"
    assert await tool() == "ok"
    assert handler.call_count == 1


@pytest.mark.asyncio
async def test_cache_fallback_on_read_error(monkeypatch):
    handler = _make_httpx_mock(200, {"id": "u1", "is_instance_admin": True})
    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())

    class BrokenStore:
        async def get(self, key, *, collection=None):
            raise RuntimeError("boom")

        async def put(self, key, value, *, collection=None, ttl=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(admin_guard, "_get_store", lambda: BrokenStore())

    @admin_guard.require_instance_admin
    def tool() -> str:
        return "ok"

    assert await tool() == "ok"
    assert await tool() == "ok"
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_plane_5xx_raises_tool_error(monkeypatch):
    handler = _make_httpx_mock(500)
    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())

    @admin_guard.require_instance_admin
    def tool() -> str:
        return "ok"

    with pytest.raises(ToolError, match="admin check failed: 500"):
        await tool()


@pytest.mark.asyncio
async def test_plane_401_raises_tool_error(monkeypatch):
    handler = _make_httpx_mock(401)
    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())

    @admin_guard.require_instance_admin
    def tool() -> str:
        return "ok"

    with pytest.raises(ToolError, match="authentication failed"):
        await tool()


@pytest.mark.asyncio
async def test_missing_access_token(monkeypatch):
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: None)

    @admin_guard.require_instance_admin
    def tool() -> str:
        return "ok"

    with pytest.raises(ToolError, match="authentication required"):
        await tool()


@pytest.mark.asyncio
async def test_is_instance_admin_missing_defaults_false(monkeypatch):
    handler = _make_httpx_mock(200, {"id": "u1"})
    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())

    @admin_guard.require_instance_admin
    def tool() -> str:
        return "ok"

    with pytest.raises(ToolError, match="requires instance admin"):
        await tool()


@pytest.mark.asyncio
async def test_async_underlying_tool(monkeypatch):
    handler = _make_httpx_mock(200, {"id": "u1", "is_instance_admin": True})
    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(admin_guard, "get_access_token", lambda: _make_token())

    @admin_guard.require_instance_admin
    async def tool() -> str:
        return "async-ok"

    assert await tool() == "async-ok"
