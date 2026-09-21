# Phase 4.1 — 스토리지 어댑터 + upload/download endpoint

> **네비게이션**: [Phase 4 목차](../05-storage.md) · [다음: 4.2 views →](02-views.md)

**목표**: `S3Storage` 를 교체할 `LocalFSStorage` 어댑터를 만들고, HMAC 서명 기반 업로드/다운로드 endpoint 를 신설한다. 이 서브가 끝나면 `storage.generate_presigned_post/url` 을 호출하는 20+ 곳이 **코드 변경 없이** 로컬 FS 를 사용한다.

**수정/신규 파일**:
- 신규 `apps/api/plane/settings/local_storage.py` — `LocalFSStorage`
- 수정 `apps/api/plane/settings/common.py` — `USE_LOCAL_STORAGE` 분기, `MEDIA_*`
- 신규 `apps/api/plane/app/views/asset/local.py` — upload/download view
- 수정 `apps/api/plane/app/urls/asset.py` (또는 인접) — `/api/assets/local-{upload,download}/` 라우트 2개
- 신규 `apps/api/plane/tests/unit/settings/test_local_storage.py`

---

## 1. HMAC 서명 설계

### 1.1 입력 필드

`generate_presigned_post` 가 만드는 `fields` 는 프론트가 FormData 에 펼쳐 POST. 서버는 이 값을 재검증.

| 필드 | 값 | 검증 |
|---|---|---|
| `Content-Type` | 요청 시 지정된 mime | POST 시 파일의 실 mime 과 일치 |
| `key` | `<workspace_id>/<uuid>-<filename>` (asset.py `get_upload_path`) | path traversal 거부 (`..`, 절대경로) |
| `x-amz-algorithm` | `"HMAC-SHA256-PLANE"` | 고정 — 버전 불일치 거부 |
| `x-amz-credential` | `"plane-local"` | 고정 — 추후 다중 키 로테이션 여지 |
| `x-amz-date` | ISO-8601 발급 시각 (`2026-04-19T10:00:00Z`) | 시간 차 ±5분 허용 |
| `policy` | base64url(JSON) — §1.2 | 그대로 HMAC 입력 |
| `x-amz-signature` | `hmac_sha256(STORAGE_SIGNING_KEY, policy)` → hex | 서버 재계산과 일치 |

### 1.2 policy document (base64url JSON)

```json
{
  "expiration": "2026-04-19T11:00:00Z",
  "conditions": [
    {"bucket": "local"},
    {"key": "workspace-uuid/uuid-filename.png"},
    {"Content-Type": "image/png"},
    ["content-length-range", 1, 5242880]
  ]
}
```

→ 서명 검증만으로 key / Content-Type / size 범위 모두 확정. fields 위변조 시 서명 불일치.

### 1.3 서명 키

```ini
STORAGE_SIGNING_KEY=<32자 랜덤>  # site.env 에서 주입
```

`common.py`:
```python
STORAGE_SIGNING_KEY = os.environ.get("STORAGE_SIGNING_KEY") or SECRET_KEY
```

`SECRET_KEY` 회전 시 저장소 서명과 독립되도록 기본값을 별도 키로. `SECRET_KEY` fallback 은 개발 편의.

---

## 2. `LocalFSStorage` 클래스

`apps/api/plane/settings/local_storage.py`:

