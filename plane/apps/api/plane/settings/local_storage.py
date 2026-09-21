# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Local-filesystem storage adapter compatible with S3Storage's public API.

Phase 4.1 (deploy): replaces S3/MinIO for Windows-native 1-user deployments.
The adapter preserves the presigned-POST contract so that the 20+ existing
call sites in ``plane.app.views.asset``, ``plane.api.views``,
``plane.space.views``, and ``plane.bgtasks`` continue to work unchanged —
``generate_presigned_post`` returns a dict with ``url`` + ``fields`` that
the frontend passes to a self-hosted upload endpoint (see
``plane.app.views.asset.local``). Signature validation uses HMAC-SHA256
over a base64url-encoded policy document, mirroring the AWS SigV4 POST
flow in shape but replacing the crypto with a local keyed MAC.
"""

# Python imports
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

# Django imports
from django.conf import settings
from django.core.files.storage import FileSystemStorage


# Algorithm identifier emitted in the presigned-POST fields. The prefix
# "HMAC-SHA256-PLANE" distinguishes the local scheme from AWS's
# "AWS4-HMAC-SHA256" while occupying the same field name that the frontend
# already treats as opaque string data.
ALG = "HMAC-SHA256-PLANE"
CRED = "plane-local"


def _signing_key() -> bytes:
    """Return the HMAC key as bytes.

    Prefers ``STORAGE_SIGNING_KEY`` so that rotating ``SECRET_KEY`` (used
    for sessions/CSRF) does not invalidate every signed upload/download
    URL in flight.
    """
    key = getattr(settings, "STORAGE_SIGNING_KEY", None) or settings.SECRET_KEY
    return key.encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(policy_b64: str) -> str:
    return hmac.new(_signing_key(), policy_b64.encode("ascii"), hashlib.sha256).hexdigest()


class LocalFSStorage(FileSystemStorage):
    """Drop-in replacement for ``plane.settings.storage.S3Storage``.

    Public surface mirrors ``S3Storage`` so callers do not need to change:
    same method names, same return shapes. Instead of pointing to
    AWS/MinIO, the returned URLs resolve to
    ``/api/assets/local-{upload,download}/`` on this server, authenticated
    by an HMAC-signed policy document.
    """

    def __init__(self, request=None, **kwargs):
        kwargs.setdefault("location", settings.MEDIA_ROOT)
        kwargs.setdefault("base_url", settings.MEDIA_URL)
        super().__init__(**kwargs)
        self.request = request
        self.signed_url_expiration = int(os.environ.get("SIGNED_URL_EXPIRATION", "3600"))

    # ---- S3Storage API parity ----

    def url(self, name, parameters=None, expire=None, http_method=None):
        # Match S3Storage.url which returns the object key verbatim so that
        # ``FileAsset.asset.url`` callers receive the raw path. Actual
        # fetches go through ``generate_presigned_url`` → local-download.
        return name

    def generate_presigned_post(self, object_name, file_type, file_size, expiration=None):
        """Build a self-hosted presigned-POST payload.

        Returns ``{"url": ..., "fields": {...}}`` with the same shape that
        S3's ``generate_presigned_post`` returns. The frontend helper in
        ``packages/services/src/file/helper.ts`` iterates over ``fields``
        and appends each to a ``FormData``, so preserving field names
        (``x-amz-*``) is critical for zero-touch frontend compatibility.
        """
        expiration = expiration or self.signed_url_expiration
        issued = datetime.now(tz=timezone.utc)
        expires = issued + timedelta(seconds=expiration)

        policy = {
            "expiration": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "conditions": [
                {"bucket": "local"},
                {"key": object_name},
                {"Content-Type": file_type},
                ["content-length-range", 1, int(file_size)],
            ],
        }
        policy_b64 = _b64url(json.dumps(policy, separators=(",", ":")).encode("utf-8"))
        signature = _sign(policy_b64)

        return {
            # Trailing slash matches the Django URL pattern
            # (``assets/local-upload/``). Without it, APPEND_SLASH=True
            # issues a 301 that browsers convert from POST to GET, which
            # then hits LocalUploadView as an unallowed method (405).
            "url": self._endpoint("local-upload") + "/",
            "fields": {
                "Content-Type": file_type,
                "key": object_name,
                "x-amz-algorithm": ALG,
                "x-amz-credential": CRED,
                "x-amz-date": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "policy": policy_b64,
                "x-amz-signature": signature,
            },
        }

    def generate_presigned_url(
        self,
        object_name,
        expiration=None,
        http_method="GET",
        disposition="inline",
        filename=None,
    ):
        """Build a time-limited, HMAC-signed download URL.

        S3's presigned GET uses SigV4 over a canonical request; the local
        scheme substitutes a simpler payload
        ``key|expires|disposition|filename``. The download view recomputes
        the MAC with the same payload order and rejects mismatches or
        expired timestamps.
        """
        expiration = expiration or self.signed_url_expiration
        expires_at = int((datetime.now(tz=timezone.utc) + timedelta(seconds=expiration)).timestamp())
        payload = f"{object_name}|{expires_at}|{disposition}|{filename or ''}"
        sig = hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()

        qs = urlencode(
            {
                "expires": expires_at,
                "disposition": disposition,
                "filename": filename or "",
                "signature": sig,
            }
        )
        return f"{self._endpoint('local-download')}/{quote(object_name)}?{qs}"

    def get_object_metadata(self, object_name):
        if not self.exists(object_name):
            return None
        path = self.path(object_name)
        stat = os.stat(path)
        return {
            # ContentType is not stored on the local filesystem; callers
            # that need it read ``FileAsset.attributes["type"]`` instead.
            "ContentType": None,
            "ContentLength": stat.st_size,
            "LastModified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "ETag": None,
            "Metadata": {},
        }

    def copy_object(self, object_name, new_object_name):
        with self.open(object_name, "rb") as src:
            self.save(new_object_name, src)
        return {"CopyObjectResult": {"ETag": None}}

    def delete_files(self, object_names):
        for name in object_names:
            if self.exists(name):
                self.delete(name)
        return True

    def upload_file(self, file_obj, object_name, content_type=None, extra_args=None):
        # ``content_type`` / ``extra_args`` are accepted for signature
        # parity with ``S3Storage`` but not stored on the local filesystem.
        self.save(object_name, file_obj)
        return True

    # ---- helpers ----

    def _endpoint(self, which):
        base = (getattr(settings, "WEB_URL", None) or "").rstrip("/")
        return f"{base}/api/assets/{which}"
