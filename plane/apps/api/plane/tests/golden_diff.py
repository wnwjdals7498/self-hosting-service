# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase A — Golden diff tool.

Compares two directories of JSON snapshots captured by golden_capture.py and
reports structural diffs using deepdiff, with tolerance for commonly mutating
fields (timestamps, auto UUIDs, ordering).

Usage:
    python apps/api/plane/tests/golden_diff.py \\
        --old apps/api/tests/golden \\
        --new /tmp/new-capture

Exit code:
    0 — no meaningful diff
    1 — diffs present (details printed)
    2 — invalid inputs (missing directory / missing file pairs)

No Django import is required for diff itself; this module can run standalone.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

try:
    from deepdiff import DeepDiff
except ImportError as exc:  # pragma: no cover
    print(f"deepdiff missing: {exc}. Install via `pip install deepdiff`.", file=sys.stderr)
    raise SystemExit(2) from exc


# --- tolerance configuration ---------------------------------------------------
# Per sqlite-migration Phase E §2.3 — timestamps and per-seed randomness are
# allowed to differ between runs as long as the structural shape matches.
TIMESTAMP_KEYS = (
    "created_at",
    "updated_at",
    "deleted_at",
    "last_saved_at",
    "completed_at",  # issue completion timestamp; moves with every re-seed
    "start_date",
    "target_date",
)
# Fields whose value is seeded from a random source (model defaults like
# get_random_color). Safe to diff away from a structural comparison.
RANDOM_SEEDED_KEYS = ("background_color",)
EXCLUDE_REGEX_PATHS = [
    # cover any list/dict depth, e.g. root['body'][0]['updated_at']
    re.compile(
        r"root(?:\[.+?\])*\['(?:"
        + "|".join(TIMESTAMP_KEYS + RANDOM_SEEDED_KEYS)
        + r")'\]"
    ),
    re.compile(r"root\['__meta__'\]"),  # meta header can safely differ between runs
]


def diff_files(old_path: Path, new_path: Path) -> DeepDiff:
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = json.loads(new_path.read_text(encoding="utf-8"))
    return DeepDiff(
        old,
        new,
        ignore_order=True,
        exclude_regex_paths=EXCLUDE_REGEX_PATHS,
    )


def diff_dirs(old_dir: Path, new_dir: Path, *, verbose: bool = True) -> dict:
    if not old_dir.is_dir() or not new_dir.is_dir():
        print(f"ERROR: not a directory — old={old_dir} new={new_dir}", file=sys.stderr)
        return {"error": "bad_dir", "exit": 2}

    old_files = {p.name: p for p in old_dir.glob("*.json")}
    new_files = {p.name: p for p in new_dir.glob("*.json")}

    missing_in_new = sorted(set(old_files) - set(new_files))
    missing_in_old = sorted(set(new_files) - set(old_files))
    common = sorted(set(old_files) & set(new_files))

    per_file_diffs: dict[str, str] = {}
    for name in common:
        dd = diff_files(old_files[name], new_files[name])
        if dd:  # truthy DeepDiff means changes present
            per_file_diffs[name] = dd.to_json()

    summary = {
        "old_dir": str(old_dir),
        "new_dir": str(new_dir),
        "compared": len(common),
        "diff_count": len(per_file_diffs),
        "missing_in_new": missing_in_new,
        "missing_in_old": missing_in_old,
    }

    if verbose:
        print(json.dumps(summary, indent=2))
        for name, body in per_file_diffs.items():
            print(f"\n--- {name} ---")
            parsed = json.loads(body)
            print(json.dumps(parsed, indent=2, default=str))

    summary["per_file_diffs"] = per_file_diffs
    return summary


def _exit_code_from_summary(summary: dict) -> int:
    if summary.get("error"):
        return 2
    if summary["diff_count"] or summary["missing_in_new"] or summary["missing_in_old"]:
        return 1
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Phase A golden diff.")
    parser.add_argument("--old", type=Path, required=True, help="Old (baseline) JSON directory.")
    parser.add_argument("--new", type=Path, required=True, help="New (current) JSON directory.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = diff_dirs(args.old, args.new, verbose=not args.quiet)
    return _exit_code_from_summary(summary)


if __name__ == "__main__":
    raise SystemExit(main())
