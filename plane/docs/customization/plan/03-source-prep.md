# Phase 2 — Plane 소스 준비 + 환경변수 단일 소스 구성

> **네비게이션**: [← Phase 1](02-infrastructure.md) · [목차](../plan.md) · [다음: Phase 3 →](04-celery-broker.md)
>
> 연관: [.claude/project-layout.md](../../../.claude/project-layout.md) · [../security-todo.md](../security-todo.md)

**목표**:
1. 운영 트리(`D:\Workspace\plane-app`) 에 저장소를 별도 clone 하고 Python venv · 프론트 의존성을 갖춘다.
2. 외부 호스트/비밀값을 **단일 파일 `ops/site.env`** 에 모으고, 각 앱의 `.env` 를 렌더 스크립트로 자동 생성하는 체계를 구축한다.
3. DB 초기화(migrate → superuser → instance 설정) 까지 완료하여 Phase 3 의 Celery broker 전환 직전 상태를 만든다.

**이 Phase 에서 생성/수정하는 파일**:
- 신규: `D:\Workspace\plane-app\ops\site.env` (단일 설정 소스)
- 신규: `D:\Workspace\plane-app\ops\render-envs.ps1` (렌더 스크립트)
- 신규: `D:\Workspace\plane-app\apps\api\.env` (스크립트 출력)
- 신규: `D:\Workspace\plane-app\apps\api\.venv\` (Python 가상환경)
- 신규: `D:\Workspace\plane-app\node_modules\` 등 (pnpm 설치)
- 신규: `D:\Workspace\plane-data\sqlite\plane.sqlite3` (`migrate` 결과)

**Plane 코드 변경 없음** — Phase 1 의 `production.py` 수정이 마지막.

---

## 1. 운영 저장소 초기화 (개발 ↔ 운영 분리)

개발 트리는 `D:\Workspace\plane`, 운영 트리는 `D:\Workspace\plane-app`.

**제약 — `plane-app/` 에 이미 운영 산출물 존재**: Phase 0~1 에서 `plane-app\ops\` (redis.conf, site.env 예정) · `plane-app\tools\` (nssm, ipban) 가 선행 생성됐다. `git clone` 은 대상 디렉토리가 비어있지 않으면 실패하므로 **clone 패턴을 쓸 수 없다**.

### 1.1 선택지 비교

| # | 방식 | 장점 | 단점 |
|---|---|---|---|
| (a) | 기존 `plane-app` 을 다른 이름으로 옮긴 뒤 `git clone` → ops/tools 를 새 위치로 이동 → rename | 가장 직관 | 파일 이동 실패 리스크 · 일시적으로 경로 흔들림 |
| (b) | 소스를 `plane-app\src\` 하위로 clone, ops/tools 는 바깥 유지 | 구조 깔끔 | Phase 5/6/7/8 의 모든 경로 상수 재작성 필요 (`apps/` → `src/apps/`) — 영향 범위 큼 |
| **(c)** | `plane-app/` 에 `git init + remote add + fetch + checkout -f` → ops/tools 는 untracked 로 공존, `.git/info/exclude` 로 git status 에서 숨김 | **기존 plan 경로 그대로 유지** · 파일 이동 없음 | 개념적으로 "clone" 이 아니라서 초보자엔 약간 낯섦 |

**선택: (c)** — 영향 최소. 1인 운영에서 익숙함보다 경로 안정성이 훨씬 중요.

### 1.2 실행

```powershell
cd D:\Workspace\plane-app

# (1) 빈 git 저장소로 초기화
git init
git remote add origin D:\Workspace\plane

# (2) 개발 트리의 master 브랜치 fetch
git fetch origin

# (3) 강제 checkout — untracked 디렉토리(ops/, tools/) 는 보존
git checkout -f master
# 주의: -f 는 tracked 파일만 강제 덮어씀. untracked 는 건드리지 않음.

# (4) 운영 산출물을 git 관점에서 영구 ignore
#   .gitignore 는 upstream 이 관리 — 수정 금지. 대신 .git/info/exclude 사용.
Add-Content .git\info\exclude "`n# Plane 운영 산출물 (Phase 0~)"
Add-Content .git\info\exclude "/ops/"
Add-Content .git\info\exclude "/tools/"

