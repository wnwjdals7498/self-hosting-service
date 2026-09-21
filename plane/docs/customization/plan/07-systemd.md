# Phase 6 — 서비스 등록 (Windows NSSM)

> **네비게이션**: [← Phase 5](06-frontend-build.md) · [목차](../plan.md) · [다음: Phase 7 →](08-external-access.md)
>
> 파일명은 `07-systemd.md` (Linux 원안 잔재). 내용은 **Windows NSSM** 전면 개정.

**목표**: Phase 0~5 까지 준비된 Plane 컴포넌트를 Windows Service 로 등록하여 부팅 시 자동 기동 + 실패 시 재시작 + 로그 회전을 확보한다.

**등록 대상 서비스** (`Redis` 는 Phase 1 에서 이미 등록됨):

| 서비스명 | 커맨드 | 계정 | 의존성 |
|---|---|---|---|
| `plane-api`   | `uvicorn plane.asgi:application --host 127.0.0.1 --port 8000 --workers 1`  | plane | Redis |
| `plane-celery` | `celery -A plane worker --pool=solo -l info` | plane | Redis, plane-api |
| `plane-beat` | `celery -A plane beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler` | plane | Redis, plane-api |
| `plane-live` | `node --env-file=.env dist/start.mjs` | plane | Redis, plane-api |

Caddy 는 Phase 7 에서 별도 등록.

**Plane 코드 수정 없음**.

---

## 1. NSSM 기본 지식

NSSM(Non-Sucking Service Manager) — 일반 실행 파일을 Windows Service 로 래핑. Phase 0 §7.2 에서 `D:\Workspace\plane-app\tools\nssm\nssm-2.24\win64\nssm.exe` 로 사전 설치.

주요 명령:
```powershell
nssm install <svc>                         # 대화형
nssm install <svc> <exe> <args>            # 비대화형
nssm set <svc> <param> <value>
nssm get <svc> <param>
nssm start|stop|restart <svc>
nssm remove <svc> confirm
```

PATH 에 추가 (Phase 0 §7.2 안 했다면):
```powershell
setx /M PATH "$env:PATH;D:\Workspace\plane-app\tools\nssm\nssm-2.24\win64"
# 새 PowerShell 세션에서 반영
```

---

## 2. 공통 환경 세팅 파라미터

각 서비스에 공통으로 적용할 NSSM 파라미터. 개별 서비스 §3~§6 에서 재사용.

```powershell
function Set-NssmCommon {
  param(
    [Parameter(Mandatory)][string]$svc,
    [Parameter(Mandatory)][string]$stdoutLog,
    [Parameter(Mandatory)][string]$stderrLog
  )
  # 계정: .\plane (Phase 0 §2.1)
  nssm set $svc ObjectName ".\plane" "<plane-password>"

  # 자동 시작
  nssm set $svc Start SERVICE_AUTO_START

  # 실패 시 재시작 (throttle: 1분 안에 3회 실패 시 중지)
  nssm set $svc AppExit Default Restart
  nssm set $svc AppRestartDelay 5000        # 5s
  nssm set $svc AppThrottle 60000           # 60s

  # 로그
  nssm set $svc AppStdout  $stdoutLog
  nssm set $svc AppStderr  $stderrLog
  nssm set $svc AppStdoutCreationDisposition 4   # append
  nssm set $svc AppStderrCreationDisposition 4

  # 로그 회전: 10MB 또는 하루 단위
  nssm set $svc AppRotateFiles   1
  nssm set $svc AppRotateOnline  1
  nssm set $svc AppRotateSeconds 86400
  nssm set $svc AppRotateBytes   10485760
}
```

`<plane-password>` 는 Phase 0 §2.1 에서 설정한 `plane` 계정 비밀번호. 스크립트에 평문 기입 금지 — 실 등록 시 인터랙티브 입력 권장.

---

## 3. `plane-api` (Django uvicorn)

**왜 uvicorn 단독?** gunicorn 은 Windows 미지원. Django 4.2 ASGI 엔트리 `plane.asgi:application` + uvicorn 으로 충분 (1인 트래픽).

**`--workers 1`** 근거:
- Windows 에서 uvicorn multi-worker 는 fork 대신 spawn — 초기화 비용 큼
- SQLite WAL + BEGIN IMMEDIATE 는 다중 프로세스에도 안전하지만 1인이면 단일로 충분
- 확장 필요 시 worker 증가는 단순 설정 변경

### 3.1 등록

```powershell
$svc = "plane-api"
$venv = "D:\Workspace\plane-app\apps\api\.venv\Scripts"
$cwd  = "D:\Workspace\plane-app\apps\api"
$logs = "D:\Workspace\plane-logs\api"

nssm install $svc "$venv\uvicorn.exe" `
  "plane.asgi:application --host 127.0.0.1 --port 8000 --workers 1 --log-level info"
nssm set $svc AppDirectory $cwd

# .env 를 NSSM 환경 변수로 로딩 — 한 줄씩 NUL 구분하여 주입
$envLines = Get-Content "$cwd\.env" |
  Where-Object { $_ -and -not $_.StartsWith("#") } |
  ForEach-Object { $_.Trim() }
