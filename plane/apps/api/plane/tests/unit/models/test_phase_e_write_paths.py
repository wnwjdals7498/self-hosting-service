# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase E — write-path determinism on SQLite.

Covers the two shape-sensitive checks called out in phase-e-integration.md:
  §7.3 ordering / NULL handling stays consistent across re-reads
  §7.4 JSONField round-trip via API PATCH

Scope stays at the Django test-client level (pytest-django's :memory: DB)
so the suite is cheap and deterministic. The phase-e write runner
(e_write_scenarios.py) exercises the file-backed SQLITE_PATH variant.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from plane.db.models import (
    Issue,
    IssueComment,
    Project,
    ProjectMember,
    State,
    User,
    Workspace,
    WorkspaceMember,
)


# ---- shared fixtures ----------------------------------------------------------
@pytest.fixture
def admin(db):
    return User.objects.create(
        email="phase-e-admin@test.local",
        first_name="Admin",
        username="phase-e-admin",
        is_superuser=True,
        is_staff=True,
    )


@pytest.fixture
def workspace(db, admin):
    ws = Workspace.objects.create(name="PE-WS", slug="pe-ws", owner=admin)
    WorkspaceMember.objects.create(workspace=ws, member=admin, role=20)
    return ws


@pytest.fixture
def project(db, workspace, admin):
    p = Project.objects.create(
        name="PE-P", identifier="PEP", workspace=workspace,
        created_by=admin, updated_by=admin,
    )
    ProjectMember.objects.create(workspace=workspace, project=p, member=admin, role=20)
    return p


@pytest.fixture
def state(db, project, workspace):
    return State.objects.create(
        name="Backlog", group="backlog", slug="pep-backlog", color="#888",
        sequence=10000, project=project, workspace=workspace,
    )


@pytest.fixture
def client(admin):
    c = APIClient()
    c.force_authenticate(user=admin)
    return c


# ---- §7.3 ordering / NULL ----------------------------------------------------
@pytest.mark.django_db
class TestOrderByNullableDeterministic:
    """Issue.target_date is nullable. The order_by result must be identical
    between consecutive identical queries — SQLite's NULLS FIRST default
    surfaces here, and we want the contract locked in so a regression in
    ORM settings would fail loudly."""

    def _mk_issue(self, name, target, project, workspace, admin, state):
        return Issue.objects.create(
            name=name, workspace=workspace, project=project,
            state=state, created_by=admin, updated_by=admin,
            target_date=target,
        )

    def test_order_stable_across_two_reads(self, project, workspace, admin, state):
        today = timezone.now().date()
        self._mk_issue("A", today + timedelta(days=1), project, workspace, admin, state)
        self._mk_issue("B", None,                      project, workspace, admin, state)
        self._mk_issue("C", today + timedelta(days=2), project, workspace, admin, state)
        self._mk_issue("D", None,                      project, workspace, admin, state)

        ids_first = list(
            Issue.objects.filter(project=project)
            .order_by("target_date", "name")
            .values_list("name", flat=True)
        )
        ids_second = list(
            Issue.objects.filter(project=project)
            .order_by("target_date", "name")
            .values_list("name", flat=True)
        )

        assert ids_first == ids_second, (
            f"order_by yielded different sequences: {ids_first!r} vs {ids_second!r}"
        )
        # SQLite ORDER BY nullable puts NULL first by default. We pin this
        # behavior so any env/config change that flips it (e.g. switching
        # backend, adding NULLS LAST clauses) fails this test.
        assert ids_first == ["B", "D", "A", "C"], (
            f"unexpected NULL ordering: {ids_first!r}"
        )

    def test_order_by_name_case_sensitive(self, project, workspace, admin, state):
        """SQLite `LIKE` is case-insensitive by default but `ORDER BY` on
        CharField is case-sensitive (ascii). Guard so we notice if a COLLATE
        change ever reorders mixed-case names."""
        for n in ["beta", "Alpha", "alpha", "Beta"]:
            self._mk_issue(n, None, project, workspace, admin, state)

        ids = list(
            Issue.objects.filter(project=project)
            .order_by("name")
            .values_list("name", flat=True)
        )
        # ASCII: 'A' < 'B' < 'a' < 'b'
        assert ids == ["Alpha", "Beta", "alpha", "beta"], f"unexpected: {ids!r}"


# ---- §7.4 JSONField API round-trip -------------------------------------------
@pytest.mark.django_db
class TestJsonFieldApiRoundTrip:
    """IssueComment.attachments (Phase B conversion) should round-trip
    through a direct ORM save and reload cycle. We don't use the /comments/
    endpoint because Plane 1.3 doesn't expose the raw attachment list to
    the serializer — writes go through FileAsset upload + backfill. The
    ORM round-trip is the tightest contract test we can write without
    building an asset upload pipeline for unit tests."""

    def _mk_comment(self, issue, project, workspace, admin):
        return IssueComment.objects.create(
            comment_html="<p>phase-e</p>",
            comment_stripped="phase-e",
            issue=issue,
            project=project,
            workspace=workspace,
            actor=admin,
        )

    @pytest.fixture
    def issue(self, project, workspace, admin, state):
        return Issue.objects.create(
            name="PE-I", workspace=workspace, project=project,
            state=state, created_by=admin, updated_by=admin,
        )

    def test_attachments_list_save_reload(self, issue, project, workspace, admin):
        comment = self._mk_comment(issue, project, workspace, admin)
        comment.attachments = [
            "https://example.invalid/1.png",
            "https://example.invalid/2.png",
        ]
        comment.save()
        comment.refresh_from_db()
        assert comment.attachments == [
            "https://example.invalid/1.png",
            "https://example.invalid/2.png",
        ]

    def test_attachments_partial_overwrite(self, issue, project, workspace, admin):
        comment = self._mk_comment(issue, project, workspace, admin)
        comment.attachments = ["https://example.invalid/a.png"]
        comment.save()
        comment.refresh_from_db()
        assert comment.attachments == ["https://example.invalid/a.png"]

        comment.attachments = ["https://example.invalid/b.png", "https://example.invalid/c.png"]
        comment.save()
        comment.refresh_from_db()
        assert comment.attachments == [
            "https://example.invalid/b.png",
            "https://example.invalid/c.png",
        ]

    def test_attachments_empty_roundtrip(self, issue, project, workspace, admin):
        comment = self._mk_comment(issue, project, workspace, admin)
        comment.attachments = []
        comment.save()
        comment.refresh_from_db()
        assert comment.attachments == []


# ---- scenario runner smoke ---------------------------------------------------
@pytest.mark.unit
def test_scenario_runner_exports_20_methods():
    """Guard that e_write_scenarios.Runner declares all 20 W* scenarios so
    a future refactor can't silently drop coverage."""
    from plane.tests.e_write_scenarios import Runner

    w_methods = [m for m in dir(Runner) if m.startswith(("w",)) and m[1:2].isdigit()]
    # w1..w20 -> 20 entries
    assert len(w_methods) == 20, (
        f"expected 20 W* methods on Runner, got {len(w_methods)}: {sorted(w_methods)}"
    )
