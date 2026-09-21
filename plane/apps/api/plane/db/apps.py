# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _apply_sqlite_pragmas(sender, connection, **kwargs):
    """Apply WAL + concurrency PRAGMAs to every new SQLite connection.

    Django 4.2's sqlite3 backend does not support the `init_command` OPTIONS
    key (added in 5.1), so the PRAGMAs are applied via the
    ``connection_created`` signal instead. The handler runs once per new
    connection, which matches ``init_command`` semantics.
    """
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA foreign_keys=ON;")


def _install_sqlite_immediate_transactions() -> None:
    """Backport of Django 5.1's SQLite ``transaction_mode='IMMEDIATE'``.

    With the default ``BEGIN DEFERRED``, two concurrent ``transaction.atomic``
    blocks that both start with a SELECT and then INSERT will both hold
    shared locks, and whichever tries to upgrade first wins — the loser hits
    ``sqlite3.OperationalError: database is locked`` immediately. WAL +
    ``busy_timeout`` cannot recover from that specific deadlock because the
    upgrade failure isn't a wait-retry scenario.

    ``BEGIN IMMEDIATE`` serializes writers at transaction start, which
    converts the race into a plain wait that ``busy_timeout=5000`` absorbs.
    The patch is SQLite-only; other backends keep their native defaults.
    """
    from django.db.backends.sqlite3.base import DatabaseWrapper

    if getattr(DatabaseWrapper, "_plane_begin_immediate_installed", False):
        return

    def _start_transaction_under_autocommit(self):
        self.cursor().execute("BEGIN IMMEDIATE")

    DatabaseWrapper._start_transaction_under_autocommit = _start_transaction_under_autocommit
    DatabaseWrapper._plane_begin_immediate_installed = True


class DbConfig(AppConfig):
    name = "plane.db"

    def ready(self):
        connection_created.connect(_apply_sqlite_pragmas)
        _install_sqlite_immediate_transactions()
