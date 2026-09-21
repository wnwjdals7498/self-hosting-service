# Phase 4 — 파일 저장소 전환 (S3/MinIO → 로컬 FS, presigned-like 어댑터)

> **네비게이션**: [← Phase 3](04-celery-broker.md) · [목차](../plan.md) · [다음: Phase 5 →](06-frontend-build.md)
>
> 연관: [.claude/project-layout.md](../../../.claude/project-layout.md) · [../security-todo.md §4](../security-todo.md)

**최종 결정**:
- **구현 방식 A2** — presigned-like 서버 endpoint. `S3Storage` 를 교체하는 `LocalFSStorage` 어댑터 1개를 신설하고, 자기 서버에 `POST /api/assets/local-upload/` · `GET /api/assets/local-download/<path>` 를 추가한다. 기존 view 20+ 곳의 `storage.generate_presigned_post/url` 호출은 그대로 작동.
- **수정 범위 B1** — `app/` + `api/` + `space/` + `bgtasks` 전부. 이유: 외부 `D:\Workspace\plane-mcp-server` (MCP 서버) 가 `api/v1/...` 공개 API 를 사용 → `api/` 경로 호환 필수.
- **구조 C2** — 본 목차 + 서브폴더 `plan/05-storage/` 4 파일.

---

## 1. Phase 4 서브 단계 (순서 대로 실행)

| # | 서브 | 링크 | 핵심 산출물 |
|---|---|---|---|
| 4.1 | 스토리지 어댑터 + upload/download endpoint | [05-storage/01-adapter.md](05-storage/01-adapter.md) | `LocalFSStorage` 클래스 · `common.py` 분기 · URL 라우트 · HMAC 서명 · 단위 테스트 |
| 4.2 | view 호환성 검증 + 잔여 수정 | [05-storage/02-views.md](05-storage/02-views.md) | app/·api/·space/ 전 view 의 storage 호출 실측 · `HttpResponseRedirect` 가 자기 서버로 향하는지 확인 |
| 4.3 | bgtasks export/cleanup 개조 | [05-storage/03-bgtasks.md](05-storage/03-bgtasks.md) | `export_task.py` 의 boto3 직접 호출을 `default_storage` 로 대체 · `exporter_expired_task.py` 대체 |
| 4.4 | 프론트엔드 타입 완화 | [05-storage/04-frontend.md](05-storage/04-frontend.md) | `@plane/types` 의 `upload_data.fields` 타입 `x-amz-*` 고정 → `Record<string, string>` |

**실행 순서 근거**: 어댑터(4.1) 가 먼저 존재해야 view 가 선택(4.2)할 수 있고, bgtask(4.3) 은 어댑터를 사용. 프론트 타입(4.4) 은 백엔드가 다른 필드명을 쓰기로 한 경우에만 수정 — **권장은 필드 이름 호환 유지로 프론트 무변경**.

---

## 2. 핵심 설계 요약 (상세는 각 서브 파일)

### 어댑터 계약

`S3Storage` 와 동일 메서드 시그니처 유지 — 호출부(view/bgtask)가 dispatch 변경 없이 작동.

```python
class LocalFSStorage:
    def generate_presigned_post(self, object_name, file_type, file_size, expiration=None) -> dict: ...
    def generate_presigned_url(self, object_name, expiration=None, http_method="GET",
                                disposition="inline", filename=None) -> str: ...
    def upload_file(self, file_obj, object_name, content_type=None, extra_args=None) -> bool: ...
    def copy_object(self, object_name, new_object_name) -> dict: ...
    def delete_files(self, object_names) -> bool: ...
    def get_object_metadata(self, object_name) -> dict: ...
```

### 응답 계약 (S3 호환 유지)

`generate_presigned_post` → 프론트 `TFileSignedURLResponse.upload_data` 와 **동일 구조**:

```python
{
    "url": f"{WEB_URL}/api/assets/local-upload/",
    "fields": {
        "Content-Type": file_type,
        "key": object_name,
        "x-amz-algorithm": "HMAC-SHA256-PLANE",    # 이름 유지 (프론트 타입 호환)
        "x-amz-credential": "plane-local",          # 고정값
        "x-amz-date": iso_timestamp,
        "policy": base64(json(policy_document)),
        "x-amz-signature": hmac_sha256(SECRET_KEY, policy),
    },
}
```