# (5) 검증
git remote -v                 # origin  D:\Workspace\plane
git branch --show-current     # master
git status                    # clean (ops/, tools/ 는 exclude 로 무시)
```

### 1.3 향후 업데이트 플로우

운영 트리에서 직접 커밋하지 않는다. 모든 변경은 개발 트리(`D:\Workspace\plane`) 에서 수행 → 커밋 → 운영 트리에서 `fetch`.

```powershell
cd D:\Workspace\plane-app
git fetch origin
git reset --hard origin/master    # tracked 만 덮어씀. ops/, tools/ 는 유지
```

`git reset --hard` 가 untracked 를 삭제하려면 `git clean -fdx` 가 추가 필요한데, 본 설계에서는 **절대 실행 금지** — ops/tools 삭제 재앙. Phase 8 업데이트 플레이북에도 `clean` 명령 포함 금지.

---

## 2. Python venv + 의존성 설치

### 2.1 venv 생성 & 활성

```powershell
cd D:\Workspace\plane-app\apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version         # Python 3.13.13 (Phase 0 에서 확인)
pip install --upgrade pip setuptools wheel
```

### 2.2 의존성 설치 (Python 3.13 호환 실측)

`local.txt` 는 `-r base.txt` 로 런타임을, `test.txt` 는 `-r base.txt` 로 런타임 + pytest 스위트를 가져온다. 운영 실행만 필요하면 `local.txt` 만으로 충분하지만, Phase 4.1 이후의 유닛 테스트를 돌리려면 **`test.txt` 도 병행** 설치해야 한다.

```powershell
pip install -r requirements\local.txt -r requirements\test.txt
```

**실측 체크포인트**:
- `pymongo 4.6.3` · `channels 4.1.0` 은 공식 지원이 Python 3.12 까지. 3.13 에서 wheel 이 있으면 바로 설치 성공, 없으면 소스 빌드 시도. 설치 실패 메시지를 전부 캡처하여 아래 분기로 진행.

**분기 A — 전부 설치 성공**:
```powershell
pip check
python -c "import django, channels, pymongo, lxml, cryptography, nh3; print('ok')"
```
Phase 2 계속 진행.

**분기 B — 특정 패키지 실패**:
- 실패 패키지만 상위 버전 시도 (`pip install pymongo --upgrade`) — `requirements/base.txt` 과 lock 불일치 주의
- 그래도 실패하면 **Python 3.12 MSI 병행 설치** 후 venv 를 3.12 로 재생성:
  ```powershell
  deactivate
  Remove-Item -Recurse -Force .\.venv
  py -3.12 -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install --upgrade pip setuptools wheel
  pip install -r requirements\local.txt
  ```
- 3.12 로 재생성한 경우 [.claude/project-layout.md §5](../../../.claude/project-layout.md) 에 "Python 3.12 사용 — 3.13 호환 이슈 패키지 X,Y" 이력 추가.

### 2.3 Django check

```powershell
$env:DJANGO_SETTINGS_MODULE = "plane.settings.production"
$env:SECRET_KEY = "temporary-placeholder-will-be-replaced-by-site-env"
$env:SQLITE_PATH = "D:/Workspace/plane-data/sqlite/plane.sqlite3"
$env:REDIS_URL = "redis://:placeholder@127.0.0.1:6379/0"
python manage.py check
# System check identified no issues (... silenced).
```

> 이 단계의 env 는 smoke 전용. 실제 `.env` 는 §4 에서 생성.

---

## 3. 프론트엔드 의존성 설치 (빌드는 Phase 5)

```powershell
cd D:\Workspace\plane-app
corepack enable
corepack prepare pnpm@10.32.1 --activate   # Phase 0 에서 이미 했지만 shim 위치가 user profile 이므로 재활성 안전
pnpm install
```

`node_modules/` 생성 + `turbo.json` 인식 확인.

```powershell
pnpm turbo ls 2>$null
# 없으면 pnpm turbo run --dry 로 대체
```

---

## 4. 단일 설정 소스 `ops/site.env`

외부 접속 주소·비밀값을 이 파일 **한 곳** 에 모은다. 도메인 전환 시 본 파일만 수정 후 §5 렌더 재실행.

### 4.1 파일 생성

`D:\Workspace\plane-app\ops\site.env` — (디렉토리는 Phase 1 §2.1 에서 생성됨)

```ini
# Plane 배포 중앙 설정 — 외부 주소 / 비밀값 / 운영 토글
# 수정 후 .\render-envs.ps1 재실행 → apps/*/.env 재생성 → 서비스 재시작

