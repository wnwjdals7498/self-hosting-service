# Fork Tools Test Scenarios — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spec `.claude/docs/customization/test-scenarios-design.md` 가 정의한 fork tools 운영 검증 체크리스트(`.claude/docs/customization/test-scenarios.md`) 와 연동 문서 갱신을 한 commit-가능 단위로 끝까지 작성한다.

**Architecture:** 단일 마크다운 산출물 + 두 개 부수 파일(`CLAUDE.md`, `deployment.md`) 한 줄씩 갱신. 코드 변경 없음. 첫 단계로 spec §6.1 의 zero-byte JPEG 가정과 `validate=False` 영향(R1-b / R1-e)을 실 환경 dry-run 으로 확인한 뒤 합격 조건을 fix-up — 이후 모든 섹션은 결과를 반영한 채 한 번에 정확하게 작성.

**Tech Stack:** Markdown only. 검증용으로 `curl.exe` (Windows PowerShell), `git` (Bash 환경에서 `git -C D:\\Workspace\\plane-mcp-server` 형태로 호출 가능). pytest / Python 코드 작성 없음.

> **Plan 위치 결정**: 본 plan 은 spec 과 같은 슬롯 `.claude/docs/customization/` 에 둔다. brainstorming skill 의 default 인 `docs/superpowers/plans/` 가 아닌 이유는 본 repo 가 `customization/` 디렉토리 하나에 fork 관련 모든 명세·로그를 모으는 패턴이기 때문 (`spec.md`, `deployment.md`, `tools-reference.md`, `todo.md`, `upstream-sync.md`).

---

## File Structure

| 파일 | 동작 | 책임 |
|------|------|------|
| `.claude/docs/customization/test-scenarios.md` | **Create** | Smoke + Regression 체크리스트 본문, 결과 기록 템플릿, 트러블슈팅 매트릭스, escape/추출 부록 — 운영자가 한 자리에 앉아 따라 가는 자체완결 문서 |
| `.claude/docs/customization/test-scenarios-design.md` | **Modify** (조건부) | Task 1 의 dry-run 결과로 spec §6 의 R1-b / R1-e 합격 조건이 바뀌면 spec 을 정정. 변동 없으면 미수정 |
| `CLAUDE.md` | **Modify** | §"참조 문서 현황" 표에 `test-scenarios.md` 행 1줄 추가 |
| `.claude/docs/customization/deployment.md` | **Modify** | Session 1 N4 표 끝에 "정식 체크리스트는 ... 참조" 문장 1줄 추가 |

---

## Task 0: Pre-flight — 환경 가정 검증

체크리스트가 참조할 환경이 실 호스트에 살아 있는지 확인. 한 가지라도 빠지면 이후 task 가 모두 막힌다.

**Files:** 없음 (read-only 검증)

- [ ] **Step 1: 두 PAT 가 환경 변수로 설정되어 있는지 확인**

PowerShell 세션 시작 시:
```powershell
$env:PLANE_ADMIN_PAT      # 비어 있으면 발급해서 설정
$env:PLANE_NONADMIN_PAT   # 이번 세션 초반에 검증 완료된 토큰
$env:PLANE_WORKSPACE_SLUG = "develop"
$env:PLANE_TEST_PROJECT_ID  # N4 의 Test project UUID
$env:PLANE_TEST_ISSUE_ID    # N4 의 issue UUID
```
Expected: 5개 변수 모두 값 존재. 없는 게 있으면 `tools-reference.md` 또는 `deployment.md` N4 에서 찾아 set.

- [ ] **Step 2: NSSM `plane-mcp` 서비스 Running 확인**

PowerShell:
```powershell
Get-Service plane-mcp
```
Expected: `Status: Running`. 다른 상태면 `Start-Service plane-mcp` 후 1분 대기.

- [ ] **Step 3: `:8211` LISTENING 확인**

PowerShell:
```powershell
netstat -an | Select-String ":8211"
```
Expected: `TCP 127.0.0.1:8211 ... LISTENING` 한 줄.

- [ ] **Step 4: Caddy Running 확인**

PowerShell:
```powershell
Get-Service caddy
```
Expected: `Status: Running`.

- [ ] **Step 5: Plane fork 의 의존 commit 3종이 운영 트리에 들어가 있는지 확인**

Bash (또는 Git Bash):
```bash
for c in 51a7e94 733c57e 8502563; do
  git -C /d/Workspace/plane log --oneline | grep "^$c" || echo "MISSING: $c"
done
```
Expected: 출력 없음 (3개 모두 존재). `MISSING:` 한 줄이라도 나오면 `deployment.md` N1·N4 의 fork sync 절차 재확인 필요 — plan 중단.

- [ ] **Step 6: 워크스페이스 멤버십 확인 (non-admin user)**

PowerShell — non-admin PAT 으로 `list_projects` 호출, `PLANE_TEST_PROJECT_ID` 가 응답에 포함되는지 확인:
```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"list_projects\",\"arguments\":{\"workspace_slug\":\"develop\"}}}'
curl.exe -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_NONADMIN_PAT" `
  -H "x-workspace-slug: develop" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body
