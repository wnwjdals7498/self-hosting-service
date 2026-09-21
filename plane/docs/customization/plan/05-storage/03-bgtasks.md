# Phase 4.3 — bgtasks export / cleanup 개조

> **네비게이션**: [← 4.2 views](02-views.md) · [Phase 4 목차](../05-storage.md) · [다음: 4.4 frontend →](04-frontend.md)

**목표**: bgtask 계층의 직접 스토리지 호출을 전부 `plane.utils.storage` 를 통한 dispatch 로 통일한다. `export_task.py` · `exporter_expired_task.py` 의 `boto3.client("s3")` 는 Django `default_storage` + `presigned_url` 헬퍼로 치환, `storage_metadata_task.py` · `copy_s3_object.py` 의 `S3Storage()` 는 **Phase 4.2 가 view 에 적용한 `get_storage()` 팩토리** 를 동일하게 적용한다.

**수정 파일**:
- `apps/api/plane/utils/storage.py` — Phase 4.2 에서 만든 파일에 `presigned_url` 헬퍼 추가
- `apps/api/plane/bgtasks/export_task.py` — boto3 4곳 치환
- `apps/api/plane/bgtasks/exporter_expired_task.py` — boto3 2곳 치환
- `apps/api/plane/bgtasks/storage_metadata_task.py` — `S3Storage()` 직접 호출을 `get_storage()` 로 (Phase 4.2 에서 이월)
- `apps/api/plane/bgtasks/copy_s3_object.py` — 동일
- `apps/api/plane/db/management/commands/create_bucket.py` — 로컬 모드 no-op
- `apps/api/plane/db/management/commands/update_bucket.py` — 로컬 모드 no-op

---

## 1. `export_task.py` 현재 동작

`bgtasks/export_task.py` 는 이슈 내보내기 결과(ZIP/CSV/JSON) 를 S3 에 업로드하고 다운로드 URL 을 `ExporterHistory.url` 에 저장한다. 핵심 경로:

| 라인 근방 | 동작 |
|---|---|
| 50 | `upload_s3 = boto3.client(...)` 로 S3 클라이언트 생성 |
| 65 | `presign_s3 = boto3.client(...)` 별도 (endpoint_url/region 다른 경우) |
| 75 | `presign_s3.generate_presigned_url("get_object", ...)` |
| 83, 91 | 실제 `upload_s3.upload_fileobj(...)` 호출 |
| 108 | 일부 경로에서 `s3.generate_presigned_url(...)` |
| 117-118 | `exporter_instance.url = presigned_url` 저장 |

문제: boto3 직접 호출이라 `USE_LOCAL_STORAGE=1` 환경에서 `AWS_ACCESS_KEY_ID=placeholder` 로 요청 → S3 서명 실패/네트워크 오류.

---

## 2. 개조 패턴

### 2.1 업로드: `upload_s3.upload_fileobj(...)` → `default_storage.save(...)`

**before**:
```python
import boto3
upload_s3 = boto3.client("s3", aws_access_key_id=..., aws_secret_access_key=...)
upload_s3.upload_fileobj(buffer, bucket, object_name, ExtraArgs={"ContentType": "application/zip"})
```

**after**:
```python
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

buffer.seek(0)
default_storage.save(object_name, ContentFile(buffer.read()))
```

`default_storage` 는 `STORAGES["default"]["BACKEND"]` 를 따라가므로 `LocalFSStorage` 또는 `S3Storage` 로 자동 분기. `ContentType` 메타는 `LocalFSStorage` 에서 저장되지 않지만, export 는 다운로드 시 Content-Disposition 으로만 사용 → 영향 없음.

### 2.2 presigned URL 생성: `presign_s3.generate_presigned_url(...)` → `storage.generate_presigned_url(...)`

**before**:
```python
presign_s3 = boto3.client("s3", ...)
url = presign_s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": bucket, "Key": key, "ResponseContentDisposition": f"attachment; filename=\"{fname}\""},
    ExpiresIn=3600,
)
exporter_instance.url = url
```

**after**:
```python
from plane.settings.local_storage import LocalFSStorage  # 또는 설정값에 따라
# 보다 범용적으로:
from django.core.files.storage import default_storage

url = default_storage.generate_presigned_url(
    object_name=key,
    expiration=3600,
    disposition="attachment",
    filename=fname,
)
exporter_instance.url = url
```

**단**: Django `FileSystemStorage` 기본에는 `generate_presigned_url` 메서드가 없음. `LocalFSStorage` 는 정의하지만 타 스토리지에는 없을 수 있음 → **호환 헬퍼 추가**:

