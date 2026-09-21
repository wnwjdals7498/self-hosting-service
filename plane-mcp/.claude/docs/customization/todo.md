# Plane MCP Server — Follow-up Todo

> `plane-mcp-v2-bootstrap` 프로젝트(code-supporter 워크플로우, 2026-04-24)에서 **1단계 범위 축소 결정**으로 뒤로 미룬 작업을 재개 가능한 형태로 고정한다.
>
> - **deferred ≠ permanent out-of-scope**. 본 파일의 항목은 "이번 범위에서만 뒤로 미룸". 영구 제외는 `spec.md` §12 Non-goals 참조.
> - 각 항목은 (a) 사유·spec 참조, (b) 선행/의존, (c) 재개 시 첫 액션 을 포함한다.
> - 항목 완료 시 해당 블록 상단에 `✅ 완료 (YYYY-MM-DD, 완료 세션/PR 링크)` 를 추가하고 최소 1분기 동안 유지.

**최종 갱신**: 2026-04-25 (#9 추가 — Plane fork page API plane-sdk 호환 404)
**관련**: `spec.md` (브레인스토밍 확정본), `CLAUDE.md` (참조 문서 현황 표)

---

## 1. Plane 포크 `AdminBackupView` 구현

> ✅ **완료 (2026-04-24, plane-mcp-v2-deploy/N1)** — Plane 포크 commit `733c57e`, plane-mcp-server stub 해제 (이번 커밋). 6/6 Plane unit test + 48/48 plane-mcp-server test green. 실 smoke 는 N4 (todo #4) 에서.

- **저장소**: `D:\Workspace\plane`
- **spec 참조**: §2.1, §4.2, §5.3
- **사유**: 이번 범위는 plane-mcp-server 코드만. Plane 포크 수정은 별 PR/세션 필요.
- **blocks**: `trigger_backup_now` tool 의 `NotImplementedError` stub 해제

### 파일 변경

| 파일 | 유형 | 내용 |
|---|---|---|
| `apps/api/plane/app/views/instance/admin.py` | 신규 | `AdminBackupView(APIView)` — `permission_classes=[InstanceAdminPermission]`, `post()` 에서 `subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Start-ScheduledTask -TaskName PlaneBackup"])` → `{task_id, started_at, pid}` 반환 |
| `apps/api/plane/app/urls/instance.py` | 수정 | `path("instances/admin/backup/", AdminBackupView.as_view(), name="instance-admin-backup")` 추가 |
| `apps/api/plane/app/permissions/__init__.py` | 수정 | `InstanceAdminPermission` export 확인/추가 |
| `apps/api/plane/tests/unit/views/test_admin_backup.py` | 신규 | `subprocess.run` mock, permission 체크 (non-admin 403), 성공 경로 |

### 선행 / 의존

- 호스트에 `PlaneBackup` Task Scheduler job 이 등록되어 있어야 함 (`D:\Workspace\plane\docs\customization\worklog.md` §7c 참조)
- Plane 포크의 기존 `InstanceAdminPermission` 존재 확인

### 재개 시 첫 액션

1. `cd /d/Workspace/plane && git status` — 운영/개발 트리 어느 쪽인지 확인
2. `apps/api/plane/app/permissions/__init__.py` 읽어 `InstanceAdminPermission` 존재 확인
3. 위 표대로 신규 파일 작성 → `pytest apps/api/plane/tests/unit/views/test_admin_backup.py` green
4. 완료 후 **이 저장소 plane-mcp-server 쪽의 `tools/admin.py:trigger_backup_now`** 를 스텁에서 실 구현으로 교체

---

## 2. Ops 스크립트 (운영 트리, git 외부)

> ✅ **완료 (2026-04-24, plane-mcp-v2-deploy/N2)** — `ops/register-plane-mcp.ps1` 신규 + `Caddyfile` `handle_path /mcp/*` 블록 + `site.env` PLANE_MCP_* 5 env. NSSM `plane-mcp` Running, `127.0.0.1:8211` LISTENING (loopback only 확인), 직접·Caddy 양쪽 경로 모두 401 Unauthorized 정상 (인증 없음). `__main__.py` 에 fork-custom 블록 추가 — OAuth CLIENT_ID 없으면 header-PAT 만 mount + host/port env 우선.
>
> ops/ 산출물은 git 외부 트리. 구성은 `D:\Workspace\plane-app\ops\` 참조.

- **저장소**: `D:\Workspace\plane-app/ops/` (git 외부)
- **spec 참조**: §4.3, §9.1, §3.4
- **사유**: 이번 범위는 코드까지. 운영 배포는 실 Plane 기동 + 서비스 등록 수반.
- **선행**: plane-mcp-server 코드 완료 (N1~N5) + 본 todo #1 완료

### 파일 변경

| 파일 | 유형 | 내용 |
|---|---|---|
| `ops/register-plane-mcp.ps1` | 신규 | NSSM `plane-mcp` 등록. `.\plane` 계정, `python.exe -m plane_mcp http`, port 8211, `DependOnService=plane-api Redis`, `AppEnvironmentExtra` 로 MCP env 주입. `register-services.ps1` 의 Remove-ZombieProcesses + polling 패턴 재사용 |
| `ops/Caddyfile` | 수정 | `handle /mcp/* { reverse_proxy 127.0.0.1:8211 }` 블록 추가 — HSTS 등 header 블록 없이 passthrough |
| `ops/site.env` | 수정 | `PLANE_BASE_URL=http://127.0.0.1:8000`, `PLANE_INTERNAL_BASE_URL=http://127.0.0.1:8000`, `PLANE_WORKSPACE_SLUG=plane-windows-server-2025`, `PLANE_MCP_HTTP_HOST=127.0.0.1`, `PLANE_MCP_HTTP_PORT=8211`, `REDIS_HOST=127.0.0.1`, `REDIS_PORT=6379`, `REDIS_DB=2`, `REDIS_PASSWORD=<ops/.redis_pass 값>`, `PLANE_MCP_IPBAN_LOG=D:\Workspace\plane-logs\ipban\stdout.log` |

### 재개 시 첫 액션

1. `ops/render-envs.ps1` 로 env 재렌더
2. `ops/register-plane-mcp.ps1` 실행 → NSSM 등록
3. `ops/register-caddy.ps1` 재실행 → Caddy 재로드
4. `Get-Service plane-mcp` 상태 확인

---

## 3. Plane 계정 IPBan 로그 읽기 권한 부여

> ✅ **완료 (2026-04-24, plane-mcp-v2-deploy/N3)** — `icacls ... /grant "FKNPOC83BVCHY1L\plane:(R)" /T` 3개 파일 처리 (디렉토리 + stderr.log + stdout.log). After 에 `plane:(R)` 명시 ACE 가 상속(`(I)(OI)(CI)(M)`) 과 함께 존재. 실 read 검증은 N4 `get_recent_ipban_events` smoke 에서.

- **spec 참조**: §7.4
- **사유**: `get_recent_ipban_events` tool 의 실 파일 접근 필요. mock 단위 테스트는 이미 통과 (N2).
- **영향**: plane 계정 권한 확대 1건 — **사용자 승인 필요** (보안 #1 잔존 세션 규칙)

### 명령

```powershell
icacls D:\Workspace\plane-logs\ipban /grant FKNPOC83BVCHY1L\plane:(R)
```

### 재개 시 첫 액션

1. 현재 ACL 확인: `icacls D:\Workspace\plane-logs\ipban`
2. 사용자 승인
3. 위 명령 실행
4. plane 계정으로 `Get-Content D:\Workspace\plane-logs\ipban\stdout.log -TotalCount 5` 테스트

---

## 4. 운영 smoke (spec §8.3 전체 5 시나리오)

> ✅ **완료 (2026-04-24, plane-mcp-v2-deploy/N4, B안)** — admin PAT 1개로 4개 시나리오 수행. Scenario 1 (`get_me`) ✅, 2 (`list_projects`) ✅, 3 (upload/download round-trip, 1x1 PNG) ✅, 5 (`trigger_backup_now` MCP→Plane 경로) 🟨 Task 권한 이슈(#8). Scenario 4 는 단위 테스트(48/48 green)로 대체. 상세 로그는 `deployment.md` Session 1.

- **spec 참조**: §8.3
- **선행**: todo #1 + #2 + #3 + 실 Plane 인스턴스(`http://127.0.0.1:8000`) 기동

### 시나리오

1. **List workspaces** — regular PAT → `list_workspaces()` → 1건
2. **List work items** — `list_work_items(<ws>, <project>)` → JSON 정상
3. **File roundtrip** — 100B text 로 `upload_file(...)` → asset_id → `download_file(asset_id, include_content_base64=True)` → content 일치
4. **admin_guard negative** — regular PAT 로 `trigger_backup_now()` → 403 상응 (ToolError "requires instance admin")
5. **admin_guard positive** — InstanceAdmin PAT 로 `trigger_backup_now()` → 200, `Get-ScheduledTask PlaneBackup` `LastTaskResult=0` 확인

### 재개 시 첫 액션

1. `Get-Service plane-api plane-mcp caddy` — 전부 Running 확인
2. PAT 2개 발급 (admin, non-admin)
3. MCP client 로 위 5개 시나리오 순차 실행
4. 결과를 `.claude/docs/customization/deployment.md` 에 기록 (todo #6 와 연계)

---

## 5. `upstream-sync.md` 이력 파일

> ✅ **완료 (2026-04-24, plane-mcp-v2-deploy/N5)** — 파일 생성 + 첫 fetch entry. upstream HEAD `b4e949d` (2 version-bump 커밋, skip). 다음 예정 2026-05-31.

- **spec 참조**: §7.5
- **사유**: 월 1회 수동 `git fetch upstream` + cherry-pick 이력 누적 위치
- **trigger**: 첫 `git fetch upstream` + `git cherry-pick <hash>` 수행 시점

### 파일

`D:\Workspace\plane-mcp-server\.claude\docs\customization\upstream-sync.md`

### 포맷

```markdown
# Upstream Sync Log

| Date | Upstream Hash | Action | Summary |
|------|---------------|--------|---------|
| YYYY-MM-DD | <hash> | cherry-pick / skip / manual-reapply | <한 줄 요약> |
```

---

## 6. `tools-reference.md`, `deployment.md`

> ✅ **완료 (2026-04-24, plane-mcp-v2-deploy/N6)** — 두 파일 모두 작성. tools-reference 는 7 fork tool 의 Scope/Args/Returns/Errors/Example + Claude Desktop 설정 부록. deployment 는 Session 1 (plane-mcp-v2-deploy) 실행 로그 전체.

- **spec 참조**: §10 매트릭스
- **사유**: 구현 완료 + 운영 배포 후 작성. 현 범위와 무관.

---

## 7. 파일 tool 의 다른 entity_type 지원 (ISSUE_ATTACHMENT 외)

- **발견 시점**: 2026-04-24, plane-mcp-v2-deploy N4 smoke Scenario 3 (round-trip). 초기 `files.py` 는 spec §5.2 의 2-step + 경로 `/api/assets/v2/` 를 가정했으나 실 Plane 포크는 workspace/project scoped 3-step 이고 이미지 전용.
- **현재 상태 (2026-04-24)**: `ISSUE_ATTACHMENT` 만 완전 동작. round-trip 검증됨.
- **미지원**: `WORKSPACE_LOGO` (WorkspaceFileAssetEndpoint), `PROJECT_COVER` (WorkspaceFileAssetEndpoint), `USER_AVATAR` / `USER_COVER` (UserAssetsV2Endpoint), `PAGE_DESCRIPTION`, `COMMENT_DESCRIPTION`, `DRAFT_ISSUE_DESCRIPTION`
- **추가 시 고려**:
  - 각 endpoint 의 `authentication_classes` 에 `APIKeyAuthentication` 추가 필요 (plane 포크 fork-custom 수정 — ProjectAssetEndpoint 는 이미 완료)
  - `upload_file` 에 `entity_type` 파라미터 재도입 + 분기 로직
  - `list_file_assets` 는 Plane v2 가 list-by-entity 미제공 — plane-sdk legacy `/work-items/<id>/attachments/` 쓰거나 Plane 포크에 list endpoint 신규

### 재개 시 첫 액션

1. Plane 포크 `WorkspaceFileAssetEndpoint`, `UserAssetsV2Endpoint` 에 `APIKeyAuthentication` 추가 (fork-custom commit)
2. plane-mcp-server `files.py` 의 `upload_file` 에 `entity_type` 파라미터 복원 + 엔드포인트 분기
3. 테스트 추가: 각 entity_type 별 mock

---

## 8. PlaneBackup Task 실행 권한 (plane 계정)

- **발견 시점**: 2026-04-24, plane-mcp-v2-deploy N4 Scenario 5.
- **증상**: `trigger_backup_now` → MCP admin_guard ✅ → Plane AdminBackupView ✅ → subprocess `Start-ScheduledTask -TaskName PlaneBackup` → `액세스가 거부되었습니다` → 500 전파.
- **원인 후보**:
  - PlaneBackup Task 의 "Run with highest privileges" 체크 해제 상태
  - Task Scheduler 의 security descriptor 에 plane 계정 Execute 권한 누락
  - Task RunAsUser 가 다른 계정 (Administrator 등) 이라 plane 계정이 trigger 불가
- **조사/수정 경로**:
  1. `Get-ScheduledTask PlaneBackup | Format-List *` — Principal, Actions, RunLevel 확인
  2. `schtasks /query /tn PlaneBackup /xml` — 전체 설정 XML
  3. 필요 시 `register-backup-task.ps1` (`D:\Workspace\plane-app\ops`) 재실행 — Task 재등록 with plane-executable permission
  4. 또는 Task XML 의 `<Principals>` 섹션에 plane 계정을 추가 (security descriptor 수정)
- **검증**: 재수정 후 `trigger_backup_now` smoke 재실행 → 200 + 30초 후 `Get-ScheduledTaskInfo PlaneBackup` 의 `LastTaskResult=0`

### 파일

| 파일 | 내용 |
|---|---|
| `D:\Workspace\plane-mcp-server\.claude\docs\customization\tools-reference.md` | 신규 7 tool (files 3 + admin 4) 의 입출력·에러·예시를 사용자 관점에서 기술 |
| `D:\Workspace\plane-mcp-server\.claude\docs\customization\deployment.md` | 운영 배포 실 명령·결과·이슈 (NSSM, Caddy, env, smoke 결과) |

### 재개 시 첫 액션

- tools-reference: N5 완료 후 각 tool 의 docstring + 명세서 §1 입출력을 합산해 마크다운 생성
- deployment: todo #4 smoke 실행 직후 기록

---

## 9. Plane fork 의 page API 와 plane-sdk 호환 — 404 회피책

- **발견 시점**: 2026-04-25, FORK 프로젝트(`Fork Customization`, id=`7084c15f-...`) 등록 도중. 11 issue + 2 module 까지는 정상 생성, summary page 시도에서 막힘.
- **증상**: 다음 두 호출 모두 `HTTP 404: Not Found`.
  - `mcp__plane__create_project_page` (project_id 명시) → 404
  - `mcp__plane__create_workspace_page` (workspace context 자동) → 404
- **원인 후보**:
  - plane-sdk 가 호출하는 path (`/api/v1/workspaces/<slug>/projects/<pid>/pages/` 또는 그 변형) 가 Plane 포크에서 disabled 또는 다른 경로에 mount
  - Plane 의 page feature 가 EE-only 이거나 fork 가 community-version pages router 를 import 안 함
  - 또는 plane-mcp-server 가 사용하는 plane-sdk 버전의 page endpoint 가 fork API 와 drift
- **영향**: 운영 검증 자체엔 영향 없음 (issue list + module 만으로 tracking 충분). 다만 fork tool 사용자가 page 기능을 호출하면 모두 실패 — 사용자 보고 가치 있음.
- **현재 회피**: 본 repo `.claude/docs/customization/deployment.md` Session 2 + 본 todo 가 summary 역할. Plane 안에선 issue 리스트 자체가 색인.

### 조사 경로

1. `D:\Workspace\plane` 실행 중인 Plane fork 의 router 확인:
   - `apps/api/plane/api/urls/page.py` (또는 동등한 파일) 가 root urls 에 include 되어 있는지
   - `grep -r "pages" D:\Workspace\plane\apps\api\plane\api\urls\` 로 실 endpoint path 측정
2. plane-mcp-server 의 page tool 구현 확인:
   - `plane_mcp/tools/pages.py` 의 `create_project_page` / `create_workspace_page` 가 호출하는 plane-sdk 메서드
   - plane-sdk 가 hit 하는 정확한 URL 을 로깅 or `httpx` event hook 으로 캡처
3. URL 차이가 확인되면:
   - **(a)** Plane fork 에 해당 router include 추가 (community-version 의 pages app 살리기)
   - **(b)** plane-mcp-server 의 page tool 들을 fork URL 에 맞게 재작성 (fork-custom)
   - **(c)** page tool 들을 NotImplementedError stub 으로 마크 + tools-reference 에 미지원 명시

### 재개 시 첫 액션

1. `curl.exe -sS -i -X GET http://127.0.0.1:8000/api/v1/workspaces/develop/projects/92631846-fd55-4a21-8b6d-407898b6735e/pages/ -H "x-api-key: <admin PAT>"` 으로 raw 응답 확인 — 404 / 405 / 200 어느 쪽인지
2. Plane fork 의 `apps/api/plane/api/urls/__init__.py` 또는 `apps/api/plane/api/urls/page.py` 존재/include 여부
3. 결과에 따라 위 (a)/(b)/(c) 중 선택 + 별 fork-custom commit 또는 plane-mcp-server PR

### 영향 범위 (page 관련 plane-mcp tool)

- `mcp__plane__create_project_page` / `create_workspace_page` (이번 세션 검증)
- `mcp__plane__retrieve_project_page` / `retrieve_workspace_page` (검증 전)
- `mcp__plane__update_workspace_features` 같은 유사 endpoint 호환 가능성 — 별도 검증

---

## 참조

- Fork 커스터마이즈 스펙: `./spec.md`
- 이번 프로젝트(plane-mcp-v2-bootstrap) 산출물: `C:\Users\joojm\docs\code-supporter\plane-mcp-v2-bootstrap\`
- Plane 배포 측 todo/worklog: `D:\Workspace\plane\docs\customization\{todo,worklog}.md`
