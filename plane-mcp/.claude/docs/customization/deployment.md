# Plane MCP Server — Deployment Log

> 운영 배포의 실 명령·결과·이슈를 세션별 블록으로 누적. 다음 배포자가 재현 가능한 수준까지 기록.
> PAT / 비밀값은 `<PAT>` placeholder 로만 기록 (최종 grep 검증 완료).

---

## Session 1 — 2026-04-24 (plane-mcp-v2-deploy)

`plane-mcp-v2-bootstrap` 에서 이관된 6 todo 항목을 실배포까지 끝낸 세션.

### Pre-check

| 항목 | 확인 명령 | 결과 |
|------|----------|------|
| plane-api service | `Get-Service plane-api` | Running |
| PlaneBackup Task | `Get-ScheduledTask -TaskName PlaneBackup` | State=Ready, TaskPath=\\ |
| dev tree | `ls /d/Workspace/plane` | OK (개발 트리) |
| ops tree | `ls /d/Workspace/plane-app/ops` | OK (git 외부) |

### N5 — Upstream sync 초기화

```bash
git remote add upstream https://github.com/makeplane/plane-mcp-server.git
git fetch upstream
git log --oneline master..upstream/main
```

- upstream HEAD `main`: `b4e949d` ("bump version", 2026-04-22)
- local baseline: `ca456fe` = upstream `24565ab`
- Delta: 2 신규 커밋 (`b4e949d`, `9b4b4de`) — 모두 version bump, `skip` 판정
- 생성: `.claude/docs/customization/upstream-sync.md`
- Commit: `e576864`

### N1 — Plane 포크 AdminBackupView + MCP stub 해제

#### Plane fork 변경 (commit `733c57e`)

- `apps/api/plane/license/api/views/admin.py` — `AdminBackupView` 추가 (`subprocess.run powershell.exe Start-ScheduledTask`)
- `apps/api/plane/license/api/views/__init__.py` — export
- `apps/api/plane/license/urls.py` — `admin/backup/` path
- `apps/api/plane/tests/unit/license/test_admin_backup.py` — 6 테스트
- pytest (Plane api venv): **6/6 green**

#### plane-mcp-server stub 해제 (commit `552207f`)

- `plane_mcp/tools/admin.py:trigger_backup_now` — stub → 실 HTTP 호출
- `tests/test_admin.py` — 2 새 테스트 (success / 500 propagation)
- pytest: 48/48 green

### N3 — IPBan log ACL 명시화

```
Before:
  D:\Workspace\plane-logs\ipban  FKNPOC83BVCHY1L\plane:(I)(OI)(CI)(M)
                                 BUILTIN\Administrators:(I)(OI)(CI)(F)
                                 NT AUTHORITY\SYSTEM:(I)(OI)(CI)(F)

Command:
  icacls D:\Workspace\plane-logs\ipban /grant "FKNPOC83BVCHY1L\plane:(R)" /T
  → 3 files processed, 0 failed

After:
  D:\Workspace\plane-logs\ipban  FKNPOC83BVCHY1L\plane:(R)               ← 신규 명시 ACE
                                 FKNPOC83BVCHY1L\plane:(I)(OI)(CI)(M)
                                 BUILTIN\Administrators:(I)(OI)(CI)(F)
                                 NT AUTHORITY\SYSTEM:(I)(OI)(CI)(F)
```

Commit: `992d1c5` (todo 마커만 — 호스트 ACL 은 commit 대상 아님)

### N2 — plane-mcp NSSM + Caddy + `__main__.py` 수정

#### ops/ (git 외부) 신규/수정

- `ops/register-plane-mcp.ps1` 신규 — NSSM install, `ObjectName=.\plane`, `DependOnService=plane-api Redis`, AppEnvironmentExtra 주입, polling 10s + listen 확인
- `ops/Caddyfile` — `handle_path /mcp/* { reverse_proxy 127.0.0.1:8211 }` (strip path)
- `ops/site.env` — `PLANE_MCP_{HTTP_HOST,HTTP_PORT,REDIS_DB,IPBAN_LOG,WORKSPACE_SLUG}` 5 env

