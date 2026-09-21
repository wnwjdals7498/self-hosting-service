## fork-custom
"""Host filesystem path resolution for the fork deployment.

Windows-only by design — see `.claude/docs/customization/spec.md` §4.1.
"""

import os
from pathlib import Path


def get_ipban_log_path() -> Path | None:
    """Resolve the IPBan stdout log path from ``PLANE_MCP_IPBAN_LOG``.

    Returns ``None`` when the env var is unset or blank, signalling "not
    configured" to callers (they return a warning, not an error).
    """
    raw = os.getenv("PLANE_MCP_IPBAN_LOG", "").strip()
    return Path(raw) if raw else None
