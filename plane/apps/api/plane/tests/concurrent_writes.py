# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase F §5 Step 5 — concurrent-write stress against a real SQLITE_PATH file.

pytest-django's in-memory DB uses ``journal_mode=MEMORY`` which doesn't
honour WAL multi-writer semantics. To exercise the Phase D PRAGMA setup
(WAL + busy_timeout=5000) the benchmark must run against the file-backed
DB the app actually uses in production.

Usage (requires the Phase F seed):

    SQLITE_PATH=/tmp/plane_f.sqlite3 \\
    DJANGO_SETTINGS_MODULE=plane.settings.test SECRET_KEY=dev \\
    APP_BASE_URL=http://localhost:3000 WEB_URL=http://localhost:3000 \\
    REDIS_URL=redis://localhost:6379/0 DEBUG=0 \\
    python plane/tests/concurrent_writes.py --n 50 --workers 5

Exit 0 when every writer succeeded and zero ``database is locked`` or
``database table is locked`` errors were raised.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))  # apps/api


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
    os.environ.setdefault("SECRET_KEY", "phase-f-concurrent")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    import django

    django.setup()


_bootstrap_django()  # noqa: E402

from django.db import connection, connections  # noqa: E402

from plane.db.models import (  # noqa: E402
    Issue,
    Project,
    State,
    User,
    Workspace,
)


WORKSPACE_SLUG = "phase-a-ws"
ADMIN_EMAIL = "admin@phase-a.local"


def _load_context() -> dict:
    ws = Workspace.objects.get(slug=WORKSPACE_SLUG)
    admin = User.objects.get(email=ADMIN_EMAIL)
    project = Project.objects.filter(workspace=ws).order_by("identifier").first()
    if project is None:
        raise SystemExit("ERROR: no project — run golden_seed.py --scale 100 first")
    state = State.objects.filter(project=project, group="backlog").first()
    if state is None:
        raise SystemExit("ERROR: no backlog state in seeded project")
    return {"ws": ws, "admin": admin, "project": project, "state": state}


def _check_pragmas_active() -> None:
    with connection.cursor() as c:
        c.execute("PRAGMA journal_mode;")
        journal = c.fetchone()[0]
        c.execute("PRAGMA busy_timeout;")
        busy = c.fetchone()[0]
    if journal.lower() != "wal":
        print(f"WARN: journal_mode={journal!r} (expected 'wal'). Concurrent writers may block.")
    if busy != 5000:
        print(f"WARN: busy_timeout={busy} (expected 5000).")


def run(n: int, workers: int) -> dict:
    ctx = _load_context()
    _check_pragmas_active()

    # Clean any leftover rows from a previous run so the count assertion is clean.
    Issue.objects.filter(
        project=ctx["project"],
        name__startswith="phase-f-conc-",
    ).delete()

    errors: list[tuple[int, BaseException]] = []
    locked_errors: list[str] = []
    created: list[str] = []
    guard = threading.Lock()

    # Bound concurrency with a simple semaphore so `workers` controls peak
    # simultaneous writers while still issuing all `n` requests.
    sem = threading.BoundedSemaphore(workers)

    def _write(idx: int) -> None:
        with sem:
            try:
                issue = Issue.objects.create(
                    name=f"phase-f-conc-{idx:03d}",
                    workspace=ctx["ws"],
                    project=ctx["project"],
                    state=ctx["state"],
                    created_by=ctx["admin"],
                    updated_by=ctx["admin"],
                    sequence_id=10_000 + idx,
                    sort_order=60_000 + idx,
                )
                with guard:
                    created.append(issue.name)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                with guard:
                    errors.append((idx, exc))
                    if "database is locked" in msg or "database table is locked" in msg:
                        locked_errors.append(msg)
            finally:
                connections.close_all()

    t0 = time.perf_counter()
    threads = [threading.Thread(target=_write, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    elapsed_s = time.perf_counter() - t0

    # Re-open the main-thread connection so the summary reads after worker close.
    connection.connect()
    final_count = Issue.objects.filter(
        project=ctx["project"],
        name__startswith="phase-f-conc-",
    ).count()

    return {
        "n": n,
        "workers": workers,
        "elapsed_s": round(elapsed_s, 3),
        "writes_per_s": round(n / elapsed_s, 2) if elapsed_s > 0 else 0,
        "created": len(created),
        "final_in_db": final_count,
        "errors": len(errors),
        "locked_errors": len(locked_errors),
        "first_errors": [
            f"{type(e).__name__}: {str(e)[:160]}" for _, e in errors[:3]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase F concurrent-write stress.")
    parser.add_argument("--n", type=int, default=50, help="total writes to attempt")
    parser.add_argument("--workers", type=int, default=5, help="peak concurrent writers")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    import json

    result = run(args.n, args.workers)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"n={result['n']}  workers={result['workers']}  "
            f"elapsed={result['elapsed_s']}s  rate={result['writes_per_s']}/s"
        )
        print(
            f"created={result['created']}  in_db={result['final_in_db']}  "
            f"errors={result['errors']}  locked={result['locked_errors']}"
        )
        for e in result["first_errors"]:
            print(f"  - {e}")

    # Pass criteria: zero locked errors AND all rows persisted.
    if result["locked_errors"] > 0:
        return 1
    if result["final_in_db"] != result["n"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