→ 프론트의 `formData.append(k, v)` 반복이 **그대로 동작**. 4.4 서브의 타입 완화는 **optional** (필드명 유지 시 불필요). 4.4 를 "스킵 가능" 으로 분류하는 이유.

### 공통 env (Phase 2 `render-envs.ps1` 에 추가)

```ini
USE_LOCAL_STORAGE=1
MEDIA_ROOT=D:/Workspace/plane-data/uploads
MEDIA_URL=/uploads/
STORAGE_SIGNING_KEY=<SECRET_KEY 와 별개, 32자 랜덤 권장>
SIGNED_URL_EXPIRATION=3600
```

`STORAGE_SIGNING_KEY` 를 별도로 두는 이유: `SECRET_KEY` 회전 시 저장소 서명이 전부 무효화되는 것을 방지. 기본값으로 `SECRET_KEY` fallback.

---

## 3. 이 Phase 에서 예상되는 Plane 코드 수정

| 파일 | 목적 | 서브 |
|---|---|---|
| 신규 `apps/api/plane/settings/local_storage.py` | `LocalFSStorage` 클래스 | 4.1 |
| `apps/api/plane/settings/common.py` | `USE_LOCAL_STORAGE` 분기 (`STORAGES["default"]`, `MEDIA_*`) | 4.1 |
| 신규 `apps/api/plane/app/views/asset/local.py` | upload/download endpoint view | 4.1 |
| `apps/api/plane/app/urls/asset.py` | `/api/assets/local-{upload,download}/` 라우트 | 4.1 |
| 신규 `apps/api/plane/utils/storage.py` | `get_storage(request)` 팩토리 | 4.2 |
| `apps/api/plane/app/views/asset/v2.py` · `app/views/issue/attachment.py` | view 11곳 factory 치환 | 4.2 |
| `apps/api/plane/api/views/asset.py` · `api/views/issue.py` | view 6곳 factory + `is_server=True` 3곳 제거 | 4.2 |
| `apps/api/plane/space/views/asset.py` · `authentication/adapter/base.py` | view 4곳 factory 치환 | 4.2 |
| `apps/api/plane/bgtasks/storage_metadata_task.py` · `bgtasks/copy_s3_object.py` | `S3Storage()` 직접 호출 → factory | 4.3 |
| `apps/api/plane/bgtasks/export_task.py` | `boto3.client("s3")` → `default_storage.save()` + `storage.generate_presigned_url()` | 4.3 |
| `apps/api/plane/bgtasks/exporter_expired_task.py` | `s3.delete_object` → `default_storage.delete()` | 4.3 |
| `apps/api/plane/db/management/commands/{create,update}_bucket.py` | 로컬 모드 no-op 처리 또는 스킵 | 4.3 |
| (선택) `packages/types/src/file.ts` | `fields: Record<string, string>` | 4.4 |

app/·api/·space/ 의 기존 view 는 **수정 없음** (어댑터 호환 덕). 4.2 는 "실측 통과 확인" 성격.

---

## 3a. 작업 단위 분해 (서브 기준)

Phase 4 는 서브 4개로 나뉘며, 각 서브 WBS 는 해당 파일에 정리된다.

| 서브 | WBS 범위 | 서브 문서 |
|---|---|---|
| 4.1 | P4.1-1 ~ P4.1-7 (어댑터 + endpoint + 테스트) | [05-storage/01-adapter.md](05-storage/01-adapter.md) |
| 4.2 | P4.2-1 ~ P4.2-7 (view round-trip + MCP) | [05-storage/02-views.md](05-storage/02-views.md) |
| 4.3 | P4.3-1 ~ P4.3-6 (export/cleanup + bucket 커맨드 no-op) | [05-storage/03-bgtasks.md](05-storage/03-bgtasks.md) |
| 4.4 | P4.4-1 ~ P4.4-3 (필드명 유지 판단 + 타입 완화) | [05-storage/04-frontend.md](05-storage/04-frontend.md) |

