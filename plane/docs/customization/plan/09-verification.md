# Phase 8 — 검증 · 백업 · 유지보수

> **네비게이션**: [← Phase 7](08-external-access.md) · [목차](../plan.md) · [다음: 리스크 →](10-risks.md)
>
> 연관: [../sqlite-reference.md §6](../sqlite-reference.md) (재검증 절차) · [../security-todo.md §6](../security-todo.md)

**목표**:
1. Phase 0~7 완료 후 **기능 · 회귀 · 부하 · 재부팅** 네 축의 실측 통과.
2. 백업(SQLite + 업로드 + site.env) 자동화 — Windows Task Scheduler.
3. 업데이트 / 롤백 플레이북 문서화.

**Plane 코드 수정 없음**.

---

## 1. 기능 검증 체크리스트

모두 `http://222.234.220.199` 에서 브라우저로 검증.

### 1.1 핵심 워크플로우

- [ ] 로그인 (email + password) — 초기 superuser 계정
- [ ] 워크스페이스 생성
- [ ] 프로젝트 생성
- [ ] 이슈 CRUD (제목, 설명, 상태, 우선순위, 담당자, 라벨)
- [ ] 사이클 생성 → 이슈 할당 → 진행 상황 차트
- [ ] 모듈 생성 → 이슈 연결
- [ ] 페이지 생성 → Tiptap 에디터에서 텍스트/이미지 붙여넣기
- [ ] 이슈 첨부파일 업로드 (이미지, PDF, zip 각 1개) — Phase 4 LocalFSStorage 실측
- [ ] 첨부파일 다운로드 (서명된 URL 302 redirect → FileResponse 스트림)
- [ ] 페이지 간 내비게이션, 뒤로 가기
- [ ] 로그아웃

### 1.2 실시간 협업 (live 필요 시)

- [ ] 페이지를 두 브라우저에서 동시 열기 → 한쪽 편집이 반대쪽에 실시간 반영
- [ ] WebSocket 연결 상태 (브라우저 DevTools → Network → WS)

혼자 쓴다면 이 섹션은 선택.

### 1.3 admin / space

- [ ] `/god-mode/` 로그인 (superuser)
- [ ] InstanceConfiguration 페이지 렌더 (Phase 2 configure_instance 결과)
- [ ] space 링크 공유 — 한 프로젝트를 public 으로 전환, `/spaces/<slug>/<pid>/` 로 익명 접근

### 1.4 Celery / 스케줄

- [ ] 이슈 수정 → activity log 에 자동 생성 (`bgtasks/issue_activities_task`)
- [ ] 5분 대기 → `stack_email_notification` 로그 (콘솔 EMAIL_BACKEND)
- [ ] `python manage.py shell` 에서 `delete_api_logs.delay()` → worker 처리 로그
- [ ] 자정 이후 로그에 `hard_delete`, `archive_and_close_old_issues` 실행 확인

---

## 2. 회귀 테스트 (포크 유지 중 자산 활용)

`sqlite-reference.md §6` 의 재검증 절차를 **운영 venv 에서** 실행.