```python
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.files.storage import FileSystemStorage


ALG = "HMAC-SHA256-PLANE"
CRED = "plane-local"


def _signing_key() -> bytes:
    return (settings.STORAGE_SIGNING_KEY or settings.SECRET_KEY).encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(policy_b64: str) -> str:
    return hmac.new(_signing_key(), policy_b64.encode("ascii"), hashlib.sha256).hexdigest()


class LocalFSStorage(FileSystemStorage):
    """Drop-in replacement for plane.settings.storage.S3Storage.

    Contract: same public method signatures as S3Storage so view-layer call
    sites (app/, api/, space/, bgtasks) need no changes. Instead of pointing
    to AWS/MinIO, the returned URLs resolve to
    /api/assets/local-{upload,download}/ on this server, signed with an
    HMAC policy document.
    """

    def __init__(self, request=None, **kwargs):
        kwargs.setdefault("location", settings.MEDIA_ROOT)
        kwargs.setdefault("base_url", settings.MEDIA_URL)
        super().__init__(**kwargs)
        self.request = request
        self.signed_url_expiration = int(os.environ.get("SIGNED_URL_EXPIRATION", "3600"))

    # ---- presigned POST ----
    def generate_presigned_post(self, object_name, file_type, file_size, expiration=None):
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
            "url": self._endpoint("local-upload"),
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

    # ---- presigned GET ----
    def generate_presigned_url(
        self,
        object_name,
        expiration=None,
        http_method="GET",
        disposition="inline",
        filename=None,
    ):
        expiration = expiration or self.signed_url_expiration
        expires_at = int((datetime.now(tz=timezone.utc) + timedelta(seconds=expiration)).timestamp())
        payload = f"{object_name}|{expires_at}|{disposition}|{filename or ''}"
        sig = hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()

        qs = urlencode({
            "expires": expires_at,
            "disposition": disposition,
            "filename": filename or "",
            "signature": sig,
        })
        return f"{self._endpoint('local-download')}/{quote(object_name)}?{qs}"

    # ---- metadata ----
    def get_object_metadata(self, object_name):
        if not self.exists(object_name):
            return None
        path = self.path(object_name)
        stat = os.stat(path)
        return {
            "ContentType": None,   # 로컬 FS 에서는 저장하지 않음 — DB(FileAsset.attributes) 에 있음
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
        self.save(object_name, file_obj)
        return True

    # ---- helpers ----
    def _endpoint(self, which):
        base = getattr(settings, "WEB_URL", None) or ""
        return f"{base.rstrip('/')}/api/assets/{which}"
```

---

## 3. `common.py` 분기

기존 하드코딩을 env 분기로 교체.

```python
# Storage
USE_LOCAL_STORAGE = int(os.environ.get("USE_LOCAL_STORAGE", 0)) == 1

STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}

if USE_LOCAL_STORAGE:
    STORAGES["default"] = {"BACKEND": "plane.settings.local_storage.LocalFSStorage"}
    MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "D:/Workspace/plane-data/uploads")
    MEDIA_URL = os.environ.get("MEDIA_URL", "/uploads/")
    STORAGE_SIGNING_KEY = os.environ.get("STORAGE_SIGNING_KEY") or SECRET_KEY
else:
    STORAGES["default"] = {"BACKEND": "plane.settings.storage.S3Storage"}
    # 기존 AWS_* 블록 유지
```

원본의 `STORAGES["default"] = "S3Storage"` 직할당 문을 지우고 위 블록으로 교체. AWS_* 블록은 `else` 아래로 이동.

---

## 4. upload/download view

`apps/api/plane/app/views/asset/local.py`:

```python
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from plane.settings.local_storage import _sign, ALG, CRED


def _verify_post_policy(fields):
    policy_b64 = fields.get("policy", "")
    sig = fields.get("x-amz-signature", "")
    if fields.get("x-amz-algorithm") != ALG or fields.get("x-amz-credential") != CRED:
        return None, "algorithm/credential mismatch"
    if not hmac.compare_digest(_sign(policy_b64), sig):
        return None, "signature mismatch"
    try:
        policy = json.loads(base64.urlsafe_b64decode(policy_b64 + "==").decode("utf-8"))
    except Exception:
        return None, "policy decode error"
    expires = datetime.strptime(policy["expiration"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if datetime.now(tz=timezone.utc) > expires:
        return None, "expired"
    return policy, None


def _policy_condition(policy, name):
    for c in policy["conditions"]:
        if isinstance(c, dict) and name in c:
            return c[name]
    return None


class LocalUploadView(APIView):
    permission_classes = [AllowAny]   # 서명으로 인증 — 세션 불필요 (MCP, 프론트, 외부 PUT 호환)

    def post(self, request):
        policy, err = _verify_post_policy(request.data)
        if err:
            return HttpResponse(err, status=403)

        key = request.data.get("key") or ""
        if key != _policy_condition(policy, "key"):
            return HttpResponse("key mismatch", status=400)
        if ".." in key or key.startswith("/") or "\\" in key:
            return HttpResponse("invalid key", status=400)

        file_obj = request.FILES.get("file")
        if not file_obj:
            return HttpResponse("missing file", status=400)

        # size range
        cond = next((c for c in policy["conditions"] if isinstance(c, list) and c[0] == "content-length-range"), None)
        if cond and not (cond[1] <= file_obj.size <= cond[2]):
            return HttpResponse("size out of range", status=400)

        # content-type
        expected_ct = _policy_condition(policy, "Content-Type")
        if expected_ct and request.data.get("Content-Type") != expected_ct:
            return HttpResponse("content-type mismatch", status=400)

        default_storage.save(key, file_obj)
        # S3 presigned POST 와 동일한 204
        return HttpResponse(status=204)


class LocalDownloadView(APIView):
    permission_classes = [AllowAny]   # 서명 기반

    def get(self, request, path):
        expires = int(request.GET.get("expires", "0"))
        disposition = request.GET.get("disposition", "inline")
        filename = request.GET.get("filename", "")
        sig = request.GET.get("signature", "")
        payload = f"{path}|{expires}|{disposition}|{filename}"
        expected = hmac.new(
            (settings.STORAGE_SIGNING_KEY or settings.SECRET_KEY).encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return HttpResponse("signature mismatch", status=403)
        if expires < int(datetime.now(tz=timezone.utc).timestamp()):
            return HttpResponse("expired", status=410)
        if ".." in path or path.startswith("/") or "\\" in path:
            return HttpResponse("invalid path", status=400)
        if not default_storage.exists(path):
            return HttpResponse("not found", status=404)

        fh = default_storage.open(path, "rb")
        resp = FileResponse(fh, content_type="application/octet-stream")
        fname = filename or path.split("/")[-1]
        resp["Content-Disposition"] = f'{disposition}; filename*=UTF-8\'\'{fname}'
        return resp
```