---

## 3b. Phase 4 레벨 요구사항 검증 체크리스트

- [ ] **S3Storage 계약 호환** — 4.1 어댑터가 `generate_presigned_post/url/upload_file/copy/delete/metadata` 시그니처 유지. view 재작성 0
- [ ] **프론트 무변경 (기본)** — 4.1 이 `x-amz-*` 필드명 유지 → 4.4 스킵 가능
- [ ] **MCP 호환 (B1)** — 4.2 §5 MCP round-trip 통과 (api/v1 의 issue-attachment 플로우)
- [ ] **HMAC 서명 + 유효기간** — 4.1 policy 의 base64url(JSON) + HMAC-SHA256(`STORAGE_SIGNING_KEY`)
- [ ] **SECRET_KEY 회전 격리** — `STORAGE_SIGNING_KEY` 를 SECRET_KEY 와 별도 관리
- [ ] **export round-trip** — 4.3 의 bgtask 가 `default_storage.save` + `presigned_url` 헬퍼로 전환되어 LocalFS 에서 동작
- [ ] **`{create,update}_bucket` 안전** — 4.3 에서 `USE_LOCAL_STORAGE=1` no-op 분기
- [ ] **`get_object_metadata` ContentType 의존 없음** — 4.2 §2.3 grep 통과 (ContentType 사용처 없음 / 또는 FileAsset.attributes 로 대체)
- [ ] **업로드 경로 정적 서빙 금지** — Caddy 가 `/uploads/*` 직접 서빙하지 않음 ([08-external-access.md §2.2](08-external-access.md))

---

## 4. 체크포인트 (Phase 4 전체 완료)

```powershell
# 어댑터
Select-String -Path D:\Workspace\plane-app\apps\api\plane\settings\local_storage.py `
  -Pattern "class LocalFSStorage" -Quiet

# .env 반영
Select-String -Path D:\Workspace\plane-app\apps\api\.env `
  -Pattern "USE_LOCAL_STORAGE=1" -Quiet

# URL 라우트
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\python.exe manage.py show_urls 2>$null | Select-String "local-upload"
# /api/assets/local-upload/  ...

# 실 업로드/다운로드 smoke
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 &
Start-Sleep 3
# 업로드 토큰 발급 + 파일 업로드 + 다운로드 round-trip 스크립트 (04-views.md §4 참조)
```

- [ ] 4.1 어댑터 + endpoint 구현 완료, 단위 테스트 통과
- [ ] 4.2 view 호환 실측 (app/·api/·space/) — 기존 API 응답 스키마 변화 없음
- [ ] 4.3 export/cleanup bgtask 대체 완료, Celery worker 로 round-trip 확인
- [ ] 4.4 프론트 타입 결정 (유지 or 완화)
- [ ] `D:\Workspace\plane-data\uploads\` 에 실 파일 생성됨
- [ ] MCP 서버 호환성 스모크 (`api/v1/workspaces/.../projects/.../issues/.../issue-attachments/` round-trip) — [05-storage/02-views.md §5](05-storage/02-views.md)

---

## 5. 이월 / 후속

- **업로드 검증 보강** — mime 매직바이트 · AV 스캔 · path traversal → [../security-todo.md §4](../security-todo.md) (Phase 4 는 HMAC + size/type 만)
- **MEDIA_ROOT Cloudflare Tunnel 직접 서빙** — 현 설계는 Django 가 스트림. Phase 7 에서 Caddy/Cloudflare 레벨에서 `/uploads/*` 정적 서빙 여부 재검토 (다만 서명 없는 직접 서빙은 권한 우회 위험)
- **S3Storage 완전 제거** — 현재는 `USE_LOCAL_STORAGE=0` 시 기존 S3 경로 유지(회귀 안전). 1인 운영에서 필요 없어지면 `S3Storage` + MinIO 관리 커맨드 완전 제거 별도 기획

---

> **네비게이션**: [← Phase 3](04-celery-broker.md) · [목차](../plan.md) · [다음: Phase 5 →](06-frontend-build.md)