# ─── 외부 접근 (공인 IP 또는 도메인) ───
PUBLIC_HOST=222.234.220.199
PUBLIC_SCHEME=http
PUBLIC_PORT=

# 예: 도메인 + HTTPS 전환 시
#   PUBLIC_HOST=plane.example.com
#   PUBLIC_SCHEME=https
#   PUBLIC_PORT=

# ─── 비밀값 ───
# Django 세션/서명 키 — 최초 1회 생성 후 교체 지양
#   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY=REPLACE_WITH_DJANGO_SECRET_KEY

# Redis requirepass — Phase 1 §2.2 에서 생성한 값과 동일
REDIS_PASSWORD=REPLACE_WITH_REDIS_PASSWORD

# Live 서버 비밀 — Node live 가 API 요청 검증에 사용 (32자 랜덤 권장)
LIVE_SERVER_SECRET_KEY=REPLACE_WITH_LIVE_SECRET

# ─── 기능 토글 (1인 기본값, 필요 시 변경) ───
ENABLE_SIGNUP=0
ENABLE_EMAIL_PASSWORD=1
ENABLE_MAGIC_LINK_LOGIN=0
DISABLE_WORKSPACE_CREATION=0
```

### 4.2 비밀값 생성 헬퍼

```powershell
# Django SECRET_KEY
.\apps\api\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 32자 랜덤 (REDIS_PASSWORD / LIVE_SERVER_SECRET_KEY)
-join ((1..32) | ForEach-Object { [char](Get-Random -InputObject (48..57 + 65..90 + 97..122)) })
```

**site.env 의 ACL**: Phase 0 §3.2 의 ACL 이 `plane-app` 전체에 적용되므로 상속됨. 비밀값 저장 파일이라 추가 확인:

```powershell
icacls D:\Workspace\plane-app\ops\site.env
# plane:(M), Administrators:(F), SYSTEM:(F) 만 있어야 함
```

---

## 5. 렌더 스크립트 `ops/render-envs.ps1`

`site.env` 를 읽어 `apps/api/.env` 를 생성한다. Phase 5 에서 web/admin/space/live 섹션을 추가할 예정이며, 본 Phase 에서는 API 전용 렌더만 포함한다.

### 5.1 파일 생성

`D:\Workspace\plane-app\ops\render-envs.ps1`

```powershell
# Plane envs renderer — site.env 를 소스로 apps/*/.env 를 생성한다.
# 수정: site.env 를 편집 후 이 스크립트를 재실행.

[CmdletBinding()]
param(
  [string]$SiteEnv = "$PSScriptRoot\site.env",
  [string]$AppRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SiteEnv)) { throw "site.env not found: $SiteEnv" }

# ─── site.env 파싱 ───
$vars = @{}
Get-Content $SiteEnv | ForEach-Object {
  $line = $_.Trim()
  if ($line -eq "" -or $line.StartsWith("#")) { return }
  $parts = $line -split "=", 2
  if ($parts.Count -ne 2) { return }
  $key = $parts[0].Trim()
  $val = $parts[1].Trim().Trim('"').Trim("'")
  $vars[$key] = $val
}

# 필수 키 검증
"PUBLIC_HOST","PUBLIC_SCHEME","SECRET_KEY","REDIS_PASSWORD","LIVE_SERVER_SECRET_KEY" | ForEach-Object {
  if (-not $vars.ContainsKey($_) -or -not $vars[$_] -or $vars[$_].StartsWith("REPLACE_")) {
    throw "site.env: $_ is missing or still a REPLACE_* placeholder"
  }
}

