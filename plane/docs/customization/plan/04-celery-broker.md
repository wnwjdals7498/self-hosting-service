# Phase 3 — Celery broker 전환 (RabbitMQ → Redis)

> **네비게이션**: [← Phase 2](03-source-prep.md) · [목차](../plan.md) · [다음: Phase 4 →](05-storage.md)
>
> 연관: [../../../apps/api/plane/settings/common.py:243-258](../../../apps/api/plane/settings/common.py) · [../../../apps/api/plane/celery.py](../../../apps/api/plane/celery.py) · [../security-todo.md §1](../security-todo.md)

**목표**:
1. `CELERY_BROKER_URL` env 가 `AMQP_URL`/`RABBITMQ_*` 보다 **우선** 적용되도록 common.py 를 수정하고, Celery 5.0+ 의 `broker_connection_retry_on_startup` 경고를 해소.
2. Redis `db=1` 을 broker 로 지정하고 `solo` pool 로 worker 를 기동해 bgtasks 가 정상 처리됨을 실측.
3. Result backend 는 **설정하지 않음** (현재 `None` 유지) — bgtasks 대부분 fire-and-forget, 결과 저장 불필요.

**결정된 운영 전제**:
- Worker pool: **`--pool=solo`** (단일 프로세스·단일 스레드, Windows 네이티브 안전, 1인 규모 충분)
- Result backend: **None** (미설정). 특정 태스크가 결과 필요 시 개별 `@task(ignore_result=False)` 로 opt-in.
- Broker DB: Redis `/1` (Phase 1 §2.4 분리 설계)

**이 Phase 에서 수정한 Plane 코드**:
- [apps/api/plane/settings/common.py](../../../apps/api/plane/settings/common.py) — `CELERY_BROKER_URL` 우선순위 재정렬 + `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP` 추가 (§1)

---

## 1. common.py Celery 블록 수정 내역

### 1.1 수정 전 (upstream 원본)

```python
# Celery Configuration
if AMQP_URL:
    CELERY_BROKER_URL = AMQP_URL
else:
    CELERY_BROKER_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VHOST}"

CELERY_TIMEZONE = TIME_ZONE
...
```

**문제**:
- `CELERY_BROKER_URL` env 를 직접 읽지 않음 → Redis URL 을 주입할 진입점 없음.
- Celery 5.0+ 에서 `broker_connection_retry_on_startup` 기본값 경고.

### 1.2 수정 후 (본 Phase 커밋)

```python
# Celery Configuration
# Broker priority: CELERY_BROKER_URL env → AMQP_URL → RABBITMQ_* fallback.
# Redis broker uses the env override; legacy RabbitMQ path preserved for
# upstream parity.
_celery_broker_url = os.environ.get("CELERY_BROKER_URL")
if _celery_broker_url:
    CELERY_BROKER_URL = _celery_broker_url
elif AMQP_URL:
    CELERY_BROKER_URL = AMQP_URL
else:
    CELERY_BROKER_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VHOST}"

# Celery 5.0+ requires explicit opt-in to retry broker connection at startup.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_TIMEZONE = TIME_ZONE
...
```

**회귀 안전성**:
- `CELERY_BROKER_URL` 미설정 + `AMQP_URL` 설정 → 원본 경로 그대로 동작.
- `CELERY_BROKER_URL` 미설정 + 둘 다 없음 → `amqp://guest:guest@localhost:5672//` fallback (테스트 환경의 기본과 동일).

---

## 2. Redis broker 활성 (Phase 2 `.env` 에서 이미 주입됨)

Phase 2 `ops/render-envs.ps1` 이 생성한 `apps/api/.env` 에 이미 포함:

```ini
REDIS_URL=redis://:<PASS>@127.0.0.1:6379/0
CELERY_BROKER_URL=redis://:<PASS>@127.0.0.1:6379/1
```

코드 변경으로 이 값이 **실효** 됨. RabbitMQ 관련 env(`RABBITMQ_*`, `AMQP_URL`) 는 `.env` 에 기록되지 않았으므로 fallback 경로 호출 없음.

### 2.1 확인

```powershell
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\Activate.ps1

# .env 로딩 (Phase 2 §6.1 스크립트 재사용)
Get-Content .\.env | Where-Object { $_ -and -not $_.StartsWith("#") } | ForEach-Object {
  $k,$v = $_ -split "=", 2
  if ($k -and $v) { Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim() }
}

# 설정 값 확인
python -c "from django.conf import settings; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','plane.settings.production'); import django; django.setup(); print(settings.CELERY_BROKER_URL)"
# → redis://:***@127.0.0.1:6379/1
```

---

## 3. 잔여 RABBITMQ / pika / kombu 참조 확인

