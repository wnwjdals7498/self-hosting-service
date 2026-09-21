# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from datetime import timedelta

# Django imports
from django.core.files.storage import default_storage
from django.utils import timezone
from django.db.models import Q

# Third party imports
from celery import shared_task

# Module imports
from plane.db.models import ExporterHistory


@shared_task
def delete_old_s3_link():
    """Purge export artifacts older than 8 days from the configured backend.

    Phase 4.3: boto3 was replaced with ``default_storage.delete`` so the
    same code path works for S3, MinIO, and the local filesystem adapter.
    The task name keeps its ``s3`` suffix because Celery beat references
    it by fully-qualified path (``plane.celery:delete_old_s3_link``) and
    renaming would drop stale beat entries on upgrade.
    """
    expired_exporter_history = ExporterHistory.objects.filter(
        Q(url__isnull=False) & Q(created_at__lte=timezone.now() - timedelta(days=8))
    ).values_list("key", "id")

    for file_name, exporter_id in expired_exporter_history:
        if file_name:
            default_storage.delete(file_name)

        ExporterHistory.objects.filter(id=exporter_id).update(url=None)
