# Fork Tools Test Scenarios — Design Spec

> 본 문서는 **설계 명세 (design spec)** 이다. 실제 체크리스트 산출물(`test-scenarios.md`)은 후속 implementation plan 에서 작성된다.
>
> - **Created**: 2026-04-25
> - **Implements**: fork-custom 7 tool 의 수동 cURL 검증 체크리스트 (재배포 smoke + 월간 regression 2 레벨)

---

## 1. 배경 & 동기

`plane-mcp-v2-deploy` 세션 (2026-04-24, `deployment.md` 참조) 에서 N4 단계로 4 시나리오 운영 smoke 를 1회 수행하고 끝냈다. 이후 다음 두 시점에 동일한 검증을 반복해야 하는데 **공식 체크리스트가 없다**:

1. **재배포 직후** — NSSM `plane-mcp` 서비스 재시작·OS 패치·Caddy 설정 변경 직후 "fork tool 7개 + transport 양쪽이 즉시 동작" 빠른 확인
2. **월 1회 upstream sync 직후** — `upstream-sync.md` 에 정의된 정기 sync (다음 예정 2026-05-31) 후 fork-custom 영역에 회귀 없음 검증

자동화된 pytest 통합 테스트(`test_integration.py`) 는 별 트랙으로 존재하지만, 운영 환경 (Windows + NSSM + Caddy) 에서 실제 reverse proxy + auth + tool 경로를 함께 보지는 않는다. 이 spec 의 산출물은 **운영 트리에서 사람이 직접 한 자리에 앉아 돌리는 cURL 체크리스트** 다.

## 2. 산출물 정의

### 2.1. 파일

`.claude/docs/customization/test-scenarios.md` — 단일 마크다운 파일.

같은 디렉토리의 `spec.md` / `deployment.md` / `tools-reference.md` / `todo.md` / `upstream-sync.md` 와 같은 슬롯. `CLAUDE.md` §"참조 문서 현황" 표에 1행 추가하여 인덱싱.

### 2.2. 형태

수동 cURL 체크리스트. 자동화 스크립트 없음 (옵션 2 — PowerShell 스크립트 — 는 회귀 빈도가 높아질 때 별 spec 으로 승격).

### 2.3. 적용 범위

**대상 (in scope)**:
- fork-custom 7 tool 전수: `upload_file`, `download_file`, `list_file_assets`, `get_instance_info`, `list_workspace_health`, `get_recent_ipban_events`, `trigger_backup_now`
- HTTP transport 의 header-PAT 엔드포인트 (`/http/api-key/mcp`)
- Caddy reverse proxy 경로 (`/mcp/...` strip-path) + 직결 (`:8211`) 양쪽

**비대상 (out of scope, 의도적 누락)**:
- stdio / SSE / OAuth transport — 운영 배포 형태가 아님 (`spec.md` §2)
- upstream 55+ tool 의 회귀 — upstream README 영역, fork 책임 외
- Plane 자체 5xx 동작·DB 무결성 — Plane 운영 영역
- `PLANE_INTERNAL_BASE_URL` 토글 — 운영에 영향 없는 server-to-server 옵션
- pytest E2E 시나리오 — 별 트랙 (`tests/test_integration.py`)

### 2.4. 환경 가정

| 항목 | 값 |
|---|---|
| 실행 OS | Windows Server 2025 (운영 호스트 직접 또는 동일 네트워크 워크스테이션) |
| 셸 | PowerShell 5/7 + `curl.exe` (cmd.exe 도 보조 — 부록 A) |
| 자격 | admin PAT 1개 + non-admin PAT 1개 (둘 다 `develop` workspace 멤버) |
| 데이터 | 환경 변수로 주입한 `PLANE_TEST_PROJECT_ID` + `PLANE_TEST_ISSUE_ID` 1세트 — 운영자 자유 |

## 3. 문서 구조

```
test-scenarios.md
├─ §0 적용 범위 (이 spec §2.3 요약)
├─ §1 Pre-flight — 환경 변수 셋업 + 두 PAT 검증
├─ §2 Smoke 체크리스트 (8 항목, 2~5분)
├─ §3 Regression 체크리스트 (21 케이스, 15~30분)
├─ §4 결과 기록 템플릿
├─ §5 트러블슈팅 매트릭스
├─ 부록 A — cmd vs PowerShell vs bash escape 가이드
└─ 부록 B — SSE 응답 핵심 필드 추출 (PowerShell helper + jq)
```

