# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Test Settings"""

from .common import *  # noqa

DEBUG = True

# Send it in a dummy outbox
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

INSTALLED_APPS.append(  # noqa
    "plane.tests"
)

# Run Celery tasks synchronously in tests. Plane's request paths publish
# bg tasks (activity log, notifications) via kombu; without a running broker
# the HTTP handlers bubble up a 500. Eager mode routes them inline.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Local-only cache backend for tests. The production CACHES config in
# common.py points at Redis; several write-path views call
# `cache.keys("*...*")` + `cache.delete_many(...)` which is a django-redis
# extension unavailable on vanilla Django cache backends. Tests use a thin
# LocMemCache subclass that stubs out those extras as no-ops, so request
# handlers that rely on cache invalidation still return 2xx.
CACHES = {
    "default": {
        "BACKEND": "plane.tests.cache_compat.DjangoRedisShimLocMemCache",
        "LOCATION": "plane-test-cache",
    }
}
