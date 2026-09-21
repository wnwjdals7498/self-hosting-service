# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""HMAC-authenticated upload/download endpoints for LocalFSStorage.

Phase 4.1 (deploy): the frontend, MCP server, and bgtasks all call
``storage.generate_presigned_post`` or ``generate_presigned_url`` on
LocalFSStorage; the URLs those helpers return point here. These views
re-verify the HMAC signatures against the policy fields or query
parameters before writing or serving bytes, so they intentionally use
``AllowAny`` — the signature itself is the authentication primitive, not
the session cookie. That matches the S3 presigned-POST/GET model.
"""

# Python imports
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import quote

# Django imports
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse

# Third party imports
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

# Module imports
from plane.settings.local_storage import ALG, CRED, _sign


def _decode_policy(fields):
    """Verify the POST policy signature and decode the JSON.

    Returns ``(policy_dict, None)`` on success or ``(None, error_msg)``.
    ``hmac.compare_digest`` guards against timing-leak attacks on the
    signature field.
    """
    policy_b64 = fields.get("policy", "")
    sig = fields.get("x-amz-signature", "")
    if fields.get("x-amz-algorithm") != ALG or fields.get("x-amz-credential") != CRED:
        return None, "algorithm/credential mismatch"
    if not policy_b64 or not sig:
        return None, "missing policy or signature"
    if not hmac.compare_digest(_sign(policy_b64), sig):
        return None, "signature mismatch"
    try:
        pad = "=" * (-len(policy_b64) % 4)
        raw = base64.urlsafe_b64decode(policy_b64 + pad).decode("utf-8")
        policy = json.loads(raw)
    except Exception:
        return None, "policy decode error"
    try:
        expires = datetime.strptime(policy["expiration"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        return None, "policy missing expiration"
    if datetime.now(tz=timezone.utc) > expires:
        return None, "expired"
    return policy, None


def _policy_condition(policy, name):
    """Return the value associated with ``name`` in the policy conditions."""
    for condition in policy.get("conditions", []):
        if isinstance(condition, dict) and name in condition:
            return condition[name]
    return None


def _size_range(policy):
    """Extract the ``content-length-range`` bounds from the policy, if any."""
    for condition in policy.get("conditions", []):
        if isinstance(condition, list) and condition and condition[0] == "content-length-range":
            return int(condition[1]), int(condition[2])
    return None


def _is_safe_key(key: str) -> bool:
    """Reject traversal-prone or Windows-specific escape attempts.

    ``..`` segment, absolute path, UNC (``\\\\host\\share``), or drive
    letter (``C:``) all indicate callers trying to escape MEDIA_ROOT.
    """
    if not key:
        return False
    if ".." in key:
        return False
    if key.startswith("/") or key.startswith("\\"):
        return False
    if "\\" in key or ":" in key:
        return False
    return True


class LocalUploadView(APIView):
    """Receive a multipart POST whose fields match a LocalFSStorage policy.

    The signature is the sole credential — see the module docstring for
    the rationale behind ``AllowAny``.
    """

    # HMAC signature is the sole credential. Clearing authentication_classes
    # removes DRF's default SessionAuthentication, which would otherwise
    # enforce CSRF on POST for any request that carries a logged-in session
    # cookie — an unavoidable side-effect when the browser is already
    # authenticated against the main app on the same origin.
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        policy, err = _decode_policy(request.data)
        if err:
            return HttpResponse(err, status=403)

        key = request.data.get("key") or ""
        if key != _policy_condition(policy, "key"):
            return HttpResponse("key mismatch", status=400)
        if not _is_safe_key(key):
            return HttpResponse("invalid key", status=400)

        file_obj = request.FILES.get("file")
        if not file_obj:
            return HttpResponse("missing file", status=400)

        size_range = _size_range(policy)
        if size_range and not (size_range[0] <= file_obj.size <= size_range[1]):
            return HttpResponse("size out of range", status=400)

        expected_ct = _policy_condition(policy, "Content-Type")
        if expected_ct and request.data.get("Content-Type") != expected_ct:
            return HttpResponse("content-type mismatch", status=400)

        default_storage.save(key, file_obj)
        # S3's presigned POST responds 204 No Content on success. The
        # frontend helper does not read a body, only the status code.
        return HttpResponse(status=204)


class LocalDownloadView(APIView):
    """Stream a locally stored file after verifying a signed query string.

    The signature payload — ``{key}|{expires}|{disposition}|{filename}`` —
    matches ``LocalFSStorage.generate_presigned_url``. Any drift between
    those two implementations breaks every signed link, so keep them in
    sync.
    """

    # Mirror LocalUploadView: HMAC-signed URL is the sole credential; skip
    # SessionAuthentication so logged-in anchors don't accidentally bind
    # download audit trails to the browser session.
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, path):
        expires = int(request.GET.get("expires", "0") or 0)
        disposition = request.GET.get("disposition", "inline")
        filename = request.GET.get("filename", "")
        sig = request.GET.get("signature", "")
        payload = f"{path}|{expires}|{disposition}|{filename}"
        key = (getattr(settings, "STORAGE_SIGNING_KEY", None) or settings.SECRET_KEY).encode("utf-8")
        expected = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

        if not sig or not hmac.compare_digest(expected, sig):
            return HttpResponse("signature mismatch", status=403)
        if expires < int(datetime.now(tz=timezone.utc).timestamp()):
            return HttpResponse("expired", status=410)
        if not _is_safe_key(path):
            return HttpResponse("invalid path", status=400)
        if not default_storage.exists(path):
            return HttpResponse("not found", status=404)

        fh = default_storage.open(path, "rb")
        response = FileResponse(fh, content_type="application/octet-stream")
        fname = filename or path.rsplit("/", 1)[-1]
        # RFC 5987 UTF-8 filename parameter.
        response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(fname)}"
        return response
