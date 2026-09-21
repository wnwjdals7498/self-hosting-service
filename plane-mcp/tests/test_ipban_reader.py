## fork-custom
"""Tests for plane_mcp.host.ipban_reader.tail_events."""

from pathlib import Path
from unittest.mock import patch

import pytest

from plane_mcp.host import ipban_reader

SAMPLE_LINES = [
    "2026-04-19 22:09:44.1454|WARN|IPBan|Banning ip address: 91.238.181.8, "
    "user name: fknpoc, config blacklisted: False, count: 6, "
    "extra info: , duration: 1.00:00:00",
    "2026-04-19 22:10:14.4280|WARN|IPBan|Banning ip address: 103.99.38.184, "
    "user name: , config blacklisted: False, count: 6, "
    "extra info: , duration: 1.00:00:00",
    "2026-04-19 22:09:29.1155|WARN|IPBan|Login failure: 103.99.38.184, , "
    "RDP, 2, 14, reason: ",
    "2026-04-19 22:09:29.1226|WARN|IPBan|Login failure: 91.238.181.8, fknpoc, "
    "RDP, 4, 4625, reason: ",
    "2026-04-19 22:11:30.0000|WARN|IPBan|Un-banning ip address: 91.238.181.8",
    "2026-04-19 22:12:00.0000|INFO|IPBan|IP blacklisted: False, user name blacklisted: False",
    "Creating default nlog.config file",
]


def _write(tmp_path: Path, lines: list[str]) -> Path:
    target = tmp_path / "stdout.log"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def test_parses_three_types(tmp_path):
    path = _write(tmp_path, SAMPLE_LINES)
    result = ipban_reader.tail_events(limit=50, log_path=path)
    assert result["warning"] is None
    types = [e["type"] for e in result["events"]]
    assert types.count("Banning") == 2
    assert types.count("Un-banning") == 1
    assert types.count("LoginFailure") == 2
    # two lines never parse (nlog.config + the info line without a prefix)
    assert len(result["events"]) == 5


def test_banning_extracts_fields(tmp_path):
    path = _write(tmp_path, [SAMPLE_LINES[0]])
    result = ipban_reader.tail_events(limit=5, log_path=path)
    event = result["events"][0]
    assert event["type"] == "Banning"
    assert event["ip"] == "91.238.181.8"
    assert event["user_name"] == "fknpoc"
    assert event["count"] == 6
    assert event["level"] == "WARN"
    assert event["timestamp"].startswith("2026-04-19")


def test_login_failure_with_blank_user(tmp_path):
    path = _write(tmp_path, [SAMPLE_LINES[2]])
    result = ipban_reader.tail_events(limit=5, log_path=path)
    event = result["events"][0]
    assert event["type"] == "LoginFailure"
    assert event["ip"] == "103.99.38.184"
    assert event["user_name"] is None
    assert event["count"] == 2


def test_unbanning(tmp_path):
    path = _write(tmp_path, [SAMPLE_LINES[4]])
    result = ipban_reader.tail_events(limit=5, log_path=path)
    event = result["events"][0]
    assert event["type"] == "Un-banning"
    assert event["ip"] == "91.238.181.8"


def test_limit_keeps_most_recent(tmp_path):
    path = _write(tmp_path, SAMPLE_LINES)
    result = ipban_reader.tail_events(limit=2, log_path=path)
    assert len(result["events"]) == 2
    # with maxlen=2, we keep the last two parseable lines (Un-banning is 5th
    # line, preceded by two logins that we already accepted)
    assert result["events"][0]["type"] == "Un-banning"


def test_empty_file(tmp_path):
    path = _write(tmp_path, [])
    result = ipban_reader.tail_events(limit=5, log_path=path)
    assert result == {"events": [], "warning": None}


def test_missing_file(tmp_path):
    path = tmp_path / "does-not-exist.log"
    result = ipban_reader.tail_events(limit=5, log_path=path)
    assert result["events"] == []
    assert result["warning"] is not None
    assert "not found" in result["warning"]


def test_permission_denied(tmp_path):
    path = _write(tmp_path, SAMPLE_LINES)
    with patch.object(Path, "open", side_effect=PermissionError("denied")):
        result = ipban_reader.tail_events(limit=5, log_path=path)
    assert result["events"] == []
    assert "access denied" in result["warning"]


def test_log_path_unset_without_env(monkeypatch):
    monkeypatch.delenv("PLANE_MCP_IPBAN_LOG", raising=False)
    result = ipban_reader.tail_events(limit=5, log_path=None)
    assert result["events"] == []
    assert "not configured" in result["warning"]


def test_limit_below_one_raises():
    with pytest.raises(ValueError):
        ipban_reader.tail_events(limit=0)


def test_limit_above_thousand_raises():
    with pytest.raises(ValueError):
        ipban_reader.tail_events(limit=1001)
