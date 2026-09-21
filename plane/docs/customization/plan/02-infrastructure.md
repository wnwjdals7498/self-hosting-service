# Phase 1 — 인프라 네이티브 구성

> **네비게이션**: [← Phase 0](01-prerequisites.md) · [목차](../plan.md) · [다음: Phase 2 →](03-source-prep.md)
>
> 연관: [../sqlite-reference.md §3](../sqlite-reference.md) (SQLite 런타임 불변식) · [../security-todo.md §1](../security-todo.md) (Redis 보안 TODO)

**목표**: Phase 0 에서 준비된 호스트 위에 SQLite 데이터 디렉토리 · Redis 운영 구성(설정 파일 이전 · 서비스 계정 전환 · DB 번호 분리) · 로그 디렉토리를 확정한다. Phase 2 가 `.env` 를 채울 때 바로 참조할 수 있는 값이 이 Phase 에서 모두 결정된다.

**이 Phase 에서 수정하는 파일**:
- 신규: `D:\Workspace\plane-app\ops\redis.conf` (Redis 설정 이전본)
- Windows Service `Redis` 의 `binPath`, 계정, 재시작

**이 Phase 에서 수정한 Plane 코드**:
- `apps/api/plane/settings/production.py` — `LOG_DIR` 를 하드코딩에서 `os.environ.get("LOG_DIR", ...)` env override 로 전환 (§6 참조)

**이 Phase 에서 수정하지 않는 파일**:
- `apps/api/plane/settings/common.py` — Celery broker 전환은 [Phase 3](04-celery-broker.md)

---

## 1. SQLite 데이터 경로 확정

DB 엔진은 Python 3.13 stdlib `sqlite3` (3.45+ 번들) 로 충족 — 별도 설치 없음. 이 Phase 에서는 **파일 경로와 env 값**만 확정한다.

### 1.1 경로

```
D:\Workspace\plane-data\sqlite\
├── plane.sqlite3        메인 DB
├── plane.sqlite3-wal    WAL journal (자동 생성)
└── plane.sqlite3-shm    Shared memory (자동 생성)
```

- `-wal` / `-shm` 은 WAL 모드에서 엔진이 자동 관리. **백업 시 3개 파일 모두** 또는 `VACUUM INTO` / `.backup` 명령으로 일관된 스냅샷 생성해야 함 ([Phase 8](09-verification.md)).
- 디렉토리 ACL 은 Phase 0 §3.2 에서 설정 완료 (`plane:(OI)(CI)M`).

### 1.2 환경변수 (Phase 2 `.env` 에 반영)

```ini
SQLITE_PATH=D:/Workspace/plane-data/sqlite/plane.sqlite3
```

> Windows 경로 이스케이프 주의: `.env` 에서는 **포워드 슬래시** 또는 **이중 백슬래시** 사용. Python `os.path` 가 내부적으로 정규화하므로 슬래시가 가장 안전.

### 1.3 PRAGMA / BEGIN IMMEDIATE

`plane.db.apps.DbConfig.ready()` 가 자동 적용 — 이 Phase 에서 수동 조치 없음. 상세는 [../sqlite-reference.md §3](../sqlite-reference.md).

적용 결과 (모든 연결):
- `journal_mode=WAL`
- `synchronous=NORMAL`
- `busy_timeout=5000`
- `foreign_keys=ON`
- 트랜잭션 `BEGIN IMMEDIATE` 몽키패치

### 1.4 WAL 자동 체크포인트

SQLite 기본 auto-checkpoint (1000 페이지, 약 4MB) 로 충분. 1인 규모에서 별도 튜닝 불필요. `PRAGMA wal_autocheckpoint` 기본값 유지.

---

## 2. Redis 설정 이전 (tporadowski/redis 5.0.14)