$pubHost   = $vars.PUBLIC_HOST
$pubScheme = $vars.PUBLIC_SCHEME
$pubPort   = $vars.PUBLIC_PORT
$portSfx   = if ([string]::IsNullOrWhiteSpace($pubPort)) { "" } else { ":$pubPort" }
$base      = "${pubScheme}://${pubHost}${portSfx}"

# ─── apps/api/.env ───
$apiEnv = @"
# AUTO-GENERATED by ops/render-envs.ps1  — do not edit directly.
# Source of truth: ops/site.env   ( host = $pubHost, scheme = $pubScheme )

# Django core
DEBUG=0
SECRET_KEY=$($vars.SECRET_KEY)
ALLOWED_HOSTS=$pubHost,localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=$base
CSRF_TRUSTED_ORIGINS=$base

# Database (SQLite)
SQLITE_PATH=D:/Workspace/plane-data/sqlite/plane.sqlite3

# Redis (Phase 1: /0 cache, /1 celery broker, /2 예비)
REDIS_URL=redis://:$($vars.REDIS_PASSWORD)@127.0.0.1:6379/0
CELERY_BROKER_URL=redis://:$($vars.REDIS_PASSWORD)@127.0.0.1:6379/1

# Base URLs (single-domain routing, Phase 7 Cloudflare Tunnel 이 prefix 라우팅)
WEB_URL=$base
APP_BASE_URL=$base
APP_BASE_PATH=/
ADMIN_BASE_URL=$base
ADMIN_BASE_PATH=/god-mode/
SPACE_BASE_URL=$base
SPACE_BASE_PATH=/spaces/
LIVE_BASE_URL=$base
LIVE_BASE_PATH=/live/

# Logging (production.py 가 env 참조 — Phase 1 §6 코드 수정 완료)
LOG_DIR=D:/Workspace/plane-logs/api

# Auth flags (1인 운영)
ENABLE_SIGNUP=$($vars.ENABLE_SIGNUP)
ENABLE_EMAIL_PASSWORD=$($vars.ENABLE_EMAIL_PASSWORD)
ENABLE_MAGIC_LINK_LOGIN=$($vars.ENABLE_MAGIC_LINK_LOGIN)
DISABLE_WORKSPACE_CREATION=$($vars.DISABLE_WORKSPACE_CREATION)

# Email (SMTP 없음 — 메일은 콘솔 로그로만 출력, security-todo §5 참조)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# Storage (Phase 4 에서 로컬 FS 로 전환 예정, 현 단계는 S3 placeholder)
USE_MINIO=0
AWS_S3_BUCKET_NAME=uploads
AWS_ACCESS_KEY_ID=placeholder
AWS_SECRET_ACCESS_KEY=placeholder
AWS_REGION=
AWS_S3_ENDPOINT_URL=
SIGNED_URL_EXPIRATION=3600
FILE_SIZE_LIMIT=5242880

# Session / CSRF
SESSION_COOKIE_AGE=604800
SESSION_COOKIE_NAME=session-id
ADMIN_SESSION_COOKIE_AGE=3600

# Rate limit
API_KEY_RATE_LIMIT=60/minute

# Hard delete
HARD_DELETE_AFTER_DAYS=60

# Live shared secret
LIVE_SERVER_SECRET_KEY=$($vars.LIVE_SERVER_SECRET_KEY)
"@

$apiEnvPath = Join-Path $AppRoot "apps\api\.env"
$apiEnv | Set-Content -Path $apiEnvPath -Encoding UTF8 -NoNewline
Write-Host "Rendered: $apiEnvPath"