`apps/api/plane/utils/storage.py` (신규):
```python
from django.core.files.storage import default_storage

def presigned_url(object_name, expiration=3600, disposition="attachment", filename=None):
    if hasattr(default_storage, "generate_presigned_url"):
        return default_storage.generate_presigned_url(
            object_name=object_name, expiration=expiration,
            disposition=disposition, filename=filename,
        )
    # FileSystemStorage fallback — 서명 없는 직접 URL (공개 파일 가정)
    return default_storage.url(object_name)
```

`export_task.py` 는 위 헬퍼를 사용:
```python
from plane.utils.storage import presigned_url
exporter_instance.url = presigned_url(key, expiration=3600,
                                       disposition="attachment", filename=fname)
```

### 2.3 `export_task.py` 수정 체크리스트

- [ ] `import boto3` / `from botocore.client import Config` 제거 또는 조건부 import (USE_LOCAL_STORAGE 시 불필요)
- [ ] 라인 50, 65, 83, 91 의 `boto3.client` 블록 → `default_storage` 호출로 치환
- [ ] 라인 75, 108 의 `generate_presigned_url` → `plane.utils.storage.presigned_url` 호출
- [ ] `exporter_instance.url` 할당 경로 2곳 모두 반영

---

## 3. `exporter_expired_task.py`

### 3.1 현재 동작

```python
s3 = boto3.client("s3", ...)
s3.delete_object(Bucket=bucket, Key=key)
```

매일 UTC 01:30 `delete_old_s3_link` 스케줄 (celery.py:48, 76). `ExporterHistory` 중 만료된 레코드를 조회해 S3 객체 삭제.

### 3.2 개조

```python
from django.core.files.storage import default_storage
default_storage.delete(key)
```

끝. `LocalFSStorage.delete` 는 `FileSystemStorage.delete` 상속 → 파일 삭제.

---

## 3a. `storage_metadata_task.py` (Phase 4.2 에서 이월)

`FileAsset.storage_metadata` 를 업데이트하는 태스크. 현재 `S3Storage()` 를 직접 import + 인스턴스화.

**before**:
```python
from plane.settings.storage import S3Storage
...
storage = S3Storage()
asset.storage_metadata = storage.get_object_metadata(object_name=asset.asset.name)
```

**after**:
```python
from plane.utils.storage import get_storage
...
storage = get_storage()
asset.storage_metadata = storage.get_object_metadata(object_name=asset.asset.name)
```

`LocalFSStorage.get_object_metadata` 는 `ContentType=None` 을 반환하지만 호출부가 JSON field 전체를 그대로 저장하므로 downstream 에서 개별 키 접근 없음 (Phase 4.2 §2.3 에서 grep 확인).

## 3b. `copy_s3_object.py` (Phase 4.2 에서 이월)

Asset 복사용 태스크. 동일 패턴.

**before**:
```python
from plane.settings.storage import S3Storage
...
storage = S3Storage()
storage.copy_object(src, dst)
```

**after**:
```python
from plane.utils.storage import get_storage
...
storage = get_storage()
storage.copy_object(src, dst)
```

`LocalFSStorage.copy_object` 는 `open(src)` → `save(dst)` 로 구현 (Phase 4.1 §2). S3 와 달리 O(n) 바이트 복사지만 1인 규모에서 허용 가능.

## 4. `create_bucket` / `update_bucket` 관리 커맨드

### 4.1 로컬 FS 모드에서는 no-op

이 커맨드들은 MinIO/S3 에 bucket 을 생성·업데이트하는 일회성 초기화 용도. 로컬 FS 에서는 개념 없음.

**패턴**: 커맨드 handle 시작부에 분기.

```python
from django.conf import settings

class Command(BaseCommand):
    help = "Create or configure the S3/MinIO bucket"

    def handle(self, *args, **options):
        if getattr(settings, "USE_LOCAL_STORAGE", False):
            self.stdout.write(self.style.NOTICE(
                "USE_LOCAL_STORAGE=1: skipping bucket provisioning (local FS has no bucket concept)."
            ))
            return
        # ... 기존 로직 그대로 ...
```

Phase 0~3 범위에서 이 커맨드를 호출할 일은 없음 (Phase 2 에서 `migrate/collectstatic` 만). 미래에 누군가 실행해도 안전하게 반환.

---

## 5. smoke test (Celery worker 기동)

### 5.1 export round-trip