nssm set $svc AppEnvironmentExtra ($envLines -join "`0")

# DJANGO_SETTINGS_MODULE (wsgi.py/asgi.py 가 setdefault 하지만 명시)
nssm set $svc AppEnvironmentExtra ($envLines + "DJANGO_SETTINGS_MODULE=plane.settings.production" -join "`0")

Set-NssmCommon -svc $svc `
  -stdoutLog "$logs\stdout.log" `
  -stderrLog "$logs\stderr.log"

# 서비스 의존성
nssm set $svc DependOnService Redis

nssm start $svc
Get-Service $svc    # Running
```

### 3.2 기동 확인

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -MaximumRedirection 0
# 200 / 301 / 404 — 500 만 아니면 정상
Get-Content "$logs\stderr.log" -Tail 20
```

---

## 4. `plane-celery` (worker)

### 4.1 등록

```powershell
$svc = "plane-celery"
$venv = "D:\Workspace\plane-app\apps\api\.venv\Scripts"
$cwd  = "D:\Workspace\plane-app\apps\api"
$logs = "D:\Workspace\plane-logs\worker"

nssm install $svc "$venv\celery.exe" "-A plane worker --pool=solo -l info"
nssm set $svc AppDirectory $cwd

$envLines = Get-Content "$cwd\.env" | Where-Object { $_ -and -not $_.StartsWith("#") }
nssm set $svc AppEnvironmentExtra (($envLines + "DJANGO_SETTINGS_MODULE=plane.settings.production") -join "`0")

Set-NssmCommon -svc $svc -stdoutLog "$logs\stdout.log" -stderrLog "$logs\stderr.log"
nssm set $svc DependOnService "Redis/plane-api"

nssm start $svc
```

`plane-api` 기동 후 연속 실행되도록 DependOnService. 실제로 Celery worker 는 API 없이도 기동 가능하지만 register_instance 가 완료된 DB 가 필요하니 API 에 종속.

### 4.2 확인

```powershell
# .env 로딩 + python manage.py shell 로 enqueue
python manage.py shell
>>> from plane.bgtasks.cleanup_task import delete_api_logs
>>> delete_api_logs.delay()
# ...
Get-Content "D:\Workspace\plane-logs\worker\stdout.log" -Tail 20
# [INFO] Task plane.bgtasks.cleanup_task.delete_api_logs[...] succeeded
```

---

## 5. `plane-beat` (Celery beat)

### 5.1 등록

```powershell
$svc = "plane-beat"
$venv = "D:\Workspace\plane-app\apps\api\.venv\Scripts"
$cwd  = "D:\Workspace\plane-app\apps\api"
$logs = "D:\Workspace\plane-logs\beat"

nssm install $svc "$venv\celery.exe" `
  "-A plane beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler"
nssm set $svc AppDirectory $cwd

$envLines = Get-Content "$cwd\.env" | Where-Object { $_ -and -not $_.StartsWith("#") }
nssm set $svc AppEnvironmentExtra (($envLines + "DJANGO_SETTINGS_MODULE=plane.settings.production") -join "`0")

Set-NssmCommon -svc $svc -stdoutLog "$logs\stdout.log" -stderrLog "$logs\stderr.log"
nssm set $svc DependOnService "Redis/plane-api"

nssm start $svc
```

### 5.2 확인

```powershell
Get-Content "D:\Workspace\plane-logs\beat\stdout.log" -Tail 30
# [INFO] beat: Starting...
# [INFO] Scheduler: Sending due task check-every-five-minutes-to-send-email-notifications
```

5분 내 첫 스케줄 발송 로그가 나와야 정상.

---

## 6. `plane-live` (Node Yjs 서버)

### 6.1 등록

```powershell
$svc = "plane-live"
$cwd = "D:\Workspace\plane-app\apps\live"
$logs = "D:\Workspace\plane-logs\live"

# nvm-windows 가 설치한 node.exe 경로 확인
$node = (Get-Command node).Source

nssm install $svc $node "--env-file=$cwd\.env $cwd\dist\start.mjs"
nssm set $svc AppDirectory $cwd

Set-NssmCommon -svc $svc -stdoutLog "$logs\stdout.log" -stderrLog "$logs\stderr.log"
nssm set $svc DependOnService "Redis"

nssm start $svc
```

### 6.2 확인

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:3100/health" -UseBasicParsing -MaximumRedirection 0 2>$null
# 200 또는 404 (health 엔드포인트 유무에 따라)
Get-Content "D:\Workspace\plane-logs\live\stdout.log" -Tail 20
# "Listening on :3100" 류 메시지
```

---

## 7. 재부팅 테스트

```powershell
Restart-Computer -Confirm
# 재부팅 후
Get-Service Redis, plane-api, plane-celery, plane-beat, plane-live | Format-Table Name, Status, StartType
# 전부 Running, StartType=Automatic
```

---

