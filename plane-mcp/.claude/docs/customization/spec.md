# Plane MCP Server — 포크 커스터마이즈 설계 (Spec)

> `makeplane/plane-mcp-server` 를 포크해 Plane 네이티브 배포 포크(`D:\Workspace\plane`, Windows Server 2025, SQLite + LocalFSStorage) 의 특성에 맞춰 tool 을 추가·수정한다. 브레인스토밍 결과(2026-04-24) 를 고정하고 후속 구현 계획(plan) 이 이 문서를 입력으로 사용.
>
> 관련:
> - Plane 배포: `D:\Workspace\plane\docs\customization\worklog.md` (완료 이력 + 교훈) · `todo.md` (앞으로 할 일)
> - 보안 기준선: `D:\Workspace\plane\docs\customization\security-audit-2026Q2.md`
> - upstream: <https://github.com/makeplane/plane-mcp-server> (초기 import HEAD `ca456fe` = upstream `24565ab` 시점)

**최종 갱신**: 2026-04-24 (브레인스토밍 완료 — 구현 착수 전)
**상태**: design 확정 / plan 미작성 / 구현 미착수

---

## 1. 배경

### 1.1 왜 포크인가

Plane 네이티브 배포(`D:\Workspace\plane` 포크) 는 upstream Plane 과 다음 두 지점에서 다르다:

- **DB**: SQLite (upstream default PostgreSQL)
- **Storage**: LocalFSStorage — `/api/assets/local-upload/` (HMAC-signed presigned POST) + `/api/assets/local-download/<key>?sig=...` (HMAC-signed GET). upstream 은 S3/MinIO 전제.

`makeplane/plane-mcp-server` upstream 은 `plane-sdk` 를 통해 Plane REST API 만 호출한다. REST API 자체는 포크에서도 대부분 동일 동작(SQLite 차이는 API layer 밖) 이나 **파일 전송 경로가 완전히 다르다**. upstream 에 파일 업로드 tool 이 없고 (`cover_image` 가 URL/ID 를 받는 수준) 포크의 LocalFSStorage 엔드포인트를 모르는 이상 **포크 특화 tool 추가가 불가피**하다.

### 1.2 Plane 배포의 본 목적

`D:\Workspace\plane\docs\customization\worklog.md` 의 Phase 0~8 + 보안 #1 작업은 전부 "MCP 서버를 올릴 호스트 안정화" 선행 작업이었다. 이 문서는 그 위에 올라갈 본 목표물의 설계.

### 1.3 upstream 과의 관계

- **Fork 형태**: 로컬 Gitea (`http://222.234.220.199:18080/joojm/plane-mcp-server`) 에 완전 독자 저장소. upstream git history 는 포기(`.git` 삭제 후 `git init`), 초기 커밋 1 개로 fresh 시작.
- **upstream 추적**: `git remote add upstream https://github.com/makeplane/plane-mcp-server.git` 수동 설정 후 **월 1회 `git fetch upstream` + 선택적 cherry-pick** (이력 `.claude/docs/customization/upstream-sync.md`). 정기 rebase 안 함.

---

## 2. 요구사항 (브레인스토밍 확정, 2026-04-24)

| # | 항목 | 결정 | 비고 |
|---|---|---|---|
| 1 | 사용 시나리오 | HTTP endpoint, **팀원 공유** | stdio/local 아님 |
| 2 | 경로 + 인증 | Caddy `/mcp/*` reverse_proxy → `:8211` + **Header PAT** | upstream 의 `/http/api-key/mcp` 경로. OAuth 는 추후 필요 시 확장 |
| 3 | 포크 tool 범위 | **C 안** — file tool + admin/운영 tool | upstream 55+ tool 유지 + 신규 7개 내외 |
| 4 | `PLANE_BASE_URL` | `http://127.0.0.1:8000` (uvicorn 직접) | Caddy 경유 X — edge 룰 불필요 |
| 5 | upstream 싱크 | **선택적 cherry-pick** | 월 1회 수동 검토 |
| 6 | admin 권한 분리 | **tool 레벨 가드** (`is_instance_admin`) | FastMCP decorator + Redis 60s 캐시 |

