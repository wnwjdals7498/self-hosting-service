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

> 모두 admin PAT 1개로. 한 항목 평균 30초.

| # | 항목 | tool | 경로 | 합격 조건 |
|---|------|------|------|----------|
| S0 | 이중 401 | (요청만) | Caddy + 직결 | 둘 다 401, content-length 동일 |
| S1 | tools/list warmup | — | Caddy | fork tool 7 종 모두 존재 |
| S2 | get_me | `get_me` | Caddy | `is_instance_admin:true` |
| S3 | list_projects | `list_projects` | Caddy | `PLANE_TEST_PROJECT_ID` 포함 |
| S4 | upload→download round-trip | `upload_file`+`download_file` | Caddy | 1×1 PNG (67B) → asset_id → base64 byte-identical |
| S5 | get_instance_info | `get_instance_info` | Caddy | `instance_id` 또는 `captured_at` 채워짐 |
| S6 | get_recent_ipban_events | `get_recent_ipban_events` | Caddy | `events` 배열 + `warning` 없음/positive |
| S7 | trigger_backup_now (200) | `trigger_backup_now` | Caddy | 200 + `task_name:"PlaneBackup"` (실 PlaneBackup 결과 검증 안 함) |

### S0. 이중 401 (인증 헤더 없이)

**합격 조건**: Caddy 와 직결 양쪽 모두 401, `Content-Length` 동일.

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_me\",\"arguments\":{}}}'
$caddyHdr  = curl.exe -sS -i -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body | Select-String -Pattern "^HTTP/|^Content-Length:"
$directHdr = curl.exe -sS -i -X POST $env:PLANE_BASE_URL_LOCAL/http/api-key/mcp -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body | Select-String -Pattern "^HTTP/|^Content-Length:"
"--- Caddy ---";  $caddyHdr
"--- 직결 ---";   $directHdr
$caddyCL  = (($caddyHdr  | Where-Object { $_ -match '^Content-Length' }) -replace '\D','')
$directCL = (($directHdr | Where-Object { $_ -match '^Content-Length' }) -replace '\D','')
if (($caddyHdr -match '401') -and ($directHdr -match '401') -and $caddyCL -and ($caddyCL -eq $directCL)) {
  Write-Host "S0 ok — both 401, Content-Length=$caddyCL"
} else {
  throw "S0 FAIL — caddy_CL=$caddyCL direct_CL=$directCL (401 둘 다? caddy=$([bool]($caddyHdr -match '401')) direct=$([bool]($directHdr -match '401')))"
}
```

**검증**: 자동 — `S0 ok` 출력 시 통과. 둘 중 하나라도 401 아니면 또는 Content-Length 다르면 throw.
**실패 시**: §5 표 1·2행 참고.

### S1. tools/list warmup

**합격 조건**: 응답 `result.tools` 의 `name` 필드에 fork tool 7 종 모두 등장.

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
if ($missing) { throw "S1 FAIL — fork tools missing: $($missing -join ', ')" } else { Write-Host "S1 ok — 7/7 fork tools present" }
```

**실패 시**: §5 표 3행 (`register_fork_tools` wiring 회귀).

### S2. get_me (admin role 확인)

**합격 조건**: `result.structuredContent.is_instance_admin` 가 `True`.

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_me\",\"arguments\":{}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body
$line = $resp | Select-String -Pattern '^data: '
$json = ($line -replace '^data: ','') | ConvertFrom-Json
if ($json.result.structuredContent.is_instance_admin) { Write-Host "S2 ok — is_instance_admin=true" } else { throw "S2 FAIL — is_instance_admin=$($json.result.structuredContent.is_instance_admin)" }
```

**실패 시**: §5 표 4행 (Plane fork commit `51a7e94` 미반영).

### S3. list_projects (워크스페이스 일반 tool 동작 확인)

**합격 조건**: 응답 배열에 `$env:PLANE_TEST_PROJECT_ID` 포함.

> **응답 구조 주의**: `list_projects` 는 결과를 `structuredContent` 가 아닌 `content[0].text` 에 JSON 배열 문자열로 직렬화한다 (fastmcp 가 list type 을 structuredContent 에 안 넣음). text 를 한 번 더 `ConvertFrom-Json` 해야 함.

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"list_projects\",\"arguments\":{}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body
$line = $resp | Select-String -Pattern '^data: '
$json = ($line -replace '^data: ','') | ConvertFrom-Json
$projects = $json.result.content[0].text | ConvertFrom-Json
$found = $projects | Where-Object { $_.id -eq $env:PLANE_TEST_PROJECT_ID }
if ($found) { Write-Host "S3 ok — project found: $($found.name) ($($found.id))" } else { throw "S3 FAIL — PLANE_TEST_PROJECT_ID not in response" }
```

**실패 시**: 환경 변수 오타, 또는 admin PAT 이 해당 workspace 멤버 아님.

