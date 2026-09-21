## fork-custom
"""Tests for plane_mcp.host.paths."""

from pathlib import Path

from plane_mcp.host.paths import get_ipban_log_path


def test_env_unset_returns_none(monkeypatch):
    monkeypatch.delenv("PLANE_MCP_IPBAN_LOG", raising=False)
    assert get_ipban_log_path() is None


def test_env_blank_returns_none(monkeypatch):
    monkeypatch.setenv("PLANE_MCP_IPBAN_LOG", "   ")
    assert get_ipban_log_path() is None


def test_env_set_returns_path(monkeypatch, tmp_path):
    target = tmp_path / "stdout.log"
    monkeypatch.setenv("PLANE_MCP_IPBAN_LOG", str(target))
    result = get_ipban_log_path()
    assert isinstance(result, Path)
    assert result == target