```powershell
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\Activate.ps1

# apps/api/.env 를 process env 로 먼저 주입한다 (SECRET_KEY/REDIS_URL 미주입 시
# plane.celery import 단계에서 AttributeError: 'NoneType' object has no attribute 'startswith'
# 으로 즉시 crash — handoff §7a #2. Plane 은 .env 를 자동 로드하지 않는다).
Get-Content .env -Encoding UTF8 | ForEach-Object {
  $line = $_.TrimStart([char]0xFEFF).Trim()
  if ($line -and -not $line.StartsWith('#')) {
    $kv = $line -split '=', 2
    if ($kv.Count -eq 2) {
      [Environment]::SetEnvironmentVariable($kv[0], $kv[1], 'Process')
    }
  }
}

$env:DJANGO_SETTINGS_MODULE = "plane.settings.test"
$env:SQLITE_PATH = "D:/tmp/plane_verify.sqlite3"
$env:APP_BASE_URL = "http://222.234.220.199"
$env:WEB_URL = "http://222.234.220.199"
$env:ALLOWED_HOSTS = "*"   # Django APIClient 기본 host 'testserver' 허용
                           # (apps/api/.env 의 ALLOWED_HOSTS=222.234.220.199,localhost,127.0.0.1
                           #  그대로면 measure_latency.py 등에서 DisallowedHost 400).

# 2.1 fresh DB + seed
Remove-Item $env:SQLITE_PATH -ErrorAction SilentlyContinue
python manage.py migrate
python plane\tests\golden_seed.py --scale 100 --quiet

# 2.2 골든 캡처 + diff
python plane\tests\golden_capture.py --capture --out D:\tmp\verify-golden
python plane\tests\golden_diff.py --old plane\tests\golden --new D:\tmp\verify-golden
# expect diff_count = 0

# 2.3 W1~W20 쓰기 시나리오
python plane\tests\e_write_scenarios.py
# 20/20 passed

# 2.4 유닛 스위트 (unit/ 전체 — bg_tasks, middleware, models, perf, serializers, settings, utils)
python -m pytest plane\tests\unit -q
# expect 106 passed + 5 failed (pre-existing 1 test_copy_s3_objects_of_description_and_assets
# + upstream known 4: test_url 3 + test_work_item_link_task 1). handoff §7a/§7b 참조.
# 이 5 건은 고정 baseline. 다른 실패 수면 신규 회귀 의심.

# 2.5 latency
python plane\tests\measure_latency.py --iterations 100
# all 6 scenarios PASS

# 2.6 동시 쓰기
python plane\tests\concurrent_writes.py --n 50 --workers 5
# created=50, locked=0

# 2.7 residue guard
python -m pytest plane\tests\unit\models\test_phase_g_residues.py -q
# 4 passed
```

---

## 3. 부하 smoke (1인 운영 상한)

1인 운영 primary 지표는 **concurrency = 1 에서 p95 < 500 ms**. c=2~5 는 보조(PASS 권장), c=10 은 reference (다중 사용자 전환 시 재측정).

선행 (운영 호스트):

