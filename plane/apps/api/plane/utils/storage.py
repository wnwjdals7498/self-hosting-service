# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Storage backend factory and helpers.

Phase 4.2 (deploy): centralizes runtime selection between the upstream
``S3Storage`` and the Windows-native ``LocalFSStorage`` so that view
call sites don't repeat the import guard or hard-code one backend.

The factory respects ``settings.USE_LOCAL_STORAGE`` and forwards the
optional ``request`` so MinIO endpoint derivation keeps working on the
upstream path (where the endpoint URL depends on the incoming Host).

Phase 4.3 adds ``presigned_url`` so bgtask call sites (which run without
a request) can produce download URLs without importing a specific
adapter — ``default_storage`` already resolves to the configured backend
via ``STORAGES["default"]["BACKEND"]``.
"""

from django.conf import settings
from django.core.files.storage import default_storage


def get_storage(request=None):
    """Return a freshly instantiated storage adapter matching the env flag.

    Each call produces a new instance — matching the pre-Phase-4.2 pattern
    where view code created ``S3Storage(request=request)`` per request.
    Backend parity is deliberate: ``S3Storage`` is not a singleton because
    it captures request-dependent state (MinIO host) at construction.
    """
    if getattr(settings, "USE_LOCAL_STORAGE", False):
        from plane.settings.local_storage import LocalFSStorage

        return LocalFSStorage(request=request)
    from plane.settings.storage import S3Storage

    return S3Storage(request=request)


def presigned_url(object_name, expiration=3600, disposition="attachment", filename=None):
    """Return a time-limited download URL for ``object_name``.

    Both ``S3Storage`` and ``LocalFSStorage`` implement
    ``generate_presigned_url`` with the same signature, so the helper
    delegates directly. The ``hasattr`` guard keeps the helper safe if a
    future deployment swaps ``default_storage`` for a stock
    ``FileSystemStorage`` (no signing) — in that case we fall back to the
    raw URL, which the download view can still resolve.
    """
    if hasattr(default_storage, "generate_presigned_url"):
        return default_storage.generate_presigned_url(
            object_name=object_name,
            expiration=expiration,
            disposition=disposition,
            filename=filename,
        )
    return default_storage.url(object_name)