## 4. §1 Pre-flight 명세

### 4.1. 환경 변수 (체크리스트 첫 머리에 명시)

```
PLANE_BASE_URL_LOCAL=http://127.0.0.1:8211
PLANE_BASE_URL_CADDY=http://127.0.0.1
PLANE_WORKSPACE_SLUG=develop
PLANE_ADMIN_PAT=plane_api_<...>
PLANE_NONADMIN_PAT=plane_api_<...>
PLANE_TEST_PROJECT_ID=<UUID>
PLANE_TEST_ISSUE_ID=<UUID>
```

### 4.2. 두 PAT sanity 체크

`get_me` 호출 2회 — admin / non-admin 각각 — 으로 `is_instance_admin` 필드 확인 (true / false). 어느 한쪽이 기대와 다르면 **체크리스트 본문 시작하지 않음**.

## 5. §2 Smoke 명세 (8 항목)

| # | 항목 | 호출 tool | 경로 | 합격 조건 |
|---|------|-----------|------|----------|
| S0 | 이중 401 (no-auth) | (요청만) | Caddy + 직결 | 둘 다 401, content-length 동일 |
| S1 | tools/list warmup | — | Caddy | `result.tools` 에 fork tool 7 종 모두 존재 |
| S2 | get_me | `get_me` | Caddy | `is_instance_admin:true` |
| S3 | list_projects | `list_projects` | Caddy | 200, 배열에 `PLANE_TEST_PROJECT_ID` 포함 |
| S4 | upload→download round-trip | `upload_file` + `download_file` | Caddy | 1×1 PNG (67B) → asset_id → base64 byte-identical |
| S5 | get_instance_info | `get_instance_info` | Caddy | 200, `instance_id` 또는 `captured_at` 채워짐 |
| S6 | get_recent_ipban_events | `get_recent_ipban_events` | Caddy | 200, `events` 배열, `warning` 이 `"file not found"` / `"permission denied"` 가 아님 |
| S7 | trigger_backup_now (200 stub) | `trigger_backup_now` | Caddy | 200, `task_name:"PlaneBackup"` (PlaneBackup 실 결과는 검증 안 함) |

**모두 admin PAT 1개로 실행**. 한 항목 평균 30초.

## 6. §3 Regression 명세 (21 케이스, R1~R7)

R0 = §5 Smoke 8 항목 모두 통과 (전제).

