# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase A — Deterministic golden seed script.

Creates a fixed set of workspace / project / issue / cycle / module / page / label
records using namespaced UUID v3, so the same seed invocation always produces
identical data (UUIDs, usernames, sequence ids).

Usage (after Phase B — SQLite must be migrate-able):
    DJANGO_SETTINGS_MODULE=plane.settings.test \\
    SECRET_KEY=... REDIS_URL=redis://localhost:6379/0 \\
    DATABASE_URL=sqlite:///.../plane.sqlite3 \\
    python apps/api/plane/tests/golden_seed.py

Invariant: running seed() twice on an empty DB yields identical `.values_list(id, flat=True)`
          for every model row. See tests/unit/test_golden_tools.py::test_seed_is_deterministic.

Note: Until Phase B finishes, this script cannot execute against SQLite
      (ArrayField schema is incompatible). Tool body is authored now so Phase B
      can validate it immediately.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# Allow running as a script from repo root
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))  # apps/api


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
    os.environ.setdefault("SECRET_KEY", "phase-a-seed-local")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("DATABASE_URL", "sqlite:///dev.sqlite3")
    import django

    django.setup()


_bootstrap_django()  # noqa: E402 — must precede model imports

from django.utils import timezone  # noqa: E402

from plane.db.models import (  # noqa: E402
    Cycle,
    CycleIssue,
    Issue,
    IssueAssignee,
    IssueLabel,
    Label,
    Module,
    ModuleIssue,
    Page,
    Project,
    ProjectMember,
    State,
    User,
    Workspace,
    WorkspaceMember,
)


# --- deterministic id allocation ------------------------------------------------
NS = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _id(label: str) -> uuid.UUID:
    """Stable UUIDv3: same `label` -> same UUID forever."""
    return uuid.uuid3(NS, label)


# --- constants (scale is parameterizable) ---------------------------------------
DEFAULT_SCALE = 20  # number of issues
SUPPORTED_SCALES = (20, 100)


