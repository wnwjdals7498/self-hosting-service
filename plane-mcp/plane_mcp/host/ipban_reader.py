## fork-custom
"""Reverse-ish tail+parse for IPBan ``stdout.log``.

Format observed on the operating host:
``YYYY-MM-DD HH:MM:SS.ffff|LEVEL|IPBan|<message>``

Only three message prefixes are extracted; everything else is skipped quietly.
File absence / permission denial surface as ``warning`` fields on a 2xx result;
they never raise (see `.claude/docs/customization/spec.md` §6).
"""

from __future__ import annotations

import logging
import re
from collections import deque
from pathlib import Path
from typing import Literal, TypedDict

from plane_mcp.host.paths import get_ipban_log_path

logger = logging.getLogger(__name__)

IpbanType = Literal["Banning", "Un-banning", "LoginFailure"]


class IpbanEvent(TypedDict):
    timestamp: str
    level: str
    type: IpbanType
    ip: str | None
    user_name: str | None
    count: int | None
    raw: str


class IpbanTailResult(TypedDict):
    events: list[IpbanEvent]
    warning: str | None


_BAN_RE = re.compile(
    r"Banning ip address:\s*(?P<ip>\S+?),\s*user name:\s*(?P<user>[^,]*),"
    r"\s*config blacklisted:\s*\S+,\s*count:\s*(?P<count>\d+)"
)
_UNBAN_RE = re.compile(
    r"Un-?banning\s+ip(?:\s+address)?:\s*(?P<ip>\S+)",
    re.IGNORECASE,
)
_LOGIN_RE = re.compile(
    r"Login failure:\s*(?P<ip>[^,]+?)\s*,\s*(?P<user>[^,]*)\s*,\s*\S+\s*,\s*(?P<count>\d+)"
)


def _parse_line(line: str) -> IpbanEvent | None:
    line = line.rstrip()
    if not line:
        return None
    parts = line.split("|", 3)
    if len(parts) < 4 or parts[2] != "IPBan":
        return None
    timestamp, level, _src, msg = parts
    if m := _BAN_RE.search(msg):
        return IpbanEvent(
            timestamp=timestamp,
            level=level,
            type="Banning",
            ip=m.group("ip"),
            user_name=(m.group("user").strip() or None),
            count=int(m.group("count")),
            raw=line,
        )
    if m := _UNBAN_RE.search(msg):
        return IpbanEvent(
            timestamp=timestamp,
            level=level,
            type="Un-banning",
            ip=m.group("ip"),
            user_name=None,
            count=None,
            raw=line,
        )
    if m := _LOGIN_RE.search(msg):
        return IpbanEvent(
            timestamp=timestamp,
            level=level,
            type="LoginFailure",
            ip=m.group("ip").strip(),
            user_name=(m.group("user").strip() or None),
            count=int(m.group("count")),
            raw=line,
        )
    return None


def tail_events(limit: int = 50, log_path: Path | None = None) -> IpbanTailResult:
    """Return up to ``limit`` most recent parsed events (newest first).

    ``log_path`` defaults to :func:`plane_mcp.host.paths.get_ipban_log_path`.
    Failures to open/read the file never raise — they return with ``warning`` set.
    """
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    path = log_path if log_path is not None else get_ipban_log_path()
    if path is None:
        return {
            "events": [],
            "warning": "log path not configured (PLANE_MCP_IPBAN_LOG unset)",
        }

    try:
        if not path.is_file():
            return {"events": [], "warning": f"log file not found: {path}"}

        buf: deque[IpbanEvent] = deque(maxlen=limit)
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                event = _parse_line(line)
                if event is not None:
                    buf.append(event)
                elif line.strip():
                    logger.debug("unparseable line skipped: %r", line[:80])
    except PermissionError as exc:
        return {"events": [], "warning": f"log file access denied: {exc}"}
    except OSError as exc:
        return {"events": [], "warning": f"log read failed: {exc}"}

    return {"events": list(reversed(buf)), "warning": None}
