## fork-custom: tool-level guard for instance-admin PAT (plane-mcp-v2-bootstrap, 2026-04-24)
"""Decorator enforcing Plane `is_instance_admin=True` with 60s Redis cache.

See `.claude/docs/customization/spec.md` §5.3, `develop/1_admin_guard_develop_plan_1.md`.
"""

import functools
import hashlib
import inspect
import logging
import os
from typing import Any

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from key_value.aio.protocols.key_value import AsyncKeyValue
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.stores.redis import RedisStore

logger = logging.getLogger(__name__)

_COLLECTION = "mcp_admin_guard"
_TTL_SECONDS = 60.0
_USER_ME_PATH = "/api/v1/users/me/"
_DEFAULT_BASE_URL = "https://api.plane.so"
_store: AsyncKeyValue | None = None


def _token_key(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"mcp:admin:{digest}"


def _build_store() -> AsyncKeyValue:
    host = os.getenv("REDIS_HOST")
    port = os.getenv("REDIS_PORT")
    if not (host and port):
        logger.warning("REDIS_HOST/PORT unset, using in-memory admin cache")
        return MemoryStore(default_collection=_COLLECTION)
    try:
        return RedisStore(
            host=host,
            port=int(port),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD") or None,
            default_collection=_COLLECTION,
        )
    except Exception as exc:
        logger.warning("Redis init failed, using in-memory admin cache: %s", exc)
        return MemoryStore(default_collection=_COLLECTION)


def _get_store() -> AsyncKeyValue:
    global _store
    if _store is None:
        _store = _build_store()
    return _store


def _reset_store_for_tests() -> None:
    global _store
    _store = None


def _plane_base_url() -> str:
    base = os.getenv("PLANE_INTERNAL_BASE_URL") or os.getenv("PLANE_BASE_URL", _DEFAULT_BASE_URL)
    return base.rstrip("/")


async def _fetch_admin_from_plane(token: str) -> bool:
    url = f"{_plane_base_url()}{_USER_ME_PATH}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers={"x-api-key": token})
    if response.status_code == 401:
        raise ToolError("authentication failed: token invalid")
    if response.status_code >= 400:
        raise ToolError(f"admin check failed: {response.status_code}")
    data = response.json()
    if "is_instance_admin" not in data:
        user_id = data.get("id", "?")
        logger.warning("is_instance_admin missing for user=%s", user_id)
        return False
    is_admin = bool(data["is_instance_admin"])
    logger.info("admin check via api: user=%s result=%s", data.get("id", "?"), is_admin)
    return is_admin


async def _check_admin(token: str) -> bool:
    key = _token_key(token)
    store = _get_store()
    try:
        cached: dict[str, Any] | None = await store.get(key)
    except Exception as exc:
        logger.warning("admin cache read failed: %s", exc)
        cached = None
    if cached is not None and "is_admin" in cached:
        logger.info("admin check via cache: key=%s result=%s", key, cached["is_admin"])
        return bool(cached["is_admin"])
    is_admin = await _fetch_admin_from_plane(token)
    try:
        await store.put(key, {"is_admin": is_admin}, ttl=_TTL_SECONDS)
    except Exception as exc:
        logger.warning("admin cache write failed: %s", exc)
    return is_admin


def require_instance_admin(func):
    """Tool decorator that enforces Plane `is_instance_admin=True`.

    Returns an async wrapper regardless of whether ``func`` is sync or async.
    Cache key is ``sha256(token)[:16]`` so a bearer-token rotation forces refresh
    without requiring user_id lookup.
    """

    is_coro = inspect.iscoroutinefunction(func)

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        access_token = get_access_token()
        if access_token is None:
            raise ToolError("authentication required")
        if not await _check_admin(access_token.token):
            raise ToolError("requires instance admin")
        if is_coro:
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

    return wrapper
