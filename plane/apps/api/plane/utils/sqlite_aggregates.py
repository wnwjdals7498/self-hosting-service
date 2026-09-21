# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""SQLite-friendly aggregate and helper expressions.

These replace Postgres-only aggregates from ``django.contrib.postgres`` that
Plane's view layer used to depend on. They are deliberately named and scoped
narrowly so the rest of the codebase can do a one-line import swap:

    from django.contrib.postgres.aggregates import ArrayAgg   # before
    from plane.utils.sqlite_aggregates import JsonGroupArray  # after

The output is a JSONField-wrapped value, which Django deserialises to a Python
list on read. This matches the downstream contract: serializers and
``.values(...)`` consumers already expected list-typed values for
``assignee_ids`` / ``label_ids`` / ``module_ids``.
"""

from __future__ import annotations

from django.db.models import Aggregate, JSONField, Value


class JsonGroupArray(Aggregate):
    """SQLite ``json_group_array`` wrapper.

    Produces a JSON array of the aggregated column. The SQL function is
    available in every SQLite build that ships with Python's standard
    ``sqlite3`` module (>= 3.38 / built-in JSON1).
    """

    function = "JSON_GROUP_ARRAY"
    name = "JsonGroupArray"
    output_field = JSONField()
    allow_distinct = False  # json_group_array has no DISTINCT form
    template = "%(function)s(%(expressions)s)"


class JsonGroupUuidArray(Aggregate):
    """UUID-aware variant of ``JsonGroupArray``.

    Django stores ``UUIDField`` on SQLite as CHAR(32) — a 32-char hex string
    without dashes. ``JSON_GROUP_ARRAY`` therefore returns raw hex, breaking
    the API contract (consumers expect the canonical ``8-4-4-4-12`` format).

    This aggregate wraps each hex value in ``SUBSTR || '-' || SUBSTR …`` before
    handing it to ``json_group_array``, so the emitted JSON array contains
    properly dashed UUID strings that match what PostgreSQL's ``ArrayAgg``
    produced pre-migration.
    """

    function = "JSON_GROUP_ARRAY"
    name = "JsonGroupUuidArray"
    output_field = JSONField()
    allow_distinct = False
    template = (
        "JSON_GROUP_ARRAY("
        "SUBSTR(%(expressions)s, 1, 8) || '-' || "
        "SUBSTR(%(expressions)s, 9, 4) || '-' || "
        "SUBSTR(%(expressions)s, 13, 4) || '-' || "
        "SUBSTR(%(expressions)s, 17, 4) || '-' || "
        "SUBSTR(%(expressions)s, 21, 12)"
        ")"
    )


def empty_json_array() -> Value:
    """Return an empty JSON array literal suitable for ``Coalesce`` fallback."""
    return Value([], output_field=JSONField())
