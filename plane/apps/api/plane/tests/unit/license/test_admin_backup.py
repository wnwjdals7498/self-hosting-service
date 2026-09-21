# fork-custom: unit tests for AdminBackupView (plane-mcp-v2-deploy, 2026-04-24)
"""Tests for ``plane.license.api.views.admin.AdminBackupView``.

``subprocess.run`` is always mocked — the real ``Start-ScheduledTask``
invocation is verified manually during operational smoke (todo #4).
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from plane.license.models import Instance, InstanceAdmin


@pytest.fixture
def instance(db):
    return Instance.objects.create(
        instance_name="test",
        instance_id="test-instance",
        last_checked_at=timezone.now(),
    )


@pytest.fixture
def instance_admin(db, create_user, instance):
    return InstanceAdmin.objects.create(
        instance=instance,
        user=create_user,
        role=20,  # >= 15 required by InstanceAdminPermission
    )


def _fake_run(returncode: int = 0, stderr: str = "", raise_exc=None):
    """Build a ``subprocess.run`` replacement that records its call and
    either raises ``raise_exc`` or returns a ``CompletedProcess`` stub."""

    def inner(*args, **kwargs):
        inner.call_args = (args, kwargs)
        if raise_exc is not None:
            raise raise_exc
        return subprocess.CompletedProcess(
            args=args[0] if args else kwargs.get("args"),
            returncode=returncode,
            stdout="",
            stderr=stderr,
        )

    inner.call_args = None
    return inner


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_backup_success(session_client, create_user, instance_admin):
    fake = _fake_run(returncode=0)
    with patch("plane.license.api.views.admin.subprocess.run", new=fake):
        response = session_client.post(reverse("instance-admin-backup"))

    assert response.status_code == 200
    body = response.json()
    assert body["task_name"] == "PlaneBackup"
    assert body["pid"] is None
    assert "started_at" in body
    # subprocess invoked with the exact powershell command
    invoked_cmd = fake.call_args[0][0]
    assert invoked_cmd[0] == "powershell.exe"
    assert "Start-ScheduledTask" in invoked_cmd[-1]


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_backup_non_admin_forbidden(session_client, create_user, instance):
    # no InstanceAdmin row for create_user → InstanceAdminPermission denies
    fake = _fake_run(returncode=0)
    with patch("plane.license.api.views.admin.subprocess.run", new=fake):
        response = session_client.post(reverse("instance-admin-backup"))

    assert response.status_code == 403
    # subprocess must NOT have run if permission denied
    assert fake.call_args is None


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_backup_unauthenticated_rejected(api_client, instance):
    fake = _fake_run(returncode=0)
    with patch("plane.license.api.views.admin.subprocess.run", new=fake):
        response = api_client.post(reverse("instance-admin-backup"))

    assert response.status_code in (401, 403)
    assert fake.call_args is None


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_backup_subprocess_error(session_client, create_user, instance_admin):
    fake = _fake_run(returncode=1, stderr="Access denied\nextra line")
    with patch("plane.license.api.views.admin.subprocess.run", new=fake):
        response = session_client.post(reverse("instance-admin-backup"))

    assert response.status_code == 500
    assert "Access denied" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_backup_timeout(session_client, create_user, instance_admin):
    fake = _fake_run(raise_exc=subprocess.TimeoutExpired(cmd="ps", timeout=10))
    with patch("plane.license.api.views.admin.subprocess.run", new=fake):
        response = session_client.post(reverse("instance-admin-backup"))

    assert response.status_code == 500
    assert "timed out" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_backup_powershell_missing(session_client, create_user, instance_admin):
    fake = _fake_run(raise_exc=FileNotFoundError("no powershell"))
    with patch("plane.license.api.views.admin.subprocess.run", new=fake):
        response = session_client.post(reverse("instance-admin-backup"))

    assert response.status_code == 500
    assert "powershell.exe" in response.json()["detail"]