MSI 설치 직후 상태(Phase 0 §6 완료):
- 서비스: `Redis`, 계정 `LocalSystem`, 설정 `C:\Program Files\Redis\redis.windows-service.conf`, 데이터 경로 `C:\Program Files\Redis\`

이 Phase 에서 다음 3가지를 한 번에 처리:
- (A) 설정 파일을 `D:\Workspace\plane-app\ops\redis.conf` 로 **이전** (템플릿 신규 작성)
- (B) 데이터 경로를 `D:\Workspace\plane-data\redis\` 로 이전, 로그를 `D:\Workspace\plane-logs\redis\` 로
- (C) 서비스 계정을 `LocalSystem` → `plane` 으로 전환

### 2.1 `ops/` 디렉토리 생성

```powershell
New-Item -ItemType Directory -Path "D:\Workspace\plane-app\ops" -Force | Out-Null
New-Item -ItemType Directory -Path "D:\Workspace\plane-logs\redis" -Force | Out-Null
```

### 2.2 `redis.conf` 템플릿

`D:\Workspace\plane-app\ops\redis.conf` 로 아래 내용을 저장. 원본(`C:\Program Files\Redis\redis.windows-service.conf`) 의 전체 주석을 보존할 필요는 없고 Plane 운영에 필요한 항목만 명시한다.

```conf
############################
# Plane 개인용 Redis 설정
# tporadowski/redis 5.0.14 기준
# - 보안 배경: ../security-todo.md §1
# - DB 분리 설계: 본 문서 §2.4
############################

# 네트워크: 로컬 loopback 만
bind 127.0.0.1
port 6379
protected-mode yes

# 인증
requirepass "REPLACE_WITH_32CHAR_RANDOM"

# 데이터 경로 (Phase 0 준비)
dir D:/Workspace/plane-data/redis

# 로그
logfile "D:/Workspace/plane-logs/redis/redis.log"
loglevel notice

# 메모리
# volatile-lru: TTL 있는 키만 eviction 대상 → cache(/0) 만 eviction, Celery broker(/1) 메시지 안전
# (redis_instance() 사용처는 모두 TTL 설정됨 — settings/redis.py + bgtasks 3곳 확인)
maxmemory 512mb
maxmemory-policy volatile-lru

# 영속성 — AOF 주 + RDB 기본 스냅샷
appendonly yes
appendfsync everysec
no-appendfsync-on-rewrite no
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# RDB 기본 스냅샷 (주기 낮게 유지 — AOF 가 주)
save 3600 1
save 300 100
save 60 10000
stop-writes-on-bgsave-error yes
rdbcompression yes
rdbchecksum yes
dbfilename dump.rdb

# DB 수 (Phase 1 §2.4 — /0 cache, /1 broker, /2 result backend, /3~ 예비)
databases 16

# 슬로우 로그
slowlog-log-slower-than 10000
slowlog-max-len 128

# 복구 불가 명령 봉인 (운영자가 실수로 실행하는 것 방지)
rename-command FLUSHALL ""
rename-command FLUSHDB ""

# 서비스 종료 시 AOF 안전 fsync
# (Windows 에서는 SIGTERM → 서비스 중지 시점에 write 완료 보장)