# --- seed entry point -----------------------------------------------------------
def seed(scale: int = DEFAULT_SCALE, *, verbose: bool = True) -> dict:
    """Create deterministic fixtures.

    Args:
        scale: number of issues to create. Supports 20 (default) and 100.
        verbose: print summary when True.

    Returns:
        dict summary with counts and key ids.
    """
    if scale not in SUPPORTED_SCALES:
        raise ValueError(f"scale must be one of {SUPPORTED_SCALES}, got {scale}")

    now = timezone.now()

    # Users (admin, member, guest)
    admin = _get_or_create_user("admin", "admin@phase-a.local", superuser=True)
    member = _get_or_create_user("member", "member@phase-a.local")
    guest = _get_or_create_user("guest", "guest@phase-a.local")

    # Workspace
    ws, _ = Workspace.objects.get_or_create(
        id=_id("workspace"),
        defaults={
            "name": "Phase A Workspace",
            "slug": "phase-a-ws",
            "owner": admin,
            "created_at": now,
            "updated_at": now,
        },
    )
    for u, role in ((admin, 20), (member, 15), (guest, 5)):
        WorkspaceMember.objects.get_or_create(
            id=_id(f"wsmember-{u.email}"),
            workspace=ws,
            member=u,
            defaults={"role": role, "created_at": now, "updated_at": now},
        )

    # Projects
    projects = []
    for i in range(2):
        p, _ = Project.objects.get_or_create(
            id=_id(f"project-{i}"),
            defaults={
                "name": f"Phase A Project {i}",
                "identifier": f"PAP{i}",
                "workspace": ws,
                "created_by": admin,
                "updated_by": admin,
                "created_at": now,
                "updated_at": now,
            },
        )
        for u, role in ((admin, 20), (member, 15)):
            ProjectMember.objects.get_or_create(
                id=_id(f"pmember-{p.id}-{u.email}"),
                project=p,
                member=u,
                workspace=ws,
                defaults={"role": role, "created_at": now, "updated_at": now},
            )
        projects.append(p)

    # States (4 per project)
    state_names = [
        ("Backlog", "backlog"),
        ("Todo", "unstarted"),
        ("In Progress", "started"),
        ("Done", "completed"),
    ]
    states = {}
    for p in projects:
        for name, group in state_names:
            s, _ = State.objects.get_or_create(
                id=_id(f"state-{p.id}-{name}"),
                defaults={
                    "name": name,
                    "group": group,
                    "slug": f"{p.identifier}-{name.lower().replace(' ', '-')}",
                    "color": "#888",
                    "sequence": 10000 + state_names.index((name, group)) * 1000,
                    "project": p,
                    "workspace": ws,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            states[(p.id, name)] = s

    # Labels (3 per project)
    labels = {}
    for p in projects:
        for lname in ("bug", "feature", "chore"):
            lab, _ = Label.objects.get_or_create(
                id=_id(f"label-{p.id}-{lname}"),
                defaults={
                    "name": lname,
                    "color": "#ccc",
                    "project": p,
                    "workspace": ws,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            labels[(p.id, lname)] = lab

    # Cycles (1 active, 1 upcoming per project)
    cycles = {}
    for p in projects:
        for idx, cname in enumerate(("Active Cycle", "Upcoming Cycle")):
            c, _ = Cycle.objects.get_or_create(
                id=_id(f"cycle-{p.id}-{cname}"),
                defaults={
                    "name": cname,
                    "description": f"{cname} of {p.identifier}",
                    "start_date": now.date(),
                    "end_date": now.date(),
                    "project": p,
                    "workspace": ws,
                    "owned_by": admin,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            cycles[(p.id, cname)] = c

    # Modules (2 per project)
    modules = {}
    for p in projects:
        for mname in ("Core", "Optional"):
            m, _ = Module.objects.get_or_create(
                id=_id(f"module-{p.id}-{mname}"),
                defaults={
                    "name": mname,
                    "description": f"{mname} module for {p.identifier}",
                    "status": "planned",
                    "project": p,
                    "workspace": ws,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            modules[(p.id, mname)] = m

    # Pages (scale-aware: 5 for scale=20, 20 for scale=100)
    page_count = 5 if scale == 20 else 20
    for p in projects:
        for i in range(page_count):
            Page.objects.get_or_create(
                id=_id(f"page-{p.id}-{i}"),
                defaults={
                    "name": f"Page {i} of {p.identifier}",
                    "workspace": ws,
                    "owned_by": admin,
                    "access": 0,
                    "created_at": now,
                    "updated_at": now,
                },
            )

    # Issues: distribute `scale` across 2 projects
    per_project = scale // 2
    priorities = ("none", "urgent", "high", "medium", "low")
    state_cycle = ("Backlog", "Todo", "In Progress", "Done")

    issues = []
    for pi, p in enumerate(projects):
        for i in range(per_project):
            issue_key = f"issue-{p.identifier}-{i:03d}"
            issue, _ = Issue.objects.get_or_create(
                id=_id(issue_key),
                defaults={
                    "name": f"{p.identifier}-{i}",
                    "description_html": f"<p>Issue {i} of {p.identifier}</p>",
                    "priority": priorities[i % len(priorities)],
                    "state": states[(p.id, state_cycle[i % len(state_cycle)])],
                    "project": p,
                    "workspace": ws,
                    "created_by": admin,
                    "updated_by": admin,
                    "created_at": now,
                    "updated_at": now,
                    "sequence_id": i + 1,
                    "sort_order": 10000 + i * 100,
                },
            )
            issues.append(issue)

            # Assignees: 0~2 per issue
            assignee_pool = [admin, member, guest]
            for a in assignee_pool[: (i % 3)]:
                IssueAssignee.objects.get_or_create(
                    id=_id(f"ia-{issue.id}-{a.email}"),
                    issue=issue,
                    assignee=a,
                    defaults={
                        "project": p,
                        "workspace": ws,
                        "created_at": now,
                        "updated_at": now,
                    },
                )

            # Labels: 0~2 per issue
            label_names = ("bug", "feature", "chore")
            for lname in label_names[: (i % 3)]:
                IssueLabel.objects.get_or_create(
                    id=_id(f"il-{issue.id}-{lname}"),
                    issue=issue,
                    label=labels[(p.id, lname)],
                    defaults={
                        "project": p,
                        "workspace": ws,
                        "created_at": now,
                        "updated_at": now,
                    },
                )

            # Module association: ~half into Core, ~quarter into Optional
            if i % 2 == 0:
                ModuleIssue.objects.get_or_create(
                    id=_id(f"mi-{issue.id}-Core"),
                    issue=issue,
                    module=modules[(p.id, "Core")],
                    defaults={
                        "project": p,
                        "workspace": ws,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            if i % 4 == 0:
                ModuleIssue.objects.get_or_create(
                    id=_id(f"mi-{issue.id}-Optional"),
                    issue=issue,
                    module=modules[(p.id, "Optional")],
                    defaults={
                        "project": p,
                        "workspace": ws,
                        "created_at": now,
                        "updated_at": now,
                    },
                )

            # Cycle assignment: Active cycle for index 0..half, Upcoming for the rest
            cycle_name = "Active Cycle" if i < per_project // 2 else "Upcoming Cycle"
            CycleIssue.objects.get_or_create(
                id=_id(f"ci-{issue.id}"),
                issue=issue,
                cycle=cycles[(p.id, cycle_name)],
                defaults={
                    "project": p,
                    "workspace": ws,
                    "created_at": now,
                    "updated_at": now,
                },
            )

    summary = {
        "scale": scale,
        "workspace_id": str(ws.id),
        "workspace_slug": ws.slug,
        "project_ids": [str(p.id) for p in projects],
        "issue_count": len(issues),
        "user_emails": [admin.email, member.email, guest.email],
    }

    if verbose:
        import json

        print(json.dumps(summary, indent=2))

    return summary


def _get_or_create_user(label: str, email: str, *, superuser: bool = False) -> User:
    user, _ = User.objects.get_or_create(
        id=_id(f"user-{label}"),
        defaults={
            "email": email,
            "username": f"phase-a-{label}",  # required unique CharField
            "first_name": label.capitalize(),
            "last_name": "PhaseA",
            "is_active": True,
            "is_superuser": superuser,
            "is_staff": superuser,
        },
    )
    return user


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Phase A deterministic seed.")
    parser.add_argument("--scale", type=int, choices=SUPPORTED_SCALES, default=DEFAULT_SCALE)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        seed(scale=args.scale, verbose=not args.quiet)
    except Exception as exc:  # noqa: BLE001
        print(f"seed failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