# Phase 5 에서 아래 주석을 해제하고 web/admin/space/live 섹션 추가.
# $webEnv = @"
# VITE_API_BASE_URL=$base
# ...
# "@
# $webEnv | Set-Content -Path (Join-Path $AppRoot "apps\web\.env") -Encoding UTF8 -NoNewline
```

### 5.2 실행

```powershell
cd D:\Workspace\plane-app\ops
.\render-envs.ps1
```

성공 출력:
```
Rendered: D:\Workspace\plane-app\apps\api\.env
```

`site.env` 의 `REPLACE_*` placeholder 가 남아 있으면 스크립트가 실패하며 어느 키가 미치환인지 지목한다.

---

## 6. 데이터 초기화

### 6.1 venv 활성 + `.env` 로딩

Django `manage.py` 는 `.env` 를 자동 로드하지 않는다. PowerShell 세션에 주입:

```powershell
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\Activate.ps1

# .env 를 현재 세션 env 로 로드
Get-Content .\.env | Where-Object { $_ -and -not $_.StartsWith("#") } | ForEach-Object {
  $k,$v = $_ -split "=", 2
  if ($k -and $v) { Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim() }
}
```

### 6.2 migrate

```powershell
python manage.py migrate
# Operations to perform:
#   Apply all migrations: ...
# Running migrations:
#   Applying db.0001_initial... OK
#   (이후 contrib.auth, sessions, celery_beat 등)
```

결과 확인:
```powershell
Test-Path D:\Workspace\plane-data\sqlite\plane.sqlite3
# True
```

### 6.3 superuser 생성 (인터랙티브)

```powershell
python manage.py createsuperuser
# Email: admin@plane.local   (가상 도메인, 실제 발송 없음 — EMAIL_BACKEND=console)
# Password: ********
# Password (again): ********
```

### 6.4 `configure_instance` — InstanceConfiguration 시드

admin UI(`/god-mode`) 가 참조하는 기능 플래그 DB 레코드를 생성.

```powershell
python manage.py configure_instance
# SECRET_KEY env variable is required. ← §6.1 이 제대로 된 경우 통과
# <각 key> loaded with value from environment variable.
```

재실행 시 기존 레코드는 건드리지 않음(get_or_create).

### 6.5 `register_instance` — Instance 레코드 등록

```powershell
python manage.py register_instance plane-windows-server-2025
# Instance registered
# (실패 무시 가능: "instance_traces.delay()" 가 Celery 에 enqueue 시도 — worker 미기동 상태라 결과 저장 없음)
```

`machine_signature` 는 임의 문자열. 1인 운영에서 구분자 역할만.

### 6.6 `collectstatic`

`whitenoise.CompressedManifestStaticFilesStorage` 가 manifest 를 요구 — 프로덕션 기동 전 필수.

```powershell
python manage.py collectstatic --noinput
# 수백 개 파일 수집. static-assets/collected-static/ 생성.
```

---

## 7. Smoke test — 개발 서버 기동

Phase 6 의 NSSM 등록 전에 개발 서버로 기본 동작 확인.

```powershell
python manage.py runserver 127.0.0.1:8000
```

다른 PowerShell 창에서:

```powershell
# 헬스체크 (적절한 공개 라우트)
curl.exe -sI http://127.0.0.1:8000/api/users/me/
# 401/403 정상 (인증 필요). 500 이면 로그 확인.

