## fork-custom
"""Tests that fork tools are exposed on the header-PAT factory only."""

from __future__ import annotations

from plane_mcp import server

FORK_TOOL_NAMES = {
    "upload_file",
    "download_file",
    "list_file_assets",
    "get_instance_info",
    "list_workspace_health",
    "get_recent_ipban_events",
    "trigger_backup_now",
}


def _tool_names(mcp) -> set[str]:
    return set(mcp._tool_manager._tools.keys())


def test_fork_tools_on_header_factory():
    names = _tool_names(server.get_header_mcp())
    assert FORK_TOOL_NAMES <= names


def test_fork_tools_absent_from_stdio_factory():
    names = _tool_names(server.get_stdio_mcp())
    assert FORK_TOOL_NAMES.isdisjoint(names)


def test_upstream_tools_present_on_all_factories():
    sample_upstream_names = {"get_me", "list_projects"}
    for factory in (server.get_header_mcp, server.get_stdio_mcp):
        assert sample_upstream_names <= _tool_names(factory())


def test_header_factory_has_more_tools_than_stdio():
    header_count = len(_tool_names(server.get_header_mcp()))
    stdio_count = len(_tool_names(server.get_stdio_mcp()))
    assert header_count - stdio_count == len(FORK_TOOL_NAMES)