### S4. upload → download round-trip (1×1 PNG)

**합격 조건**: upload 200 → asset_id 반환 → download `include_content_base64=true` → 받은 `content_base64` 가 원본과 byte-identical.

> **페이로드**: 67-byte 1×1 transparent PNG. base64 길이 = 92.

```powershell
$png1x1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

try {
  # upload
  $bodyUp = @{
    jsonrpc="2.0"; id=1; method="tools/call"
    params=@{
      name="upload_file"
      arguments=@{
        workspace_slug=$env:PLANE_WORKSPACE_SLUG
        project_id=$env:PLANE_TEST_PROJECT_ID
        entity_id=$env:PLANE_TEST_ISSUE_ID
        name="smoke-1x1.png"
        mime="image/png"
        content_base64=$png1x1
      }
    }
  } | ConvertTo-Json -Depth 5 -Compress
  $bodyUp | Out-File -FilePath s4-upload.json -Encoding ascii -NoNewline
  $resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
    -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
    -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
    -H "content-type: application/json" `
    -H "accept: application/json, text/event-stream" `
    --data-binary "@s4-upload.json"
  $line = $resp | Select-String -Pattern '^data: '
  $json = ($line -replace '^data: ','') | ConvertFrom-Json
  if ($json.result.isError) { throw "S4 upload FAIL — $($json.result.content[0].text)" }
  $assetId = $json.result.structuredContent.asset_id
  if (-not $assetId) { throw "S4 upload FAIL — no asset_id returned" }

  # download
  $bodyDn = '{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"download_file\",\"arguments\":{\"workspace_slug\":\"' + $env:PLANE_WORKSPACE_SLUG + '\",\"project_id\":\"' + $env:PLANE_TEST_PROJECT_ID + '\",\"asset_id\":\"' + $assetId + '\",\"include_content_base64\":true}}}'
  $resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
    -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
    -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
    -H "content-type: application/json" `
    -H "accept: application/json, text/event-stream" `
    -d $bodyDn
  $line = $resp | Select-String -Pattern '^data: '
  $json = ($line -replace '^data: ','') | ConvertFrom-Json
  if ($json.result.structuredContent.content_base64 -eq $png1x1) {
    Write-Host "S4 ok — round-trip identical (asset_id=$assetId)"
  } else {
    $got = $json.result.structuredContent.content_base64
    $gotLen = if ($got) { $got.Length } else { 0 }
    $gotPrefix = if ($got -and $got.Length -ge 12) { $got.Substring(0, 12) } else { "$got" }
    throw "S4 FAIL — base64 mismatch (expected len=$($png1x1.Length) prefix=$($png1x1.Substring(0,12)); got len=$gotLen prefix=$gotPrefix)"
  }
} finally {
  Remove-Item s4-upload.json -ErrorAction SilentlyContinue
}
```

**실패 시**: §5 표 5행 (Plane v2 asset 3-step flow 회귀).

### S5. get_instance_info

**합격 조건**: `instance_id` 또는 `captured_at` 중 하나 이상 채워짐 (Plane 미설정 instance 면 모두 null + captured_at 만 — degrade 응답도 통과).

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_instance_info\",\"arguments\":{}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body
$line = $resp | Select-String -Pattern '^data: '
$json = ($line -replace '^data: ','') | ConvertFrom-Json
if ($json.result.isError) { throw "S5 FAIL — $($json.result.content[0].text)" }
$sc = $json.result.structuredContent
if ($sc.instance_id -or $sc.captured_at) { Write-Host "S5 ok — instance_id=$($sc.instance_id) version=$($sc.version) captured_at=$($sc.captured_at)" } else { throw "S5 FAIL — both instance_id and captured_at empty" }
```

**실패 시**: admin_guard 가 admin 판정 실패 (§5 표 4행) 또는 Plane `/api/instances/` 응답 형식 변경.

### S6. get_recent_ipban_events

**합격 조건**: `events` 가 배열 (빈 배열 OK) + `warning` 이 `"file not found"` / `"permission denied"` 가 아닐 것.

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_recent_ipban_events\",\"arguments\":{\"limit\":10}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body
$line = $resp | Select-String -Pattern '^data: '
$json = ($line -replace '^data: ','') | ConvertFrom-Json
if ($json.result.isError) { throw "S6 FAIL — $($json.result.content[0].text)" }
$sc = $json.result.structuredContent
$bad = @('file not found','permission denied')
if ($sc.warning -and ($bad -contains $sc.warning)) { throw "S6 FAIL — IPBan log access regression: warning=$($sc.warning)" } else { Write-Host "S6 ok — events=$($sc.events.Count) warning=$($sc.warning)" }
```

**실패 시**: §5 표 6행 (IPBan 로그 경로/ACL 회귀).

### S7. trigger_backup_now (200 stub)