Plane 코드는 Celery 추상층 위에서만 broker 를 호출 → RabbitMQ 고유 API 직접 호출 없음.

```powershell
# apps/api 전수 확인
Select-String -Path D:\Workspace\plane-app\apps\api\plane -Pattern "^import pika|^from pika|^import kombu|^from kombu" -Recurse
# 결과 없음(기대)

Select-String -Path D:\Workspace\plane-app\apps\api\plane -Pattern "RABBITMQ_" -Recurse
# settings/common.py 의 fallback 경로 5줄만 (fallback 이라 안전)
```

`.env.example` 에 남아있는 `RABBITMQ_*` 는 참고용이며 실제 `.env` 는 `render-envs.ps1` 산출물을 사용하므로 영향 없음.

---

## 4. Celery worker 수동 smoke test

서비스 등록(Phase 6)에 앞서 솔로 풀로 기동해 본다.

### 4.1 worker 기동

```powershell
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\Activate.ps1

# .env 로딩 (§2.1 스크립트)
Get-Content .\.env | Where-Object { $_ -and -not $_.StartsWith("#") } | ForEach-Object {
  $k,$v = $_ -split "=", 2
  if ($k -and $v) { Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim() }
}

celery -A plane worker --pool=solo -l info
```

기동 로그에서 확인할 항목:
```
-------------- celery@<hostname> v5.4.0
... [config]
.> transport:   redis://127.0.0.1:6379/1
.> results:     disabled
...
[tasks]
  . plane.bgtasks.email_notification_task.stack_email_notification
  . plane.bgtasks.cleanup_task.hard_delete
  . ...
celery@<hostname> ready.
```

- `transport` 가 `redis://.../1` 이면 §1 수정 성공.
- `results: disabled` 가 Q2(A) 의도와 일치.
- 경고 메시지 `The broker_connection_retry configuration setting will no longer determine ...` 가 **사라져야** 한다.

### 4.2 태스크 enqueue

별도 PowerShell 창에서:

```powershell
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\Activate.ps1
# .env 로딩 (§2.1)

python manage.py shell
>>> from plane.bgtasks.cleanup_task import delete_api_logs
>>> delete_api_logs.delay()
<AsyncResult: ...>
>>> exit()
```

worker 창에서:
```
[INFO] Task plane.bgtasks.cleanup_task.delete_api_logs[…] received
[INFO] Task plane.bgtasks.cleanup_task.delete_api_logs[…] succeeded in 0.0xxs
```

성공 후 Ctrl+C 로 worker 종료.

### 4.3 Redis 측 확인

```powershell
redis-cli -a "<REDIS_PASSWORD>" -n 1 INFO keyspace
# db1: keys=N,expires=0,... 으로 누적되었다가 처리 후 비워짐
```

---

## 5. Celery beat 고려 (서비스 등록은 Phase 6)

`apps/api/plane/celery.py` 에 기본 스케줄 12개 등록됨 (daily cleanup, 5분마다 이메일 알림 등 — [celery.py:29-80](../../../apps/api/plane/celery.py)).

Phase 6 에서 beat 를 NSSM 으로 서비스 등록한다. 본 Phase 에서는 수동 smoke test 만:

```powershell
celery -A plane beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

기동 후 `django_celery_beat_periodictask` 테이블에 schedule 이 저장됨 (1회 실행 후 중지 가능).

---

## 5a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P3-1 | `common.py` Celery 블록 수정 (**완료**) | — | §1 | `CELERY_BROKER_URL` env 우선 + `CONNECTION_RETRY_ON_STARTUP` |
| P3-2 | `.env` 의 `CELERY_BROKER_URL` 실효 확인 (Django 설정 로딩 시) | P2-10, P3-1 | §2 | `redis://.../1` |
| P3-3 | `RABBITMQ_*` / `pika` / `kombu` 잔재 전수 스캔 | P3-1 | §3 | fallback 5줄 외 0건 |
| P3-4 | Celery worker `--pool=solo` 수동 기동 | P2-13, P3-2 | §4.1 | transport=redis/1, results=disabled, deprecation 경고 X |
| P3-5 | `delete_api_logs.delay()` enqueue → 처리 완료 | P3-4 | §4.2 | succeeded 로그 |
| P3-6 | Redis /1 키 관찰 | P3-5 | §4.3 | enqueue 중 key 축적 → 처리 후 소거 |
| P3-7 | Celery beat 수동 기동 (DatabaseScheduler) | P3-4 | §5 | `django_celery_beat_periodictask` 레코드 |

---

