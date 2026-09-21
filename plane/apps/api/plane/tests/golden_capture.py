# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase A — Golden response capture tool.

Calls a curated list of API endpoints against a seeded DB and persists each
response body as JSON under apps/api/tests/golden/ (or a specified output dir).

Usage:
    python apps/api/plane/tests/golden_capture.py --capture --out apps/api/tests/golden
    python apps/api/plane/tests/golden_capture.py --list      # show endpoint slugs
    python apps/api/plane/tests/golden_capture.py --capture --endpoints issues_list

Prerequisite: DB must already be migrated & seeded
  (`python apps/api/plane/tests/golden_seed.py`).

Notes (Path C):
  Until Phase B replaces ArrayField with JSONField, this tool cannot execute
  against SQLite. The tool body is authored now so Phase B / C can run it
  immediately after schema changes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterable

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))  # apps/api


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
    os.environ.setdefault("SECRET_KEY", "phase-a-capture-local")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("DATABASE_URL", "sqlite:///dev.sqlite3")
    import django

    django.setup()


_bootstrap_django()  # noqa: E402

from rest_framework.test import APIClient  # noqa: E402

from plane.db.models import Project, User, Workspace  # noqa: E402


WORKSPACE_SLUG = "phase-a-ws"
ADMIN_EMAIL = "admin@phase-a.local"


# --- endpoint registry ----------------------------------------------------------
def _endpoints(ws_slug: str, project_ids: list[str]) -> list[tuple[str, str, str]]:
    """Return list of (slug, method, url) tuples.

    Slugs must be unique and filesystem-safe.
    """
    p0, p1 = project_ids[0], project_ids[1] if len(project_ids) > 1 else project_ids[0]

    eps: list[tuple[str, str, str]] = [
        # ------ workspace / project meta ------
        ("workspaces_list",          "GET", "/api/workspaces/"),
        ("workspace_detail",         "GET", f"/api/workspaces/{ws_slug}/"),
        ("projects_list",            "GET", f"/api/workspaces/{ws_slug}/projects/"),
        ("project_detail",           "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/"),
        ("members_list",             "GET", f"/api/workspaces/{ws_slug}/members/"),
        ("project_members_list",     "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/members/"),
        # ------ labels / states ------
        ("labels_list",              "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/labels/"),
        ("states_list",              "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/states/"),
        # ------ issues (read) ------
        ("issues_list",              "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/issues/"),
        ("issues_list_p1",           "GET", f"/api/workspaces/{ws_slug}/projects/{p1}/issues/"),
        ("issues_list_priority_high","GET", f"/api/workspaces/{ws_slug}/projects/{p0}/issues/?priority=high"),
        ("issues_list_state_done",   "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/issues/?group_by=state"),
        # ------ cycles ------
        ("cycles_list",              "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/cycles/"),
        ("cycles_archive",           "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/archived-cycles/"),
        # ------ modules ------
        ("modules_list",             "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/modules/"),
        ("modules_archive",          "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/archived-modules/"),
        # ------ pages ------
        ("pages_list",               "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/pages/"),
        # ------ drafts ------
        ("drafts_list",              "GET", f"/api/workspaces/{ws_slug}/draft-issues/"),
        # ------ search ------
        ("search_simple",            "GET", f"/api/workspaces/{ws_slug}/search/?search=Issue&workspace_search=true"),
        # ------ space (public portal) ------
        ("space_projects_list",      "GET", f"/api/public/workspaces/{ws_slug}/projects/"),
        # ------ analytics / views / estimates (optional, may 404 without features enabled) ------
        ("views_list",               "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/views/"),
        ("estimates_list",           "GET", f"/api/workspaces/{ws_slug}/projects/{p0}/estimates/"),
    ]
    return eps


# --- capture runner -------------------------------------------------------------
def capture(
    out_dir: Path,
    endpoint_filter: Iterable[str] | None = None,
    *,
    verbose: bool = True,
) -> dict:
    """Hit each endpoint with an authenticated APIClient and persist the body.

    Returns summary dict with counts.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        ws = Workspace.objects.get(slug=WORKSPACE_SLUG)
    except Workspace.DoesNotExist:
        print(
            f"ERROR: workspace slug '{WORKSPACE_SLUG}' not found. "
            "Run golden_seed.py first.",
            file=sys.stderr,
        )
        return {"error": "workspace_missing"}

    try:
        admin = User.objects.get(email=ADMIN_EMAIL)
    except User.DoesNotExist:
        print(f"ERROR: admin user '{ADMIN_EMAIL}' not found.", file=sys.stderr)
        return {"error": "admin_missing"}

    project_ids = [str(p.id) for p in Project.objects.filter(workspace=ws).order_by("identifier")]
    if not project_ids:
        print("ERROR: no projects found for seed workspace.", file=sys.stderr)
        return {"error": "no_projects"}

    client = APIClient()
    client.force_authenticate(user=admin)

    eps = _endpoints(ws.slug, project_ids)
    if endpoint_filter:
        wanted = set(endpoint_filter)
        eps = [e for e in eps if e[0] in wanted]
        unknown = wanted - {e[0] for e in eps}
        if unknown:
            print(f"WARN: unknown endpoint slugs skipped: {sorted(unknown)}", file=sys.stderr)

    counts = {"ok": 0, "non2xx": 0, "error": 0}
    for slug, method, url in eps:
        try:
            resp = client.generic(method, url)
        except Exception as exc:  # noqa: BLE001
            print(f"[{slug}] EXCEPTION: {exc}", file=sys.stderr)
            counts["error"] += 1
            continue

        status_code = resp.status_code
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {"__raw": resp.content.decode("utf-8", errors="replace")}

        payload = {
            "__meta__": {
                "endpoint": slug,
                "method": method,
                "url": url,
                "status": status_code,
            },
            "body": body,
        }
        target = out_dir / f"{slug}.json"
        target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

        if 200 <= status_code < 300:
            counts["ok"] += 1
        else:
            counts["non2xx"] += 1
            if verbose:
                print(f"[{slug}] {method} {url} -> {status_code}")

    if verbose:
        print(json.dumps(counts, indent=2))
    counts["out_dir"] = str(out_dir)
    counts["endpoint_count"] = len(eps)
    return counts


def list_endpoints() -> None:
    for slug, method, url in _endpoints("<ws>", ["<p0>", "<p1>"]):
        print(f"{slug:30s} {method:6s} {url}")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Phase A golden capture.")
    parser.add_argument("--capture", action="store_true", help="Run capture.")
    parser.add_argument("--list", action="store_true", help="List endpoint slugs.")
    parser.add_argument(
        "--out",
        type=Path,
        default=_HERE.parent / "golden",
        help="Output directory for JSON files (default: tests/golden/).",
    )
    parser.add_argument(
        "--endpoints",
        nargs="+",
        help="Optional subset of endpoint slugs to capture.",
    )
    args = parser.parse_args()

    if args.list:
        list_endpoints()
        return 0

    if args.capture:
        res = capture(args.out, args.endpoints)
        if res.get("error"):
            return 2
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