# 관리자 UI
curl.exe -sI http://127.0.0.1:8000/god-mode/
```

Ctrl+C 로 중지. `D:\Workspace\plane-logs\api\` 하위에 `plane-error.log` 가 생성되는지 확인.

---

## 7a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P2-1 | `plane-app/` 에 `git init + fetch + checkout -f` 로 소스 초기화 (`ops/`, `tools/` 보존) + `.git/info/exclude` | P0-14 | §1 | git 저장소 + exclude 설정 |
| P2-2 | Python venv 생성 + 활성 | P0-10, P2-1 | §2.1 | `.venv/` |
| P2-3 | `pip install -r requirements/local.txt` | P2-2 | §2.2 | deps 설치 |
| P2-4 | Python 3.13 호환 실측 (`import django, channels, pymongo, lxml, cryptography, nh3`) | P2-3 | §2.2 | ok / 폴백 3.12 |
| P2-5 | Django check (임시 env) | P2-3 | §2.3 | `System check identified no issues` |
| P2-6 | `pnpm install` (모노레포) | P0-12, P2-1 | §3 | `node_modules/` |
| P2-7 | `ops/site.env` 작성 (PUBLIC_HOST=222.234.220.199 등) | P1-1 | §4.1 | site.env |
| P2-8 | 비밀값 3종 생성: `SECRET_KEY`, `REDIS_PASSWORD`(P1-3 동일), `LIVE_SERVER_SECRET_KEY` | P2-7 | §4.2 | site.env 치환 완료 |
| P2-9 | `ops/render-envs.ps1` 작성 + `$host` 충돌 회피 (`$pubHost`) | P2-7 | §5.1 | render 스크립트 |
| P2-10 | render-envs 실행 → `apps/api/.env` 생성 | P2-7, P2-9 | §5.2 | api .env |
| P2-11 | site.env ACL 확인 (plane:M, Admins:F) | P0-9, P2-7 | §4.2 | icacls 출력 |
| P2-12 | `.env` PowerShell 세션 로딩 헬퍼 | P2-10 | §6.1 | 로딩 스크립트 |
| P2-13 | `python manage.py migrate` | P2-3, P2-10, P1-1 | §6.2 | plane.sqlite3 생성 |
| P2-14 | `python manage.py createsuperuser` | P2-13 | §6.3 | superuser DB 레코드 |
| P2-15 | `python manage.py configure_instance` | P2-13 | §6.4 | InstanceConfiguration 시드 |
| P2-16 | `python manage.py register_instance plane-windows-server-2025` | P2-13 | §6.5 | Instance 레코드 |
| P2-17 | `python manage.py collectstatic --noinput` | P2-13 | §6.6 | `static-assets/collected-static/` |
| P2-18 | `runserver 127.0.0.1:8000` smoke | P2-10, P2-17 | §7 | 200/401 응답 + `plane-error.log` 생성 |

---

## 7b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P2-1 | `git -C D:\Workspace\plane-app remote -v` · `Select-String .git\info\exclude -Pattern '^/ops/','^/tools/'` · `git status` | `origin …\plane` · 2 건 · `nothing to commit` (ops/tools 미표시) |
| P2-3 | `pip check` | `No broken requirements` |
| P2-4 | `python -c "import django, channels, pymongo, lxml, cryptography, nh3; print('ok')"` | `ok` |
| P2-5 | `python manage.py check` | no issues |
| P2-6 | `Test-Path D:\Workspace\plane-app\node_modules` | True |
| P2-7 | `Test-Path D:\Workspace\plane-app\ops\site.env` | True |
| P2-8 | `Select-String ops\site.env -Pattern "^REPLACE_" -Quiet` | False (치환 완료) |
| P2-10 | `Test-Path D:\Workspace\plane-app\apps\api\.env` | True |
| P2-13 | `Test-Path D:\Workspace\plane-data\sqlite\plane.sqlite3` | True |
| P2-14 | `python manage.py shell -c "from plane.db.models import User; print(User.objects.filter(is_superuser=True).count())"` | ≥ 1 |
| P2-15 | `python manage.py shell -c "from plane.license.models import InstanceConfiguration; print(InstanceConfiguration.objects.count())"` | ≥ 10 |
| P2-16 | `python manage.py shell -c "from plane.license.models import Instance; print(Instance.objects.count())"` | 1 |
| P2-17 | `Test-Path apps\api\plane\static-assets\collected-static\staticfiles.json` | True |
| P2-18 | `Invoke-WebRequest http://127.0.0.1:8000/api/users/me/ -UseBasicParsing -SkipHttpErrorCheck \| % StatusCode` | 401 or 403 |

---

## 7c. 요구사항 검증 체크리스트