| 그룹 | Tool | 케이스 ID | 입력 | 합격 조건 |
|------|------|-----------|------|----------|
| R1 | `upload_file` | R1-a | PNG 1×1 5KB, admin PAT | 200, asset_id UUID |
| | | R1-b | JPEG 2.5MB (PowerShell `[Convert]::ToBase64String([byte[]]::new(2500000))` 으로 zero-byte 더미 동적 생성, mime=`image/jpeg`) | 200 + `warning:"consider Plane UI for files > 2MB"` |
| | | R1-c | mime=`application/pdf` | `unsupported mime` |
| | | R1-d | 6MB 페이로드 (zero-byte 더미) | `file too large` |
| | | R1-e | `content_base64="not_b64!!!"` | `invalid base64` |
| | | R1-f | random UUID `entity_id` | `plane api error: 404 ...` |
| | | R1-g | R1-a 와 동일, **non-admin PAT** | 200 (project member 권한이면 admin 불필요) |
| R2 | `download_file` | R2-a | R1-a 의 asset_id, `include_content_base64=false` | 200, `presigned_url` 채워짐, `content_base64=null` |
| | | R2-b | 같은 asset_id, `include_content_base64=true` | base64 가 R1-a 원본과 일치 |
| | | R2-c | random UUID asset_id | `plane api error: 404 ...` |
| | | R2-d | R2-a, **non-admin PAT** | 200 |
| R3 | `list_file_assets` | R3-a | 임의 args | `NotImplementedError: Plane fork's /api/assets/v2/ does not expose a list-by-entity endpoint — see .claude/docs/customization/todo.md #7` 정확 일치 |
| R4 | `get_instance_info` | R4-a | admin PAT | 200, `version` 또는 `instance_id` 채워짐 |
| | | R4-b | **non-admin PAT** | `requires instance admin` |
| R5 | `list_workspace_health` | R5-a | `limit=20`, admin PAT | `workspaces` 배열, 항목에 `slug`, `member_count` 채워짐 |
| | | R5-b | `limit=51` | validation error (1..50) |
| | | R5-c | **non-admin PAT** | `requires instance admin` |
| R6 | `get_recent_ipban_events` | R6-a | `limit=10`, admin PAT | `events` 배열, 빈 배열이면 `warning` 확인 |
| | | R6-b | `limit=1001` | validation error (1..1000) |
| | | R6-c | **non-admin PAT** | `requires instance admin` |
| R7 | `trigger_backup_now` | R7-a | admin PAT | **200 만 통과** — Plane 측 5xx (현재 `todo.md` #8 미해결로 예상) 면 **fail 표기**. 의도된 알람 — todo #8 해결 시 자연 통과로 전환. |
| | | R7-b | **non-admin PAT** | `requires instance admin` |

**총 21 케이스**. 케이스당 30~60초 → 합 15~25분.

### 6.1. R1-b / R1-d 더미 페이로드 생성 (정식)

PowerShell:
```powershell
$big = [Convert]::ToBase64String([byte[]]::new(2500000))   # R1-b: 2.5MB
$over = [Convert]::ToBase64String([byte[]]::new(6000000))  # R1-d: 6MB
```

**주의**: zero-byte buffer 라 실제 JPEG/PNG 헤더 없음. 서버는 **size 체크가 mime 검증보다 먼저** 또는 **파일 매직 검증 안 함** 가정. 실 동작이 다르면 R1-b/R1-d 합격 조건 재검토 필요 — implementation plan 의 첫 dry-run 에서 확인.

## 7. §4 결과 기록 명세

### 7.1. Smoke 결과 (한 줄)

```
| 일시 | 트리거 | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | 비고 |
|------|--------|-----|-----|-----|-----|-----|-----|-----|-----|------|
| 2026-MM-DD HH:MM | NSSM 재시작 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |  |
```

### 7.2. Regression 결과 (한 줄 + 실패 상세)

```
| 일시 | upstream HEAD | R1 | R2 | R3 | R4 | R5 | R6 | R7 | 실패 항목 상세 |
|------|---------------|-----|-----|-----|-----|-----|-----|-----|----------------|
| 2026-MM-DD | upstream/main = abc123 | ✅(7/7) | ✅(4/4) | ✅(1/1) | ✅(2/2) | ✅(3/3) | ✅(3/3) | ❌(0/2) | R7-a 500 — todo #8 미해결 |
```

→ 두 표 모두 `deployment.md` 의 세션 블록에 누적.

## 8. §5 트러블슈팅 매트릭스 명세

| 증상 | 가능 원인 | 1차 확인 |
|------|----------|---------|
| S0 직결 401 + Caddy 502/404 | Caddy 미기동, Caddyfile 오타 | `Get-Service caddy`, `caddy validate` |
| S0 양쪽 connection refused | NSSM `plane-mcp` 미기동 | `Get-Service plane-mcp`, `netstat -an \| findstr :8211` |
| S1 fork 7 종 누락 | `register_fork_tools()` wiring 회귀 | `pytest tests/test_server_wiring.py` |
| S2 admin PAT 인데 `is_instance_admin:false` | Plane fork commit `51a7e94` 미반영 | `git -C D:\Workspace\plane log --oneline \| Select-String 51a7e94` |
| S4 upload 200 + download base64 mismatch | Plane v2 asset flow 회귀 | `tools/files.py` 실 코드 vs `tools-reference.md` flow |
| S6 `events:[]` + `warning:"file not found"` | IPBan 로그 경로/ACL 회귀 | `icacls D:\Workspace\plane-logs\ipban`, `PLANE_MCP_IPBAN_LOG` env |
| S7 / R7 `Start-ScheduledTask ... 액세스가 거부` | `todo.md` #8 미해결 | 알려진 이슈, R7-a 의도된 fail |
| 모든 항목 `Parse error: Expecting value: line 1 column 1` | cmd single quote escape 오류 | 부록 A 참고 |

## 9. 부록 A — escape 가이드 명세

3-way 동일 명령 (`get_me` 1회) 비교표:

- **PowerShell** (권장): `curl.exe ... -d '{\"jsonrpc\":...}'` (`curl` alias 가 `Invoke-WebRequest` 가리킴 → `curl.exe` 명시 필수 단락 포함)
- **cmd.exe**: `curl ... -d "{\"jsonrpc\":...}"` (single quote 미지원 함정 단락 포함)
- **bash** (참고용): `curl ... -d '{"jsonrpc":...}'`

## 10. 부록 B — SSE 응답 필드 추출 helper 명세

PowerShell:
```powershell
function Get-McpField { param($body, $jq)
  $line = $body | Select-String -Pattern '^data: '
  $json = ($line -replace '^data: ','') | ConvertFrom-Json
  return $json.result.structuredContent | Select-Object -ExpandProperty $jq
}
```

bash (참고):
```bash
curl ... | grep '^data:' | sed 's/^data: //' | jq '.result.structuredContent.is_instance_admin'
```

## 11. 연동 문서 갱신

implementation plan 에 포함될 부수 작업:

1. `CLAUDE.md` §"참조 문서 현황" 표에 1행 추가:
   ```
   | 운영 검증 체크리스트 | `.claude/docs/customization/test-scenarios.md` | ✅ 존재 (2026-04-25) |
   ```
2. `deployment.md` Session 1 의 N4 표 끝에 한 줄: `→ 정식 체크리스트는 .claude/docs/customization/test-scenarios.md §2 참조`
3. (선택) `tools-reference.md` 본문에는 변경 없음. 부록 A 의 escape 가이드가 본문 cURL 예시의 함정을 보완.

## 12. 의존성 & 제약

- **Plane fork 의존**:
  - `51a7e94` (`is_instance_admin` 노출) — S2 / R4-b / R5-c / R6-c / R7-b 합격에 필수
  - `733c57e` (AdminBackupView) — S7 / R7-a 200 자체에 필수
  - `8502563` (`ProjectAssetEndpoint` API key 인증) — S4 / R1-a / R2-a 에 필수
- **호스트 의존**:
  - IPBan 로그: `D:\Workspace\plane-logs\ipban\stdout.log` 존재 + `.\plane` 계정 R 권한 (`deployment.md` N3)
  - PlaneBackup Task: 등록 자체는 되어 있어 `Get-ScheduledTask -TaskName PlaneBackup` 이 State=Ready 반환. 단 `.\plane` 계정의 실행 권한 부족으로 `Start-ScheduledTask` 가 거부 — R7-a 가 실통과 안 되는 원인 (`todo.md` #8)
- **자격 의존**: non-admin user 가 `develop` workspace 의 멤버 + `PLANE_TEST_PROJECT_ID` 의 project member (R1-g / R2-d 통과 조건)
- **시간 분리**: Smoke 와 Regression 은 독립 실행 가능. Regression 은 R0 = Smoke 통과 전제.

## 13. 의도된 알람 / known fail

본 spec 채택 시점에 **fail 로 남는 케이스 1건**:

- **R7-a** (`trigger_backup_now` admin) — `todo.md` #8 해결까지 Plane 500 반환. 합격 기준 (b)200 만 통과 선택했으므로 의도된 알람. 해결 즉시 자연 통과.

## 14. 비대상 명시 (재확인)

- 자동화 스크립트 (PowerShell 또는 pytest) — 별 트랙
- non-admin PAT 의 project-member 권한 동적 생성/회수 — 운영자 사전 셋업
- Caddy strip-path 외 reverse proxy 회귀 (TLS, header rewrite 등) — `/mcp/*` block 만 검증
- Plane 자체 헬스체크 (DB pool, S3 등) — 영역 외

## 15. 후속

- 회귀 빈도가 월 1회를 넘어서거나 케이스 수가 ~30 을 넘으면 옵션 2 (PowerShell 보조 스크립트) 로 승격 검토
- pytest E2E 트랙 (옵션 3) 은 CI 도입 시점에 별 spec
- `todo.md` #7 (list_file_assets 구현) 진행 시 R3 갱신 — 현재 negative 케이스 → positive + negative 추가
- `todo.md` #8 해결 시 R7-a 합격 조건은 그대로 (200 통과). PlaneBackup 의 actual run 검증은 별 케이스로 추가 검토.