# 기타 보안: CONFIG/DEBUG/KEYS 봉인은 운영 편의상 1차 배포 미적용.
# 중기 전환 시 security-todo §1 에 따라 rename-command 로 랜덤 문자열 치환.
```

**`requirepass` 값 생성**:

```powershell
$pw = -join ((1..32) | ForEach-Object { [char](Get-Random -InputObject (48..57 + 65..90 + 97..122)) })
$pw    # 이 값을 redis.conf 와 .env (REDIS_URL, CELERY_BROKER_URL) 양쪽에 동일하게 반영
```

> `requirepass` 는 평문 저장이 불가피하다. 파일 ACL 로 `plane` / Administrators 만 읽기 가능하도록 Phase 0 §3.2 에서 이미 처리. 중기적으로 Credential Manager 또는 DPAPI 이관 — [../security-todo.md §5](../security-todo.md).

### 2.3 기존 Redis 데이터 이관 (깨끗한 설치 가정 시 생략)

MSI 설치 직후 실제 운영 데이터가 없다면 생략. 만약 기존 `dump.rdb` 가 있다면:

```powershell
Stop-Service Redis
Move-Item "C:\Program Files\Redis\dump.rdb"          "D:\Workspace\plane-data\redis\dump.rdb" -ErrorAction SilentlyContinue
Move-Item "C:\Program Files\Redis\appendonly.aof"    "D:\Workspace\plane-data\redis\appendonly.aof" -ErrorAction SilentlyContinue
```

### 2.4 Redis DB 번호 분리 설계

| DB | 용도 | 설정 키 | TTL 여부 |
|---|---|---|---|
| `/0` | Django cache (`CACHES["default"]`), 앱 레벨 분산 락(`plane.settings.redis.redis_instance()`) | `REDIS_URL` | 있음(300s default + 앱 락 TTL) |
| `/1` | Celery broker (작업 큐) | `CELERY_BROKER_URL` | **없음** (eviction 금지) |
| `/2` | Celery result backend (Phase 3 활성화 시) | `CELERY_RESULT_BACKEND` | 설정 가능 |
| `/3~/15` | 예비 | — | — |

- `/0` 은 기존 코드(`redis_instance()`)가 `db=0` 하드코딩 — 변경하지 않음 (호환성 유지).
- `/1`, `/2` 는 환경변수로만 분리. Phase 3 에서 실제 Celery 전환 시 사용.
- `volatile-lru` 정책상 TTL 없는 키는 evict 대상 아님 → `/1` broker 메시지는 메모리가 꽉 차도 유실되지 않음 (대신 쓰기 거부).

### 2.5 Redis Windows Service 재구성

**서비스 실행 파일 인자 변경**:

```powershell
# 서비스 중지
Stop-Service Redis

# binPath 변경 (conf 파일 경로 교체)
sc.exe config Redis binPath= '"C:\Program Files\Redis\redis-server.exe" --service-run "D:\Workspace\plane-app\ops\redis.conf"'

# 결과 확인
sc.exe qc Redis
```

**서비스 계정 변경** (`LocalSystem` → `plane`):

```powershell
# plane 계정 비밀번호 입력 (Phase 0 §2.1 에서 설정한 것)
$planePw = Read-Host "plane 계정 비밀번호"

sc.exe config Redis obj= ".\plane" password= "$planePw"