- **부하 도구**: `D:\Workspace\plane-app\tools\bombardier\bombardier.exe` (v2.0.2 windows amd64, <https://github.com/codesenberg/bombardier/releases/tag/v2.0.2> 의 `bombardier-windows-amd64.exe` asset). `hey` 는 v0.1.5 release 에 windows precompiled binary 미제공 (`https://api.github.com/repos/rakyll/hey/releases/latest` 의 `"assets": []`).
- **API token**: Django shell `APIToken.objects.create(user=<superuser>, user_type=0, label="smoke-...")` 또는 `/profile/api-tokens` UI. Plane 인증 헤더는 **`X-API-Key`** 이다 (DRF `APIKeyAuthentication.auth_header_name = "X-Api-Key"`, `plane/api/middleware/api_authentication.py:24`). `Authorization: Bearer ...` 는 OAuth provider 용. APIToken 의 `allowed_rate_limit` 필드는 현 코드에서 실 enforce 안 됨 — 실제 rate limit 은 env `API_KEY_RATE_LIMIT` (`plane/api/rate_limit.py:14`) 가 전역 결정.
- **Rate limit 상향**: 기본 `60/minute` 은 `-n 1000` 에 즉시 걸림 (첫 60 req 만 2xx, 나머지 4xx). `ops/site.env` 에 `API_KEY_RATE_LIMIT=10000/minute` 추가 → `ops/render-envs.ps1` (`$PSScriptRoot` 공백 이슈로 `-SiteEnv`/`-AppRoot` 명시 필수, handoff §7) 재렌더 → `ops/register-services.ps1` (Admin PS, `PLANE_SERVICE_PASSWORD` env 또는 `ops/.plane_pass`) 로 NSSM `AppEnvironmentExtra` 재주입 → plane-api 자동 재기동. 상세 handoff §7g.

```powershell
$bomb  = "D:\Workspace\plane-app\tools\bombardier\bombardier.exe"
$url   = "http://127.0.0.1/api/v1/workspaces/<slug>/projects/"
$token = "<api-token>"

# primary — 1인 운영 기준
& $bomb -n 1000 -c 1 -l -H "X-API-Key: $token" $url
# 기대: p95 < 500 ms

# 보조 — c 증가에 따른 지연 추이
foreach ($c in 2, 5, 10) {
  & $bomb -n 1000 -c $c -l -H "X-API-Key: $token" $url
}
```

실측 baseline (2026-04-24, Caddy → uvicorn --workers 1 → plane.sqlite3, loopback):

| c | n | p50 (ms) | p95 (ms) | p99 (ms) | verdict |
|---:|---:|---:|---:|---:|---|
| 1 | 50 | 53.7 | **64.7** | 89.1 | PASS (primary) |
| 2 | 50 | 58.4 | 99.3 | 105.6 | PASS |
| 5 | 100 | 139.0 | 158.5 | 164.9 | PASS |
| 10 | 1000 | 488.5 | 649.3 | 726.1 | reference (1인 운영 상정 밖) |

c=10 의 p95 500 ms 초과는 `--workers 1` + Django sync ORM → async loop thread pool + SQLite single-writer lock 의 직렬화 때문. 1인 운영(동시 사용자 1~5)에서는 c=5 p95=159 ms 까지 안정. 다중 사용자 전환 시 `uvicorn --workers N` 증설 또는 Postgres 전환 재측정. SQLite WAL + BEGIN IMMEDIATE 한계는 `sqlite-reference.md §4` 실측과 일관.

---

## 4. 재부팅 내성

```powershell
Restart-Computer -Confirm
# 재부팅 후 3분 내 다시 접속:
curl.exe -sI http://222.234.220.199/
# 200
Get-Service Redis, plane-api, plane-celery, plane-beat, plane-live, caddy |
  Where-Object Status -ne "Running"
# 빈 결과
```

---

## 5. 백업 자동화 (Windows Task Scheduler)

### 5.1 백업 스크립트

`D:\Workspace\plane-app\ops\backup.ps1`:

```powershell
[CmdletBinding()]
param(
  [string]$BackupRoot = "D:\Workspace\plane-data\backup"
)

$ErrorActionPreference = "Stop"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $BackupRoot $ts
New-Item -ItemType Directory -Path $target -Force | Out-Null

# 1) SQLite 일관 백업 (VACUUM INTO — WAL 에 있는 변경도 반영)
$venv = "D:\Workspace\plane-app\apps\api\.venv\Scripts\python.exe"
& $venv -c "import sqlite3, os; src=r'D:\Workspace\plane-data\sqlite\plane.sqlite3'; dst=r'$target\plane.sqlite3'; conn=sqlite3.connect(src); conn.execute(f\"VACUUM INTO '{dst}'\"); conn.close()"

# 2) 업로드 디렉토리 (증분은 robocopy /MIR 대신 매 백업 전체 복사 — 1인 규모 충분)
robocopy "D:\Workspace\plane-data\uploads" "$target\uploads" /E /NFL /NDL /NJH /NJS | Out-Null

# 3) site.env (비밀값 포함 — AES 암호화 필수)
# TODO: 7z + AES-256 암호화 (security-todo §6 에 이월)
Copy-Item "D:\Workspace\plane-app\ops\site.env" "$target\site.env"

# 4) 14일 지난 백업 삭제
Get-ChildItem $BackupRoot -Directory | Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-14) } | Remove-Item -Recurse -Force

Write-Host "Backup completed: $target"
```

### 5.2 Task Scheduler 등록

매일 02:00 UTC (Windows 기본 시각이 UTC — Phase 0 §1.4):

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File D:\Workspace\plane-app\ops\backup.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At "02:00"
$principal = New-ScheduledTaskPrincipal -UserId "plane" -LogonType Password -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName "PlaneBackup" `
  -Action $action -Trigger $trigger -Principal $principal -Settings $settings
```

`plane` 계정으로 실행. 비밀번호 최초 등록 시 인터랙티브 입력.

### 5.3 복구 훈련 (분기 1회)

```powershell
# 1. 별도 경로에 복구
$restore = "D:\Workspace\plane-restore"
Copy-Item "D:\Workspace\plane-data\backup\<YYYYMMDD-HHMMSS>\plane.sqlite3" "$restore\plane.sqlite3"

# 2. 운영 DB 와 분리된 venv 로 migrate 검증
$env:SQLITE_PATH = "$restore\plane.sqlite3"
python manage.py migrate --plan       # 변경 없음 확인
python manage.py dbshell
sqlite> SELECT count(*) FROM db_issue;  # 건수 일치
```

---

## 6. 업데이트 / 롤백 플레이북

### 6.1 정기 업데이트

```powershell
# 1) 백업 (§5)
powershell -File D:\Workspace\plane-app\ops\backup.ps1

# 2) 서비스 중지
Stop-Service plane-beat, plane-celery, plane-live, plane-api, caddy

# 3) 코드 fetch
cd D:\Workspace\plane-app
git fetch origin
git reset --hard origin/master

# 4) 의존성
cd apps\api
.\.venv\Scripts\Activate.ps1
pip install -r requirements\local.txt

cd ..\..
pnpm install

# 5) 마이그레이션
cd apps\api
python manage.py migrate
python manage.py configure_instance
python manage.py collectstatic --noinput

# 6) 프론트 재빌드 (render-envs 필요 시)
cd ..\..
pnpm turbo build --filter=web --filter=admin --filter=space --filter=live

# 7) 서비스 재개
Start-Service caddy, plane-api, plane-celery, plane-beat, plane-live
```

### 6.2 롤백

백업이 있으므로:

```powershell
Stop-Service plane-beat, plane-celery, plane-live, plane-api, caddy

# 1) 코드 역행
cd D:\Workspace\plane-app
git reset --hard <이전 커밋>

# 2) DB 복원
Copy-Item "D:\Workspace\plane-data\backup\<이전 스냅샷>\plane.sqlite3" `
  "D:\Workspace\plane-data\sqlite\plane.sqlite3" -Force
Remove-Item "D:\Workspace\plane-data\sqlite\plane.sqlite3-wal" -ErrorAction SilentlyContinue
Remove-Item "D:\Workspace\plane-data\sqlite\plane.sqlite3-shm" -ErrorAction SilentlyContinue

# 3) uploads 복원 (이슈/페이지 첨부가 최근 추가되었다면 선택적 복원)
# robocopy backup/<ts>/uploads uploads /MIR

# 4) 서비스 재개
Start-Service caddy, plane-api, plane-celery, plane-beat, plane-live
```

### 6.3 유지보수 모드 (선택)

Caddy 설정에 `maintenance.html` 정적 반환 사이트 추가 가능. 현 Phase 범위 밖 (단기 유지보수는 서비스 중지로 충분 — 외부 클라이언트는 connection refused).

---

## 7. 모니터링 기본

1인 규모라 외부 모니터링 시스템 불필요. 수동 점검 위주.

### 7.1 주간 헬스 체크 스크립트

`D:\Workspace\plane-app\ops\healthcheck.ps1`:

```powershell
$out = "D:\Workspace\plane-logs\healthcheck-$(Get-Date -Format yyyyMMdd).log"

"=== Services ===" | Out-File $out
Get-Service Redis, plane-api, plane-celery, plane-beat, plane-live, caddy |
  Format-Table Name, Status, StartType | Out-File $out -Append

"`n=== Disk ===" | Out-File $out -Append
Get-PSDrive C, D | Format-Table Name, Used, Free | Out-File $out -Append

"`n=== DB size ===" | Out-File $out -Append
(Get-Item "D:\Workspace\plane-data\sqlite\plane.sqlite3").Length / 1MB | Out-File $out -Append

"`n=== Recent errors ===" | Out-File $out -Append
@("api","worker","beat","live","caddy") | ForEach-Object {
  $err = "D:\Workspace\plane-logs\$_\stderr.log"
  if (Test-Path $err) {
    "`n--- $_ ---" | Out-File $out -Append
    Get-Content $err -Tail 20 | Out-File $out -Append
  }
}

"`n=== HTTP ===" | Out-File $out -Append
@("/", "/god-mode/", "/spaces/", "/api/users/me/") | ForEach-Object {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1$_" -UseBasicParsing -MaximumRedirection 0
    "$_ → $($r.StatusCode)" | Out-File $out -Append
  } catch {
    "$_ → ERROR: $_" | Out-File $out -Append
  }
}
```

주 1회 Task Scheduler 로 실행 → 이메일 알림 가능 (SMTP 도입 시).

---

## 7a. 전체 Phase WBS 집계 (최종 종합)

Phase 0~7 의 모든 WBS 가 완료 상태인지 한 장으로 교차 검증. 각 WBS 의 상세는 해당 Phase 문서 § 참조.

### Phase 0 — 사전 준비 ([01-prerequisites.md](01-prerequisites.md) §9)

- [ ] P0-1 OS 업데이트 · P0-2 디스크 여유 · P0-3 실행 정책 · P0-4 UTC
- [ ] P0-5 `plane` · P0-6a `plane-admin` (로컬 전용) · P0-6b `joojm` (RDP) · P0-7 RDP/NLA
- [ ] P0-8 3 루트 + 4 하위 · P0-9 ACL
- [ ] P0-10 Python 3.13 · P0-11 Node 24 · P0-12 pnpm 10.32.1
- [ ] P0-13 Redis MSI · P0-14 Git · P0-15 NSSM · P0-16 VC++ · P0-17 cloudflared
- [ ] P0-18 내부 6 포트 인바운드 차단

### Phase 1 — 인프라 ([02-infrastructure.md](02-infrastructure.md) §4a)

- [ ] P1-1 ops + logs/redis · P1-2 redis.conf · P1-3 REDIS_PASSWORD
- [ ] P1-4 데이터 이전 · P1-5 binPath · P1-6 계정 전환 · P1-7 재시작+검증
- [ ] P1-8 원본 conf 백업 · P1-9 로그 5 하위 · P1-10 production.py LOG_DIR (완료)

### Phase 2 — 소스 준비 ([03-source-prep.md](03-source-prep.md) §7a)

- [ ] P2-1 clone · P2-2 venv · P2-3 pip install · P2-4 3.13 실측 · P2-5 check
- [ ] P2-6 pnpm install · P2-7 site.env · P2-8 비밀값 · P2-9 render-envs · P2-10 api/.env
- [ ] P2-11 ACL · P2-12 env 로딩 · P2-13 migrate · P2-14 superuser
- [ ] P2-15 configure_instance · P2-16 register_instance · P2-17 collectstatic · P2-18 runserver

### Phase 3 — Celery broker ([04-celery-broker.md](04-celery-broker.md) §5a)

- [ ] P3-1 common.py (완료) · P3-2 .env 실효 · P3-3 RABBITMQ 잔재 0
- [ ] P3-4 worker solo · P3-5 enqueue smoke · P3-6 /1 관찰 · P3-7 beat

### Phase 4 — 저장소 (서브 4) ([05-storage.md](05-storage.md) §3a)

- [ ] P4.1-1~7 어댑터 + endpoint + 테스트 5종
- [ ] P4.2-1~7 view round-trip + MCP
- [ ] P4.3-1~6 export/cleanup + bucket no-op
- [ ] P4.4-1~3 프론트 타입 유지/완화 판단

### Phase 5 — 프론트 빌드 ([06-frontend-build.md](06-frontend-build.md) §5a)

- [ ] P5-1~6 render-envs 4 섹션 · turbo build · 산출물 4종 · VITE inline · live 기동

### Phase 6 — NSSM 서비스 ([07-systemd.md](07-systemd.md) §7a)

- [ ] P6-1 NSSM 함수 · P6-2 plane-api · P6-3 plane-celery · P6-4 plane-beat · P6-5 plane-live
- [ ] P6-6 4 Running · P6-7 재부팅 자동 기동

### Phase 7 — 외부 접근 ([08-external-access.md](08-external-access.md) §6a)

- [ ] P7-1 Caddy 설치 · P7-2 Caddyfile · P7-3 validate · P7-4 루프백 smoke
- [ ] P7-5 Caddy Service · P7-6 방화벽 80 · P7-7 포트 포워딩 · P7-8 외부 실측

---

## 7b. plan.md 전제 요구사항 최종 검증

[../plan.md §0](../plan.md) 의 확정 전제가 실 배포 시스템에서 충족되는지 최종 대조.

| 전제 | 실측 근거 | 충족 |
|---|---|---|
| Windows Server 2025 네이티브 | P0-1 (Build 26100) · 전 서비스 Windows 바이너리 | [ ] |
| Docker/WSL2 불사용 | Get-Process 에 docker/wsl 없음 | [ ] |
| 경로 `D:\Workspace\plane-{app,data,logs}` | P0-8, P0-9 ACL + Phase 2 배치 | [ ] |
| `plane` 서비스 계정 + `plane-admin` RDP | P0-5, P0-6 | [ ] |
| SQLite 단일 파일 `plane-data/sqlite/plane.sqlite3` | P2-13 생성 확인 | [ ] |
| Redis tporadowski 5.0.14 · /0 cache · /1 broker | P1-7, P3-2 | [ ] |
| Celery `--pool=solo` + result backend None | P6-3 · `transport: redis://.../1, results: disabled` | [ ] |
| LocalFSStorage (A2 어댑터) · app/·api/·space/·bgtasks | P4.1-7 + P4.2-1~7 + P4.3-5 | [ ] |
| Caddy 단일 80 포트 path prefix | P7-4, P7-8 | [ ] |
| 공인 IP 222.234.220.199 (HTTP) | P7-8 외부 실측 | [ ] |
| NSSM 프로세스 매니저 | P6-6 4 서비스 | [ ] |
| ops/site.env 단일 설정 소스 (Q1) | P2-7, P2-9 + P5-1 4 섹션 | [ ] |

