# Phase 4.2 — view 호환성 검증

> **네비게이션**: [← 4.1 adapter](01-adapter.md) · [Phase 4 목차](../05-storage.md) · [다음: 4.3 bgtasks →](03-bgtasks.md)

**실측 결과 — 전제가 틀렸다**. 원래 이 서브 페이즈는 "어댑터가 투명하므로 view 수정 없음" 이라고 계획했으나, 코드 조사 결과 **21곳이 `S3Storage(...)` 를 직접 import + 인스턴스화**. 어댑터가 `STORAGES["default"]` 로 등록돼도 view 코드가 S3Storage 를 명시 호출하면 LocalFSStorage 로 dispatch 안 됨.

**실제 목표**: view 레이어의 직접 생성을 `plane.utils.storage.get_storage(request=request)` 팩토리로 일괄 치환. 팩토리는 `USE_LOCAL_STORAGE` 를 읽어 backend 를 동적 선택.

**치환 완료 범위** (21 call sites):

| 파일 | 치환 수 | 커밋 |
|---|---:|---|
| `plane/utils/storage.py` (신규) | — | 45fda23 |
| `app/views/asset/v2.py` | 9 | d5c9a04 |
| `app/views/issue/attachment.py` | 2 | d5c9a04 |
| `api/views/asset.py` | 4 (+ 3 `is_server=True` 제거) | 4dca8bb |
| `api/views/issue.py` | 2 | 4dca8bb |
| `space/views/asset.py` | 2 | 526561f |
| `authentication/adapter/base.py` | 2 | 526561f |

**확인된 추가 이슈**:
- `api/views/asset.py` 3곳이 `S3Storage(request=request, is_server=True)` 를 호출하는데 `S3Storage.__init__` 에 `is_server` 인자 없음 — 업스트림부터 TypeError 잠재. 팩토리 치환 시 `is_server=True` 제거 (dead param).
- `bgtasks/storage_metadata_task.py`, `bgtasks/copy_s3_object.py` 도 `S3Storage()` 직접 호출 → **Phase 4.3 범위로 이월** (bgtask 그룹 일관성).

**Phase 4.2 에서 더 이상 필요한 코드 수정 없음** — 4 커밋으로 완료. 잔여 작업은 호스트 상에서의 view 호환성 실측(§2.1~§2.5) 과 MCP round-trip(§5) 으로 E2E 검증.

---

## 레거시 호환성 매트릭스 (참고)

어댑터 투명성이 "완전 무수정"은 아니지만, factory 치환 후에는 다음이 성립:

---

## 1. 호환성 매트릭스

| 호출 패턴 | `S3Storage` 동작 | `LocalFSStorage` 동작 | 결과 |
|---|---|---|---|
| `storage.generate_presigned_post(key, type, size)` 결과를 `{"upload_data": r}` 로 JSON 응답 | `{url: s3-url, fields: {amz-*}}` | `{url: /api/assets/local-upload/, fields: {amz-* 이름 유지}}` | **무수정 동작** |
| `storage.generate_presigned_url(key)` 결과를 `HttpResponseRedirect` | `302 → s3-url` | `302 → /api/assets/local-download/...?signature=...` | **무수정 동작** |
| `storage.generate_presigned_url(key)` 결과를 응답 JSON 에 직접 삽입 | s3 URL 문자열 | 로컬 URL 문자열 | **무수정 동작** |
| `storage.upload_file(file_obj, key)` | boto3 upload_fileobj | `default_storage.save()` | **무수정 동작** |
| `storage.get_object_metadata(key)` | head_object | `os.stat` | ContentType 이 None — DB(`FileAsset.attributes`) 에서 참조해야 함. 호출부 확인 필요 (§2.3) |
| `storage.copy_object(a, b)` | S3 copy_object | read→write | **무수정 동작**, 성능 차이 O(n) |
| `storage.delete_files([keys])` | delete_objects | `default_storage.delete()` 반복 | **무수정 동작** |

---

## 2. 실측 절차

### 2.1 `app/views/asset/v2.py` (내부 UI 핵심)

