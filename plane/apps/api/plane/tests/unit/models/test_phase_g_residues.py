# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase G — guard tests locking in the SQLite-only state.

§7.1 scans the runtime source (settings, utils, views, models) and
requirements files for Postgres-era identifiers that must not reappear.
The exempt paths are:

  - migrations/                   : historical schema, frozen
  - tests/                        : includes these guard tests themselves,
                                    plus deferred-tool helpers that still
                                    mention `DATABASE_URL` in docstrings
                                    (e.g. plane/tests/golden_seed.py)
  - plane/utils/sqlite_aggregates.py : docstring example only
  - plane/middleware/db_routing.py + plane/utils/core/dbrouters.py
                                    : unused replica infra, not wired
                                    into settings (left as dead code)

§7.2 asserts the live Django settings collapsed to a single SQLite entry.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings


REPO_ROOT = Path(__file__).resolve().parents[5]          # D:/Workspace/plane
APP_API = REPO_ROOT / "apps" / "api"


FORBIDDEN = (
    "psycopg",
    "POSTGRES_",
    "dj_database_url",
    "dj-database-url",
    "plane-db",
    "pgdata",
)


def _scan(root: Path, globs: tuple[str, ...], exempt_suffixes: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for pattern in globs:
        for path in root.rglob(pattern):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(rel.endswith(suf) or suf in rel for suf in exempt_suffixes):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for token in FORBIDDEN:
                if token in text:
                    hits.append(f"{rel}: {token}")
    return hits


# ---- §7.1 --------------------------------------------------------------------
@pytest.mark.unit
def test_no_postgres_residues_in_runtime_source():
    """Runtime Python source under apps/api/plane/ — migrations/tests/the
    shim docstring are the only documented exemptions. The replica routing
    infrastructure that used to live in plane/middleware/db_routing.py and
    plane/utils/core/ was deleted post-Phase-G; their exemptions are gone."""
    exempt = (
        "/migrations/",
        "/tests/",
        "plane/utils/sqlite_aggregates.py",
    )
    hits = _scan(APP_API / "plane", globs=("*.py",), exempt_suffixes=exempt)
    assert not hits, "forbidden Postgres tokens in runtime source:\n  " + "\n  ".join(hits)


@pytest.mark.unit
def test_no_postgres_residues_in_requirements():
    """pip requirements should no longer pull Postgres drivers."""
    hits = _scan(APP_API / "requirements", globs=("*.txt",), exempt_suffixes=())
    assert not hits, "forbidden Postgres tokens in requirements:\n  " + "\n  ".join(hits)


@pytest.mark.unit
def test_no_postgres_residues_in_docker_compose():
    hits: list[str] = []
    for name in ("docker-compose.yml", "docker-compose-local.yml"):
        path = REPO_ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN:
            if token in text:
                hits.append(f"{name}: {token}")
    assert not hits, "forbidden Postgres tokens in docker-compose:\n  " + "\n  ".join(hits)


# ---- §7.2 --------------------------------------------------------------------
@pytest.mark.unit
def test_database_config_is_sqlite_only():
    """The live settings must expose exactly one sqlite default alias —
    any leftover 'replica' or postgresql ENGINE would be a Phase G regression."""
    default = settings.DATABASES["default"]
    assert default["ENGINE"] == "django.db.backends.sqlite3", (
        f"expected sqlite, got {default['ENGINE']!r}"
    )
    assert "replica" not in settings.DATABASES, (
        "replica alias leaked back into DATABASES; Phase G removed it"
    )
    # Phase D PRAGMA hook still handles WAL; ensure default path is file-backed.
    name = str(default.get("NAME", ""))
    assert name, "DATABASES['default']['NAME'] is empty"
    assert name != ":memory:", (
        "production config must not default to :memory:; set SQLITE_PATH"
    )
