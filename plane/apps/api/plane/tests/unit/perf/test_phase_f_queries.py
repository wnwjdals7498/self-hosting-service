# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Phase F §5 Step 3 — query-count ceiling for 6 core read endpoints.

Seeds an isolated test DB with scale=100 (100 issues across 2 projects) and
asserts each endpoint stays under the per-endpoint query budget defined in
phase-f-performance.md §2.2.

Coverage (one parametrize per row):
    issues_list            ≤ 20
    issues_list_filtered   ≤ 25  (?priority=high)
    cycles_list            ≤ 15
    modules_list           ≤ 15
    pages_list             ≤ 10
    search                 ≤ 15  (/search/?search=...)
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from plane.db.models import Project, User, Workspace
from plane.tests.golden_seed import seed


WORKSPACE_SLUG = "phase-a-ws"
ADMIN_EMAIL = "admin@phase-a.local"


@pytest.fixture(scope="session")
def phase_f_seed(django_db_setup, django_db_blocker):
    """Populate the pytest session DB with the scale=100 seed exactly once."""
    with django_db_blocker.unblock():
        seed(scale=100, verbose=False)
    return {
        "slug": WORKSPACE_SLUG,
        "admin_email": ADMIN_EMAIL,
    }


@pytest.fixture
def seeded_client(phase_f_seed, django_db_blocker):
    with django_db_blocker.unblock():
        admin = User.objects.get(email=phase_f_seed["admin_email"])
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def project_id(phase_f_seed, django_db_blocker):
    with django_db_blocker.unblock():
        ws = Workspace.objects.get(slug=phase_f_seed["slug"])
        pid = str(
            Project.objects.filter(workspace=ws).order_by("identifier").first().id
        )
    return pid


SCENARIOS = [
    # (name,                 url template,                                  query limit)
    ("issues_list",          "/api/workspaces/{slug}/projects/{pid}/issues/",                20),
    ("issues_list_filtered", "/api/workspaces/{slug}/projects/{pid}/issues/?priority=high",  25),
    ("cycles_list",          "/api/workspaces/{slug}/projects/{pid}/cycles/",                15),
    ("modules_list",         "/api/workspaces/{slug}/projects/{pid}/modules/",               15),
    ("pages_list",           "/api/workspaces/{slug}/projects/{pid}/pages/",                 10),
    ("search",               "/api/workspaces/{slug}/search/?search=Issue&workspace_search=true", 15),
]


@pytest.mark.django_db
@pytest.mark.parametrize("name,url_tpl,limit", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_query_count_under_limit(
    name: str,
    url_tpl: str,
    limit: int,
    seeded_client: APIClient,
    project_id: str,
    phase_f_seed: dict,
) -> None:
    url = url_tpl.format(slug=phase_f_seed["slug"], pid=project_id)
    with CaptureQueriesContext(connection) as ctx:
        resp = seeded_client.get(url)
    count = len(ctx.captured_queries)
    assert resp.status_code == 200, (
        f"{name} returned {resp.status_code}; body={resp.content[:300]!r}"
    )
    assert count <= limit, (
        f"{name}: {count} queries exceeds ceiling {limit}. "
        f"Top queries (first 3):\n"
        + "\n".join(
            f"  [{i}] {q['sql'][:200]}" for i, q in enumerate(ctx.captured_queries[:3])
        )
    )