```powershell
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\Activate.ps1
# .env 로딩 + USE_LOCAL_STORAGE=1 상태
python manage.py runserver 127.0.0.1:8000
```

다른 창에서 superuser 세션으로 흐름 테스트 (PowerShell):

```powershell
# 1. 로그인 (세션 쿠키 확보)
$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = Invoke-WebRequest -Uri "http://127.0.0.1:8000/auth/sign-in/" -Method POST -WebSession $s `
  -Body @{ email="admin@plane.local"; password="<pw>" }

# 2. workspace asset presign 요청 (실제 엔드포인트는 Phase 4.1 실행 시 show_urls 로 확인)
$presign = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/workspaces/<slug>/file-assets/" `
  -Method POST -WebSession $s -ContentType "application/json" -Body (@{
    name="test.png"; type="image/png"; size=100;
    entity_type="USER_AVATAR"; entity_identifier="<user-uuid>"
  } | ConvertTo-Json)

# 3. upload_data.url 로 실제 업로드 (multipart)
$form = @{}
$presign.upload_data.fields.PSObject.Properties | ForEach-Object { $form[$_.Name] = $_.Value }
$form["file"] = Get-Item "C:\path\to\test.png"
Invoke-WebRequest -Uri $presign.upload_data.url -Method POST -Form $form  # 204 기대

# 4. asset 확정 (is_uploaded=True 반영하는 PATCH)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/workspaces/<slug>/file-assets/$($presign.asset_id)/" `
  -Method PATCH -WebSession $s

# 5. 다운로드 (presigned GET 302 redirect 확인)
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/workspaces/<slug>/file-assets/$($presign.asset_id)/" `
  -WebSession $s -MaximumRedirection 0
# 302 Location: /api/assets/local-download/...
```

### 2.2 `app/views/issue/attachment.py`

위와 유사하게 이슈 첨부 경로로 반복:
- `POST /api/workspaces/<slug>/projects/<pid>/issues/<iid>/attachments/` → upload_data 수령
- presigned POST 실행 → 204
- 다시 `PATCH` 로 is_uploaded 반영
- `GET .../attachments/<aid>/` 로 download redirect 확인

### 2.3 `get_object_metadata` 호출부 개별 확인

`LocalFSStorage.get_object_metadata` 가 `ContentType=None` 을 반환 — S3 는 객체 헤더에서 읽지만 로컬은 파일시스템에 저장 안 됨. 호출부가 `ContentType` 을 실제로 참조하는지 grep:

```powershell
Select-String -Path D:\Workspace\plane-app\apps\api\plane -Recurse `
  -Pattern "get_object_metadata|ContentType"
```

만약 참조한다면 `FileAsset.attributes["type"]` (프론트가 presign 시 전달한 `file_type`) 또는 `python-magic` 으로 런타임 재감지. **대부분의 호출부는 size 만 사용** — Plane 이 프론트에서 받은 mime 을 `FileAsset.attributes` 에 이미 저장하므로 실질 영향 없을 가능성 높음.

### 2.4 `api/views/asset.py` & `api/views/issue.py` (MCP 경로)

API key 인증:

```powershell
$headers = @{ "X-Api-Key" = "<api-key>" }

# MCP 가 사용할 issue attachment 업로드
$presign = Invoke-RestMethod -Headers $headers `
  -Uri "http://127.0.0.1:8000/api/v1/workspaces/<slug>/projects/<pid>/issues/<iid>/issue-attachments/" `
  -Method POST -ContentType "application/json" -Body (@{
    name="screenshot.png"; type="image/png"; size=50000
  } | ConvertTo-Json)
# upload_data.url → local-upload
# 이하 2.1 와 동일
```

MCP 서버가 이 플로우로 정상 첨부 업로드 가능하면 Phase 4 목표 달성.

### 2.5 `space/views/asset.py` (공개 포털)

공개 링크 기반 asset 다운로드 (익명). signature 검증이 핵심:

```powershell
# 공개 space 에서 공유된 이슈 첨부 GET
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/public/workspaces/<slug>/projects/<pid>/issue-attachments/<aid>/" `
  -MaximumRedirection 0