**합격 조건**: 200 + `task_name="PlaneBackup"`. **PlaneBackup 의 실 실행 결과는 검증하지 않음** — Plane 측 5xx (e.g. `todo.md` #8 의 권한 거부) 가 떨어지면 fail.

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"trigger_backup_now\",\"arguments\":{}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp `
  -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" `
  -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" `
  -H "content-type: application/json" `
  -H "accept: application/json, text/event-stream" `
  -d $body
$line = $resp | Select-String -Pattern '^data: '
$json = ($line -replace '^data: ','') | ConvertFrom-Json
if ($json.result.isError) { throw "S7 FAIL — $($json.result.content[0].text)" }
if ($json.result.structuredContent.task_name -eq "PlaneBackup") { Write-Host "S7 ok — task_name=PlaneBackup started_at=$($json.result.structuredContent.started_at)" } else { throw "S7 FAIL — unexpected task_name=$($json.result.structuredContent.task_name)" }
```

**실패 시**: §5 표 7행 (`todo.md` #8 — `.\plane` 계정 PlaneBackup Task 실행 권한 부족).



## 3. Regression 체크리스트 (21 케이스, 15~30분)

**Prerequisite (R0)**: §2 Smoke 8 항목 전체 통과.

| 그룹 | Tool | 케이스 | 입력 | 합격 조건 |
|------|------|--------|------|----------|
| R1 | `upload_file` | R1-a | PNG 1×1 5KB, admin | 200, asset_id UUID |
| R1 | `upload_file` | R1-b | JPEG 2.5MB zero-byte 더미, admin | 200 + `warning="consider Plane UI for files > 2MB"` |
| R1 | `upload_file` | R1-c | mime=`application/pdf`, admin | substring `unsupported mime` |
| R1 | `upload_file` | R1-d | 6MB 페이로드 zero-byte 더미, admin | substring `file too large` |
| R1 | `upload_file` | R1-e | `content_base64="not_b64!!!"`, admin | 정확 `invalid base64` |
| R1 | `upload_file` | R1-f | random UUID `entity_id`, admin | substring `plane api error: 404` |
| R1 | `upload_file` | R1-g | R1-a 와 동일, **non-admin** | 200 |
| R2 | `download_file` | R2-a | R1-a asset_id, `include_content_base64=false`, admin | 200, `presigned_url` 채워짐, `content_base64=null` |
| R2 | `download_file` | R2-b | 같은 asset_id, `include_content_base64=true`, admin | content_base64 가 R1-a 원본과 일치 |
| R2 | `download_file` | R2-c | random UUID asset_id, admin | substring `plane api error: 404` |
| R2 | `download_file` | R2-d | R2-a, **non-admin** | 200 |
| R3 | `list_file_assets` | R3-a | 임의 args | substring `Plane fork's /api/assets/v2/ does not expose a list-by-entity endpoint — see .claude/docs/customization/todo.md #7` |
| R4 | `get_instance_info` | R4-a | admin | 200, `version` 또는 `instance_id` 채워짐 |
| R4 | `get_instance_info` | R4-b | **non-admin** | 정확 `requires instance admin` |
| R5 | `list_workspace_health` | R5-a | `limit=20`, admin | `workspaces` 배열, 항목에 `slug`/`member_count` 채워짐 |
| R5 | `list_workspace_health` | R5-b | `limit=51`, admin | 정확 `limit must be between 1 and 50` |
| R5 | `list_workspace_health` | R5-c | **non-admin** | 정확 `requires instance admin` |
| R6 | `get_recent_ipban_events` | R6-a | `limit=10`, admin | `events` 배열, 빈 배열이면 `warning` 확인 |
| R6 | `get_recent_ipban_events` | R6-b | `limit=1001`, admin | substring `limit must be between 1 and 1000` |
| R6 | `get_recent_ipban_events` | R6-c | **non-admin** | 정확 `requires instance admin` |
| R7 | `trigger_backup_now` | R7-a | admin | **200 만 통과** — Plane 측 5xx (`todo.md` #8 미해결) 면 fail 표기 (의도된 알람) |
| R7 | `trigger_backup_now` | R7-b | **non-admin** | 정확 `requires instance admin` |

> **공통 사전 셋업**: §1.1 환경 변수 + §1.2 sanity 통과 후 시작. R1-a → R2-a/b 는 stateful — R1-a 의 asset_id 를 R2-a/b 가 재사용.
>
> **응답 메시지 노트**: fastmcp 는 `ToolError` 의 메시지를 그대로 `content[0].text` 에 노출하지만, `ValueError` / `NotImplementedError` 등 generic exception 은 `Error calling tool 'X': ...` prefix 로 wrap 한다 — 따라서 일부 케이스가 "substring" 매치, 다른 케이스가 "정확" 매치인 것은 의도된 차이.

### R1. `upload_file` (7 케이스)

R1 의 모든 케이스는 `$env:PLANE_TEST_ISSUE_ID` 의 issue 에 첨부 시도. R1-a 의 asset_id 는 R2-a/b 가 사용하므로 변수에 저장.

#### R1-a — PNG 1×1 admin (positive)

```powershell
$global:R1aPng1x1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
$body = @{
  jsonrpc="2.0"; id=1; method="tools/call"
  params=@{ name="upload_file"; arguments=@{
    workspace_slug=$env:PLANE_WORKSPACE_SLUG
    project_id=$env:PLANE_TEST_PROJECT_ID
    entity_id=$env:PLANE_TEST_ISSUE_ID
    name="r1a-1x1.png"; mime="image/png"; content_base64=$global:R1aPng1x1
  }}
} | ConvertTo-Json -Depth 5 -Compress
$body | Out-File -FilePath r1a.json -Encoding ascii -NoNewline
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" --data-binary "@r1a.json"
Remove-Item r1a.json -ErrorAction SilentlyContinue
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R1-a FAIL — $($j.result.content[0].text)" }
$global:R1aAssetId = $j.result.structuredContent.asset_id
if ($global:R1aAssetId -match '^[0-9a-f-]{36}$') { Write-Host "R1-a ok — asset_id=$global:R1aAssetId" } else { throw "R1-a FAIL — asset_id not UUID: $global:R1aAssetId" }
```

#### R1-b — JPEG 2.5MB zero-byte admin (warning 경계)

```powershell
$big = [Convert]::ToBase64String([byte[]]::new(2500000))
$body = @{
  jsonrpc="2.0"; id=1; method="tools/call"
  params=@{ name="upload_file"; arguments=@{
    workspace_slug=$env:PLANE_WORKSPACE_SLUG; project_id=$env:PLANE_TEST_PROJECT_ID
    entity_id=$env:PLANE_TEST_ISSUE_ID
    name="r1b-2_5mb.jpg"; mime="image/jpeg"; content_base64=$big
  }}
} | ConvertTo-Json -Depth 5 -Compress
$body | Out-File -FilePath r1b.json -Encoding ascii -NoNewline
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" --data-binary "@r1b.json"
Remove-Item r1b.json -ErrorAction SilentlyContinue
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R1-b FAIL — $($j.result.content[0].text)" }
$w = $j.result.structuredContent.warning
if ($w -eq "consider Plane UI for files > 2MB") { Write-Host "R1-b ok — asset_id=$($j.result.structuredContent.asset_id) warning=$w" } else { throw "R1-b FAIL — warning mismatch: $w" }
```

#### R1-c — unsupported mime (`application/pdf`)

```powershell
$body = @{
  jsonrpc="2.0"; id=1; method="tools/call"
  params=@{ name="upload_file"; arguments=@{
    workspace_slug=$env:PLANE_WORKSPACE_SLUG; project_id=$env:PLANE_TEST_PROJECT_ID
    entity_id=$env:PLANE_TEST_ISSUE_ID
    name="r1c.pdf"; mime="application/pdf"; content_base64="JVBERi0xLjQK"
  }}
} | ConvertTo-Json -Depth 5 -Compress
$body | Out-File -FilePath r1c.json -Encoding ascii -NoNewline
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" --data-binary "@r1c.json"
Remove-Item r1c.json -ErrorAction SilentlyContinue
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
$txt = $j.result.content[0].text
if ($j.result.isError -and ($txt -like '*unsupported mime*')) { Write-Host "R1-c ok — $txt" } else { throw "R1-c FAIL — expected substring 'unsupported mime'; got: $txt" }
```

#### R1-d — file too large (6MB)

```powershell
$over = [Convert]::ToBase64String([byte[]]::new(6000000))
$body = @{
  jsonrpc="2.0"; id=1; method="tools/call"
  params=@{ name="upload_file"; arguments=@{
    workspace_slug=$env:PLANE_WORKSPACE_SLUG; project_id=$env:PLANE_TEST_PROJECT_ID
    entity_id=$env:PLANE_TEST_ISSUE_ID
    name="r1d-6mb.png"; mime="image/png"; content_base64=$over
  }}
} | ConvertTo-Json -Depth 5 -Compress
$body | Out-File -FilePath r1d.json -Encoding ascii -NoNewline
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" --data-binary "@r1d.json"
Remove-Item r1d.json -ErrorAction SilentlyContinue
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
$txt = $j.result.content[0].text
if ($j.result.isError -and ($txt -like '*file too large*')) { Write-Host "R1-d ok — $txt" } else { throw "R1-d FAIL — expected substring 'file too large'; got: $txt" }
```

#### R1-e — invalid base64

```powershell
$body = @{
  jsonrpc="2.0"; id=1; method="tools/call"
  params=@{ name="upload_file"; arguments=@{
    workspace_slug=$env:PLANE_WORKSPACE_SLUG; project_id=$env:PLANE_TEST_PROJECT_ID
    entity_id=$env:PLANE_TEST_ISSUE_ID
    name="r1e.png"; mime="image/png"; content_base64="not_b64!!!"
  }}
} | ConvertTo-Json -Depth 5 -Compress
$body | Out-File -FilePath r1e.json -Encoding ascii -NoNewline
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" --data-binary "@r1e.json"
Remove-Item r1e.json -ErrorAction SilentlyContinue
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
$txt = $j.result.content[0].text
if ($j.result.isError -and ($txt -eq "invalid base64")) { Write-Host "R1-e ok — invalid base64" } else { throw "R1-e FAIL — expected exact 'invalid base64'; got: $txt" }
```

#### R1-f — Plane 404 (random entity_id)

```powershell
if (-not $global:R1aPng1x1) { throw "R1-f precondition — `$global:R1aPng1x1 미설정. R1-a 먼저 실행하거나 페이로드 직접 할당." }
$bogus = [guid]::NewGuid().ToString()
$body = @{
  jsonrpc="2.0"; id=1; method="tools/call"
  params=@{ name="upload_file"; arguments=@{
    workspace_slug=$env:PLANE_WORKSPACE_SLUG; project_id=$env:PLANE_TEST_PROJECT_ID
    entity_id=$bogus
    name="r1f.png"; mime="image/png"; content_base64=$global:R1aPng1x1
  }}
} | ConvertTo-Json -Depth 5 -Compress
$body | Out-File -FilePath r1f.json -Encoding ascii -NoNewline
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" --data-binary "@r1f.json"
Remove-Item r1f.json -ErrorAction SilentlyContinue
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
$txt = $j.result.content[0].text
if ($j.result.isError -and ($txt -like '*plane api error: 404*')) { Write-Host "R1-f ok — $txt" } else { throw "R1-f FAIL — expected substring 'plane api error: 404'; got: $txt" }
```

#### R1-g — non-admin PAT (project member 권한)

```powershell
$body = @{
  jsonrpc="2.0"; id=1; method="tools/call"
  params=@{ name="upload_file"; arguments=@{
    workspace_slug=$env:PLANE_WORKSPACE_SLUG; project_id=$env:PLANE_TEST_PROJECT_ID
    entity_id=$env:PLANE_TEST_ISSUE_ID
    name="r1g-1x1.png"; mime="image/png"; content_base64=$global:R1aPng1x1
  }}
} | ConvertTo-Json -Depth 5 -Compress
$body | Out-File -FilePath r1g.json -Encoding ascii -NoNewline
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_NONADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" --data-binary "@r1g.json"
Remove-Item r1g.json -ErrorAction SilentlyContinue
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R1-g FAIL — $($j.result.content[0].text). non-admin user 가 project member 인지 확인하세요." }
if ($j.result.structuredContent.asset_id) { Write-Host "R1-g ok — non-admin upload asset_id=$($j.result.structuredContent.asset_id)" } else { throw "R1-g FAIL — no asset_id" }
```

### R2. `download_file` (4 케이스)

R2-a/b 는 R1-a 의 asset_id (`$global:R1aAssetId`) 를 재사용. R1 을 안 돌리고 R2 부터 하면 직접 asset_id 를 변수에 채울 것.

#### R2-a — admin, content_base64=false

```powershell
if (-not $global:R1aAssetId) { throw "R2-a precondition — `$global:R1aAssetId 미설정. R1-a 먼저 실행하세요." }
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"download_file\",\"arguments\":{\"workspace_slug\":\"' + $env:PLANE_WORKSPACE_SLUG + '\",\"project_id\":\"' + $env:PLANE_TEST_PROJECT_ID + '\",\"asset_id\":\"' + $global:R1aAssetId + '\",\"include_content_base64\":false}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R2-a FAIL — $($j.result.content[0].text)" }
$sc = $j.result.structuredContent
if ($sc.presigned_url -match '^http.*sig=' -and -not $sc.content_base64) { Write-Host "R2-a ok — presigned_url=$($sc.presigned_url.Substring(0, [Math]::Min(80, $sc.presigned_url.Length)))..." } else { throw "R2-a FAIL — url=$($sc.presigned_url) content_base64=$($sc.content_base64)" }
```

#### R2-b — admin, content_base64=true (round-trip identity)

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"download_file\",\"arguments\":{\"workspace_slug\":\"' + $env:PLANE_WORKSPACE_SLUG + '\",\"project_id\":\"' + $env:PLANE_TEST_PROJECT_ID + '\",\"asset_id\":\"' + $global:R1aAssetId + '\",\"include_content_base64\":true}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R2-b FAIL — $($j.result.content[0].text)" }
if (-not $global:R1aPng1x1) { throw "R2-b precondition — `$global:R1aPng1x1 미설정. R1-a 먼저 실행." }
if ($j.result.structuredContent.content_base64 -eq $global:R1aPng1x1) { Write-Host "R2-b ok — round-trip identity" } else { throw "R2-b FAIL — content_base64 mismatch" }
```

#### R2-c — Plane 404 (random asset_id)

```powershell
$bogus = [guid]::NewGuid().ToString()
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"download_file\",\"arguments\":{\"workspace_slug\":\"' + $env:PLANE_WORKSPACE_SLUG + '\",\"project_id\":\"' + $env:PLANE_TEST_PROJECT_ID + '\",\"asset_id\":\"' + $bogus + '\"}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
$txt = $j.result.content[0].text
if ($j.result.isError -and ($txt -like '*plane api error: 404*')) { Write-Host "R2-c ok — $txt" } else { throw "R2-c FAIL — expected substring 'plane api error: 404'; got: $txt" }
```

#### R2-d — non-admin

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"download_file\",\"arguments\":{\"workspace_slug\":\"' + $env:PLANE_WORKSPACE_SLUG + '\",\"project_id\":\"' + $env:PLANE_TEST_PROJECT_ID + '\",\"asset_id\":\"' + $global:R1aAssetId + '\",\"include_content_base64\":false}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_NONADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R2-d FAIL — $($j.result.content[0].text). non-admin 이 project member 인지 확인." }
if ($j.result.structuredContent.presigned_url) { Write-Host "R2-d ok — non-admin download" } else { throw "R2-d FAIL — no presigned_url" }
```

### R3. `list_file_assets` (1 케이스)

#### R3-a — NotImplementedError

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"list_file_assets\",\"arguments\":{\"workspace_slug\":\"' + $env:PLANE_WORKSPACE_SLUG + '\",\"project_id\":\"' + $env:PLANE_TEST_PROJECT_ID + '\",\"entity_id\":\"' + $env:PLANE_TEST_ISSUE_ID + '\"}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
$txt = $j.result.content[0].text
$expected = "Plane fork's /api/assets/v2/ does not expose a list-by-entity endpoint — see .claude/docs/customization/todo.md #7"
if ($j.result.isError -and ($txt -like "*$expected*")) { Write-Host "R3-a ok — NotImplementedError as documented" } else { throw "R3-a FAIL — expected substring '$expected'; got: $txt" }
```

### R4. `get_instance_info` (2 케이스)

#### R4-a — admin

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_instance_info\",\"arguments\":{}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R4-a FAIL — $($j.result.content[0].text)" }
$sc = $j.result.structuredContent
if ($sc.version -or $sc.instance_id) { Write-Host "R4-a ok — version=$($sc.version) instance_id=$($sc.instance_id)" } else { throw "R4-a FAIL — both version and instance_id empty" }
```

#### R4-b — non-admin (admin_guard 거부)

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_instance_info\",\"arguments\":{}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_NONADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError -and ($j.result.content[0].text -eq "requires instance admin")) { Write-Host "R4-b ok — denied with 'requires instance admin'" } else { throw "R4-b FAIL — expected 'requires instance admin'; got isError=$($j.result.isError) text=$($j.result.content[0].text)" }
```

### R5. `list_workspace_health` (3 케이스)

#### R5-a — admin, limit=20

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"list_workspace_health\",\"arguments\":{\"limit\":20}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R5-a FAIL — $($j.result.content[0].text)" }
$ws = $j.result.structuredContent.workspaces
if ($ws.Count -ge 1 -and $ws[0].slug -and ($null -ne $ws[0].member_count)) { Write-Host "R5-a ok — total=$($j.result.structuredContent.total) first.slug=$($ws[0].slug) member_count=$($ws[0].member_count)" } else { throw "R5-a FAIL — workspaces[0] slug/member_count missing" }
```

#### R5-b — limit=51 (validation)

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"list_workspace_health\",\"arguments\":{\"limit\":51}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
$txt = $j.result.content[0].text
if ($j.result.isError -and ($txt -eq "limit must be between 1 and 50")) { Write-Host "R5-b ok — validation error 'limit must be between 1 and 50'" } else { throw "R5-b FAIL — expected exact 'limit must be between 1 and 50'; got: $txt" }
```

#### R5-c — non-admin

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"list_workspace_health\",\"arguments\":{\"limit\":20}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_NONADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError -and ($j.result.content[0].text -eq "requires instance admin")) { Write-Host "R5-c ok — denied" } else { throw "R5-c FAIL — got: $($j.result.content[0].text)" }
```

### R6. `get_recent_ipban_events` (3 케이스)

#### R6-a — admin, limit=10

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_recent_ipban_events\",\"arguments\":{\"limit\":10}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R6-a FAIL — $($j.result.content[0].text)" }
$sc = $j.result.structuredContent
$bad = @('file not found','permission denied')
if ($sc.warning -and ($bad -contains $sc.warning)) { throw "R6-a FAIL — IPBan log access regression: $($sc.warning)" }
Write-Host "R6-a ok — events=$($sc.events.Count) warning=$($sc.warning)"
```

#### R6-b — limit=1001 (validation)

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_recent_ipban_events\",\"arguments\":{\"limit\":1001}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
$txt = $j.result.content[0].text
if ($j.result.isError -and ($txt -like '*limit must be between 1 and 1000*')) { Write-Host "R6-b ok — $txt" } else { throw "R6-b FAIL — expected substring 'limit must be between 1 and 1000'; got: $txt" }
```

