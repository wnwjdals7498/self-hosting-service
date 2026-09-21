# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase F §5 Step 5 — PRAGMA guard for the file-backed concurrency path.

pytest-django spawns a ``:memory:`` DB whose ``journal_mode`` is forced to
``MEMORY`` regardless of the ``connection_created`` hook. WAL + multi-
writer contention cannot be observed there, so the actual thread-stress
benchmark lives in ``plane/tests/concurrent_writes.py`` (invoked against
an SQLITE_PATH file). This unit test only pins the guaranteed PRAGMA
surface so a regression in the hook would fail noisily inside the normal
pytest run.
"""

from __future__ import annotations

import pytest
from django.db import connection


@pytest.mark.django_db
def test_busy_timeout_applied():
    if connection.vendor != "sqlite":
        pytest.skip("sqlite-only pragma check")
    with connection.cursor() as c:
        c.execute("PRAGMA busy_timeout;")
        busy = c.fetchone()[0]
        c.execute("PRAGMA foreign_keys;")
        foreign = c.fetchone()[0]
    assert busy == 5000, f"busy_timeout={busy}, expected 5000 (phase-d hook)"
    assert foreign == 1, f"foreign_keys={foreign}, expected 1 (phase-d hook)"