# 302 → local-download?signature=...  (anonymous 허용 — signature 기반)
```

---

## 3. 예외 보정 — host 추정

`LocalFSStorage._endpoint` 가 `settings.WEB_URL` 을 사용. 현재 `.env` 는 `WEB_URL=http://222.234.220.199` (Phase 2 render-envs 산출). Cloudflare Tunnel 뒤에서 동작하면 `Host` 헤더는 cloudflare 가 전달.

**검증**:
- `WEB_URL` 이 외부 공인 주소와 일치 → presigned URL 이 브라우저에서 resolve 가능
- 만약 프론트가 **내부 호스트** 에서 렌더된다면 (개발 환경) `WEB_URL` 을 상대 경로 `""` 로 만들면 `//api/assets/local-upload/` 처럼 스킴 없는 형태가 되어 브라우저가 현재 origin 으로 fallback — 원격 배포 호환.

**선택**: 운영에서 `WEB_URL` 을 외부 주소로 고정(현 설계). 개발용 local runserver 테스트 시에만 `WEB_URL=http://127.0.0.1:8000` 로 override.

---

## 4. 업로드 후 `is_uploaded` 전이 경로

Plane 의 현재 플로우:
1. presign → DB 에 `FileAsset(is_uploaded=False)` 생성
2. 클라이언트가 업로드 endpoint 로 PUT/POST
3. 클라이언트가 Plane API 로 `is_uploaded=True` 를 PATCH 반영

**로컬 전환 후 문제 가능성**: presigned POST 수신 endpoint (`LocalUploadView`) 가 DB 에 상태를 업데이트하지 않음 — S3 와 똑같이 클라이언트의 PATCH 를 기다린다. **문제 없음** (기존 플로우 그대로).

단, 업로드 실패(서명 검증 실패 등) 시 DB `FileAsset` 은 `is_uploaded=False` 로 고아 상태. 이 정리는 이미 `bgtasks/file_asset_task.py` 의 `delete_unuploaded_file_asset` (celery beat `02:00` UTC) 가 담당 — 변경 없음.

---

## 5. MCP 서버 round-trip 스모크

Phase 4 성공 기준의 핵심. `D:\Workspace\plane-mcp-server\.env.test` 를 복제해 본 서버를 가리키도록:

```ini
# plane-mcp-server/.env.test override
PLANE_API_KEY=<본 서버 API key>
PLANE_WORKSPACE_SLUG=<본 서버 workspace slug>
PLANE_BASE_URL=http://222.234.220.199
```

```powershell
cd D:\Workspace\plane-mcp-server
# uv sync 또는 pip install -e . (pyproject 기반)
# tests/ 또는 직접 호출
uv run pytest tests/integration/test_asset_upload.py -q    # 해당 테스트가 존재할 때
```

테스트 부재 시 MCP 의 issue-attachment tool 을 수동 호출:
```
# Claude Desktop 또는 inspector 에서
tools/call { "name": "upload_issue_attachment", "arguments": {...} }
```

기대: 로컬 FS 에 파일 저장 + MCP 응답 성공.

---