### 2.1 호스트 배치

**Approach 1 (Co-hosted) + trigger_backup_now 는 Plane endpoint 하이브리드**:

- MCP 는 plane-api 와 **같은 호스트**, NSSM `plane-mcp` 서비스, **`.\plane` 계정 공유**
- admin tool 대부분은 plane 계정으로 호스트 리소스 직접 접근 (IPBan stdout.log read, plane-logs/backup read)
- 예외: `trigger_backup_now` 는 plane 계정이 `Start-ScheduledTask` 할 권한 없음 → **Plane Django 포크에 admin endpoint 신규**, subprocess 는 Django 측 (plane 계정) 이 실행

Sidecar 격리(별도 `plane-mcp` 계정) 와 API-only 안은 반려 — 전자는 3곳 동기화 규칙 2배 부담, 후자는 Plane 포크 diff 대폭 확대로 보안/rebase 부담.

---

## 3. 아키텍처

### 3.1 배포 토폴로지

```
[공인 IP :80] ──► caddy (기존 + 1 블록 신규)
   ├ /api/*   /auth/*  /static/*  ──► uvicorn :8000 (plane-api)
   ├ /live/*                       ──► :3100 (plane-live)
   ├ /uploads/*                    ──► 403 (직접 접근 차단)
   ├ handle_path /spaces/*         ──► static (space SPA)
   ├ handle_path /god-mode/*       ──► static (admin SPA)
   ├ handle /mcp/*                 ──► 127.0.0.1:8211 (plane-mcp)  ◄── 신규
   └ handle fallback               ──► static (web SPA)

NSSM 서비스 (7 → 8):
  Redis · IPBan · plane-api · plane-celery · plane-beat · plane-live · caddy
  + plane-mcp (신규, .\plane, port 8211, DependOnService=plane-api Redis)

plane-mcp 호출 경로:
  - plane-api REST : http://127.0.0.1:8000  (PLANE_BASE_URL)
  - Redis          : 127.0.0.1:6379 DB 2   (토큰/캐시, DB 0/1 과 분리)
  - 호스트 FS      : D:\Workspace\plane-logs\ipban\stdout.log 등
  - Plane admin EP : POST /api/instances/admin/backup/ (신규, trigger_backup_now)
```

### 3.2 Transport mode

- **HTTP 단일** — `python -m plane_mcp http` (upstream `__main__.py`). stdio/SSE 미등록.
- FastMCP 가 `:8211` 에 두 경로 노출:
  - `/mcp/http/api-key/mcp` — Header PAT 인증 (**주 사용**)
  - `/mcp/oauth/mcp` — OAuth flow (선택 기능, 팀 OAuth 전환 시 활용)
- Caddy 는 `/mcp/*` 를 통째로 passthrough.

### 3.3 외부 노출 경계

- 8211 은 **loopback only** (`127.0.0.1:8211`)
- 외부 노출은 Caddy 80 경유 `/mcp/*` 만 허용 (기존 uploads/live 와 동일 패턴)
- HTTPS 전환은 보안 #3 (§C) 이후 자동 상속

### 3.4 MCP 서비스 환경변수

