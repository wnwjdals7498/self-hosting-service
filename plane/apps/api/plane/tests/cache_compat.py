# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Test-only cache backend: LocMemCache + django-redis extras stubbed.

Plane's cache invalidation helpers call django-redis-specific methods like
``cache.keys("*pattern*")`` and ``cache.delete_pattern(...)``. Those do not
exist on Django's built-in LocMemCache, which causes a 500 on write-path
handlers under settings/test.py when Redis isn't running.

This subclass forwards every real call to ``LocMemCache`` and stubs the
django-redis extras as no-ops, so tests exercise the full view logic
without requiring a broker.
"""

from __future__ import annotations

from django.core.cache.backends.locmem import LocMemCache


class DjangoRedisShimLocMemCache(LocMemCache):
    """LocMemCache with enough django-redis compatibility for tests."""

    def keys(self, search: str = "*", *args, **kwargs):  # noqa: D401
        """Return an empty list; LocMemCache has no cross-process keyspace."""
        return []

    def delete_pattern(self, pattern: str, *args, **kwargs) -> int:  # noqa: D401
        """No-op pattern delete; returns zero keys removed."""
        return 0

    def ttl(self, key: str, *args, **kwargs):  # noqa: D401
        """LocMemCache has no TTL introspection API; return None."""
        return None