### 4.1 URL 라우트

`apps/api/plane/app/urls/asset.py` (또는 인접한 urls) 에 아래 2줄 추가:

```python
from plane.app.views.asset.local import LocalUploadView, LocalDownloadView
from django.urls import re_path

urlpatterns += [
    re_path(r"^assets/local-upload/?$", LocalUploadView.as_view(), name="local-upload"),
    re_path(r"^assets/local-download/(?P<path>.+)$", LocalDownloadView.as_view(), name="local-download"),
]
```

라우트 prefix 는 `apps/api/plane/urls.py` 가 `app/urls/asset.py` 를 `/api/` 아래 포함한다는 가정. 실제 포함 경로는 Phase 4.2 에서 검증.

---

## 5. 단위 테스트

`apps/api/plane/tests/unit/settings/test_local_storage.py`:

```python
import pytest
from plane.settings.local_storage import LocalFSStorage


@pytest.fixture
def storage(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.MEDIA_URL = "/uploads/"
    settings.STORAGE_SIGNING_KEY = "test-key"
    settings.SECRET_KEY = "fallback"
    settings.WEB_URL = "http://localhost:8000"
    return LocalFSStorage()


def test_presigned_post_fields_shape(storage):
    r = storage.generate_presigned_post("ws/abc-image.png", "image/png", 1000)
    assert r["url"].endswith("/api/assets/local-upload")
    for k in ("Content-Type", "key", "x-amz-algorithm", "x-amz-credential",
              "x-amz-date", "policy", "x-amz-signature"):
        assert k in r["fields"]


def test_presigned_post_signature_verifies(storage):
    from plane.settings.local_storage import _sign
    r = storage.generate_presigned_post("ws/x.png", "image/png", 1000)
    assert _sign(r["fields"]["policy"]) == r["fields"]["x-amz-signature"]


def test_presigned_url_roundtrip(storage):
    url = storage.generate_presigned_url("ws/x.png", expiration=3600)
    assert "signature=" in url and "expires=" in url


def test_delete_files(storage, tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    assert storage.delete_files(["a.txt"]) is True
    assert not (tmp_path / "a.txt").exists()


def test_copy_object(storage, tmp_path):
    (tmp_path / "src.txt").write_text("x")
    storage.copy_object("src.txt", "dst.txt")
    assert (tmp_path / "dst.txt").read_text() == "x"
```

실행: `pytest plane/tests/unit/settings/test_local_storage.py -q`.

---

