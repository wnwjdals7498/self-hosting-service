## fork-custom
"""Unit tests for plane_mcp.tools.files (3-step, project-scoped)."""

from __future__ import annotations

import base64

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken

from plane_mcp.tools import files as files_module

WS = "develop"
PID = "92631846-fd55-4a21-8b6d-407898b6735e"
IID = "e51a5999-2ec1-423a-88be-b6eb26c6602e"
# 1x1 transparent PNG
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6300010000000500010d0a2db40000000049454e44"
    "ae426082"
)


def _make_token(token: str = "pat-xyz") -> AccessToken:
    return AccessToken(
        token=token,
        client_id="test",
        scopes=["read", "write"],
        expires_at=None,
        claims={"auth_method": "api_key_header", "workspace_slug": WS},
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
def mcp(monkeypatch):
    monkeypatch.setattr(files_module, "get_access_token", lambda: _make_token())
    server = FastMCP("test")
    files_module.register_files_tools(server)
    return server


@pytest.mark.asyncio
async def test_upload_file_happy_path(mcp, monkeypatch):
    content_b64 = base64.b64encode(PNG_1X1).decode("ascii")
    calls = {"create": 0, "multipart": 0, "patch": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == f"/api/assets/v2/workspaces/{WS}/projects/{PID}/":
            calls["create"] += 1
            return httpx.Response(
                200,
                json={"asset_id": "asset-1", "asset_url": "x", "upload_data": {"url": "http://up.local/post", "fields": {"key": "k"}}},
            )
        if request.method == "POST" and request.url.host == "up.local":
            calls["multipart"] += 1
            return httpx.Response(204)
        if request.method == "PATCH" and path == f"/api/assets/v2/workspaces/{WS}/projects/{PID}/asset-1/":
            calls["patch"] += 1
            return httpx.Response(204)
        raise AssertionError(f"unexpected: {request.method} {request.url}")

    _patch_http(monkeypatch, handler)

    tool = _get_tool(mcp, "upload_file")
    result = await tool.fn(
        workspace_slug=WS, project_id=PID, entity_id=IID,
        name="shot.png", mime="image/png", content_base64=content_b64,
    )
    assert result.asset_id == "asset-1"
    assert result.size == len(PNG_1X1)
    assert result.warning is None
    assert calls == {"create": 1, "multipart": 1, "patch": 1}


@pytest.mark.asyncio
async def test_upload_file_rejects_non_image_mime(mcp):
    tool = _get_tool(mcp, "upload_file")
    with pytest.raises(ToolError, match="unsupported mime"):
        await tool.fn(
            workspace_slug=WS, project_id=PID, entity_id=IID,
            name="note.txt", mime="text/plain",
            content_base64=base64.b64encode(b"hi").decode("ascii"),
        )


@pytest.mark.asyncio
async def test_upload_file_rejects_oversize(mcp):
    huge = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode("ascii")
    tool = _get_tool(mcp, "upload_file")
    with pytest.raises(ToolError, match="file too large"):
        await tool.fn(
            workspace_slug=WS, project_id=PID, entity_id=IID,
            name="huge.png", mime="image/png", content_base64=huge,
        )


@pytest.mark.asyncio
async def test_upload_file_invalid_base64(mcp):
    tool = _get_tool(mcp, "upload_file")
    with pytest.raises(ToolError, match="invalid base64"):
        await tool.fn(
            workspace_slug=WS, project_id=PID, entity_id=IID,
            name="bad.png", mime="image/png", content_base64="!!!not base64!!!",
        )


@pytest.mark.asyncio
async def test_upload_file_warns_above_2mb(mcp, monkeypatch):
    payload = b"P" + b"\x00" * (2 * 1024 * 1024)  # slightly over 2MB
    content_b64 = base64.b64encode(payload).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.startswith("/api/assets/v2/"):
            return httpx.Response(
                200,
                json={"asset_id": "a2", "upload_data": {"url": "http://up.local/post", "fields": {}}},
            )
        if request.url.host == "up.local":
            return httpx.Response(204)
        if request.method == "PATCH":
            return httpx.Response(204)
        raise AssertionError(f"unexpected: {request.method} {request.url}")

    _patch_http(monkeypatch, handler)

    tool = _get_tool(mcp, "upload_file")
    result = await tool.fn(
        workspace_slug=WS, project_id=PID, entity_id=IID,
        name="big.png", mime="image/png", content_base64=content_b64,
    )
    assert result.warning is not None
    assert "2MB" in result.warning


@pytest.mark.asyncio
async def test_upload_file_multipart_failure(mcp, monkeypatch):
    content_b64 = base64.b64encode(PNG_1X1).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/projects/" + PID + "/") and request.method == "POST":
            return httpx.Response(
                200,
                json={"asset_id": "a", "upload_data": {"url": "http://up.local/post", "fields": {}}},
            )
        if request.url.host == "up.local":
            return httpx.Response(500)
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, handler)

    tool = _get_tool(mcp, "upload_file")
    with pytest.raises(ToolError, match="upload failed: 500"):
        await tool.fn(
            workspace_slug=WS, project_id=PID, entity_id=IID,
            name="x.png", mime="image/png", content_base64=content_b64,
        )


@pytest.mark.asyncio
async def test_upload_file_patch_failure(mcp, monkeypatch):
    content_b64 = base64.b64encode(PNG_1X1).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/projects/" + PID + "/"):
            return httpx.Response(
                200,
                json={"asset_id": "a", "upload_data": {"url": "http://up.local/post", "fields": {}}},
            )
        if request.url.host == "up.local":
            return httpx.Response(204)
        if request.method == "PATCH":
            return httpx.Response(500)
        raise AssertionError(f"unexpected: {request.method} {request.url}")

    _patch_http(monkeypatch, handler)

    tool = _get_tool(mcp, "upload_file")
    with pytest.raises(ToolError, match="plane patch failed: 500"):
        await tool.fn(
            workspace_slug=WS, project_id=PID, entity_id=IID,
            name="x.png", mime="image/png", content_base64=content_b64,
        )


@pytest.mark.asyncio
async def test_upload_file_plane_400_propagates(mcp, monkeypatch):
    content_b64 = base64.b64encode(PNG_1X1).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad"})

    _patch_http(monkeypatch, handler)

    tool = _get_tool(mcp, "upload_file")
    with pytest.raises(ToolError, match="plane api error: 400"):
        await tool.fn(
            workspace_slug=WS, project_id=PID, entity_id=IID,
            name="x.png", mime="image/png", content_base64=content_b64,
        )


@pytest.mark.asyncio
async def test_download_file_url_only_via_302(mcp, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == f"/api/assets/v2/workspaces/{WS}/projects/{PID}/a/":
            return httpx.Response(302, headers={"location": "http://dn/x?sig=abc"})
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, handler)

    tool = _get_tool(mcp, "download_file")
    result = await tool.fn(workspace_slug=WS, project_id=PID, asset_id="a")
    assert result.presigned_url == "http://dn/x?sig=abc"
    assert result.content_base64 is None


@pytest.mark.asyncio
async def test_download_file_with_content(mcp, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/api/assets/v2/workspaces/{WS}/projects/{PID}/a/":
            return httpx.Response(302, headers={"location": "http://dn/x?sig=abc"})
        if str(request.url) == "http://dn/x?sig=abc":
            return httpx.Response(200, content=PNG_1X1)
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, handler)

    tool = _get_tool(mcp, "download_file")
    result = await tool.fn(
        workspace_slug=WS, project_id=PID, asset_id="a",
        include_content_base64=True,
    )
    assert result.content_base64 == base64.b64encode(PNG_1X1).decode("ascii")


@pytest.mark.asyncio
async def test_download_file_large_content_skipped(mcp, monkeypatch):
    big = b"x" * (5 * 1024 * 1024 + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/api/assets/v2/workspaces/{WS}/projects/{PID}/big/":
            return httpx.Response(302, headers={"location": "http://dn/big"})
        if str(request.url) == "http://dn/big":
            return httpx.Response(200, content=big)
        raise AssertionError(f"unexpected: {request.url}")

    _patch_http(monkeypatch, handler)

    tool = _get_tool(mcp, "download_file")
    result = await tool.fn(
        workspace_slug=WS, project_id=PID, asset_id="big",
        include_content_base64=True,
    )
    assert result.content_base64 is None
    assert result.warning is not None
    assert "URL only" in result.warning


@pytest.mark.asyncio
async def test_list_file_assets_is_stub(mcp):
    tool = _get_tool(mcp, "list_file_assets")
    with pytest.raises(NotImplementedError, match="/api/assets/v2/"):
        await tool.fn(workspace_slug=WS, project_id=PID, entity_id=IID)
