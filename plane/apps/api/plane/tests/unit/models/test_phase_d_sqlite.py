# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase D — SQLite backend switch verification.

Assumptions:
  - `plane.settings.test` is loaded with SQLITE_PATH pointing at a real file
    (handoff §2 pattern). DEBUG / SECRET_KEY / REDIS_URL already wired.
  - The harness hits the process-wide default Django connection, so any
    `connection_created` signal side-effects (PRAGMAs) are observable via
    `django.db.connection`.

Coverage (3 guards):
  7.1 migrate_exists  — a fresh SQLITE_PATH run produces a file with the
                        expected table set, proving migrate completed.
  7.2 pragmas_applied — DbConfig.ready() installs WAL + busy_timeout +
                        foreign_keys on every new connection.
  7.3 no_postgres_import — nothing in apps/api/plane/ imports
                           django.contrib.postgres outside of the
                           documented exemptions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.db import connection


# ---- 7.1 --------------------------------------------------------------------
@pytest.mark.unit
def test_migrate_produced_core_tables(db):
    """After migrate, the key Plane tables exist and are queryable."""
    assert connection.vendor == "sqlite", (
        f"expected sqlite, got {connection.vendor}; "
        "set SQLITE_PATH before running this test."
    )
    with connection.cursor() as c:
        c.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row[0] for row in c.fetchall()}
    required = {
        "users",
        "workspaces",
        "projects",
        "issues",
        "issue_labels",
        "issue_assignees",
        "module_issues",
    }
    missing = required - tables
    assert not missing, f"core tables missing after migrate: {missing}"


# ---- 7.2 --------------------------------------------------------------------
@pytest.mark.unit
def test_sqlite_pragmas_applied(db):
    """DbConfig.ready() hook sets busy_timeout / foreign_keys / WAL.

    Note: pytest-django spawns a `:memory:` test database, on which SQLite
    forces journal_mode=MEMORY regardless of the PRAGMA — the signal still
    runs, just the WAL pragma is a no-op there. We assert the two pragmas
    that *do* apply to memory DBs, and accept either WAL (file) or MEMORY
    (pytest clone) for journal_mode.
    """
    if connection.vendor != "sqlite":
        pytest.skip("pragma test only meaningful on sqlite")
    with connection.cursor() as c:
        c.execute("PRAGMA journal_mode;")
        journal = c.fetchone()[0]
        c.execute("PRAGMA foreign_keys;")
        foreign = c.fetchone()[0]
        c.execute("PRAGMA busy_timeout;")
        busy = c.fetchone()[0]

    assert journal.lower() in {"wal", "memory"}, (
        f"journal_mode={journal!r}, expected wal (file db) or memory (pytest)"
    )
    assert foreign == 1, f"foreign_keys={foreign}, expected 1"
    assert busy == 5000, f"busy_timeout={busy}, expected 5000"


# ---- 7.3 --------------------------------------------------------------------
@pytest.mark.unit
def test_no_django_contrib_postgres_import_in_source():
    """No live import of django.contrib.postgres in the production code.

    Exemptions (documented):
      - plane/utils/sqlite_aggregates.py  (docstring example only)
      - plane/tests/                      (guard tests)
      - */migrations/                     (historical schema)
    """
    root = Path(__file__).resolve().parents[4] / "plane"
    forbidden_substr = "django.contrib.postgres"
    hits: list[str] = []
    for py in root.rglob("*.py"):
        rel = py.relative_to(root).as_posix()
        if rel.startswith("tests/"):
            continue
        if "/migrations/" in rel:
            continue
        if rel == "utils/sqlite_aggregates.py":
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if forbidden_substr in text:
            hits.append(rel)

    assert not hits, (
        "django.contrib.postgres import leaked outside exempt paths:\n  "
        + "\n  ".join(hits)
    )