## 7a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P6-1 | `Set-NssmCommon` PowerShell 함수 로딩 (공통 파라미터) | P0-15 | §2 | 등록 자동화 |
| P6-2 | `plane-api` 등록 + DependOn Redis | P2-18, P6-1 | §3 | Windows Service |
| P6-3 | `plane-celery` 등록 (--pool=solo) + DependOn Redis/plane-api | P3-4, P6-2 | §4 | Windows Service |
| P6-4 | `plane-beat` 등록 + DependOn Redis/plane-api | P3-7, P6-2 | §5 | Windows Service |
| P6-5 | `plane-live` 등록 + DependOn Redis | P5-4, P6-1 | §6 | Windows Service |
| P6-6 | 4 서비스 모두 `Running` 상태 확인 | P6-2~P6-5 | §8 | 4 Running |
| P6-7 | 재부팅 후 자동 기동 실측 | P6-6 | §7 | 전부 Running · Auto |

---

## 7b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P6-2 | `Get-Service plane-api \| Select Status, StartType` | Running · Automatic |
| P6-2 | `curl.exe -sI http://127.0.0.1:8000/` | 200/301/401 (500 아님) |
| P6-3 | `Get-Service plane-celery` · worker stdout 에 `ready.` | Running · `ready.` |
| P6-4 | `Get-Service plane-beat` · beat stdout 에 `Scheduler: Sending due task` (5 분 내) | Running · 스케줄 송출 |
| P6-5 | `Get-Service plane-live` · `curl -sI http://127.0.0.1:3100/` | Running · 200 |
| P6-6 | `Get-Service plane-api, plane-celery, plane-beat, plane-live \| ? Status -ne Running` | (빈 결과) |
| P6-7 | 재부팅 3분 후 `Get-Service plane-*` | 전부 Running |
| 전반 | 각 서비스 `stderr.log` tail | 치명 예외 0 |

---

## 7c. 요구사항 검증 체크리스트

- [ ] **systemd → NSSM 대체** — Linux 원안의 4 unit 이 Windows Service 로 1:1 매핑
- [ ] **서비스 계정 일원화** — 4 서비스 모두 `.\plane` 로 실행 (최소 권한)
- [ ] **자동 기동** — 재부팅 시 Redis → api → celery/beat/live 순서대로 자동 기동 (의존성)
- [ ] **실패 시 재시작** — `AppExit Default Restart`, 60s throttle
- [ ] **로그 회전** — NSSM `AppRotateBytes=10MB` + `AppRotateSeconds=86400` 적용
- [ ] **uvicorn 단독** — gunicorn 미사용 (Windows 네이티브)
- [ ] **Celery solo pool** — worker 가 `--pool=solo` 인자로 기동
- [ ] **`EnvironmentFile` 대체** — `.env` 를 NSSM `AppEnvironmentExtra` 로 주입
- [ ] **평문 비밀번호 이월** — `plane` 계정 비밀번호 수동 입력, DPAPI 이관 → [../security-todo.md §5](../security-todo.md)

---

## 8. 체크포인트

```powershell
$services = "Redis", "plane-api", "plane-celery", "plane-beat", "plane-live"
Get-Service $services | ForEach-Object {
  "$($_.Name): $($_.Status)"
}

# 각 stderr 에 예외 누적 여부
$services | ForEach-Object {
  $dir = $_ -replace "plane-", ""
  if ($dir -eq "Redis") { return }
  $err = "D:\Workspace\plane-logs\$dir\stderr.log"
  if (Test-Path $err) {
    "`n=== $_ stderr tail ==="
    Get-Content $err -Tail 5
  }
}
```

- [ ] 5개 서비스 모두 `Running` + `Automatic`
- [ ] `stdout.log` 에 기동 로그 정상
- [ ] `stderr.log` 에 치명 예외 없음
- [ ] `delete_api_logs.delay()` 로 celery round-trip 확인
- [ ] beat 가 5분 내 첫 태스크 발송
- [ ] Windows 재부팅 후 자동 기동 확인

---

## 9. 운영 체인 (참조)

```
[Windows 부팅]
   │
   ▼
Redis (Windows Service, Phase 1)
   │
   ▼
plane-api (uvicorn, 127.0.0.1:8000)
   │
   ├─▶ plane-celery (worker, --pool=solo)
   ├─▶ plane-beat (스케줄러)
   └─▶ plane-live (Node, 127.0.0.1:3100)
        [Phase 7 Caddy 가 상위에서 라우팅]
```

---

## 10. 이월 / 후속

- **`<plane-password>` 를 DPAPI 암호화해서 스크립트에서 제거** → [../security-todo.md §5](../security-todo.md)
- **Windows Performance Counter / Event Log 로 health 통합** → Phase 8 모니터링
- **NSSM 로그 자동 압축** — 회전된 로그를 주간 7z 로 묶기 (Task Scheduler, Phase 8)
- **`--workers > 1` 전환 실험** — uvicorn multi-worker 실측 필요 시 별도 기획

---

> **네비게이션**: [← Phase 5](06-frontend-build.md) · [목차](../plan.md) · [다음: Phase 7 →](08-external-access.md)