#### plane-mcp-server (commit `f84b544`)

- `plane_mcp/__main__.py` — OAuth CLIENT_ID 없으면 header factory 만 mount, host/port env (`PLANE_MCP_HTTP_HOST/PORT`)
  - spec §3.3 loopback-only 준수 (env `127.0.0.1:8211`)

#### 실행

```
PS> .\register-plane-mcp.ps1 -SiteEnv D:\Workspace\plane-app\ops\site.env
 ...
 [OK] plane-mcp registered and running

PS> netstat -an | findstr :8211
  TCP    127.0.0.1:8211         0.0.0.0:0              LISTENING

PS> Restart-Service caddy -Force  # Caddyfile reload
```

기초 smoke (헤더 없이 POST):

```
curl -X POST http://127.0.0.1:8211/http/api-key/mcp → 401 Unauthorized  (직접)
curl -X POST http://127.0.0.1/mcp/http/api-key/mcp → 401 Unauthorized   (Caddy)
```

두 경로 응답 동일 (content-length 301 일치) — 서비스 기동 + Caddy 프록시 정합.

### N4 — Operational smoke 4 시나리오 (B안)

PAT: admin 1개. Non-admin 시나리오(#4) 는 단위 테스트(`test_admin.py`, `test_admin_guard.py`) 48/48 green 로 대체.

| # | Tool | Path | 기대 | 실측 | 판정 |
|---|------|------|------|------|------|
| 0 | `tools/list` (warmup) | Caddy | tool 목록 JSON | 60+ tools | ✅ |
| 1 | `get_me` | Caddy | user JSON with `is_instance_admin:true` | `id=bb3a1a2f-...`, `is_instance_admin:true` | ✅ |
| 2 | `list_projects` | Caddy | project 배열 | Test project 반환 | ✅ |
| 3 | `upload_file` + `download_file` (round-trip) | Caddy | base64 동일 | 1x1 PNG 67B → asset_id=`a9756163-...` → `content_base64` 원본 일치 | ✅ |
| 4 | `trigger_backup_now` (non-admin 거부) | — | 403 상응 | skip (B안) | ⏭ |
| 5 | `trigger_backup_now` (admin) | Caddy | 200 + PlaneBackup `LastTaskResult=0` | **MCP → Plane 경로 통과**; subprocess 에서 `액세스가 거부되었습니다` 500 | 🟨 |

시나리오 5 는 admin_guard / AdminBackupView / Plane 호출 전 경로는 **모두 통과**. `Start-ScheduledTask` 가 .\plane 계정 권한 부족으로 거부 — **별 이슈 (`todo.md` #8)**.

> **2026-04-25 정식 체크리스트로 승격**: 본 N4 의 4 시나리오는 정식 운영 체크리스트 `.claude/docs/customization/test-scenarios.md` §2 (Smoke 8 항목) 으로 확장되었고, 월 1회 회귀 (§3, 21 케이스) 도 함께 정의되었다. 다음 재배포부터는 본 N4 표 대신 `test-scenarios.md` §4 결과 기록 템플릿으로 누적.

#### N4 도중 발견되어 즉시 수정한 2 구조 결함

**발견 1**: `admin_guard` 가 `/api/v1/users/me/` 응답에서 `is_instance_admin` 을 기대했으나 Plane v1 은 이 필드 미반환 → 모든 admin tool 이 "requires instance admin" 으로 거부.
→ Plane fork commit `51a7e94` — `UserEndpoint.get()` 응답에 `is_instance_admin` 추가.

**발견 2**: `plane_mcp/tools/files.py` 가 spec §5.2 의 가정 (`/api/assets/v2/`, 2-step) 대로 구현됐으나 실 Plane 은 workspace/project-scoped 3-step 에 이미지 전용.
→ `files.py` 전면 재작성 (commit `6fae501`) + Plane fork commit `8502563` (`ProjectAssetEndpoint` 에 `APIKeyAuthentication` 추가).

### N6 — User docs + 이 파일

- `.claude/docs/customization/tools-reference.md` 신규 — 7 fork tool 사용자 문서
- 이 `deployment.md` 작성
- `CLAUDE.md` 참조 문서 현황 표 2행 추가
- `todo.md` #1~#6 완료 마커 + 새 #7 (files entity_type matrix) + #8 (PlaneBackup Task 권한) 추가

### 세션 1 사용자 변경 파일 요약

#### plane-mcp-server (`D:\Workspace\plane-mcp-server`, commit 8개)

| Commit | 제목 |
|--------|------|
| `e576864` | docs: initialize upstream sync log |
| `552207f` | feat(tools): wire trigger_backup_now to Plane AdminBackupView |
| `992d1c5` | docs: mark todo #3 complete — IPBan log ACL grant applied |
| `f84b544` | feat(server): make HTTP mode deployable without OAuth client |
| `6fae501` | refactor(tools): rework files.py for Plane v2 project-scoped asset flow |
| (이 commit) | docs: tools-reference + deployment log (N6) |

#### Plane fork (`D:\Workspace\plane`, commit 3개)

| Commit | 제목 |
|--------|------|
| `733c57e` | feat(license): add on-demand PlaneBackup trigger endpoint |
| `51a7e94` | feat(api): expose is_instance_admin on /api/v1/users/me/ |
| `8502563` | feat(asset): accept X-Api-Key on ProjectAssetEndpoint |

Plane fork → 운영 트리 sync: `git pull --ff-only` × 2.

#### ops (`D:\Workspace\plane-app\ops`, git 외부)

- `register-plane-mcp.ps1` 신규
- `Caddyfile` 수정 (/mcp/* handle_path 블록)
- `site.env` 수정 (5 PLANE_MCP_* env)

### 발견된 이슈 / 후속

- `todo.md` #7 — 다른 entity_type 의 파일 tool 지원 (WORKSPACE_LOGO / USER_AVATAR / PAGE_DESCRIPTION 등)
- `todo.md` #8 — plane 계정의 PlaneBackup Task 실행 권한 (현재 `Start-ScheduledTask` 액세스 거부)
- Non-admin PAT 발급 → scenario 4 실 검증 (현재는 단위 테스트로 대체)

### 최종 테스트 / 서비스 상태

- plane-mcp-server fork suite: **49/49 green** + ruff clean
- Plane fork admin_backup unit: **6/6 green**
- Services: `plane-api` Running, `plane-mcp` Running (`127.0.0.1:8211` LISTENING), `caddy` Running
- End-to-end: file upload/download round-trip (1x1 PNG) on live Plane fork

---

## Session 2 — 2026-04-25 (test scenarios documentation)

Session 1 N4 의 ad-hoc 4-시나리오 smoke 를 정식 운영 체크리스트로 승격 + 월간 회귀 21 케이스 정의.

### Pre-check

| 항목 | 결과 |
|------|------|
| `plane-mcp` / `caddy` 서비스 | Running |
| `:8211` LISTENING | OK |
| Plane fork commit 3종 (`51a7e94`, `733c57e`, `8502563`) | 모두 존재 |
| 자격 | admin PAT (id=`bb3a1a2f-...`) + 신규 non-admin PAT (id=`8c1c1102-...`, email `wnwjdals7498@kakao.com`) |
| Test project / issue | id=`92631846-...` (Test, identifier=TEST), issue id=`e51a5999-...` |
| non-admin 멤버십 | workspace + Test project 둘 다 멤버 (project member_role=20) |

### 산출물

| 파일 | 동작 | Commit |
|------|------|--------|
| `.claude/docs/customization/test-scenarios-design.md` | 신규 (260줄) | `90bc1d1` + 자체 점검 fixup `19dd273` |
| `.claude/docs/customization/test-scenarios-plan.md` | 신규 (924줄, 11 task) | `487048b` |
| `.claude/docs/customization/test-scenarios.md` | 신규 (~795줄) | `fe1f6cb` (skeleton) → `4586e0b` (Smoke S0..S7) → `9d181e2` (Smoke fixup) → `c89118a` (Regression R1..R7) → `e160deb` (Regression fixup) → `d878eb1` (§4) → `fcfa2d4` (§5) → `85c3c48` (부록 A/B) |
| `CLAUDE.md` | §"참조 문서 현황" 표에 3행 추가 | `517c9ee` |
| `.claude/docs/customization/deployment.md` | N4 footnote + 본 Session 2 블록 | `517c9ee` + (이 commit) |

### Dry-run 결과 (Task 1 — R1-b / R1-e 가정 검증)

| 케이스 | 측정 결과 | spec 정정? |
|--------|----------|-----------|
| **R1-b** (2.5MB zero-byte JPEG) | 200 + `warning="consider Plane UI for files > 2MB"`, asset_id=`dc3fc411-2845-40b3-9ddf-55122c0de6f3` | 정정 불필요 — Plane 매직 검증 안 함, spec §6 가정 일치 |
| **R1-e** (`"not_b64!!!"`) | `isError=true`, `text="invalid base64"` | 정정 불필요 — `validate=False` 임에도 짧은 invalid input 은 ToolError raise, spec §6 가정 일치 |

### Self-validation (Task 9 — §2 Smoke 1회 실행)

| 일시 | 트리거 | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | 비고 |
|------|--------|-----|-----|-----|-----|-----|-----|-----|-----|------|
| 2026-04-25 | docs self-validation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | S7 의도된 fail (todo.md #8) — 그 외 7/7 통과, 체크리스트 정합 |

S5 의 응답에서 `instance_id` 는 null, `captured_at` 만 채워짐 → spec §6 의 "Plane 미설정 instance 면 모두 null + captured_at 만 — degrade 응답도 통과" 분기에 해당.

### Validation error 메시지 측정 (Task 4 — R5-b / R6-b)

| Tool | 입력 | 측정 메시지 | spec 인용 형식 |
|------|------|------------|-----------------|
| `list_workspace_health` | `limit=51` | exact `limit must be between 1 and 50` | exact match (R5-b) |
| `get_recent_ipban_events` | `limit=1001` | `Error calling tool 'get_recent_ipban_events': limit must be between 1 and 1000` | substring `limit must be between 1 and 1000` (R6-b) |

차이 원인: `list_workspace_health` 는 `ToolError` raise (fastmcp 가 그대로 노출), `get_recent_ipban_events` 는 `ValueError` raise (fastmcp 가 `Error calling tool 'X':` prefix 로 wrap). 산출물 §3 line 318 callout 에 명시.

### 부수 효과 / cleanup 후보

- Task 1 dry-run 의 R1-b: zero-byte 2.5MB asset (`dc3fc411-...`) 이 Test issue 에 첨부됨. Plane Web 에서 수동 삭제 권장.
- Task 9 self-validation 의 S4: 1×1 PNG asset (`3ac75fd5-...`) 추가. 누적될 수 있으니 정기 cleanup.

### 후속

- 다음 정기 upstream sync (예정 2026-05-31) 에서 §3 Regression 첫 실행 — 결과를 본 deployment.md 에 새 행으로 추가.
- R7-a 의 의도된 fail 은 `todo.md` #8 (PlaneBackup Task 권한) 해결 시 자연 통과로 전환.
- 회귀 빈도가 월 1회를 넘어서거나 케이스 수가 ~30 을 넘으면 보조 PowerShell 스크립트 (옵션 2) 로 승격 검토 — 현재는 수동 cURL 만.