## 5a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 | 상태 |
|---|---|---|---|---|---|
| P4.2-0 | `plane/utils/storage.py` `get_storage` 팩토리 신규 | P4.1-7 | (본문 상단) | 45fda23 | 완료 |
| P4.2-A | `app/views/asset/v2.py` + `attachment.py` factory 치환 | P4.2-0 | — | d5c9a04 | 완료 |
| P4.2-B | `api/views/asset.py` + `issue.py` factory 치환 + `is_server=True` 제거 | P4.2-0 | — | 4dca8bb | 완료 |
| P4.2-C | `space/views/asset.py` + `authentication/adapter/base.py` factory 치환 | P4.2-0 | — | 526561f | 완료 |
| P4.2-1 | `app/views/asset/v2.py` 엔드포인트 round-trip (E2E) | P4.2-A, Phase 5+7 | §2.1 | upload 204 + download 200 | Phase 5/7 이후 |
| P4.2-2 | `app/views/issue/attachment.py` round-trip (E2E) | P4.2-A, Phase 5+7 | §2.2 | 동일 | Phase 5/7 이후 |
| P4.2-3 | `get_object_metadata` 호출부 ContentType 의존 검증 | P4.2-0 | §2.3 | ContentType 미의존 확인 | 완료 (호출 2곳 모두 JSON 전체 저장) |
| P4.2-4 | `api/views/asset.py` + `issue.py` API key round-trip | P4.2-B, Phase 5+7 | §2.4 | MCP 호환 | Phase 5/7 이후 |
| P4.2-5 | `space/views/asset.py` anonymous 서명 다운로드 | P4.2-C, Phase 5+7 | §2.5 | 공개 포털 검증 | Phase 5/7 이후 |
| P4.2-6 | host 추정 (`WEB_URL`) 실측 | P2-10 | §3 | presigned URL 이 외부 도메인/IP 포함 | 완료 (reverse 확인) |
| P4.2-7 | MCP 서버 tool 호출 round-trip | P4.2-4 | §5 | 첨부 업로드 성공 | Phase 5/7 이후 |

---

## 5b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P4.2-1 | PowerShell round-trip 스크립트 (§2.1) | 204 + 200 + 파일 `plane-data/uploads/` |
| P4.2-2 | 이슈 첨부 POST → upload → PATCH → GET | 동일 |
| P4.2-3 | `Select-String plane -Recurse -Pattern "get_object_metadata\|ContentType"` | ContentType 의존 호출부 0 또는 `FileAsset.attributes` 참조 |
| P4.2-4 | `curl -H "X-Api-Key: $k" http://.../api/v1/.../issue-attachments/` | 200 + upload_data |
| P4.2-5 | 공개 space asset GET | 302 → local-download (서명 검증 통과) |
| P4.2-6 | `Select-String apps\web\build\client\assets\*.js -Pattern "222\.234\.220\.199"` | True (빌드 후 단계는 Phase 5) |
| P4.2-7 | MCP inspector 또는 integration test | tool 응답 성공 |

---

## 5c. 요구사항 검증 체크리스트

- [ ] **app/ 경로 호환** — 내부 UI 로그인 후 업로드·다운로드 전부 동작 (P4.2-1, P4.2-2)
- [ ] **api/ 공개 API 호환 (B1)** — MCP 가 사용할 `/api/v1/...` 경로 OK (P4.2-4)
- [ ] **space/ 공개 포털 호환** — 익명 링크 다운로드 정상 (P4.2-5)
- [ ] **view 코드 재작성 0** — 어댑터 투명성으로 기존 view 수정 없이 동작
- [ ] **ContentType 의존 없음** — 있을 경우 `FileAsset.attributes["type"]` 로 대체
- [ ] **업로드 → is_uploaded PATCH 플로우 보존** — 기존 Plane 플로우 그대로
- [ ] **MCP round-trip 통과 (또는 이월)** — 통과 못 하면 [../security-todo.md](../security-todo.md) 또는 후속 기획
- [ ] **presigned URL 의 host** — Cloudflare/Caddy 뒤에서도 `WEB_URL` 이 외부에서 resolve 가능

---

## 6. 체크포인트

- [ ] app/views/asset/v2.py 5개 엔드포인트 presign → upload → download round-trip 통과
- [ ] app/views/issue/attachment.py 2개 엔드포인트 round-trip 통과
- [ ] api/views/asset.py · api/views/issue.py (MCP 호환) round-trip 통과
- [ ] space/views/asset.py (anonymous 서명 기반) download 200
- [ ] `get_object_metadata` 호출부 ContentType 의존 없음 확인
- [ ] MCP 서버 tool 호출 end-to-end 통과 (필수 아님 — 스킵 가능 시 security-todo 에 이월)
- [ ] `D:\Workspace\plane-data\uploads\` 에 실제 파일 축적됨

---

> **네비게이션**: [← 4.1 adapter](01-adapter.md) · [Phase 4 목차](../05-storage.md) · [다음: 4.3 bgtasks →](03-bgtasks.md)