```
Expected: 응답 SSE 의 `result.structuredContent.results` 배열에 `$env:PLANE_TEST_PROJECT_ID` 포함. 없으면 운영자가 Plane Web 에서 non-admin user 를 해당 project member 로 초대해야 R1-g/R2-d 가 200 받음.

---

## Task 1: Dry-run R1-b / R1-e 가정 검증

`files.py` 코드와 spec 가정을 실 호스트에서 1회 호출해 확인 — 여기서 결과가 spec §6.1 가정과 다르면 spec 을 미세 조정.

**Files:**
- Read: `plane_mcp/tools/files.py:127-135` (mime/decode/size 검증 순서)
- Modify (조건부): `.claude/docs/customization/test-scenarios-design.md:108-114` (R1-b / R1-e 행)

- [ ] **Step 1: R1-b — zero-byte 2.5MB JPEG 더미가 Plane 매직 검증을 통과하는가**

PowerShell:
```powershell
$zerob64 = [Convert]::ToBase64String([byte[]]::new(2500000))
$body = @"
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"upload_file","arguments":{"workspace_slug":"$env:PLANE_WORKSPACE_SLUG","project_id":"$env:PLANE_TEST_PROJECT_ID","entity_id":"$env:PLANE_TEST_ISSUE_ID","name":"dryrun-2_5mb.jpg","mime":"image/jpeg","content_base64":"$zerob64"}}}
"@
$body | Out-File -FilePath dryrun-b.json -Encoding utf8
curl.exe -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  --data-binary @dryrun-b.json
```
Expected — 두 가지 가능 outcome:
- **(가능 1) 200 + `warning: "consider Plane UI for files > 2MB"`** → spec §6 R1-b 합격 조건 그대로 유지
- **(가능 2) `plane api error: <status> ...`** (Plane 매직 검증 실패) → spec §6 R1-b 합격 조건을 "Plane 4xx 반환" 으로 정정 필요

- [ ] **Step 2: R1-e — `"not_b64!!!"` 가 `invalid base64` 로 떨어지는가**

PowerShell:
```powershell
$body = @"
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"upload_file","arguments":{"workspace_slug":"$env:PLANE_WORKSPACE_SLUG","project_id":"$env:PLANE_TEST_PROJECT_ID","entity_id":"$env:PLANE_TEST_ISSUE_ID","name":"dryrun-bad.png","mime":"image/png","content_base64":"not_b64!!!"}}}
"@
$body | Out-File -FilePath dryrun-e.json -Encoding utf8
curl.exe -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  --data-binary @dryrun-e.json
```
Expected — 두 가지 가능 outcome:
- **(가능 1) `invalid base64`** → 합격 조건 그대로
- **(가능 2) base64 decode 가 silent 하게 빈/짧은 byte 로 통과 → Plane 으로 호출이 진입 → `plane api error: ...` 또는 200** → 합격 조건을 "decode 가 일부 통과해 Plane 까지 갈 수 있음 — 핵심은 ToolError 발생 자체" 로 fold-down. 정확한 결과 메시지를 측정해 spec 에 명시.

> 코드 근거: `files.py:79` 가 `base64.b64decode(content_base64, validate=False)` 사용. `validate=False` 는 non-base64 alphabet 문자를 silent 무시하므로 `"not_b64!!!"` 의 `_b6` 등 일부가 살아남아 짧은 byte 를 만들 수 있음.

- [ ] **Step 3: dry-run 결과 기록**

`.claude/docs/customization/deployment.md` 본 세션 블록(아직 없음 — Task 8 에서 추가) 또는 임시 메모. 결과를 한 줄 메모:
```
dry-run R1-b: <200+warning | plane 4xx>  / R1-e: <invalid base64 | plane 4xx | 200>
```

- [ ] **Step 4 (조건부): spec 정정 commit**

Step 1 또는 Step 2 결과가 spec §6 의 합격 조건과 다르면 `.claude/docs/customization/test-scenarios-design.md` 의 해당 행을 수정.

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/test-scenarios-design.md
git -C /d/Workspace/plane-mcp-server commit -m "docs(spec): refine R1-b/R1-e pass criteria after dry-run

Dry-run on live host showed <observed behaviour>; updated R1-b/R1-e
acceptance criteria to match actual response shape."
```

dry-run 결과가 spec 과 일치하면 commit 생략하고 다음 task 로.

---

## Task 2: 산출물 골격 + §0 + §1 작성

**Files:**
- Create: `.claude/docs/customization/test-scenarios.md` (전체 골격 + §0 적용 범위 + §1 Pre-flight)

- [ ] **Step 1: 파일 생성 — 헤더 + 섹션 마크 + §0 + §1 본문**

`.claude/docs/customization/test-scenarios.md`:

