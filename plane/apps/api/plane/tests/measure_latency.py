# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase F §5 Step 4 — response-time p50/p95/p99 for 6 core read endpoints.

The tool exercises Django's full request stack via `APIClient` (same layer
as golden_capture.py); the localhost socket hop is intentionally excluded
so numbers reflect ORM + serializer cost, not network noise. §2.2 latency
ceilings in phase-f-performance.md were written with this interpretation.

Usage (requires a seeded SQLITE_PATH DB — the scale=100 path is canonical):

    SQLITE_PATH=/tmp/plane_f.sqlite3 \\
    DJANGO_SETTINGS_MODULE=plane.settings.test SECRET_KEY=dev \\
    APP_BASE_URL=http://localhost:3000 WEB_URL=http://localhost:3000 \\
    REDIS_URL=redis://localhost:6379/0 DEBUG=0 \\
    python plane/tests/measure_latency.py --iterations 100

Output: per-scenario p50/p95/p99/mean in milliseconds + limit verdict.
Exit 0 when all scenarios fit their §2.2 p95 budget.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))  # apps/api


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
    os.environ.setdefault("SECRET_KEY", "phase-f-latency")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    import django

    django.setup()


_bootstrap_django()  # noqa: E402

from rest_framework.test import APIClient  # noqa: E402

from plane.db.models import Project, User, Workspace  # noqa: E402


WORKSPACE_SLUG = "phase-a-ws"
ADMIN_EMAIL = "admin@phase-a.local"


def _scenarios(slug: str, pid: str) -> list[tuple[str, str, float]]:
    """Return (name, url, p95_ceiling_ms) tuples from phase-f-performance.md §2.2."""
    return [
        ("issues_list",          f"/api/workspaces/{slug}/projects/{pid}/issues/",                              500),
        ("issues_list_filtered", f"/api/workspaces/{slug}/projects/{pid}/issues/?priority=high",                800),
        ("cycles_list",          f"/api/workspaces/{slug}/projects/{pid}/cycles/",                              300),
        ("modules_list",         f"/api/workspaces/{slug}/projects/{pid}/modules/",                             300),
        ("pages_list",           f"/api/workspaces/{slug}/projects/{pid}/pages/",                               200),
        ("search",               f"/api/workspaces/{slug}/search/?search=Issue&workspace_search=true",          400),
    ]


def _percentile(samples: list[float], pct: float) -> float:
    """Linear-interpolation percentile without requiring numpy."""
    if not samples:
        return 0.0
    srt = sorted(samples)
    k = (len(srt) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(srt) - 1)
    frac = k - lo
    return srt[lo] + (srt[hi] - srt[lo]) * frac


def measure(client: APIClient, url: str, iterations: int) -> dict:
    # Warm up (JIT caches, connection pool, lazy serializer imports) — 3 hits.
    for _ in range(3):
        client.get(url)
    samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        resp = client.get(url)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if resp.status_code != 200:
            return {"error": f"status={resp.status_code}", "samples": 0}
        samples.append(dt_ms)
    return {
        "samples": len(samples),
        "mean":  statistics.fmean(samples),
        "p50":   _percentile(samples, 0.50),
        "p95":   _percentile(samples, 0.95),
        "p99":   _percentile(samples, 0.99),
        "min":   min(samples),
        "max":   max(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase F latency benchmark.")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    ws = Workspace.objects.get(slug=WORKSPACE_SLUG)
    admin = User.objects.get(email=ADMIN_EMAIL)
    project = Project.objects.filter(workspace=ws).order_by("identifier").first()
    if project is None:
        print("ERROR: no project found; run golden_seed.py --scale 100", file=sys.stderr)
        return 1

    client = APIClient()
    client.force_authenticate(user=admin)

    all_results: list[dict] = []
    all_pass = True
    for name, url, ceiling in _scenarios(ws.slug, str(project.id)):
        stats = measure(client, url, args.iterations)
        if "error" in stats:
            entry = {
                "name": name, "url": url, "ceiling_ms": ceiling,
                "error": stats["error"], "pass": False,
            }
            all_results.append(entry)
            all_pass = False
            continue
        passed = stats["p95"] <= ceiling
        entry = {
            "name": name, "url": url, "ceiling_ms": ceiling,
            **{k: round(v, 2) for k, v in stats.items() if k != "samples"},
            "samples": stats["samples"], "pass": passed,
        }
        all_results.append(entry)
        if not passed:
            all_pass = False

    if args.json:
        print(json.dumps({"iterations": args.iterations, "results": all_results}, indent=2))
    else:
        print(f"{'name':<24} {'mean':>8} {'p50':>8} {'p95':>8} {'p99':>8}  {'limit':>6}  verdict")
        print("-" * 84)
        for r in all_results:
            if "error" in r:
                print(f"{r['name']:<24}  ERROR: {r['error']}")
                continue
            verdict = "PASS" if r["pass"] else "FAIL"
            print(
                f"{r['name']:<24} {r['mean']:>8.2f} {r['p50']:>8.2f} "
                f"{r['p95']:>8.2f} {r['p99']:>8.2f}  {r['ceiling_ms']:>6}  {verdict}"
            )

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