`ops/site.env` 를 source 로 `ops/render-envs.ps1` 가 `apps/plane-mcp-server/.env` 를 렌더, 이후 `ops/register-plane-mcp.ps1` 이 NSSM `AppEnvironmentExtra` 로 주입 (plane-api 와 동일 패턴, worklog §7a #1 교훈 반영 — `.env` 파일이 아닌 NSSM env 가 실 런타임 소스).

```
PLANE_BASE_URL=http://127.0.0.1:8000           # uvicorn 직접 (결정 Q5a)
PLANE_INTERNAL_BASE_URL=http://127.0.0.1:8000  # server-to-server 별도 URL 없으면 동일
PLANE_WORKSPACE_SLUG=plane-windows-server-2025  # 기본 workspace (Header 로 override 가능)
PLANE_MCP_HTTP_HOST=127.0.0.1                  # loopback bind
PLANE_MCP_HTTP_PORT=8211
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=2                                      # plane-api(0/1) 과 분리
REDIS_PASSWORD=<ops/.redis_pass 값 주입>
PLANE_MCP_IPBAN_LOG=D:\Workspace\plane-logs\ipban\stdout.log  # host/ipban_reader 에서 참조
```

OAuth 관련 env (`PLANE_OAUTH_PROVIDER_*`) 는 §12 Non-goals — Header PAT 모드에서는 미주입. `PLANE_API_KEY` 도 미주입 (HTTP 모드 + Header 기반이므로 env 불필요).

---

## 4. 컴포넌트

### 4.1 `plane-mcp-server/` (이 저장소)

| 파일 | 유형 | 내용 |
|---|---|---|
| `plane_mcp/__main__.py` | upstream 유지 | `python -m plane_mcp http` 진입점 |
| `plane_mcp/server.py` | **수정** | `get_header_mcp()` factory 에 `register_files_tools()` + `register_admin_tools()` 호출 추가. OAuth/stdio factory 는 건드리지 않음 |
| `plane_mcp/tools/__init__.py` | **수정** | `from .files import register_files_tools` + `from .admin import register_admin_tools` export |
| `plane_mcp/tools/files.py` | **신규** | `upload_file` · `download_file` · `list_file_assets` |
| `plane_mcp/tools/admin.py` | **신규** | `get_instance_info` · `list_workspace_health` · `get_recent_ipban_events` · `trigger_backup_now` |
| `plane_mcp/auth/admin_guard.py` | **신규** | FastMCP tool decorator — `/api/users/me/` 조회 → `is_instance_admin` 체크. Redis 60s TTL 캐시 (key `mcp:admin:<user_id>`) |
| `plane_mcp/host/ipban_reader.py` | **신규** | `D:\Workspace\plane-logs\ipban\stdout.log` tail + regex parse (`Banning|Un-banning|Login failure`) |
| `plane_mcp/host/paths.py` | **신규** | 호스트 경로 상수 (env 주입, Windows only, Linux fallback 없음) |
| `plane_mcp/tools/{cycles,epics,...}` 20 개 | upstream 유지 | cherry-pick 외 변경 금지 |

### 4.2 Plane 포크 (`D:\Workspace\plane`)

| 파일 | 유형 | 내용 |
|---|---|---|
| `apps/api/plane/app/urls/instance.py` | 수정 | `path("instances/admin/backup/", AdminBackupView.as_view(), name="instance-admin-backup")` 추가 |
| `apps/api/plane/app/views/instance/admin.py` | **신규** | `AdminBackupView(APIView)` — `permission_classes = [InstanceAdminPermission]`, `post()` 에서 `subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Start-ScheduledTask -TaskName PlaneBackup"])` → `{task_id, started_at, pid}` 반환 |
| `apps/api/plane/app/permissions/__init__.py` | 수정 | `InstanceAdminPermission` export (이미 있으면 유지) |
| `apps/api/plane/tests/unit/views/test_admin_backup.py` | **신규** | `AdminBackupView` unit test (Start-ScheduledTask 는 mock) |

### 4.3 운영 트리 (`D:\Workspace\plane-app/ops/`, git 외부)

| 파일 | 유형 | 내용 |
|---|---|---|
| `ops/register-plane-mcp.ps1` | **신규** | NSSM `plane-mcp` 등록. `.\plane` 계정, `python.exe -m plane_mcp http`, port 8211, `DependOnService=plane-api Redis`, `AppEnvironmentExtra` 로 `PLANE_BASE_URL`, `PLANE_INTERNAL_BASE_URL`, `REDIS_HOST/PORT/DB/PASSWORD`, `PLANE_WORKSPACE_SLUG` 등 주입. `register-services.ps1` 의 Remove-ZombieProcesses + polling 패턴 재사용 |
| `ops/Caddyfile` | 수정 | `handle /mcp/* { reverse_proxy 127.0.0.1:8211 }` 블록 추가. HSTS 등 header 블록 없이 passthrough |
| `ops/site.env` | 수정 | MCP 관련 env 추가 (§3.4) |

---

## 5. 데이터 흐름

### 5.1 (S1) Regular tool call (예: `list_work_items`)

```
Claude MCP client
  ──(HTTP POST)──► http://222.234.220.199/mcp/http/api-key/mcp
       Header: x-api-key: <Plane PAT>, x-workspace-slug: <slug>
       Body: {"method":"tools/call","params":{"name":"list_work_items", ...}}

caddy :80
  ──► plane-mcp :8211 (PlaneHeaderAuthProvider)
       → AccessToken { token: <PAT>, claims: {auth_method:"api_key_header", workspace_slug} }

get_plane_client_context()
  → PlaneClient(base_url="http://127.0.0.1:8000", api_key=<PAT>)
       → plane-api :8000  (GET /api/workspaces/<slug>/projects/<pid>/issues/ with X-API-Key)
            → JSON array
       ← Pydantic list[WorkItem]
  ← MCP tool result
```

### 5.2 (S2) `upload_file` (file tool 대표 시나리오)

```
Claude
  ──► upload_file(entity_type="ISSUE_ATTACHMENT", entity_id=<uuid>,
                  name="img.png", mime="image/png",
                  content_base64="iVBORw0KGgo...")

plane-mcp
  1. Plane REST POST /api/assets/v2/
        Body: {name, type:mime, size:len(bytes), entity_type, entity_id}
       ← 201 {upload_data: {url:"http://127.0.0.1:8000/api/assets/local-upload/",
                             fields:{key,policy,x-amz-algorithm,...}},
              asset_id}
  2. base64.b64decode(content_base64)
  3. HTTP POST upload_data.url  (multipart/form-data)
        Fields: upload_data.fields + file=<bytes>
       ← 204 No Content  (Plane 이 is_uploaded=True 승격)
  4. return {asset_id, size, name, mime}

limits:
  - base64 decode 후 size > settings.FILE_SIZE_LIMIT (5MB) → 400 "file too large"
  - base64 decode 후 size > 2MB → tool result 에 warning "consider Plane UI for files > 2MB"
```

### 5.3 (S3) admin tool — `trigger_backup_now`

```
Claude
  ──► trigger_backup_now()

plane-mcp admin_guard decorator
  1. Redis GET mcp:admin:<user_id> → cache hit? 없으면:
  2. Plane REST GET /api/users/me/  (X-API-Key)
       ← {id, email, is_instance_admin, ...}
  3. Redis SET mcp:admin:<user_id> = is_instance_admin, EX=60
  4. is_instance_admin == False → 403 "requires instance admin"
  ↓ True 면 진행

plane-mcp
  → Plane REST POST /api/instances/admin/backup/
       (Plane AdminBackupView 가 permission_classes=[InstanceAdminPermission] 로 재확인)
       → subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                         "Start-ScheduledTask -TaskName PlaneBackup"])
       → {task_id: "<scheduled task id>", started_at: "2026-04-24T18:30:00+09:00"}
  ← Claude
```

### 5.4 (S4) `get_recent_ipban_events` (호스트 FS 직접 접근)

```
Claude (admin)
  ──► get_recent_ipban_events(limit=50)

plane-mcp admin_guard → ok
  → plane_mcp.host.ipban_reader.tail_events(limit=50)
       open D:\Workspace\plane-logs\ipban\stdout.log  (plane 계정 ACL 필요)
       reverse tail → regex parse →
         [{timestamp, level, type:"Banning"|"Un-banning"|"LoginFailure",
           ip, user_name, count}]
  ← events list
```

---

## 6. 에러 처리

| 조건 | 결과 |
|---|---|
| PAT 헤더 누락/무효 | `PlaneHeaderAuthProvider` 401 (upstream 동작) |
| admin tool 을 non-admin PAT 로 호출 | `admin_guard` 403 `"requires is_instance_admin"` |
| plane-api 4xx/5xx | `plane-sdk` 의 `PlaneAPIError` → MCP tool error (status code + message 전파) |
| `get_recent_ipban_events` — log 파일 없음 / read 거부 | `{events: [], warning: "log unavailable: <reason>"}` 2xx 유지 |
| `upload_file` — base64 decode 실패 | 400 `"invalid base64"` |
| `upload_file` — size > FILE_SIZE_LIMIT | Plane 응답 전파 (`400 file too large`) |
| `upload_file` — multipart POST 실패 (204 아님) | tool error `"upload failed: <status>"`, Plane FileAsset 레코드는 stub (is_uploaded=False) 으로 남음. housekeeping 은 Plane 쪽 task |
| `trigger_backup_now` — Start-ScheduledTask 실패 | Plane AdminBackupView 가 5xx 전파 → MCP tool error |
| admin_guard — Redis 불가 | fallback: 매 호출마다 `/api/users/me/` 조회 (캐시 없이 degrade) |
| MCP 서비스 crash | NSSM `AppExit Default=Restart` + `AppRestartDelay 30000` (plane-* 패턴 재사용) |

---

## 7. 보안

### 7.1 인증/인가

- PAT 는 **HTTP Header 전용** (`x-api-key`, `x-workspace-slug`). query string/body 금지 (로그 노출 방지)
- admin_guard 는 **tool call 마다** `is_instance_admin` 확인. 캐시 TTL 60s 후 재확인.
- Plane admin endpoint (`POST /api/instances/admin/backup/`) 는 `InstanceAdminPermission` 독립 체크 — MCP 가 admin_guard 를 우회해도 Plane 에서 한 번 더 막음 (defense-in-depth)

### 7.2 PAT 저장/관리

- 팀원 각자 Plane Web UI 에서 발급 (`/<workspace>/settings/api-tokens/` 또는 유사) — MCP 서버에는 PAT 저장 X
- 팀원은 Claude Desktop / Claude Code / Claude API client 의 MCP 설정에서 header 로 주입
- PAT 폐기 시 Plane 측에서 revoke → 이후 MCP 호출 즉시 401

### 7.3 file upload

- MIME 재검증 + 실행 확장자 denylist + SVG sanitize 는 **보안 #4 (§D)** 에서 Plane 쪽에 추가. MCP 는 Plane 검증 결과를 전파만.
- base64 content 는 메모리에서만 존재 (디스크 임시 파일 생성 X) → plane-mcp 서비스 stdout 로 유출 위험 최소화

### 7.4 호스트 리소스 접근

- `plane-logs/ipban/stdout.log` — 현 ACL 확인 필요. plane 계정이 read 권한 없으면 `icacls D:\Workspace\plane-logs\ipban /grant FKNPOC83BVCHY1L\plane:(R)` 로 grant (plane 계정의 권한 확대 1건 — 보안 #1 잔존 세션에서 승인 필요)
- IPBan 의 `ipban.sqlite` 는 **접근 안 함** (DB 직독 대신 log 기반만)
- `Start-ScheduledTask PlaneBackup` 은 **Plane Django 가 실행** — MCP 서비스는 subprocess 쓰지 않음

### 7.5 upstream cherry-pick 정책

- **월 1회** 수동 검토: `git fetch upstream && git log --oneline upstream/main ^main`
- **pick 허용 조건**: bug fix 또는 upstream 신규 tool 이며 우리 신규 파일 (`tools/files.py`, `tools/admin.py`, `auth/admin_guard.py`, `host/*`) 을 touch 하지 않는 것
- **pick 금지**: upstream refactor 로 `server.py` / `tools/__init__.py` 구조가 바뀐 경우 — 수동 재구현 (주석 `## fork-custom` 표식으로 우리 블록 식별 가능하게)
- 이력은 `.claude/docs/customization/upstream-sync.md` 에 `YYYY-MM-DD <upstream hash> — <요약>` 한 줄씩 누적

### 7.6 비밀값

- MCP 서비스 env 는 `ops/site.env` 공유. 별도 `.mcp_pass` 같은 파일 없음
- `PLANE_API_KEY` 는 설정 안 함 (팀원 Header 로 매 호출 전달, stdio 모드가 아니므로 env 불필요)
- `.redis_pass` 재사용 (Redis DB 2 격리해도 같은 인스턴스)

### 7.7 네트워크

- plane-mcp 는 `127.0.0.1:8211` 만 listen (`--host 127.0.0.1`). 외부 인터페이스 bind 금지
- 외부 노출은 Caddy 80 경유만. 도메인/HTTPS 전환(§C) 시 자동 상속

---

## 8. 테스트

### 8.1 단위 (pytest)

- `tests/test_files.py` — `upload_file`
  - base64 ↔ bytes round-trip
  - mime/size 검증 경로
  - Plane `/api/assets/v2/` 응답 mock → multipart POST mock → asset_id 반환 경로
- `tests/test_admin_guard.py` — decorator 동작
  - `is_instance_admin=True` 통과
  - `is_instance_admin=False` 403
  - Redis 캐시 hit / miss / Redis 불가 fallback
- `tests/test_admin.py` — admin tool 4 종
  - `get_instance_info` (Plane API mock)
  - `list_workspace_health` (여러 workspace 조합)
  - `get_recent_ipban_events` (샘플 log 입력)
  - `trigger_backup_now` (Plane admin endpoint mock)
- `tests/test_ipban_reader.py` — log parse
  - Banning / Un-banning / Login failure 라인 각 1건씩
  - 빈 파일 / 권한 거부 / 파일 부재 edge case

### 8.2 upstream test 유지

`tests/test_integration.py` · `test_oauth_security.py` · `test_stateless_http.py` 는 upstream 그대로. 우리 수정(`server.py` factory 블록) 이 upstream test 를 깨지 않음을 `pytest tests/` 전체 green 으로 확인.

### 8.3 통합 smoke (운영 환경 1회)

운영 Plane (`http://127.0.0.1:8000`) 을 대상으로 MCP 서비스 기동 후:

1. **List workspaces** — regular PAT → `list_workspaces()` → 1건
2. **List work items** — `list_work_items(<ws>, <project>)` → JSON 정상
3. **File roundtrip** — 100B text 로 `upload_file(...)` → asset_id → `download_file(asset_id)` → 받은 URL 에 HTTP GET → 200 + content 일치
4. **admin_guard negative** — regular PAT 로 `trigger_backup_now()` → 403
5. **admin_guard positive** — InstanceAdmin PAT 로 `trigger_backup_now()` → 200, PlaneBackup Task `LastTaskResult=0` 확인

### 8.4 Plane 포크 쪽 단위 테스트

- `apps/api/plane/tests/unit/views/test_admin_backup.py` — `AdminBackupView.post()` 이 `subprocess.run` 을 정확한 인자로 호출하는지 mock (실행 X). permission 체크가 non-admin 403.

---

## 9. 배포 / 운영

### 9.1 NSSM 등록 절차 (신규 세션)

1. Plane 포크 쪽 먼저:
   - `apps/api/plane/app/views/instance/admin.py` + `urls/instance.py` 추가
   - `pytest apps/api/plane/tests/unit/views/test_admin_backup.py` green
   - commit: `feat(fork-mcp): add /api/instances/admin/backup/ endpoint`
   - 개발 트리 → 운영 트리 sync (`git fetch origin && git reset --hard origin/master`)
   - `ops/register-services.ps1` 재실행 (plane-api 재기동, 신규 URL 반영)
   - smoke: InstanceAdmin PAT 로 `curl -X POST .../api/instances/admin/backup/` 200 확인
2. plane-mcp-server 쪽:
   - `plane_mcp/tools/files.py` + `tools/admin.py` + `auth/admin_guard.py` + `host/ipban_reader.py` 구현
   - `server.py` factory 블록 수정
   - `pytest tests/` green (upstream + 신규)
   - commit: `feat: add file/admin tools for plane-fork` + `gitea push`
3. 운영 트리:
   - `ops/register-plane-mcp.ps1` 작성 (NSSM 등록 스크립트)
   - `ops/Caddyfile` 에 `handle /mcp/* { reverse_proxy 127.0.0.1:8211 }` 추가
   - `ops/site.env` 에 MCP env 추가
   - `ops/render-envs.ps1` 실행 (env 재주입)
   - `ops/register-plane-mcp.ps1` 실행 (NSSM 등록)
   - `ops/register-caddy.ps1` 재실행 (Caddyfile 재로드)
   - plane 계정 ACL: `icacls D:\Workspace\plane-logs\ipban /grant FKNPOC83BVCHY1L\plane:(R)` (사용자 승인 필요)
4. smoke § 8.3 전체 수행
5. `.claude/docs/customization/deployment.md` 에 실제 실행 명령/결과 기록

### 9.2 운영 모니터링

- `plane-mcp` NSSM stdout/stderr → `D:\Workspace\plane-logs\mcp\{stdout,stderr}.log`
- PlaneBackup 과 동일 패턴으로 AppRotate 설정
- `Get-Service plane-mcp` 를 `IPBan-watchdog` 확장 대상에 포함 (Plane 배포 worklog §7h / 보안 #1 micro-session 재사용)

### 9.3 upstream sync 프로시저

월 1회:

```bash
git fetch upstream
git log --oneline main..upstream/main
# 검토:
#  - bug fix, 우리 신규 파일 무관 → git cherry-pick <hash>
#  - structural refactor → 수동 재적용 + .claude/docs/customization/upstream-sync.md 기록
git push gitea main
```

---

## 10. 변경 범위 매트릭스

| 저장소 | 디렉토리 | 신규 | 수정 | 삭제 |
|---|---|---|---|---|
| `plane-mcp-server` | `plane_mcp/tools/` | `files.py`, `admin.py` | `__init__.py` | — |
| `plane-mcp-server` | `plane_mcp/auth/` | `admin_guard.py` | — | — |
| `plane-mcp-server` | `plane_mcp/host/` | `__init__.py`, `ipban_reader.py`, `paths.py` | — | — |
| `plane-mcp-server` | `plane_mcp/` | — | `server.py` | — |
| `plane-mcp-server` | `tests/` | `test_files.py`, `test_admin_guard.py`, `test_admin.py`, `test_ipban_reader.py` | — | — |
| `plane-mcp-server` | `.claude/docs/customization/` | `spec.md` (이 문서), `upstream-sync.md`, `tools-reference.md`, `deployment.md` | — | — |
| **Plane 포크** (`D:\Workspace\plane`) | `apps/api/plane/app/views/instance/` | `admin.py` | — | — |
| **Plane 포크** | `apps/api/plane/app/urls/` | — | `instance.py` | — |
| **Plane 포크** | `apps/api/plane/tests/unit/views/` | `test_admin_backup.py` | — | — |
| **운영 트리** (`ops/`, git 외부) | — | `register-plane-mcp.ps1` | `Caddyfile`, `site.env` | — |

---

## 11. 참조

- upstream: <https://github.com/makeplane/plane-mcp-server>
- FastMCP: <https://gofastmcp.com/>
- plane-sdk (PyPI): <https://pypi.org/project/plane-sdk/>
- Plane 배포 worklog: `D:\Workspace\plane\docs\customization\worklog.md`
- Plane 배포 todo: `D:\Workspace\plane\docs\customization\todo.md`
- 보안 감사: `D:\Workspace\plane\docs\customization\security-audit-2026Q2.md`
- 배포 교훈 (§7a NSSM / §7c Task Scheduler / §7g 부하 smoke): worklog.md 해당 섹션

---

## 12. Non-goals (이번 범위에서 제외)

- **응답 필드 축약 refactor** (daou_messenger 패턴) — upstream diff 대폭 확대 → 보류. 구현 중 context 초과가 실측으로 확인되면 tool 단위로 재평가
- **stdio mode** — HTTP 전용. 로컬 1인 개발자 편의 요청 생기면 차후 추가 (upstream 기본 이라 쉬움)
- **OAuth flow** — Header PAT 로 시작. Plane 어드민 OAuth client 등록 + 팀 전환 의사결정 이후 `/mcp/oauth/mcp` 활성
- **도메인/HTTPS** — 보안 #3 (§C) 완료 후 자동 상속
- **외부 오프사이트 백업 연동** — MCP 범위 밖 (security-todo §6)
- **Plane 포크 upstream rebase** — 기존 `D:\Workspace\plane` 의 정책 유지 (이 MCP 프로젝트는 별개)