모두 `[ ]` 가 `[x]` 로 채워져야 배포 완료.

---

## 7c. 엔드투엔드 시나리오 (최종 종합 테스트)

개별 Phase 의 단위 테스트 이후 전체 사슬을 검증하는 E2E 시나리오. 각각을 순서대로 실행.

### E2E-1. 로그인 → 이슈 CRUD

1. 외부 브라우저에서 `http://222.234.220.199/` 접속 → 로그인 화면 렌더
2. superuser 로그인 (`admin@plane.local` / 설정 비밀번호)
3. 워크스페이스 생성 → 프로젝트 생성 → 이슈 생성 (제목·설명·담당자·라벨·우선순위)
4. 이슈 수정 → 상태 변경 → 댓글 작성
5. 이슈 삭제

기대: 모든 단계 200 응답 + UI 반영.

### E2E-2. 첨부파일 업로드 → 다운로드 (LocalFSStorage 라운드트립)

1. E2E-1 의 이슈 상세 → 첨부 드래그 (이미지 PNG, PDF, ZIP 각 1)
2. DevTools Network → `/api/.../file-assets/` → `upload_data.url` 이 `http://222.234.220.199/api/assets/local-upload` 인지 확인
3. 업로드 완료 후 브라우저에서 첨부 클릭 → 다운로드 성공
4. `D:\Workspace\plane-data\uploads\<ws>/...` 에 실 파일 존재

