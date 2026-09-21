## fork-custom: admin tools (instance info, workspace health, ipban events, backup stub)
"""Admin-only tools that require ``is_instance_admin=True``.

Wired into the header-PAT factory only via ``register_fork_tools``.
All four tools apply the :func:`require_instance_admin` decorator.

See `.claude/docs/customization/spec.md` §4.1, §5.3, §5.4 and
`develop/4_admin_tools_develop_plan_1.md`.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from pydantic import BaseModel

from plane_mcp.auth.admin_guard import require_instance_admin
from plane_mcp.host.ipban_reader import IpbanEvent, tail_events

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.plane.so"


class InstanceInfo(BaseModel):
    instance_id: str | None
    version: str | None
    workspace_count: int | None
    user_count: int | None
    is_setup_done: bool | None
    captured_at: str


class WorkspaceHealth(BaseModel):
    workspace_id: str
    slug: str
    name: str
    member_count: int | None
    project_count: int | None
    issue_count: int | None
    last_activity_at: str | None


class ListWorkspaceHealthResult(BaseModel):
    workspaces: list[WorkspaceHealth]
    total: int


class GetRecentIpbanEventsResult(BaseModel):
    events: list[IpbanEvent]
    warning: str | None = None


def _plane_base_url() -> str:
    base = os.getenv("PLANE_INTERNAL_BASE_URL") or os.getenv("PLANE_BASE_URL", _DEFAULT_BASE_URL)
    return base.rstrip("/")


def _require_token() -> str:
    access_token = get_access_token()
    if access_token is None:
        raise ToolError("authentication required")
    return access_token.token


def _raise_for_plane_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        body = response.json()
        message = body.get("detail") or body.get("error") or str(body)
    except Exception:
        message = response.text or ""
    raise ToolError(f"plane api error: {response.status_code} {message}".strip())


def register_admin_tools(mcp: FastMCP) -> None:
    """Register the four admin tools (all require instance-admin PAT)."""

    @mcp.tool()
    @require_instance_admin
    async def get_instance_info() -> InstanceInfo:
        """Return Plane instance metadata (version, counts, setup flag).

        The underlying ``/api/instances/`` endpoint availability depends on the
        Plane fork; missing fields degrade to ``None`` rather than raise.
        """
        token = _require_token()
        base_url = _plane_base_url()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/api/instances/",
                headers={"x-api-key": token},
            )
            if resp.status_code == 404:
                logger.warning("get_instance_info: /api/instances/ not available")
                return InstanceInfo(
                    instance_id=None,
                    version=None,
                    workspace_count=None,
                    user_count=None,
                    is_setup_done=None,
                    captured_at=datetime.now(tz=timezone.utc).isoformat(),
                )
            _raise_for_plane_status(resp)
            data = resp.json()

        return InstanceInfo(
            instance_id=str(data["id"]) if data.get("id") is not None else None,
            version=data.get("version") or data.get("current_version"),
            workspace_count=data.get("workspaces_count") or data.get("workspace_count"),
            user_count=data.get("users_count") or data.get("user_count"),
            is_setup_done=data.get("is_setup_done"),
            captured_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    @mcp.tool()
    @require_instance_admin
    async def list_workspace_health(limit: int = 20) -> ListWorkspaceHealthResult:
        """Return per-workspace member/project counts for the first ``limit`` workspaces.

        Workspaces that return 403/404 individually are skipped (logged at WARN)
        so partial results remain useful. ``issue_count`` is ``None`` in the
        current implementation — see `.claude/docs/customization/todo.md`.
        """
        if not 1 <= limit <= 50:
            raise ToolError("limit must be between 1 and 50")

        token = _require_token()
        base_url = _plane_base_url()
        headers = {"x-api-key": token}

        async with httpx.AsyncClient(timeout=20) as client:
            list_resp = await client.get(f"{base_url}/api/workspaces/", headers=headers)
            _raise_for_plane_status(list_resp)
            payload = list_resp.json()
            rows = payload if isinstance(payload, list) else (payload.get("results") or [])
            rows = rows[:limit]

            workspaces: list[WorkspaceHealth] = []
            for row in rows:
                slug = row.get("slug") or ""
                if not slug:
                    continue
                member_count: int | None = None
                project_count: int | None = None
                try:
                    members_resp = await client.get(
                        f"{base_url}/api/workspaces/{slug}/members/",
                        headers=headers,
                    )
                    if members_resp.status_code in (401, 403, 404):
                        logger.warning(
                            "list_workspace_health: skipped members for workspace=%s status=%s",
                            slug, members_resp.status_code,
                        )
                    else:
                        _raise_for_plane_status(members_resp)
                        members = members_resp.json()
                        member_count = len(members) if isinstance(members, list) else None

                    projects_resp = await client.get(
                        f"{base_url}/api/workspaces/{slug}/projects/",
                        headers=headers,
                    )
                    if projects_resp.status_code in (401, 403, 404):
                        logger.warning(
                            "list_workspace_health: skipped projects for workspace=%s status=%s",
                            slug, projects_resp.status_code,
                        )
                    else:
                        _raise_for_plane_status(projects_resp)
                        projects = projects_resp.json()
                        project_count = len(projects) if isinstance(projects, list) else None
                except ToolError as exc:
                    logger.warning(
                        "list_workspace_health: skipped workspace=%s reason=%s",
                        slug, exc,
                    )
                    continue

                workspaces.append(
                    WorkspaceHealth(
                        workspace_id=str(row.get("id", "")),
                        slug=slug,
                        name=row.get("name", ""),
                        member_count=member_count,
                        project_count=project_count,
                        issue_count=None,
                        last_activity_at=row.get("updated_at"),
                    )
                )

        return ListWorkspaceHealthResult(workspaces=workspaces, total=len(workspaces))

    @mcp.tool()
    @require_instance_admin
    async def get_recent_ipban_events(limit: int = 50) -> GetRecentIpbanEventsResult:
        """Return recent IPBan events from the host stdout log.

        Thin wrapper around :func:`plane_mcp.host.ipban_reader.tail_events`.
        Missing / unreadable log returns ``warning`` with ``events=[]``.
        """
        result = tail_events(limit=limit)
        return GetRecentIpbanEventsResult(
            events=result["events"],
            warning=result["warning"],
        )

    @mcp.tool()
    @require_instance_admin
    async def trigger_backup_now() -> dict[str, Any]:
        """Kick off an on-demand Plane backup via the fork's admin endpoint.

        Calls ``POST /api/instances/admin/backup/`` which runs
        ``Start-ScheduledTask -TaskName PlaneBackup`` on the host. Returns
        Plane's response body: ``{task_name, started_at, pid}`` (pid is
        typically ``None`` because ``Start-ScheduledTask`` fires and
        returns before a backup process is spawned).
        """
        token = _require_token()
        base_url = _plane_base_url()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{base_url}/api/instances/admin/backup/",
                headers={"x-api-key": token},
            )
            _raise_for_plane_status(response)
            return response.json()