#### R6-c — non-admin

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_recent_ipban_events\",\"arguments\":{\"limit\":10}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_NONADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError -and ($j.result.content[0].text -eq "requires instance admin")) { Write-Host "R6-c ok — denied" } else { throw "R6-c FAIL — got: $($j.result.content[0].text)" }
```

### R7. `trigger_backup_now` (2 케이스)

> **R7-a 의 의도된 fail**: `todo.md` #8 미해결 동안 R7-a 는 fail 로 남는다 — Plane fork 의 `AdminBackupView` 가 `Start-ScheduledTask` 호출에서 `.\plane` 계정 권한 부족으로 거부, Plane API 가 500 반환. #8 해결 시 자연 통과.

#### R7-a — admin (200 통과만)

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"trigger_backup_now\",\"arguments\":{}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_ADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError) { throw "R7-a FAIL (의도된 fail until todo.md #8) — $($j.result.content[0].text)" }
if ($j.result.structuredContent.task_name -eq "PlaneBackup") { Write-Host "R7-a ok — task_name=PlaneBackup" } else { throw "R7-a FAIL — task_name=$($j.result.structuredContent.task_name)" }
```

#### R7-b — non-admin

```powershell
$body = '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"trigger_backup_now\",\"arguments\":{}}}'
$resp = curl.exe -sS -X POST $env:PLANE_BASE_URL_CADDY/mcp/http/api-key/mcp -H "Authorization: Bearer $env:PLANE_NONADMIN_PAT" -H "x-workspace-slug: $env:PLANE_WORKSPACE_SLUG" -H "content-type: application/json" -H "accept: application/json, text/event-stream" -d $body
$j = (($resp | Select-String -Pattern '^data: ') -replace '^data: ','') | ConvertFrom-Json
if ($j.result.isError -and ($j.result.content[0].text -eq "requires instance admin")) { Write-Host "R7-b ok — denied" } else { throw "R7-b FAIL — got: $($j.result.content[0].text)" }
```



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
| 2026-MM-DD | upstream/main = abc123 | ✅(7/7) | ✅(4/4) | ✅(1/1) | ✅(2/2) | ✅(3/3) | ✅(3/3) | ❌(1/2) | R7-a 500 — todo #8 미해결 (intentional) |
```

### 4.3. 기록 위치 규약

- 한 운영 이벤트 = 한 행. 이벤트 = NSSM 재시작 / 의존성 업그레이드 / upstream sync / 호스트 패치 등.
- `R<X>` 셀의 `(N/M)` 은 통과/전체. 실패 케이스 ID 를 "실패 항목 상세" 에 명시.
- `R7-a` 의 의도된 fail 은 비고에 `(intentional, todo.md #8)` 표기. 그 외 fail 은 별 줄로 root cause 기록.
- Smoke / Regression 표는 `deployment.md` 의 같은 세션 블록 안에 두 sub-section 으로 분리.

## 5. 트러블슈팅 매트릭스

| # | 증상 | 가능 원인 | 1차 확인 명령 |
|---|------|----------|--------------|
| 1 | S0 직결 401 + Caddy 502/404 | Caddy 미기동 또는 Caddyfile 오타 | `Get-Service caddy` ; `caddy validate --config D:\Workspace\plane-app\ops\Caddyfile` |
| 2 | S0 양쪽 connection refused | NSSM `plane-mcp` 미기동 | `Get-Service plane-mcp` ; `netstat -an \| Select-String ":8211"` |
| 3 | S1 fork 7 종 누락 | `register_fork_tools()` wiring 회귀 | `pytest /d/Workspace/plane-mcp-server/tests/test_server_wiring.py -v` |
| 4 | S2 admin PAT 인데 `is_instance_admin:false` | Plane fork commit `51a7e94` 미반영 | `git -C /d/Workspace/plane log --oneline \| Select-String 51a7e94` |
| 5 | S4 upload 200 + download base64 mismatch | Plane v2 asset 3-step flow 회귀 | `plane_mcp/tools/files.py` 코드 vs `tools-reference.md` flow 비교 |
| 6 | S6 `events:[]` + `warning:"file not found"` | IPBan 로그 경로/ACL 회귀 | `icacls D:\Workspace\plane-logs\ipban` ; NSSM `AppEnvironmentExtra` 의 `PLANE_MCP_IPBAN_LOG` 확인 |
| 7 | S7 / R7-a `Start-ScheduledTask ... 액세스가 거부` | `todo.md` #8 미해결 | 알려진 이슈 — R7-a fail 그대로 두고 #8 진행 시 재시험 |
| 8 | 모든 항목 `Parse error: Expecting value: line 1 column 1` | cmd single quote escape 오류 | 부록 A 참고 — PowerShell `curl.exe` 사용 또는 `--data-binary @file.json` |
| 9 | `tools/call` 응답이 SSE 가 아닌 JSON 직접 | `accept` 헤더 누락 | 모든 호출에 `-H "accept: application/json, text/event-stream"` 포함 |
| 10 | `requires instance admin` 이 admin PAT 인데 발생 | admin_guard 캐시 stale (60s TTL) | 60s 대기 후 재시도; 재발 시 `get_me` 응답의 `is_instance_admin` 직접 확인 |

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

> **PowerShell 함정**:
> 1. `curl` 은 `Invoke-WebRequest` 의 alias. 반드시 `curl.exe` 로 명시.
> 2. PowerShell 의 single-quoted body 안의 `\"` 는 PS 단계에서 literal 로 보존되고, **`curl.exe` 의 native arg parser 가 `\"` → `"` 변환**해 wire 에 정상 JSON 도달. 따라서 PS 에선 `'{\"...\"}'` 가 정답이다 — `'{"..."}' ` (PS literal `{"..."}`) 는 `curl.exe` 가 `"` 를 token 경계로 해석해 깨진다.

### A.2. cmd.exe

```cmd
curl -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp ^
  -H "Authorization: Bearer %PLANE_ADMIN_PAT%" ^
  -H "x-workspace-slug: develop" ^
  -H "content-type: application/json" ^
  -H "accept: application/json, text/event-stream" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_me\",\"arguments\":{}}}"
```

> **cmd 함정**: single quote (`'...'`) 는 string literal 로 인식 안 됨. body 가 통째로 깨져 `Parse error: Expecting value: line 1 column 1` 이 떨어진다. 반드시 double quote + 내부 `\"` escape, 또는 파일에 저장 후 `--data-binary @body.json`.

### A.3. bash (참고)

```bash
curl -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp \
  -H "Authorization: Bearer $PLANE_ADMIN_PAT" \
  -H "x-workspace-slug: develop" \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_me","arguments":{}}}'
```

### A.4. 큰 페이로드 (base64 등) — 셸 무관 권장 패턴

```powershell
# PowerShell — body 를 hashtable 로 만든 후 file 로 dump → --data-binary
$body = @{
  jsonrpc="2.0"; id=1; method="tools/call"
  params=@{ name="upload_file"; arguments=@{ ... } }
} | ConvertTo-Json -Depth 5 -Compress
$body | Out-File -FilePath body.json -Encoding ascii -NoNewline
curl.exe -sS -X POST ... --data-binary "@body.json"
Remove-Item body.json -ErrorAction SilentlyContinue
```

base64 안에 `+` `/` `=` 등이 있어도 file 경로라 어떤 셸에서도 안전.

## 부록 B — SSE 응답 핵심 필드 추출

응답 포맷이 `event: message\ndata: {...}` 라 핵심 필드 한 개를 보려면 한 단계 가공이 필요.

### B.1. PowerShell helper

```powershell
function Get-McpField {
  <#
  .SYNOPSIS  SSE 응답에서 result.structuredContent 의 한 필드 추출.
  .EXAMPLE   Get-McpField $resp 'is_instance_admin'
  #>
  param(
    [Parameter(Mandatory)] $body,         # curl.exe 의 stdout (string 또는 string[])
    [Parameter(Mandatory)] [string] $jq   # 예: 'is_instance_admin', 'asset_id'
  )
  $line = $body | Select-String -Pattern '^data: '
  if (-not $line) { throw "no data: line in SSE response" }
  $json = ($line -replace '^data: ','') | ConvertFrom-Json
  return $json.result.structuredContent.$jq
}
```

사용:

```powershell
$resp = curl.exe ... 
$role = Get-McpField $resp 'is_instance_admin'
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
if ($json.result.isError) {
  Write-Host "ERROR: $($json.result.content[0].text)"
}
```

### B.4. List 반환 tool 의 응답

`list_projects` 같이 list 를 반환하는 일부 tool 은 `structuredContent` 가 비고 `content[0].text` 에 JSON 배열 문자열이 들어간다 (fastmcp 가 list type 을 structuredContent 에 자동 직렬화 안 함). 한 번 더 `ConvertFrom-Json`:

```powershell
$projects = $json.result.content[0].text | ConvertFrom-Json
$projects | Where-Object { $_.id -eq $env:PLANE_TEST_PROJECT_ID }
```