# plane 계정에 "서비스로 로그온" 권한 부여 (Phase 0 §2.1 에서 이미 했으면 생략)
# secpol.msc → 로컬 정책 → 사용자 권한 할당 → "서비스로 로그온" 에 plane 추가
```

**데이터/로그 디렉토리 권한 재확인**:

```powershell
# Phase 0 §3.2 ACL 이 plane 에게 Modify 권한을 부여했으므로 Redis 쓰기 가능.
# plane 계정이 실제 쓸 수 있는지 확인:
Start-Service Redis
Get-Service Redis      # Status: Running
Get-ChildItem "D:\Workspace\plane-data\redis\"
Get-ChildItem "D:\Workspace\plane-logs\redis\"
```

### 2.6 설치 정리

기존 설정·데이터 파일은 원본 위치(`C:\Program Files\Redis\`) 에 방치하지 말고 삭제 또는 백업 이동:

```powershell
Move-Item "C:\Program Files\Redis\redis.windows-service.conf" "C:\Program Files\Redis\redis.windows-service.conf.bak" -Force
```

MSI 업데이트 시 `.bak` 이 덮어쓰기 회피 버퍼 역할.

---

## 3. 로그 디렉토리 구조

### 3.1 디렉토리 레이아웃

```
D:\Workspace\plane-logs\
├── api\        Django API 서비스 (NSSM stdout/stderr, Phase 6)
├── worker\     Celery worker (NSSM stdout/stderr)
├── beat\       Celery beat (NSSM stdout/stderr)
├── live\       Node live 서버 (NSSM stdout/stderr)
└── redis\      Redis (redis.conf logfile → redis.log, 본 Phase)
```

```powershell
"api","worker","beat","live","redis" | ForEach-Object {
  New-Item -ItemType Directory -Path "D:\Workspace\plane-logs\$_" -Force | Out-Null
}
```

권한: Phase 0 §3.2 에서 상위 `plane-logs` 에 `plane:(OI)(CI)M` 부여 → 하위 상속.

### 3.2 애플리케이션 레이어 로그 회전 (Django)

`plane/settings/production.py` 의 `LOGGING` 이미 `SizedTimedRotatingFileHandler` 사용 중:
- 파일: `BASE_DIR/logs/plane-error.log`
- 크기 트리거: `maxBytes = 1 MB`
- 시간 트리거: 매초 체크
- 회전 보관: 최대 5개 (총 ~5 MB)
- 형식: JSON (`python-json-logger`)

**코드 수정 이력**: 원본은 `LOG_DIR = os.path.join(BASE_DIR, "logs")` 하드코딩이었다. 운영 경로(`D:\Workspace\plane-logs\api\`)로 돌리기 위해 본 Phase 에서 `LOG_DIR = os.environ.get("LOG_DIR", os.path.join(BASE_DIR, "logs"))` 로 변경 완료 — §6 참조. 실효는 Phase 2 에서 `.env` 에 `LOG_DIR` 을 주입하는 시점.

**결과 배치 (Phase 2 `.env` 주입 이후)**:
- Django `plane.exception` 로거 → `D:\Workspace\plane-logs\api\plane-error.log` (내장 회전)
- 그 외 `plane.api`, `plane.worker` 등 console 로거 → **NSSM 이 stdout capture** → `D:\Workspace\plane-logs\{api,worker,beat}\stdout.log` (NSSM 자체 회전 설정 — Phase 6)

### 3.3 NSSM 로그 회전 정책 (Phase 6 선제 확정)

NSSM 은 자체 rotation 플래그 제공:
- `AppRotateFiles 1`
- `AppRotateOnline 1`   (서비스 실행 중 회전)
- `AppRotateSeconds 86400`   (1일)
- `AppRotateBytes 10485760`   (10 MB)

→ Phase 6 에서 각 서비스 등록 시 동일 정책 적용.

### 3.4 Redis 로그

`redis.conf` 의 `logfile D:/Workspace/plane-logs/redis/redis.log` 로 저장. Redis 자체는 회전 기능 없음. 주간 스케줄드 태스크로 회전 (Phase 8 백업/유지보수 플레이북에 편입):

```powershell
# 예시 (Phase 8 에서 Task Scheduler 등록)
Compress-Archive -Path "D:\Workspace\plane-logs\redis\redis.log" `
  -DestinationPath "D:\Workspace\plane-data\backup\redis-log-$(Get-Date -Format yyyyMMdd).zip"
Clear-Content "D:\Workspace\plane-logs\redis\redis.log"
```

---

## 4. 이 Phase 에서 확정된 환경변수

아래 값을 Phase 2 `.env` 작성 시 그대로 사용한다. 지금 단계에서는 메모만.

```ini
# SQLite
SQLITE_PATH=D:/Workspace/plane-data/sqlite/plane.sqlite3

# Redis — Django cache + redis_instance()
REDIS_URL=redis://:REPLACE_WITH_32CHAR_RANDOM@127.0.0.1:6379/0

# Celery broker (Phase 3 코드 수정 후 실효)
CELERY_BROKER_URL=redis://:REPLACE_WITH_32CHAR_RANDOM@127.0.0.1:6379/1

# Celery result backend (Phase 3 에서 결정 — django-db vs redis://.../2)
# CELERY_RESULT_BACKEND=redis://:REPLACE_WITH_32CHAR_RANDOM@127.0.0.1:6379/2

# 로그 경로 (production.py 수정 완료 — §6, Phase 2 에서 .env 주입 시 실효)
LOG_DIR=D:/Workspace/plane-logs/api
```

> `REPLACE_WITH_32CHAR_RANDOM` 은 §2.2 에서 생성한 값으로 치환.

---