## 5b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P3-1 | `Select-String common.py -Pattern "_celery_broker_url = os.environ.get","CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True"` | 각 1건 |
| P3-2 | `python -c "import django; django.setup(); from django.conf import settings; print(settings.CELERY_BROKER_URL)"` | `redis://:***@127.0.0.1:6379/1` |
| P3-3 | `Select-String plane -Recurse -Pattern "^import pika\|^from pika\|^import kombu\|^from kombu"` | 0 건 |
| P3-3 | `Select-String plane -Recurse -Pattern "RABBITMQ_"` | common.py fallback 5줄 + .env.example 5줄 만 |
| P3-4 | worker 기동 로그 `transport:\s+redis` 포함 + `broker_connection_retry` 경고 없음 | True · True |
| P3-5 | `celery-smoke.log` 에 `plane.bgtasks.cleanup_task.delete_api_logs[…] succeeded` | 1건 |
| P3-6 | `redis-cli -a $pw -n 1 DBSIZE` (enqueue 직후 / 처리 직후) | ≥1 → 0 |
| P3-7 | beat 기동 로그 `beat: Starting` + `Sending due task check-every-five-minutes-...` | 5 분 내 |

---

## 5c. 요구사항 검증 체크리스트

- [ ] **broker 전환** — P3-1, P3-2 로 Celery 가 Redis /1 을 사용. RabbitMQ 호출 0
- [ ] **업스트림 회귀 안전** — P3-1 의 코드가 fallback 을 보존. `CELERY_BROKER_URL` 미설정 시 기존 AMQP 경로 유지
- [ ] **Deprecation 해소** — P3-4 worker 로그에 `broker_connection_retry` 경고 미출력
- [ ] **Pool 선택** — `--pool=solo` 단일 스레드 (Windows 네이티브 안전)
- [ ] **Result backend 비활성** — transport 로그에 `results: disabled`
- [ ] **Redis DB 분리 실측** — /1 이 broker 전용. /0 cache 는 영향 없음
- [ ] **Phase 6 준비** — P3-4, P3-7 결과를 바탕으로 NSSM 서비스 등록 인자 확정 (worker/beat)

---

## 6. 체크포인트

Phase 4 로 넘어가기 전 전부 통과.

```powershell
# 코드 수정 반영
Select-String -Path D:\Workspace\plane-app\apps\api\plane\settings\common.py `
  -Pattern "CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP" -Quiet
# True
Select-String -Path D:\Workspace\plane-app\apps\api\plane\settings\common.py `
  -Pattern "_celery_broker_url = os.environ.get" -Quiet
# True

# 설정 로딩
cd D:\Workspace\plane-app\apps\api
.\.venv\Scripts\Activate.ps1
# ... .env 로딩 ...
python -c "from django.conf import settings; import django; django.setup(); assert settings.CELERY_BROKER_URL.startswith('redis://'), settings.CELERY_BROKER_URL; print('ok')"

# worker 기동 경로 확인 (기동 직후 5초 후 종료)
Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\celery.exe" `
  -ArgumentList "-A","plane","worker","--pool=solo","-l","info" `
  -RedirectStandardOutput "celery-smoke.log" -RedirectStandardError "celery-smoke.err"
Start-Sleep -Seconds 5
Stop-Process -Name celery -ErrorAction SilentlyContinue
Select-String -Path celery-smoke.log -Pattern "transport:\s+redis" -Quiet
# True
```

- [ ] common.py §1.2 수정 2줄 포함 (우선순위 + CONNECTION_RETRY_ON_STARTUP)
- [ ] `.env` 의 `CELERY_BROKER_URL` 이 `redis://.../1` 로 주입됨
- [ ] worker 기동 로그 `transport: redis://.../1`, `results: disabled`
- [ ] `broker_connection_retry` deprecation 경고 없음
- [ ] `delete_api_logs.delay()` enqueue → 처리 완료
- [ ] RABBITMQ/pika/kombu 직접 참조 없음(fallback 5줄 제외)

---

## 7. 이월 / 후속

- **Celery worker NSSM 서비스 등록** → [Phase 6](07-systemd.md) (pool=solo, concurrency 지정, EnvironmentFile, 자동 재시작)
- **Celery beat NSSM 서비스 등록** → [Phase 6](07-systemd.md) (Windows Task Scheduler 대안 가능 — beat 제거 시 cron 등가물로 우회)
- **Result backend 필요성 재평가** — 만약 프론트에서 태스크 진행률 표시가 요구되면 `CELERY_RESULT_BACKEND=redis://:.../2` 추가 검토 (별도 기획)
- **`.env.example` 갱신** — `RABBITMQ_*` 블록 제거 + `CELERY_BROKER_URL` 템플릿 추가. 현 Phase 에서는 미처리 (render-envs.ps1 가 실 `.env` 담당이라 영향 없음). 업스트림 머지를 하지 않으므로 후순위.

---

> **네비게이션**: [← Phase 2](03-source-prep.md) · [목차](../plan.md) · [다음: Phase 4 →](05-storage.md)