### E2E-3. Celery 백그라운드 작업

1. 이슈 수정 직후 30초 대기
2. `Get-Content D:\Workspace\plane-logs\worker\stdout.log -Tail 30` → `plane.bgtasks.issue_activities_task` 처리 로그
3. beat 가 5분 내 `stack_email_notification` 호출 (콘솔 출력 → `plane-logs/api/stderr.log` 에 메일 페이로드 덤프)
4. `redis-cli -a $pw -n 1 DBSIZE` → 평시 0 근처 (enqueue 중에만 증가)

### E2E-4. 공개 Space 공유

1. 프로젝트 설정 → public 전환 → 공유 링크 획득
2. **시크릿 창** (로그아웃 상태) 에서 링크 방문
3. 프로젝트 조회 + 이슈 상세 + 첨부 다운로드 (익명 서명 URL)

### E2E-5. MCP 서버 연결 (API 키 경로)

1. `/god-mode/` → API key 발급 (1개)
2. `D:\Workspace\plane-mcp-server` 환경변수:
   ```
   PLANE_API_KEY=<키>
   PLANE_WORKSPACE_SLUG=<슬러그>
   PLANE_BASE_URL=http://222.234.220.199
   ```
3. MCP inspector 또는 Claude Desktop 에서 Plane MCP 연결
4. `list_workspaces` / `create_issue` / `upload_issue_attachment` 툴 호출
5. 각 호출이 `/api/v1/...` 경로로 200 반환