```markdown
# Plane MCP Server — Fork Tools Test Scenarios

> Fork-custom 7 tool (files 3 + admin 4) 검증용 수동 체크리스트. 두 레벨 — Smoke (재배포 후 2~5분) / Regression (월 1회 upstream sync 후 15~30분).
>
> - 설계 명세: `.claude/docs/customization/test-scenarios-design.md`
> - 실행 환경: Windows Server 2025 + PowerShell + `curl.exe`
> - 자격: admin PAT + non-admin PAT (둘 다 `develop` 멤버)

## 0. 적용 범위

**대상**:
- fork-custom 7 tool: `upload_file`, `download_file`, `list_file_assets`, `get_instance_info`, `list_workspace_health`, `get_recent_ipban_events`, `trigger_backup_now`
- HTTP transport `/http/api-key/mcp` (header-PAT)
- Caddy reverse proxy (`/mcp/...` strip-path) + 직결 (`:8211`) 양쪽

**비대상**: stdio / SSE / OAuth transport, upstream 55+ tool, Plane 자체 5xx, `PLANE_INTERNAL_BASE_URL` 토글, pytest E2E.

## 1. Pre-flight — 환경 변수 & PAT 셋업

### 1.1. 환경 변수 (PowerShell 세션 시작 시)

```powershell
$env:PLANE_BASE_URL_LOCAL = "http://127.0.0.1:8211"
$env:PLANE_BASE_URL_CADDY = "http://127.0.0.1"
$env:PLANE_WORKSPACE_SLUG = "develop"
$env:PLANE_ADMIN_PAT      = "plane_api_..."
$env:PLANE_NONADMIN_PAT   = "plane_api_..."
$env:PLANE_TEST_PROJECT_ID = "<UUID>"
$env:PLANE_TEST_ISSUE_ID   = "<UUID>"
```

### 1.2. 두 PAT sanity 체크

admin / non-admin 각각 `get_me` 1회 — `is_instance_admin` 필드가 `true` / `false` 이면 통과.

```powershell
function Test-PatRole {
  param([string]$pat, [bool]$expectAdmin)
  $body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_me\",\"arguments\":{}}}'
  $resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
    -H "Authorization: Bearer $pat" `
    -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
    -H "content-type: application/json" `
    -H "accept: application/json, text/event-stream" `
    -d $body
  $line = $resp | Select-String -Pattern '^data: '
  $json = ($line -replace '^data: ','') | ConvertFrom-Json
  $isAdmin = $json.result.structuredContent.is_instance_admin
  if ($isAdmin -ne $expectAdmin) { throw "PAT role mismatch: expected admin=$expectAdmin got $isAdmin" }
  Write-Host "PAT role ok (is_instance_admin=$isAdmin)"
}
Test-PatRole $env:PLANE_ADMIN_PAT    $true
Test-PatRole $env:PLANE_NONADMIN_PAT $false
```

> 한 PAT 라도 mismatch 면 본문 시작하지 말고 PAT 발급/계정 권한부터 점검 (`tools-reference.md` §공통규약).

## 2. Smoke 체크리스트 (8 항목, 2~5분)
<!-- Task 3 에서 채움 -->

## 3. Regression 체크리스트 (21 케이스, 15~30분)
<!-- Task 4 에서 채움 -->

## 4. 결과 기록 템플릿
<!-- Task 5 에서 채움 -->

## 5. 트러블슈팅 매트릭스
<!-- Task 6 에서 채움 -->

## 부록 A — cmd / PowerShell / bash escape 가이드
<!-- Task 7 에서 채움 -->

## 부록 B — SSE 응답 핵심 필드 추출
<!-- Task 7 에서 채움 -->
```

- [ ] **Step 2: 파일 존재 확인**

```bash
ls -la /d/Workspace/plane-mcp-server/.claude/docs/customization/test-scenarios.md
```
Expected: 1 file with non-zero size.

- [ ] **Step 3: Commit**

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/test-scenarios.md
git -C /d/Workspace/plane-mcp-server commit -m "docs: scaffold fork tools test scenarios checklist (skeleton + pre-flight)

Adds the empty section markers that follow-up commits will fill. §0 scope
and §1 pre-flight (env vars + two-PAT sanity check) are complete."
```

---

## Task 3: §2 Smoke 체크리스트 (S0~S7) 작성

**Files:**
- Modify: `.claude/docs/customization/test-scenarios.md` — `## 2. Smoke 체크리스트 (8 항목, 2~5분)` 섹션 채움

산출물의 §2 본문은 표 1개 + 8 개 sub-section. 표는 한눈 요약, sub-section 은 실 실행 명령. 각 항목은 다음 4부 구조:

```
### S<N>. <항목명>

**합격 조건**: <한 줄>
**호출**:
\`\`\`powershell
... curl.exe ...
\`\`\`
**검증**: <Get-McpField 호출 또는 grep 한 줄>
**실패 시 1차 확인**: <§5 트러블슈팅 어느 행 참고>
```

- [ ] **Step 1: §2 표 작성**

```markdown
## 2. Smoke 체크리스트 (8 항목, 2~5분)

> 모두 admin PAT 1개로. 한 항목 평균 30초.

| # | 항목 | tool | 경로 | 합격 조건 |
|---|------|------|------|----------|
| S0 | 이중 401 | (요청만) | Caddy + 직결 | 둘 다 401, content-length 동일 |
| S1 | tools/list warmup | — | Caddy | fork tool 7 종 모두 존재 |
| S2 | get_me | `get_me` | Caddy | `is_instance_admin:true` |
| S3 | list_projects | `list_projects` | Caddy | `PLANE_TEST_PROJECT_ID` 포함 |
| S4 | upload→download round-trip | `upload_file`+`download_file` | Caddy | 1×1 PNG → asset_id → base64 byte-identical |
| S5 | get_instance_info | `get_instance_info` | Caddy | `instance_id` 또는 `captured_at` 채워짐 |
| S6 | get_recent_ipban_events | `get_recent_ipban_events` | Caddy | `events` 배열 + `warning` 없음/positive |
| S7 | trigger_backup_now (200) | `trigger_backup_now` | Caddy | 200 + `task_name:"PlaneBackup"` (실 PlaneBackup 결과 검증 안 함) |
```

- [ ] **Step 2: S0 sub-section — 이중 401**

```markdown
### S0. 이중 401 (인증 헤더 없이)

**합격 조건**: Caddy 와 직결 양쪽 모두 401, `Content-Length` 동일.

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_me\",\"arguments\":{}}}'
curl.exe -sS -i -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body | Select-String -Pattern "^HTTP/|^Content-Length:"

curl.exe -sS -i -X POST $env:PLANE_BASE_URL_LOCAL/http/api-key/mcp `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body | Select-String -Pattern "^HTTP/|^Content-Length:"
```
**검증**: 두 명령 모두 `HTTP/1.1 401 Unauthorized`. Content-Length 값이 동일 (오타·헤더 변형이 없다는 뜻).
**실패 시**: §5 표 1·2행 참고.
```

- [ ] **Step 3: S1 sub-section — tools/list warmup**

```markdown
### S1. tools/list warmup

**합격 조건**: 응답 `result.tools` 의 `name` 필드에 fork tool 7 종이 모두 등장.

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body
$line = $resp | Select-String -Pattern '^data: '
$json = ($line -replace '^data: ','') | ConvertFrom-Json
$expected = @('upload_file','download_file','list_file_assets','get_instance_info','list_workspace_health','get_recent_ipban_events','trigger_backup_now')
$names = $json.result.tools.name
$missing = $expected | Where-Object { $_ -notin $names }
if ($missing) { throw "fork tools missing: $($missing -join ', ')" } else { Write-Host "S1 ok — 7/7 fork tools present" }
```
**실패 시**: §5 표 3행 (`register_fork_tools` wiring 회귀).
```

- [ ] **Step 4: S2~S7 sub-section 작성**

S2~S7 도 같은 4부 포맷으로. 각 항목의 실 명령은 `tools-reference.md` 의 cURL 예시를 PowerShell escape (Task 1 의 escape 패턴) 로 변환:

S2 — `get_me`, 검증 `is_instance_admin -eq $true`
S3 — `list_projects`, 검증 `$json.result.structuredContent.results.id -contains $env:PLANE_TEST_PROJECT_ID`
S4 — `upload_file` 으로 1×1 PNG (67B) `iVBORw0KGgo...`, 받은 asset_id 로 `download_file` `include_content_base64=true`. PowerShell:
```powershell
$png1x1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
# upload → asset_id 추출 → download → content_base64 == $png1x1 검증
```
검증: `if ($download.content_base64 -ne $png1x1) { throw "S4 mismatch" }`
S5 — `get_instance_info`, 검증 `$json.result.structuredContent.instance_id` 또는 `captured_at` 둘 중 하나 truthy
S6 — `get_recent_ipban_events` `limit=10`, 검증 `events -is [Array]` 그리고 `warning` 이 `"file not found"` / `"permission denied"` 가 아닐 것
S7 — `trigger_backup_now`, 검증 `task_name -eq "PlaneBackup"` (status 200 자체만, PlaneBackup 결과는 무시)

각 sub-section 마다 실 실행 가능한 PowerShell 블록을 그대로 넣는다 — 운영자가 복붙해서 쓸 수 있어야 함.

- [ ] **Step 5: §2 작성 후 산출물 미리보기**

```bash
sed -n '/## 2. Smoke/,/## 3. Regression/p' /d/Workspace/plane-mcp-server/.claude/docs/customization/test-scenarios.md | head -120
```
Expected: 표 + S0~S7 sub-section 8 개 모두 보임.

- [ ] **Step 6: Commit**

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/test-scenarios.md
git -C /d/Workspace/plane-mcp-server commit -m "docs: write smoke checklist (S0..S7) for fork tools test scenarios

Eight items covering dual-path 401, tools/list warmup, get_me, list_projects,
upload/download round-trip, get_instance_info, get_recent_ipban_events, and
trigger_backup_now (200-stub only)."
```

---

## Task 4: §3 Regression 체크리스트 (R1~R7) 작성

**Files:**
- Modify: `.claude/docs/customization/test-scenarios.md` — `## 3. Regression 체크리스트` 섹션 채움

§3 의 본문은 prerequisite 한 줄 + R1~R7 그룹 7 sub-section + 21 케이스 표. 각 그룹 sub-section 은 표 + 케이스별 실 명령 블록 묶음.

- [ ] **Step 1: §3 prerequisite + 전체 케이스 표 작성**

```markdown
## 3. Regression 체크리스트 (21 케이스, 15~30분)

**Prerequisite (R0)**: §2 Smoke 8 항목 전체 통과.

| 그룹 | Tool | 케이스 | 입력 | 합격 조건 |
|------|------|--------|------|----------|
| R1 | `upload_file` | R1-a | PNG 1×1 5KB, admin | 200, asset_id UUID |
| R1 | `upload_file` | R1-b | JPEG 2.5MB zero-byte 더미, admin | <Task 1 dry-run 결과> |
| R1 | `upload_file` | R1-c | mime=`application/pdf`, admin | `unsupported mime` |
| R1 | `upload_file` | R1-d | 6MB 페이로드 zero-byte 더미, admin | `file too large` |
| R1 | `upload_file` | R1-e | `content_base64="not_b64!!!"`, admin | <Task 1 dry-run 결과> |
| R1 | `upload_file` | R1-f | random UUID `entity_id`, admin | `plane api error: 404 ...` |
| R1 | `upload_file` | R1-g | R1-a 와 동일, **non-admin** | 200 |
| R2 | `download_file` | R2-a | R1-a asset_id, `include_content_base64=false`, admin | 200, presigned_url 채워짐, content_base64=null |
| R2 | `download_file` | R2-b | 같은 asset_id, `include_content_base64=true`, admin | content_base64 가 R1-a 원본과 일치 |
| R2 | `download_file` | R2-c | random UUID asset_id, admin | `plane api error: 404 ...` |
| R2 | `download_file` | R2-d | R2-a, **non-admin** | 200 |
| R3 | `list_file_assets` | R3-a | 임의 args | `NotImplementedError: Plane fork's /api/assets/v2/ does not expose a list-by-entity endpoint — see .claude/docs/customization/todo.md #7` 정확 일치 |
| R4 | `get_instance_info` | R4-a | admin | 200, `version` 또는 `instance_id` 채워짐 |
| R4 | `get_instance_info` | R4-b | **non-admin** | `requires instance admin` |
| R5 | `list_workspace_health` | R5-a | `limit=20`, admin | `workspaces` 배열, 항목에 `slug`/`member_count` 채워짐 |
| R5 | `list_workspace_health` | R5-b | `limit=51` | validation error (1..50) |
| R5 | `list_workspace_health` | R5-c | **non-admin** | `requires instance admin` |
| R6 | `get_recent_ipban_events` | R6-a | `limit=10`, admin | `events` 배열, 빈 배열이면 `warning` 확인 |
| R6 | `get_recent_ipban_events` | R6-b | `limit=1001` | validation error (1..1000) |
| R6 | `get_recent_ipban_events` | R6-c | **non-admin** | `requires instance admin` |
| R7 | `trigger_backup_now` | R7-a | admin | **200 만 통과** — Plane 측 5xx (`todo.md` #8 미해결) 면 fail 표기 (의도된 알람) |
| R7 | `trigger_backup_now` | R7-b | **non-admin** | `requires instance admin` |
```

> Task 1 의 dry-run 결과로 R1-b·R1-e 의 "합격 조건" 셀이 결정됨. dry-run 결과를 그대로 인용.

- [ ] **Step 2: R1 sub-section (`upload_file`, 7 케이스)**

각 케이스마다 PowerShell block (페이로드는 here-string `@" ... "@` 으로) + 검증 한 줄. R1-a ~ R1-g 순서대로.

```markdown
### R1. `upload_file`

R1 의 모든 케이스는 `$env:PLANE_TEST_ISSUE_ID` 의 issue 에 첨부 시도.

#### R1-a — PNG 1×1 5KB, admin
```powershell
$png5kb = [Convert]::ToBase64String((1..5120 | ForEach-Object {0x42}))  # 5120-byte 더미; 또는 fixture 사용
# 정확한 1x1 PNG 가 필요하면 S4 의 67B 페이로드 그대로 + 파일명만 다르게.
... curl.exe ...
```
**검증**: `$json.result.structuredContent.asset_id` 가 UUID 형식.

#### R1-b — JPEG 2.5MB zero-byte 더미, admin
```powershell
$big = [Convert]::ToBase64String([byte[]]::new(2500000))
... curl.exe with mime=image/jpeg, content_base64=$big ...
```
**검증**: <Task 1 dry-run 결과 그대로 옮김>.

#### R1-c — unsupported mime
```powershell
... curl.exe with mime=application/pdf, content_base64=$png5kb ...
```
**검증**: `$json.result.content[0].text` 가 `unsupported mime` 으로 시작.
... (R1-d ~ R1-g 동일 포맷) ...
```

각 R1-c~R1-g 의 PowerShell block 도 모두 실 실행 가능한 형태로 작성. R1-g 는 `Authorization: Bearer $env:PLANE_NONADMIN_PAT` 로 변경.

- [ ] **Step 3: R2 sub-section (`download_file`, 4 케이스)**

R2-a 의 asset_id 는 직전 R1-a 응답에서 추출:
```powershell
# R1-a 실행 후
$assetId = $json.result.structuredContent.asset_id
# R2-a:
$body = "{\"jsonrpc\":\"2.0\",...,\"asset_id\":\"$assetId\",\"include_content_base64\":false}"
... curl.exe ...
```

**검증**:
- R2-a: `presigned_url` 매치 `^http.*sig=`, `content_base64 -eq $null`
- R2-b: `content_base64 -eq $png5kb` (정확 일치)
- R2-c: 응답 `content[0].text` 가 `plane api error: 404` 으로 시작
- R2-d: R2-a 와 동일하지만 `Authorization: Bearer $env:PLANE_NONADMIN_PAT`

- [ ] **Step 4: R3 sub-section (`list_file_assets`, 1 케이스)**

```markdown
#### R3-a — NotImplementedError
```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"list_file_assets\",\"arguments\":{\"workspace_slug\":\"develop\",\"project_id\":\"...\",\"entity_id\":\"...\"}}}'
... curl.exe ...
```
**검증**: `$json.result.content[0].text` 가 정확히 (substring 포함):
`Plane fork's /api/assets/v2/ does not expose a list-by-entity endpoint — see .claude/docs/customization/todo.md #7`
```

- [ ] **Step 5: R4 sub-section (`get_instance_info`, 2 케이스)**

R4-a (admin): `$json.result.structuredContent.version -or .instance_id` 둘 중 하나 truthy.
R4-b (non-admin): `$json.result.content[0].text` 정확 일치 `requires instance admin`.

- [ ] **Step 6: R5 sub-section (`list_workspace_health`, 3 케이스)**

R5-a: `$json.result.structuredContent.workspaces.Count -gt 0`, 첫 항목에 `slug` + `member_count` 채워짐.
R5-b: validation error 메시지 — fastmcp 가 Pydantic validation error 를 어떻게 노출하는지 확인 후 정확 문구 명시 (Task 1 dry-run 한번 더 — `limit=51` 을 admin PAT 로 호출, 응답 메시지를 그대로 옮김).
R5-c: `requires instance admin`.

> **Step 6 sub-task**: `limit=51` 한 번 호출해 fastmcp 가 응답하는 validation error 정확 문구 측정 후 합격 조건에 그대로 인용. 추측 금지.

- [ ] **Step 7: R6 sub-section (`get_recent_ipban_events`, 3 케이스)**

R6-a: `events -is [Array]`, 빈 배열이면 `warning` 확인 (현 운영에서 IPBan log 가 비어있을 수 있음 — 빈 배열은 정상).
R6-b: validation error (1..1000) — `limit=1001` 한 번 호출해 fastmcp 응답 정확 문구를 spec 으로 측정 (R5-b 와 같은 방식).
R6-c: `requires instance admin`.

- [ ] **Step 8: R7 sub-section (`trigger_backup_now`, 2 케이스)**

R7-a: 호출만. 응답이 200 + `task_name="PlaneBackup"` 이면 PASS, 그 외 (특히 `plane api error: 500 ... 액세스가 거부`) 면 FAIL — 의도된 알람.
R7-b: `requires instance admin`.

```markdown
> **R7 의 의도된 fail**: `todo.md` #8 미해결 동안 R7-a 는 fail 로 남는다. PlaneBackup Task 가 `.\plane` 계정 권한 부족으로 거부됨. #8 해결 시 자연 통과.
```

- [ ] **Step 9: §3 작성 후 산출물 미리보기**

```bash
sed -n '/## 3. Regression/,/## 4. 결과 기록/p' /d/Workspace/plane-mcp-server/.claude/docs/customization/test-scenarios.md | wc -l
```
Expected: ~250 라인 이상 (21 케이스 × ~10 라인).

- [ ] **Step 10: Commit**

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/test-scenarios.md
git -C /d/Workspace/plane-mcp-server commit -m "docs: write regression checklist (R1..R7, 21 cases) for fork tools

R1 covers upload_file (7 cases incl. zero-byte dummies), R2 download_file (4),
R3 list_file_assets (1, NotImplementedError), R4..R6 admin tools with
admin/non-admin/validation triplets each, R7 trigger_backup_now (2). R7-a is
expected to fail until todo.md #8 lands — intentional alarm."
```

---

## Task 5: §4 결과 기록 템플릿 작성

**Files:**
- Modify: `.claude/docs/customization/test-scenarios.md` — `## 4. 결과 기록 템플릿` 섹션 채움

- [ ] **Step 1: §4 본문 작성**

```markdown
## 4. 결과 기록 템플릿

체크리스트 수행 후 `deployment.md` 의 새 세션 블록에 한 줄씩 누적.

### 4.1. Smoke 결과 (한 줄)

```markdown
| 일시 | 트리거 | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | 비고 |
|------|--------|-----|-----|-----|-----|-----|-----|-----|-----|------|
| 2026-MM-DD HH:MM | NSSM 재시작 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |  |
```

### 4.2. Regression 결과 (한 줄 + 실패 상세)

```markdown
| 일시 | upstream HEAD | R1 | R2 | R3 | R4 | R5 | R6 | R7 | 실패 항목 상세 |
|------|---------------|-----|-----|-----|-----|-----|-----|-----|----------------|
| 2026-MM-DD | upstream/main = abc123 | ✅(7/7) | ✅(4/4) | ✅(1/1) | ✅(2/2) | ✅(3/3) | ✅(3/3) | ❌(0/2) | R7-a 500 — todo #8 미해결 |
```

### 4.3. 기록 위치 규약

- 한 운영 이벤트 = 한 행. 이벤트 = NSSM 재시작 / 의존성 업그레이드 / upstream sync / 호스트 패치 등.
- `R<X>` 셀의 `(N/M)` 은 통과/전체. 실패 케이스 ID 를 "실패 항목 상세" 에 명시.
- `R7-a` 의 의도된 fail 은 비고에 `(intentional, todo.md #8)` 표기. 그 외 fail 은 별 줄로 root cause 기록.
```

- [ ] **Step 2: Commit**

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/test-scenarios.md
git -C /d/Workspace/plane-mcp-server commit -m "docs: add result recording templates (smoke + regression) to test-scenarios"
```

---

## Task 6: §5 트러블슈팅 매트릭스 작성

**Files:**
- Modify: `.claude/docs/customization/test-scenarios.md` — `## 5. 트러블슈팅 매트릭스` 섹션 채움

- [ ] **Step 1: §5 본문 작성**

```markdown
## 5. 트러블슈팅 매트릭스

| 증상 | 가능 원인 | 1차 확인 명령 |
|------|----------|--------------|
| S0 직결 401 + Caddy 502/404 | Caddy 미기동 또는 Caddyfile 오타 | `Get-Service caddy` ; `caddy validate --config D:\Workspace\plane-app\ops\Caddyfile` |
| S0 양쪽 connection refused | NSSM `plane-mcp` 미기동 | `Get-Service plane-mcp` ; `netstat -an \| Select-String ":8211"` |
| S1 fork 7 종 누락 | `register_fork_tools()` wiring 회귀 | `pytest /d/Workspace/plane-mcp-server/tests/test_server_wiring.py -v` |
| S2 admin PAT 인데 `is_instance_admin:false` | Plane fork commit `51a7e94` 미반영 | `git -C /d/Workspace/plane log --oneline \| Select-String 51a7e94` |
| S4 upload 200 + download base64 mismatch | Plane v2 asset 3-step flow 회귀 | `plane_mcp/tools/files.py` 코드 vs `tools-reference.md` flow 비교 |
| S6 `events:[]` + `warning:"file not found"` | IPBan 로그 경로/ACL 회귀 | `icacls D:\Workspace\plane-logs\ipban` ; NSSM `AppEnvironmentExtra` 의 `PLANE_MCP_IPBAN_LOG` 확인 |
| S7 / R7-a `Start-ScheduledTask ... 액세스가 거부` | `todo.md` #8 미해결 | 알려진 이슈, R7-a fail 그대로 두고 #8 진행 시 재시험 |
| 모든 항목 `Parse error: Expecting value: line 1 column 1` | cmd single quote escape 오류 | 부록 A 참고 — PowerShell `curl.exe` 사용 또는 `--data-binary @file.json` |
| `tools/call` 응답 SSE 가 아닌 JSON 직접 | `accept` 헤더 누락 | 모든 호출에 `-H "accept: application/json, text/event-stream"` 포함 |
| `requires instance admin` 이 admin PAT 인데 발생 | admin_guard 캐시 stale (60s TTL) | 60s 대기 후 재시도; 재발 시 Plane fork `is_instance_admin` 응답 직접 확인 |
```

- [ ] **Step 2: Commit**

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/test-scenarios.md
git -C /d/Workspace/plane-mcp-server commit -m "docs: add troubleshooting matrix to test-scenarios

Maps 10 observable symptoms to the 1st-line probe command an operator
should run before deeper digging."
```

---

## Task 7: 부록 A + 부록 B 작성

**Files:**
- Modify: `.claude/docs/customization/test-scenarios.md` — `## 부록 A`, `## 부록 B`

- [ ] **Step 1: 부록 A — escape 가이드**

```markdown
## 부록 A — cmd / PowerShell / bash escape 가이드

같은 `get_me` 1회 호출을 3개 셸에서 그대로 동작하는 형태.

### A.1. PowerShell (권장)

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_me\",\"arguments\":{}}}'
curl.exe -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: develop" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body
```

> **PowerShell 함정**: `curl` 은 `Invoke-WebRequest` 의 alias 이므로 반드시 `curl.exe` 로 명시. 그렇지 않으면 `-H` 옵션 형식이 달라 401 이 아닌 parse error 가 떨어진다.

### A.2. cmd.exe

```cmd
curl -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp ^
  -H "Authorization: Bearer %PLANE_ADMIN_PAT%" ^
  -H "x-workspace-slug: develop" ^
  -H "content-type: application/json" ^
  -H "accept: application/json, text/event-stream" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_me\",\"arguments\":{}}}"
```

> **cmd 함정**: single quote (`'...'`) 를 string literal 로 인식하지 않아 페이로드가 통째로 깨진다. 반드시 double quote + 내부 `\"` escape 또는 파일에 저장해 `--data-binary @body.json` 사용.

### A.3. bash (참고)

```bash
curl -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp \
  -H "Authorization: Bearer $PLANE_ADMIN_PAT" \
  -H "x-workspace-slug: develop" \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_me","arguments":{}}}'
```
```

- [ ] **Step 2: 부록 B — SSE 응답 핵심 필드 추출**

```markdown
## 부록 B — SSE 응답 핵심 필드 추출

응답이 `event: message\ndata: {...}` 포맷이라 핵심 필드 한 개를 보려면 한 단계 가공이 필요.

### B.1. PowerShell helper

```powershell
function Get-McpField {
  param(
    [Parameter(Mandatory)] $body,         # curl.exe 의 stdout (string 또는 string[])
    [Parameter(Mandatory)] [string] $jq   # 예: 'is_instance_admin', 'asset_id'
  )
  $line = $body | Select-String -Pattern '^data: '
  if (-not $line) { throw "no data: line in SSE response" }
  $json = ($line.Line -replace '^data: ','') | ConvertFrom-Json
  return $json.result.structuredContent.$jq
}

# 사용:
$resp = curl.exe ... 
Get-McpField $resp 'is_instance_admin'
```

### B.2. bash + jq

```bash
curl -sS ... | grep '^data:' | sed 's/^data: //' | jq '.result.structuredContent.is_instance_admin'
```

### B.3. 에러 응답에서 메시지 추출

`isError: true` 일 때 메시지는 `result.content[0].text` 에 있다 (`structuredContent` 가 비어 있음):

```powershell
$line = $resp | Select-String -Pattern '^data: '
$json = ($line -replace '^data: ','') | ConvertFrom-Json
if ($json.result.isError) { Write-Host "ERROR: $($json.result.content[0].text)" }
```
```

- [ ] **Step 3: 산출물 전체 길이 확인**

```bash
wc -l /d/Workspace/plane-mcp-server/.claude/docs/customization/test-scenarios.md
```
Expected: ~500~700 라인 (모든 섹션 포함).

- [ ] **Step 4: Commit**

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/test-scenarios.md
git -C /d/Workspace/plane-mcp-server commit -m "docs: add appendices A (escape guide) and B (SSE field extraction)"
```

---

## Task 8: 연동 문서 갱신 — `CLAUDE.md` + `deployment.md`

**Files:**
- Modify: `CLAUDE.md` — §"참조 문서 현황" 표
- Modify: `.claude/docs/customization/deployment.md` — N4 표 끝 주석

- [ ] **Step 1: `CLAUDE.md` 표에 1행 추가**

`CLAUDE.md` 의 §"참조 문서 현황" 표 (현재 9개 행 — `Fork 커스터마이즈 스펙` ~ `DB 참조`) 에서 마지막 행 (`DB 참조 ... 해당 없음`) 위에 1행 삽입:

```
| 운영 검증 체크리스트 (Smoke + Regression) | `.claude/docs/customization/test-scenarios.md` | ✅ 존재 (2026-04-25) |
| 시나리오 설계 spec | `.claude/docs/customization/test-scenarios-design.md` | ✅ 존재 (2026-04-25) |
```

> 두 문서를 둘 다 등재. spec 은 변경 가이드, scenarios 는 실 체크리스트.

- [ ] **Step 2: `deployment.md` N4 표에 1줄 footnote**

`deployment.md` 의 `### N4 — Operational smoke 4 시나리오 (B안)` 표 직후, 다음 단락(`#### N4 도중 발견되어 즉시 수정한 2 구조 결함`) 앞에 1 단락 추가:

```markdown
> **정식 체크리스트로 승격됨 (2026-04-25)**: 본 N4 의 4 시나리오는 정식 운영 체크리스트 `.claude/docs/customization/test-scenarios.md` §2 (Smoke 8 항목) 으로 확장되었고, 월 1회 회귀 (§3, 21 케이스) 도 함께 정의되었다. 다음 재배포부터는 본 N4 표 대신 위 체크리스트의 §4 결과 기록 템플릿으로 누적.
```

- [ ] **Step 3: Commit (두 파일 한꺼번에)**

```bash
git -C /d/Workspace/plane-mcp-server add CLAUDE.md .claude/docs/customization/deployment.md
git -C /d/Workspace/plane-mcp-server commit -m "docs: link test-scenarios.md from CLAUDE.md doc index and deployment.md N4

Adds two rows to the doc-index in CLAUDE.md (the spec + the checklist) and
back-links from deployment.md N4 so that future redeploys use the formal
checklist instead of the ad-hoc N4 table."
```

---

## Task 9: 체크리스트 자체로 1회 Smoke 실행 — self-validation

체크리스트 본문이 운영 환경에서 그대로 동작하는지를 자기 자신의 §2 Smoke 8 항목을 따라 1회 실행해 검증한다. 이 단계 통과 = 체크리스트 정합.

**Files:** 없음 (read-only 검증; 결과는 다음 단계에서 deployment.md 에 기록)

- [ ] **Step 1: §1.1 환경 변수 셋업 그대로 따라하기**

`.claude/docs/customization/test-scenarios.md` 의 §1.1 PowerShell 블록을 PowerShell 세션에서 그대로 실행. 빠진 변수가 있으면 — 본 plan Task 0 으로 회귀.

- [ ] **Step 2: §1.2 두 PAT sanity 체크 그대로 실행**

`Test-PatRole` 함수 정의 + 호출 2번. 둘 다 `PAT role ok ...` 메시지 떨어지면 통과.

- [ ] **Step 3: §2 S0~S7 순차 실행**

각 sub-section 의 PowerShell 블록을 순서대로 실행. 한 항목씩 합격 조건 확인 후 다음으로.

- [ ] **Step 4: 발견된 오타·escape 누락 인라인 수정**

S0~S7 중 하나라도 합격 조건과 다르게 동작하면 — **체크리스트의 결함**: 명령 자체가 잘못. spec 의 합격 조건이 잘못된 게 아니라 산출물 표현이 잘못된 것이므로:
- 명령 인라인 수정 (Edit tool)
- 즉시 다시 실행해 통과 확인
- 한 줄짜리 fix-up commit

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/test-scenarios.md
git -C /d/Workspace/plane-mcp-server commit -m "docs(fixup): correct <S?> command after self-validation run"
```

- [ ] **Step 5: 8 항목 모두 통과 확인**

PowerShell 콘솔에 `S0..S7 ok` 8 메시지 모두 나오면 통과. 다음 task.

---

## Task 10: 결과 기록 + 최종 인계

**Files:**
- Modify: `.claude/docs/customization/deployment.md` — Session 2 블록 추가 (이번 세션 결과)

- [ ] **Step 1: Session 2 블록 작성**

`deployment.md` 마지막에 세션 2 추가:

```markdown
---

## Session 2 — 2026-04-25 (test scenarios documentation)

`plane-mcp-v2-deploy` Session 1 의 N4 ad-hoc smoke 를 정식 체크리스트로 승격.

### 산출물

| 파일 | 동작 | Commit |
|------|------|--------|
| `.claude/docs/customization/test-scenarios-design.md` | 신규 | `90bc1d1` (브레인스토밍 출력) + 자체 점검 fixup |
| `.claude/docs/customization/test-scenarios-plan.md` | 신규 | (이 plan 자체) |
| `.claude/docs/customization/test-scenarios.md` | 신규 | Task 2~7 의 5 commit (skeleton + S0..S7 + R1..R7 + 결과/트러블슈팅 + 부록) |
| `CLAUDE.md` | 수정 (1행) | Task 8 |
| `.claude/docs/customization/deployment.md` | 수정 (이 블록) | Task 8 + Task 10 |

### Dry-run 결과 (R1-b / R1-e)

- R1-b 실측: <Task 1 Step 1 결과>
- R1-e 실측: <Task 1 Step 2 결과>
- spec 정정 여부: <yes (Task 1 Step 4 commit) / no — spec 가정과 일치>

### Self-validation (§2 Smoke)

| 일시 | 트리거 | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | 비고 |
|------|--------|-----|-----|-----|-----|-----|-----|-----|-----|------|
| 2026-04-25 HH:MM | docs self-validation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 체크리스트 정합 검증 |

### 후속

- 다음 정기 upstream sync (예정 2026-05-31) 에서 §3 Regression 첫 실행 — 결과를 본 표에 새 행으로 추가.
- R7-a 의 의도된 fail 은 `todo.md` #8 (PlaneBackup Task 권한) 해결 시 자연 통과로 전환.
```

> Task 1 의 dry-run 실측값을 `<...>` 자리에 그대로 옮길 것.

- [ ] **Step 2: 최종 commit**

```bash
git -C /d/Workspace/plane-mcp-server add .claude/docs/customization/deployment.md
git -C /d/Workspace/plane-mcp-server commit -m "docs(deployment): record session 2 — test scenarios checklist landed

Session 2 block captures dry-run results, self-validation smoke run, and
linkage to the new test-scenarios.md / test-scenarios-design.md / -plan.md."
```

- [ ] **Step 3: 최종 git log 확인**

```bash
git -C /d/Workspace/plane-mcp-server log --oneline -15
```
Expected: 본 plan 의 task 별 commit 이 시간순으로 보임 — `90bc1d1` (spec) → spec self-review fix → scaffold → S/R/template/troubleshoot/appendix → CLAUDE+deploy 링크 → self-validation fixup (있다면) → session 2.

- [ ] **Step 4: 사용자에게 인계**

운영자에게 한 문단 인계:
> 새 운영 체크리스트 `.claude/docs/customization/test-scenarios.md` 살림. 다음 재배포부터는 §2 Smoke 8 항목으로 (2~5분), 다음 upstream sync (예정 2026-05-31) 에서 §3 Regression 21 케이스 (15~30분). 결과 누적은 `deployment.md` 의 새 세션 블록에. R7-a 의 의도된 fail 은 `todo.md` #8 해결 시 자연 통과.

---

## Self-Review (작성자 확인용)

### Spec coverage

| spec 섹션 | 구현 task |
|-----------|-----------|
| §2.1 파일 위치 (`.claude/docs/customization/test-scenarios.md`) | Task 2 |
| §2.3 적용 범위 (대상/비대상) | Task 2 §0 |
| §2.4 환경 가정 | Task 2 §1.1 |
| §3 문서 구조 | Task 2 (skeleton) + Task 3~7 (각 섹션) |
| §4 §1 Pre-flight 명세 | Task 2 §1.1, §1.2 |
| §5 §2 Smoke 8 항목 | Task 3 |
| §6 §3 Regression 21 케이스 | Task 4 |
| §6.1 zero-byte 가정 | Task 1 (dry-run) → Task 4 R1-b/R1-e 합격 조건 인용 |
| §7.1 Smoke 결과 표 | Task 5 |
| §7.2 Regression 결과 표 | Task 5 |
| §8 트러블슈팅 매트릭스 | Task 6 |
| §9 부록 A escape 가이드 | Task 7 |
| §10 부록 B SSE 추출 helper | Task 7 |
| §11 연동 문서 갱신 (`CLAUDE.md`, `deployment.md`) | Task 8 |
| §12 의존성 (Plane fork commit 3종, IPBan 로그) | Task 0 (Pre-flight 검증) |
| §13 의도된 알람 (R7-a) | Task 4 R7 sub-section + Task 6 §5 트러블슈팅 |
| §14 비대상 | Task 2 §0 |
| §15 후속 | Task 10 deployment.md "후속" 단락 |

→ 모든 spec 섹션이 task 에 매핑됨. 갭 없음.

### Placeholder scan

- "<Task 1 dry-run 결과>" — Task 1 Step 4 가 명시적으로 spec 으로 결과를 옮기고, Task 4 Step 1/2 가 spec 의 그 행을 인용하라고 지시. placeholder 가 아니라 **데이터 의존성** — plan 실행 시점에 채워질 정확한 값. spec 이 dry-run 결과를 단일 source of truth 로 가짐.
- `<...>` 가 Task 9 fixup commit 메시지에 있음 — 실 fixup 시점에 어느 S 항목이었는지 채워질 자리. 이것도 placeholder 가 아니라 실행 시 결정 변수.
- "TBD"/"TODO"/"implement later" 등 일반 placeholder 는 plan 본문에 없음.

### Type consistency

- 산출물 파일명: `test-scenarios.md` 모든 task 에서 일관.
- spec 파일명: `test-scenarios-design.md` 모든 task 에서 일관.
- 환경 변수명: `PLANE_ADMIN_PAT` / `PLANE_NONADMIN_PAT` / `PLANE_TEST_PROJECT_ID` / `PLANE_TEST_ISSUE_ID` / `PLANE_WORKSPACE_SLUG` / `PLANE_BASE_URL_LOCAL` / `PLANE_BASE_URL_CADDY` 모든 task 일관.
- 케이스 ID: `S0..S7`, `R1-a..R7-b` 일관.
- helper 함수: `Test-PatRole`, `Get-McpField` — 정의된 곳 (Task 2 §1.2, Task 7 부록 B) 와 사용처 (Task 3, 4, 9) 의 시그니처 일치.

→ 일관성 갭 없음.