1. UI 에서 이슈 export 트리거 (workspace 설정 → exports → 새 export)
2. API: `POST /api/workspaces/<slug>/exports/` 등
3. Celery worker 창 로그에 `plane.bgtasks.export_task.issue_export_task` 처리 확인
4. `D:\Workspace\plane-data\uploads\` 아래 export ZIP 파일 생성 확인
5. UI 또는 API 에서 export URL 가져와서 브라우저 접근 → 다운로드 성공

### 5.2 expired cleanup

```powershell
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\Activate.ps1
python manage.py shell
>>> from plane.bgtasks.exporter_expired_task import delete_old_s3_link
>>> delete_old_s3_link()
# 만료된 export 의 파일이 D:\Workspace\plane-data\uploads\ 에서 사라지는지 확인
```

---

## 5a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P4.3-1 | `plane/utils/storage.py` 에 `presigned_url` 헬퍼 추가 (Phase 4.2 의 `get_storage` 옆) | P4.1-2, P4.2-0 | §2.2 | 헬퍼 함수 |
| P4.3-2 | `bgtasks/export_task.py` 4곳 `boto3.client` → `default_storage.save` / 헬퍼 | P4.3-1 | §2 | export_task 수정 |
| P4.3-3 | `bgtasks/exporter_expired_task.py` 2곳 `s3.delete_object` → `default_storage.delete` | P4.3-1 | §3 | cleanup task 수정 |
| P4.3-4 | `db/management/commands/{create,update}_bucket.py` `USE_LOCAL_STORAGE` no-op 분기 | P4.1-2 | §4 | 2 커맨드 |
| P4.3-5 | `bgtasks/storage_metadata_task.py` `S3Storage()` → `get_storage()` | P4.2-0 | §3a | metadata task 수정 |
| P4.3-6 | `bgtasks/copy_s3_object.py` `S3Storage()` → `get_storage()` | P4.2-0 | §3b | copy task 수정 |
| P4.3-7 | export round-trip smoke (UI 트리거 → Celery 처리 → 파일 생성 → 다운로드) | P4.3-2, P3-4 | §5.1 | 파일 + URL 동작 |
| P4.3-8 | `delete_old_s3_link` 수동 호출로 만료 삭제 확인 | P4.3-3 | §5.2 | 파일 사라짐 |

---

## 5b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P4.3-1 | `Select-String plane\utils\storage.py -Pattern "def presigned_url"` | 1건 |
| P4.3-2 | `Select-String bgtasks\export_task.py -Pattern "boto3\.client"` | 0 건 |
| P4.3-2 | `Select-String bgtasks\export_task.py -Pattern "default_storage\|presigned_url"` | ≥ 2건 |
| P4.3-3 | `Select-String bgtasks\exporter_expired_task.py -Pattern "boto3\.client"` | 0 건 |
| P4.3-4 | `Select-String db\management\commands\create_bucket.py -Pattern "USE_LOCAL_STORAGE"` | 1건 |
| P4.3-4 | `python manage.py create_bucket` (USE_LOCAL_STORAGE=1) | NOTICE "skipping bucket provisioning" |
| P4.3-5 | worker stdout 에 `issue_export_task` succeeded + `plane-data/uploads/` 에 export ZIP | True + 파일 존재 |
| P4.3-6 | `delete_old_s3_link()` 실행 전후 `plane-data/uploads/` 파일 수 비교 | 감소 |

---

## 5c. 요구사항 검증 체크리스트

- [ ] **boto3 직접 호출 제거** — export/cleanup 에서 `boto3.client` 0건
- [ ] **범용 헬퍼** — `plane.utils.storage.presigned_url` 이 스토리지 추상화. S3/MinIO/LocalFS 에 투명
- [ ] **Export 결과 URL 유효** — `ExporterHistory.url` 이 `/api/assets/local-download/...` 로 저장되고 다운로드 200
- [ ] **자동 cleanup** — beat 01:30 `delete_old_s3_link` 가 로컬 파일 삭제 동작
- [ ] **Bucket 커맨드 안전** — `USE_LOCAL_STORAGE=1` 시 no-op 으로 긴 timeout 방지
- [ ] **기존 테스트 회귀 없음** — `pytest plane/tests/unit -q` 전부 통과

---

## 6. 체크포인트

- [ ] `bgtasks/export_task.py` 의 `boto3.client` / `generate_presigned_url` 직접 호출 0 건
- [ ] `bgtasks/exporter_expired_task.py` 의 `boto3.client` 직접 호출 0 건
- [ ] `plane/utils/storage.py` 헬퍼 신규, 두 bgtask 가 사용
- [ ] `create_bucket` / `update_bucket` 커맨드에 `USE_LOCAL_STORAGE` no-op 분기 추가
- [ ] export round-trip 성공 (파일 생성 + 다운로드 + 만료 삭제)
- [ ] 기존 테스트 (`pytest plane/tests/unit -q`) 회귀 없음

---

> **네비게이션**: [← 4.2 views](02-views.md) · [Phase 4 목차](../05-storage.md) · [다음: 4.4 frontend →](04-frontend.md)