## 4a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P1-1 | `ops/` 디렉토리 + `plane-logs/redis/` 생성 | P0-8 | §2.1 | 2 디렉토리 |
| P1-2 | `ops/redis.conf` 작성 (bind/requirepass/volatile-lru/AOF/rename-command) | P1-1 | §2.2 | redis.conf |
| P1-3 | `REDIS_PASSWORD` 32자 생성 (site.env 반영은 Phase 2) | — | §2.2 | 비밀값 결정 |
| P1-4 | 기존 `dump.rdb`/`appendonly.aof` 이전 (깨끗한 MSI 설치면 스킵) | P0-13 | §2.3 | D: 데이터 경로 |
| P1-5 | Redis 서비스 `binPath` 을 `ops/redis.conf` 로 교체 (`sc.exe config`) | P0-13, P1-2 | §2.5 | 서비스 인자 갱신 |
| P1-6 | Redis 서비스 계정 `LocalSystem` → `.\plane` 전환 | P0-5, P1-5 | §2.5 | 최소권한 실행 |
| P1-7 | Redis 서비스 재시작 + PING/CONFIG 실측 | P1-5, P1-6 | §2.5 | volatile-lru · AOF on |
| P1-8 | 원본 `redis.windows-service.conf` → `.bak` 백업 | P1-5 | §2.6 | MSI 업데이트 대비 |
| P1-9 | 로그 하위 5개 (`api`, `worker`, `beat`, `live`, `redis`) 생성 | P0-8 | §3.1 | 5 디렉토리 |
| P1-10 | `production.py` `LOG_DIR` env override (**완료**) | — | §6 | 코드 수정 완료 |
| P1-11 | Redis 로그 회전 Task Scheduler 등록 (Phase 8 연계 — 결정만) | — | §3.4 | 정책 문서화 |

---

## 4b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P1-1 | `Test-Path D:\Workspace\plane-app\ops, D:\Workspace\plane-logs\redis` | True ×2 |
| P1-2 | `Select-String redis.conf -Pattern "^bind 127\.0\.0\.1","^requirepass","^maxmemory-policy volatile-lru","^appendonly yes","^rename-command FLUSHALL" \| Measure` | Count=5 |
| P1-3 | `$env:REDIS_PASSWORD.Length -ge 32` (site.env 로딩 후 Phase 2) | True |
| P1-5 | `sc.exe qc Redis \| findstr /I BINARY_PATH` | ops/redis.conf 포함 |
| P1-6 | `sc.exe qc Redis \| findstr /I SERVICE_START_NAME` | `.\plane` |
| P1-7 | `redis-cli -a $pw ping` · `redis-cli -a $pw CONFIG GET maxmemory-policy` | `PONG` · `volatile-lru` |
| P1-7 | `redis-cli -a $pw CONFIG GET appendonly` | `yes` |
| P1-9 | `"api","worker","beat","live","redis" \| % { Test-Path "D:\Workspace\plane-logs\$_" }` | True ×5 |
| P1-10 | `Select-String production.py -Pattern "LOG_DIR = os.environ.get"` | 1건 |

---

## 4c. 요구사항 검증 체크리스트

- [ ] **Redis 설정 이전** — P1-2, P1-5 로 `ops/redis.conf` 가 서비스 설정의 단일 출처
- [ ] **Redis 서비스 계정 최소권한** — P1-6 로 `.\plane` 전환
- [ ] **DB 번호 분리 가능** — Redis `databases 16` 유지 · /0 cache · /1 broker · /2 예비 (실 주입은 Phase 2)
- [ ] **volatile-lru 정책** — P1-7 로 실측. broker 메시지 eviction 방지
- [ ] **로그 디렉토리 사전 준비** — P1-9 로 Phase 6 NSSM 이 쓸 5 하위 준비
- [ ] **production.py LOG_DIR env** — P1-10 완료, Phase 2 에서 `.env` 주입 시 실효
- [ ] **SQLite 경로 정책** — §1.1 로 경로만 확정, 파일 생성은 Phase 2 `migrate`
- [ ] **보안 이월** — `rename-command CONFIG/DEBUG/KEYS` 미적용, `requirepass` 평문 → [../security-todo.md §1, §5](../security-todo.md)

---

## 5. 체크포인트

