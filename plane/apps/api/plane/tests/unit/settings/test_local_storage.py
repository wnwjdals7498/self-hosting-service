# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Unit tests for ``plane.settings.local_storage.LocalFSStorage``.

Phase 4.1 (deploy) — validate the drop-in contract that lets S3Storage
callers keep working unchanged when the deployment flips
``USE_LOCAL_STORAGE=1``.

The tests exercise the adapter without spinning up any HTTP server: the
views that consume the presigned URLs have their own integration layer,
and the adapter itself is a pure-Python object that can be asserted
against a pytest ``tmp_path``.
"""

import pytest
from django.test import override_settings

from plane.settings.local_storage import ALG, CRED, LocalFSStorage, _sign


@pytest.fixture
def storage(tmp_path):
    """LocalFSStorage rooted in a pytest tmp_path with fixed test keys.

    ``override_settings`` wraps the ``yield`` so every test gets the same
    deterministic MEDIA_ROOT / STORAGE_SIGNING_KEY / WEB_URL, and the
    original Django settings are restored on teardown without leaking
    between tests.
    """
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        MEDIA_URL="/uploads/",
        STORAGE_SIGNING_KEY="test-key",
        SECRET_KEY="fallback-key",
        WEB_URL="http://localhost:8000",
    ):
        yield LocalFSStorage()


@pytest.mark.unit
class TestLocalFSStoragePresignedPost:
    """Presigned POST must keep S3's field names for frontend parity."""

    def test_fields_shape(self, storage):
        """Every expected x-amz-* field is present and labelled correctly."""
        response = storage.generate_presigned_post("ws/abc-image.png", "image/png", 1000)

        assert response["url"].endswith("/api/assets/local-upload/")
        assert set(response["fields"].keys()) == {
            "Content-Type",
            "key",
            "x-amz-algorithm",
            "x-amz-credential",
            "x-amz-date",
            "policy",
            "x-amz-signature",
        }
        assert response["fields"]["x-amz-algorithm"] == ALG
        assert response["fields"]["x-amz-credential"] == CRED
        assert response["fields"]["Content-Type"] == "image/png"
        assert response["fields"]["key"] == "ws/abc-image.png"

    def test_signature_verifies(self, storage):
        """The HMAC returned in ``x-amz-signature`` matches ``_sign(policy)``."""
        response = storage.generate_presigned_post("ws/x.png", "image/png", 1000)
        assert _sign(response["fields"]["policy"]) == response["fields"]["x-amz-signature"]


@pytest.mark.unit
class TestLocalFSStoragePresignedUrl:
    """Presigned GET URL carries the four query parameters the view needs."""

    def test_contains_required_query_params(self, storage):
        url = storage.generate_presigned_url("ws/x.png", expiration=3600)

        assert url.startswith("http://localhost:8000/api/assets/local-download/")
        for param in ("signature=", "expires=", "disposition=", "filename="):
            assert param in url


@pytest.mark.unit
class TestLocalFSStorageFileOps:
    """File-system parity with the ``S3Storage.copy_object`` / ``delete_files`` behaviour."""

    def test_delete_files_removes_existing(self, storage, tmp_path):
        (tmp_path / "a.txt").write_text("hi")
        assert storage.delete_files(["a.txt"]) is True
        assert not (tmp_path / "a.txt").exists()

    def test_copy_object_duplicates_bytes(self, storage, tmp_path):
        (tmp_path / "src.txt").write_text("x" * 17)
        storage.copy_object("src.txt", "dst.txt")
        assert (tmp_path / "dst.txt").read_text() == "x" * 17