### E2E-6. 재부팅 내성

1. `Restart-Computer`
2. 재부팅 후 3분 대기
3. `Get-Service Redis, plane-api, plane-celery, plane-beat, plane-live, caddy` → 전부 Running
4. 외부 브라우저에서 접속 → 로그인 가능

### E2E-7. 업데이트 드라이런

1. `Stop-Service plane-beat, plane-celery, plane-live, plane-api, caddy`
2. `cd D:\Workspace\plane-app; git fetch origin; git reset --hard origin/master` (변경 없음)
3. `pip install -r apps\api\requirements\local.txt` / `pnpm install`
4. `python manage.py migrate` → `No migrations to apply`
5. `python manage.py collectstatic --noinput`
6. `pnpm turbo build` (cache hit)
7. `Start-Service caddy, plane-api, plane-celery, plane-beat, plane-live`
8. 외부 접근 재검증

### E2E-8. 백업 + 복구 훈련

1. `.\ops\backup.ps1` 수동 실행 → `plane-data\backup\<ts>\` 생성 확인
2. 별도 경로 (`D:\Workspace\plane-restore`) 에 복원
3. 임시 `SQLITE_PATH` 로 `python manage.py migrate --plan` → no changes
4. 복원 DB 의 `User`, `FileAsset`, `Issue` 레코드 수가 원본과 일치

### E2E-9. 회귀 테스트 (SQLite 자산)

1. `sqlite-reference.md §6` 의 재검증 절차 전체 실행
2. golden_diff = 0
3. W1~W20 = 20/20 passed
4. unit 스위트 (phase-g residue 포함) passed
5. latency 6/6 PASS
6. concurrent 50/0 locked

### E2E-10. 도메인 전환 드라이런 (미래 경로 확인)

1. `ops/site.env` 에서 `PUBLIC_HOST=plane.example.com`, `PUBLIC_SCHEME=https` 가상 편집
2. `.\ops\render-envs.ps1`
3. `apps/api/.env` 의 `WEB_URL` · `ALLOWED_HOSTS` · `CSRF_TRUSTED_ORIGINS` 가 새 값으로 변경
4. `apps/web/.env` 의 `VITE_*_BASE_URL` 도 변경
5. 편집을 원복 (`PUBLIC_HOST=222.234.220.199`) + render-envs 재실행
6. 기존 상태 복원

---

## 7d. 보안 TODO 이월 상태

배포 완료 시점에 [../security-todo.md](../security-todo.md) 의 항목 중 **이월 채택** 된 것들을 명시.

- [ ] §1 Redis tporadowski EOL — Memurai 중기 전환 계획 별도 수립 시점
- [ ] §2 RDP Cloudflare Access/MFA — 도메인 확보 후
- [ ] §3 `/god-mode/` 접근 제한 — Cloudflare Access + 서비스 비활성 정책
- [ ] §4 업로드 AV 스캔 — Windows Defender MpCmdRun 통합
- [ ] §5 비밀값 Credential Manager/DPAPI — site.env 평문 해제
- [ ] §6 백업 암호화 — AES-256 / age
- [ ] §7 Celery 태스크 격리
- [ ] §8 로그 PII 마스킹

배포 직후는 모두 open. 각 항목은 별도 기획 승격 시점에 plan 서브폴더로 이관.

---

## 8. 체크포인트 (Phase 8 전체 완료)

- [ ] §1 기능 체크리스트 전 항목 통과
- [ ] §2 회귀 테스트 (golden diff=0, W1~W20, unit 53+, latency 6/6, concurrent 50/0) 통과
- [ ] §3 부하 smoke p95 < 500ms
- [ ] §4 재부팅 후 서비스 자동 기동
- [ ] §5.1 backup.ps1 수동 실행 성공 + §5.3 복구 훈련 1회
- [ ] §5.2 Task Scheduler "PlaneBackup" 등록, 익일 자동 실행 로그 확인
- [ ] §6.1 업데이트 플레이북 1회 드라이런 (코드 no-op 업데이트)
- [ ] §7.1 healthcheck.ps1 수동 실행

---

## 9. 이월 / 후속

- **site.env 백업 암호화** — 현재 평문 복사. AES-256 + 키 분리 → [../security-todo.md §6](../security-todo.md)
- **오프사이트 백업** — rclone + B2/S3 동기화 → security-todo §6
- **SMTP 도입** → security-todo §5 연장: healthcheck 결과 이메일 자동 발송
- **Prometheus + Grafana** — 과잉. healthcheck.ps1 로 충분
- **FTS5 검토** — 이슈/페이지 텍스트 대량 축적 후 재평가 → [../sqlite-reference.md §5 #1](../sqlite-reference.md)

---

> **네비게이션**: [← Phase 7](08-external-access.md) · [목차](../plan.md) · [다음: 리스크 →](10-risks.md)
