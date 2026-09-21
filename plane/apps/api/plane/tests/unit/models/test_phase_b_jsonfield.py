# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase B — ArrayField -> JSONField round-trip tests.

Verifies each converted field survives a save + refresh_from_db cycle for
three cases:
  - empty list
  - single element
  - many elements

Fields covered (6 total):
  IssueActivity.attachments   (issue.py:413  URLField list)
  IssueComment.attachments    (issue.py:448  URLField list)
  IssueVersion.assignees      (issue.py:688  UUIDField list)
  IssueVersion.labels         (issue.py:690  UUIDField list)
  IssueVersion.modules        (issue.py:699  UUIDField list)
  ExporterHistory.project     (exporter.py:35  UUIDField list)

18 test cases total (6 fields x 3 cardinalities).
"""

from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from plane.db.models import (
    ExporterHistory,
    Issue,
    IssueActivity,
    IssueComment,
    IssueVersion,
    Project,
    State,
    User,
    Workspace,
)


# ---- fixtures ------------------------------------------------------------------
@pytest.fixture
def admin(db):
    return User.objects.create(
        email="phase-b-admin@test.local",
        first_name="Admin",
        is_superuser=True,
        is_staff=True,
    )


@pytest.fixture
def workspace(db, admin):
    return Workspace.objects.create(name="PB-WS", slug="pb-ws", owner=admin)


@pytest.fixture
def project(db, workspace, admin):
    return Project.objects.create(
        name="PB-P", identifier="PBP", workspace=workspace,
        created_by=admin, updated_by=admin,
    )


@pytest.fixture
def state(db, project, workspace):
    return State.objects.create(
        name="Backlog", group="backlog", slug="pbp-backlog", color="#888",
        sequence=10000, project=project, workspace=workspace,
    )


@pytest.fixture
def issue(db, project, workspace, admin, state):
    return Issue.objects.create(
        name="PB-1", workspace=workspace, project=project,
        state=state, created_by=admin, updated_by=admin,
    )


@pytest.fixture
def issue_comment(db, issue, project, workspace, admin):
    return IssueComment.objects.create(
        issue=issue, project=project, workspace=workspace, actor=admin,
        comment_stripped="hello",
    )


@pytest.fixture
def issue_activity(db, issue, project, workspace, admin):
    return IssueActivity.objects.create(
        issue=issue, project=project, workspace=workspace, actor=admin,
        verb="created",
    )


@pytest.fixture
def issue_version(db, issue, project, workspace, admin, state):
    # IssueVersion.state is a plain UUIDField (not FK), so pass state.id
    return IssueVersion.objects.create(
        issue=issue, project=project, workspace=workspace,
        owned_by=admin, state=state.id, name="PB-1",
    )


@pytest.fixture
def exporter_history(db, workspace, admin):
    return ExporterHistory.objects.create(
        workspace=workspace, type="issue_exports", provider="json",
        initiated_by=admin,
    )


# ---- helper assertions ---------------------------------------------------------
def _roundtrip(obj, field: str, value):
    setattr(obj, field, value)
    obj.save()
    obj.refresh_from_db()
    actual = getattr(obj, field)
    assert actual == value, f"{type(obj).__name__}.{field}: saved={value!r} got={actual!r}"


# ---- IssueActivity.attachments (URLField list) ---------------------------------
@pytest.mark.django_db
class TestIssueActivityAttachments:
    FIELD = "attachments"

    def test_empty(self, issue_activity):
        _roundtrip(issue_activity, self.FIELD, [])

    def test_single(self, issue_activity):
        _roundtrip(issue_activity, self.FIELD, ["https://cdn.example.com/a.png"])

    def test_many(self, issue_activity):
        _roundtrip(
            issue_activity, self.FIELD,
            [f"https://cdn.example.com/{i}.png" for i in range(10)],
        )


# ---- IssueComment.attachments (URLField list) ----------------------------------
@pytest.mark.django_db
class TestIssueCommentAttachments:
    FIELD = "attachments"

    def test_empty(self, issue_comment):
        _roundtrip(issue_comment, self.FIELD, [])

    def test_single(self, issue_comment):
        _roundtrip(issue_comment, self.FIELD, ["https://cdn.example.com/doc.pdf"])

    def test_many(self, issue_comment):
        _roundtrip(
            issue_comment, self.FIELD,
            [f"https://cdn.example.com/doc{i}.pdf" for i in range(7)],
        )


# ---- IssueVersion.assignees (UUID list) ---------------------------------------
@pytest.mark.django_db
class TestIssueVersionAssignees:
    FIELD = "assignees"

    def test_empty(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [])

    def test_single(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [str(uuid.uuid4())])

    def test_many(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [str(uuid.uuid4()) for _ in range(5)])


# ---- IssueVersion.labels (UUID list) -------------------------------------------
@pytest.mark.django_db
class TestIssueVersionLabels:
    FIELD = "labels"

    def test_empty(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [])

    def test_single(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [str(uuid.uuid4())])

    def test_many(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [str(uuid.uuid4()) for _ in range(5)])


# ---- IssueVersion.modules (UUID list) ------------------------------------------
@pytest.mark.django_db
class TestIssueVersionModules:
    FIELD = "modules"

    def test_empty(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [])

    def test_single(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [str(uuid.uuid4())])

    def test_many(self, issue_version):
        _roundtrip(issue_version, self.FIELD, [str(uuid.uuid4()) for _ in range(5)])


# ---- ExporterHistory.project (UUID list) ---------------------------------------
@pytest.mark.django_db
class TestExporterHistoryProject:
    FIELD = "project"

    def test_empty(self, exporter_history):
        _roundtrip(exporter_history, self.FIELD, [])

    def test_single(self, exporter_history):
        _roundtrip(exporter_history, self.FIELD, [str(uuid.uuid4())])

    def test_many(self, exporter_history):
        _roundtrip(
            exporter_history, self.FIELD,
            [str(uuid.uuid4()) for _ in range(4)],
        )


# ---- scan guards (no ArrayField leaks in models) -------------------------------
@pytest.mark.unit
def test_no_array_field_in_models_layer():
    """grep-equivalent check that ArrayField import/usage is gone from models."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[4] / "plane" / "db" / "models"
    # use pathlib to avoid shelling out on Windows — read files directly
    forbidden = ("ArrayField", "django.contrib.postgres.fields")
    hits = []
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden:
            if token in text:
                hits.append(f"{py.name}: {token}")
    assert not hits, "ArrayField leaked in models layer:\n" + "\n".join(hits)