Phase 2 로 넘어가기 전 모두 통과.

```powershell
# --- SQLite 경로 ---
Test-Path "D:\Workspace\plane-data\sqlite"

# --- Redis 설정 이전 ---
Test-Path "D:\Workspace\plane-app\ops\redis.conf"
Select-String -Path "D:\Workspace\plane-app\ops\redis.conf" -Pattern "^requirepass" -Quiet
Select-String -Path "D:\Workspace\plane-app\ops\redis.conf" -Pattern "^dir D:/Workspace/plane-data/redis" -Quiet

# --- Redis 서비스 상태 ---
Get-Service Redis                    # Running
sc.exe qc Redis | findstr /I "BINARY_PATH SERVICE_START_NAME"
# BINARY_PATH_NAME  에 redis.conf 경로 포함
# SERVICE_START_NAME 이 .\plane

# --- Redis 응답 ---
redis-cli -a "REPLACE_WITH_32CHAR_RANDOM" ping     # PONG
redis-cli -a "REPLACE_WITH_32CHAR_RANDOM" -n 0 dbsize
redis-cli -a "REPLACE_WITH_32CHAR_RANDOM" -n 1 dbsize

# --- Redis 설정 실측 ---
redis-cli -a "REPLACE_WITH_32CHAR_RANDOM" CONFIG GET maxmemory-policy
# "volatile-lru"
redis-cli -a "REPLACE_WITH_32CHAR_RANDOM" CONFIG GET appendonly
# "yes"

# --- 로그 디렉토리 ---
"api","worker","beat","live","redis" | ForEach-Object {
  Test-Path "D:\Workspace\plane-logs\$_"
}

# --- Redis 로그 쓰기 확인 ---
Test-Path "D:\Workspace\plane-logs\redis\redis.log"
```

- [ ] `D:\Workspace\plane-data\sqlite\` 디렉토리 존재 (파일은 Phase 2 `migrate` 이후 생성)
- [ ] `D:\Workspace\plane-app\ops\redis.conf` 배치, requirepass 설정
- [ ] Redis 서비스 `binPath` 가 새 conf 경로 참조
- [ ] Redis 서비스 계정 `.\plane`
- [ ] `redis-cli -a … ping` → PONG
- [ ] `maxmemory-policy` = `volatile-lru`, `appendonly` = `yes`
- [ ] `plane-logs/{api,worker,beat,live,redis}` 5개 폴더 생성
- [ ] `redis.log` 파일 생성되어 writable

---

## 6. 본 Phase 에서 수행한 Plane 코드 수정 (완료)

| 파일 | 변경 | 목적 |
|---|---|---|
| [apps/api/plane/settings/production.py:25](../../../apps/api/plane/settings/production.py) | `LOG_DIR = os.path.join(BASE_DIR, "logs")` → `LOG_DIR = os.environ.get("LOG_DIR", os.path.join(BASE_DIR, "logs"))` | 운영 로그 경로를 `D:\Workspace\plane-logs\api\` 로 env 주입 가능하도록 전환 |

**회귀 검증** — 환경변수 미설정 시 기존 경로(`BASE_DIR/logs`)로 폴백되므로 개발/테스트 동작은 변경 없음. 실효는 Phase 2 에서 `.env` 에 `LOG_DIR=D:/Workspace/plane-logs/api` 를 주입하고 `python manage.py check` 로 확인.

---

## 7. 남긴 TODO → 후속 기획

- Redis `rename-command` 로 `CONFIG`/`DEBUG`/`KEYS` 봉인 → [../security-todo.md §1](../security-todo.md)
- Redis `requirepass` 를 Credential Manager / DPAPI 로 이관 → [../security-todo.md §5](../security-todo.md)
- 중기적으로 Memurai Developer 전환 → [../security-todo.md §1](../security-todo.md)
- Redis 로그 회전 자동화 → Phase 8 백업/유지보수 Task Scheduler 등록

---

> **네비게이션**: [← Phase 0](01-prerequisites.md) · [목차](../plan.md) · [다음: Phase 2 →](03-source-prep.md)
