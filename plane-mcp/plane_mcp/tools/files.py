## fork-custom: file tools for Plane fork's LocalFSStorage presigned flow
"""File asset tools for the Plane fork (ISSUE_ATTACHMENT entity type).

Plane's `/api/assets/v2/` endpoints are workspace- and project-scoped,
and accept only image MIME types (`image/jpeg|png|webp|gif`). This
module targets the ``ISSUE_ATTACHMENT`` entity type only — the other
entity types (`WORKSPACE_LOGO`, `PROJECT_COVER`, `USER_AVATAR`,
`USER_COVER`, `PAGE_DESCRIPTION`, …) live behind different endpoints
and are tracked in ``.claude/docs/customization/todo.md`` #7.

Upload flow (3-step, see Plane `ProjectAssetEndpoint.post/patch`):

  1. POST /api/assets/v2/workspaces/<slug>/projects/<pid>/
       body: { name, type=mime, size, entity_type="ISSUE_ATTACHMENT",
               entity_identifier=<issue_uuid> }
       → { upload_data: {url, fields}, asset_id, asset_url }
  2. POST upload_data.url (multipart; LocalFSStorage HMAC-signed)
       fields: upload_data.fields  + file=<bytes>
       → 204
  3. PATCH /api/assets/v2/workspaces/<slug>/projects/<pid>/<asset_id>/
       body: {}
       → 204  (asset.is_uploaded = True)

`list_file_assets` is intentionally a stub — Plane's v2 surface has
no list-by-entity endpoint, and legacy `/work-items/<id>/attachments/`
is out of scope for this tool (see todo.md #7).
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_FILE_SIZE_LIMIT = 5 * 1024 * 1024  # 5 MB — Plane's `FILE_SIZE_LIMIT`
_WARN_THRESHOLD = 2 * 1024 * 1024
_DEFAULT_BASE_URL = "https://api.plane.so"
_ALLOWED_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}


class UploadFileResult(BaseModel):
    asset_id: str
    name: str
    mime: str
    size: int
    warning: str | None = None


class DownloadFileResult(BaseModel):
    asset_id: str
    presigned_url: str
    content_base64: str | None = None
    warning: str | None = None


def _plane_base_url() -> str:
    base = os.getenv("PLANE_INTERNAL_BASE_URL") or os.getenv("PLANE_BASE_URL", _DEFAULT_BASE_URL)
    return base.rstrip("/")


def _require_token() -> str:
    access_token = get_access_token()
    if access_token is None:
        raise ToolError("authentication required")
    return access_token.token


def _decode_base64(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=False)
    except (ValueError, TypeError) as exc:
        raise ToolError("invalid base64") from exc


def _raise_for_plane_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        body = response.json()
        message = body.get("detail") or body.get("error") or str(body)
    except Exception:
        message = response.text or ""
    raise ToolError(f"plane api error: {response.status_code} {message}".strip())


def register_files_tools(mcp: FastMCP) -> None:
    """Register ``upload_file``, ``download_file``, ``list_file_assets``."""

    @mcp.tool()
    async def upload_file(
        workspace_slug: str,
        project_id: str,
        entity_id: str,
        name: str,
        mime: str,
        content_base64: str,
    ) -> UploadFileResult:
        """Upload an issue attachment to a Plane project (3-step).

        Entity type is fixed to ``ISSUE_ATTACHMENT``. ``entity_id`` must
        be the target issue's UUID within ``project_id``/``workspace_slug``.
        Plane accepts only image MIME types for the v2 asset surface;
        non-image payloads will be rejected with a clear error before
        any Plane call.

        Args:
            workspace_slug: Workspace slug (e.g. ``develop``).
            project_id: Project UUID that owns the issue.
            entity_id: Issue UUID the attachment belongs to.
            name: File name including extension.
            mime: Image MIME type. One of ``image/jpeg|jpg|png|webp|gif``.
            content_base64: Base64-encoded file bytes, decoded size ≤ 5 MB.

        Returns:
            ``UploadFileResult`` with ``asset_id`` and an optional warning
            when decoded size > 2 MB.
        """
        if mime not in _ALLOWED_MIMES:
            raise ToolError(
                f"unsupported mime for Plane v2 asset: {mime!r} (allowed: {sorted(_ALLOWED_MIMES)})"
            )
        payload = _decode_base64(content_base64)
        size = len(payload)
        if size > _FILE_SIZE_LIMIT:
            raise ToolError(f"file too large: {size} bytes (max {_FILE_SIZE_LIMIT})")

        token = _require_token()
        base_url = _plane_base_url()
        scoped = f"{base_url}/api/assets/v2/workspaces/{workspace_slug}/projects/{project_id}"
        headers = {"x-api-key": token, "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "name": name,
            "type": mime,
            "size": size,
            "entity_type": "ISSUE_ATTACHMENT",
            "entity_identifier": entity_id,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            create_resp = await client.post(f"{scoped}/", json=body, headers=headers)
            _raise_for_plane_status(create_resp)
            create_data = create_resp.json()
            upload_data = create_data.get("upload_data") or {}
            asset_id = create_data.get("asset_id") or create_data.get("id")
            if not asset_id or not upload_data.get("url"):
                raise ToolError("plane api error: missing upload_data/asset_id")

            multipart_resp = await client.post(
                upload_data["url"],
                data=upload_data.get("fields") or {},
                files={"file": (name, payload, mime)},
            )
            if multipart_resp.status_code not in (200, 201, 204):
                raise ToolError(f"upload failed: {multipart_resp.status_code}")

            patch_resp = await client.patch(
                f"{scoped}/{asset_id}/",
                json={},
                headers=headers,
            )
            if patch_resp.status_code not in (200, 204):
                raise ToolError(f"plane patch failed: {patch_resp.status_code}")

        warning: str | None = None
        if size > _WARN_THRESHOLD:
            warning = "consider Plane UI for files > 2MB"
            logger.warning("upload size > 2MB: project=%s entity=%s size=%d", project_id, entity_id, size)

        logger.info(
            "upload_file workspace=%s project=%s issue=%s size=%d mime=%s asset_id=%s",
            workspace_slug, project_id, entity_id, size, mime, asset_id,
        )
        return UploadFileResult(asset_id=asset_id, name=name, mime=mime, size=size, warning=warning)

    @mcp.tool()
    async def download_file(
        workspace_slug: str,
        project_id: str,
        asset_id: str,
        include_content_base64: bool = False,
    ) -> DownloadFileResult:
        """Return the presigned GET URL (and optionally the bytes) for an asset.

        Plane's project-scoped asset GET responds with a 302 redirect to a
        presigned URL; this tool follows manually so the URL can be
        returned to the caller. When ``include_content_base64=True`` and
        the file is ≤ 5 MB, it also fetches the bytes and base64-encodes
        them; larger files return URL-only with a warning.

        Args:
            workspace_slug: Workspace slug.
            project_id: Project UUID.
            asset_id: Asset UUID.
            include_content_base64: If True, also inline the content.

        Returns:
            ``DownloadFileResult`` with the presigned URL and optional
            inline bytes.
        """
        token = _require_token()
        base_url = _plane_base_url()
        scoped = f"{base_url}/api/assets/v2/workspaces/{workspace_slug}/projects/{project_id}/{asset_id}/"
        headers = {"x-api-key": token}

        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            meta_resp = await client.get(scoped, headers=headers)
            if meta_resp.status_code == 302:
                presigned = meta_resp.headers.get("location", "")
            elif meta_resp.status_code == 200:
                data = meta_resp.json() if meta_resp.content else {}
                presigned = data.get("presigned_url") or data.get("url") or ""
            else:
                _raise_for_plane_status(meta_resp)
                presigned = ""
            if not presigned:
                raise ToolError("plane api error: missing presigned URL in redirect location")

            content_b64: str | None = None
            warning: str | None = None
            if include_content_base64:
                body_resp = await client.get(presigned)
                if body_resp.status_code != 200:
                    raise ToolError(f"download failed: {body_resp.status_code}")
                body_bytes = body_resp.content
                if len(body_bytes) > _FILE_SIZE_LIMIT:
                    warning = f"content too large for inline transfer ({len(body_bytes)} bytes); URL only"
                else:
                    content_b64 = base64.b64encode(body_bytes).decode("ascii")

        logger.info(
            "download_file workspace=%s project=%s asset=%s include_content=%s",
            workspace_slug, project_id, asset_id, include_content_base64,
        )
        return DownloadFileResult(
            asset_id=asset_id,
            presigned_url=presigned,
            content_base64=content_b64,
            warning=warning,
        )

    @mcp.tool()
    async def list_file_assets(
        workspace_slug: str,
        project_id: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """List file assets attached to an entity.

        **Not yet implemented** — Plane's `/api/assets/v2/` surface does
        not expose a listing endpoint, and the legacy
        `/work-items/<id>/attachments/` path is out of scope for this
        fork-custom tool (see `.claude/docs/customization/todo.md` #7).
        """
        raise NotImplementedError(
            "Plane fork's /api/assets/v2/ does not expose a list-by-entity endpoint — "
            "see .claude/docs/customization/todo.md #7"
        )