- [ ] **개발/운영 분리** — P2-1 로 plane-app 독립 트리, origin=개발 트리
- [ ] **의존성 락** — P2-3 + `pip check` 로 buildable 상태
- [ ] **Python 3.13 호환 실측** — P2-4 로 검증, 실패 시 3.12 폴백 경로 문서화
- [ ] **단일 설정 소스(Q1)** — P2-7, P2-9 로 site.env + render-envs 구조 가동. 도메인 변경 시 site.env 1 파일 수정으로 모든 .env 재생성
- [ ] **비밀값 평문 보관 범위 최소화** — P2-11 로 site.env ACL plane 전용. 중기 DPAPI 이관 → [../security-todo.md §5](../security-todo.md)
- [ ] **Plane 초기화 3종** — P2-13~P2-16 완료로 migrate/Instance/InstanceConfiguration/superuser 일괄 준비
- [ ] **whitenoise manifest** — P2-17 로 CompressedManifestStaticFilesStorage 전제 충족
- [ ] **Phase 3 준비** — P2-10 의 `.env` 에 `CELERY_BROKER_URL=redis://.../1` 기록 (실효는 Phase 3 코드 수정)

---

## 8. 체크포인트

Phase 3 로 넘어가기 전 전부 통과.

```powershell
# 운영 트리
Test-Path D:\Workspace\plane-app\.git
git -C D:\Workspace\plane-app remote -v    # origin = D:\Workspace\plane

# Python / pnpm
Test-Path D:\Workspace\plane-app\apps\api\.venv\Scripts\python.exe
Test-Path D:\Workspace\plane-app\node_modules

# site.env 와 렌더 결과
Test-Path D:\Workspace\plane-app\ops\site.env
Test-Path D:\Workspace\plane-app\ops\render-envs.ps1
Test-Path D:\Workspace\plane-app\apps\api\.env
Select-String -Path D:\Workspace\plane-app\ops\site.env -Pattern "^REPLACE_" -Quiet
# False  (REPLACE_* placeholder 가 남아있지 않아야 함)

# DB / 초기화
Test-Path D:\Workspace\plane-data\sqlite\plane.sqlite3
Test-Path D:\Workspace\plane-app\apps\api\plane\static-assets\collected-static

# Django check
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\python.exe manage.py check
```

- [ ] 운영 트리 clone 완료, origin = 개발 트리
- [ ] venv 생성, `pip install -r requirements/local.txt` 성공 (Python 3.13 또는 폴백 3.12)
- [ ] pnpm install 성공
- [ ] `ops/site.env` 의 모든 `REPLACE_*` 치환 완료
- [ ] `ops/render-envs.ps1` 실행 → `apps/api/.env` 생성
- [ ] `migrate` 성공, `plane.sqlite3` 생성
- [ ] `createsuperuser` 완료
- [ ] `configure_instance` 성공
- [ ] `register_instance` 성공
- [ ] `collectstatic` 성공
- [ ] `runserver` 로 기본 응답 확인

---

## 9. 이 Phase 에서 이월된 결정

- **프론트 `.env` 생성** — Phase 5 에서 `render-envs.ps1` 에 web/admin/space/live 섹션 추가.
- **Storage `.env` 값** — 현재 placeholder. Phase 4 에서 `USE_LOCAL_STORAGE=1` 분기 + MEDIA 관련 키 추가.
- **Celery broker 실효** — `CELERY_BROKER_URL` 은 `.env` 에 기록됐으나 `common.py` 는 아직 `AMQP_URL` / `RABBITMQ_*` 우선 읽기 → Phase 3 코드 수정 후 `CELERY_BROKER_URL` 이 실효.
- **SMTP** — EMAIL_BACKEND=console. 실제 메일 발송 필요 시 security-todo §5 + Phase 이후.

---

## 10. 남긴 TODO → 후속 기획

- `.env` 파일 권한 추가 강화 — Credential Manager / DPAPI 이관 ([../security-todo.md §5](../security-todo.md))
- `site.env` 자체가 평문 비밀을 품는 구조 — 1인 규모에서 허용. 중기 전환 시 DPAPI 암호화된 `site.env.enc` + render 시 복호화
- Python 3.13 유지 시 `pymongo`/`channels` 공식 지원 전환 모니터링

---

> **네비게이션**: [← Phase 1](02-infrastructure.md) · [목차](../plan.md) · [다음: Phase 3 →](04-celery-broker.md)