## 5a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P4.1-1 | `settings/local_storage.py` 신규 작성 (`LocalFSStorage`) | P2-3 | §2 | 새 파일 |
| P4.1-2 | `settings/common.py` `USE_LOCAL_STORAGE` 분기 추가 + `STORAGE_SIGNING_KEY` | P4.1-1 | §3 | common.py 수정 |
| P4.1-3 | `app/views/asset/local.py` 신규 (`LocalUploadView`/`LocalDownloadView`) | P4.1-2 | §4 | 새 view |
| P4.1-4 | `/api/assets/local-{upload,download}/` URL 라우트 등록 | P4.1-3 | §4.1 | urls 수정 |
| P4.1-5 | `site.env` + `render-envs.ps1` 에 `USE_LOCAL_STORAGE/MEDIA_ROOT/STORAGE_SIGNING_KEY` 추가 | P2-9 | — | render 확장 |
| P4.1-6 | 단위 테스트 5종 작성 (`test_local_storage.py`) | P4.1-1 | §5 | pytest 통과 |
| P4.1-7 | `python manage.py check` + `show_urls \| findstr local-` | P4.1-1~P4.1-4 | §6 | 통과 |

---

## 5b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P4.1-1 | `Select-String local_storage.py -Pattern "class LocalFSStorage\(FileSystemStorage\)"` | 1건 |
| P4.1-2 | `python -c "from django.conf import settings; print(settings.STORAGES['default']['BACKEND'])"` (USE_LOCAL_STORAGE=1) | `plane.settings.local_storage.LocalFSStorage` |
| P4.1-2 | `python -c "from django.conf import settings; print(bool(settings.STORAGE_SIGNING_KEY))"` | True |
| P4.1-3 | `Select-String local.py -Pattern "class LocalUploadView","class LocalDownloadView"` | 2건 |
| P4.1-4 | `python manage.py show_urls \| findstr local-` | 2 라우트 |
| P4.1-5 | `Select-String render-envs.ps1 -Pattern "USE_LOCAL_STORAGE=1"` | 1건 |
| P4.1-6 | `pytest plane/tests/unit/settings/test_local_storage.py -q` | 5 passed |
| P4.1-7 | `python manage.py check` | no issues |

**정합성 smoke** (수동):
```powershell
python manage.py shell
>>> from django.core.files.storage import default_storage
>>> r = default_storage.generate_presigned_post("ws/abc-test.png", "image/png", 1000)
>>> r["url"], sorted(r["fields"].keys())
# ('http://222.234.220.199/api/assets/local-upload',
#  ['Content-Type','key','policy','x-amz-algorithm','x-amz-credential','x-amz-date','x-amz-signature'])
```

---

## 5c. 요구사항 검증 체크리스트

- [ ] **S3 계약 호환** — `generate_presigned_post` 응답의 `fields` 키가 `x-amz-*` 유지 → 프론트 타입·MCP 무변경
- [ ] **HMAC 서명** — `_sign(policy_b64)` 가 `STORAGE_SIGNING_KEY` 로 서명, 서버 endpoint 재검증
- [ ] **만료 검증** — `LocalUploadView._verify_post_policy` 의 `expires` 체크
- [ ] **Path traversal 방어** — `..`, `/`, `\` 포함 key 거부
- [ ] **size/mime 검증** — policy 의 `content-length-range` · `Content-Type` 재대조
- [ ] **다운로드 서명** — `GET /api/assets/local-download/<path>?signature=...&expires=...` 의 HMAC 검증
- [ ] **SECRET_KEY 분리** — `STORAGE_SIGNING_KEY` env 가 SECRET_KEY 와 독립 (기본은 SECRET_KEY fallback)
- [ ] **테스트 커버리지** — 5 유닛 테스트가 post/sign/url/delete/copy 각 동작 커버

---

## 6. 체크포인트

- [ ] `LocalFSStorage` 파일 생성, 단위 테스트 5개 통과
- [ ] `common.py` `USE_LOCAL_STORAGE` 분기 추가
- [ ] `LocalUploadView`/`LocalDownloadView` 생성 + URL 라우트 등록
- [ ] `python manage.py check` 통과
- [ ] `python manage.py show_urls | findstr local-` 로 두 엔드포인트 노출 확인
- [ ] `.env` 에 `USE_LOCAL_STORAGE=1`, `MEDIA_ROOT`, `STORAGE_SIGNING_KEY` 추가 (render-envs.ps1 에 반영)

---

> **네비게이션**: [Phase 4 목차](../05-storage.md) · [다음: 4.2 views →](02-views.md)
