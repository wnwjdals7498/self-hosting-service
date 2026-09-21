# SQLite 전환 참고 (Reference)

> 이 포크는 Plane v1.3.0 을 **SQLite 단일 파일 DB** 위에서 구동하도록 전환 완료된 상태다.
> 전환 실행 계획(`sqlite-migration.md` + `sqlite-migration/` 폴더, Phase A~G)은 정리되어 제거되었고, 본 문서는 **전환 이후의 런타임 상태 · 런타임 불변식 · 남은 리스크 · 재검증 방법**만 한 곳에 모아 둔 참고 자료다.
> 함께 읽을 문서: [initial-reference.md](initial-reference.md) (포크 전체 구조·의존성), [plan.md](plan.md) (배포 실행 계획).

---

## 1. 런타임 한 줄 요약

- **DB**: SQLite 3.38+ (Python 3.12+ stdlib `sqlite3` 로 충족) · **파일 하나** (`SQLITE_PATH` env 또는 기본값 `<BASE_DIR>/plane.sqlite3`)
- **드라이버/호환**: `psycopg*` / `dj-database-url` 없음 · `django.contrib.postgres` import 0건 (런타임 코드 기준)
- **연결 초기화**: 모든 SQLite 연결에 `PRAGMA journal_mode=WAL · synchronous=NORMAL · busy_timeout=5000 · foreign_keys=ON` 적용 + 트랜잭션 시작을 `BEGIN IMMEDIATE` 로 몽키패치
- **테스트 자산**: `plane/tests/` 아래에 golden capture/diff, W1~W20 쓰기 시나리오, latency/concurrency 벤치 3종 + 회귀 가드 유닛 테스트

---

## 2. 파일·심볼 단위 변경점 (Upstream 대비)

### 2.1 모델 (`apps/api/plane/db/models/`)

| 파일 | 변경 | 비고 |
|---|---|---|
| [issue.py](../../apps/api/plane/db/models/issue.py) | `ArrayField` → `JSONField(default=list)` (attachments, assignees, labels, modules) · `Issue.save()` 내 `pg_advisory_xact_lock` 을 `connection.vendor == "postgresql"` 가드로 감쌈 | 가드는 SQLite 경로를 no-op 으로 만들고 원본 Postgres 동작 보존 |
| [exporter.py](../../apps/api/plane/db/models/exporter.py) | `ExporterHistory.project` `ArrayField` → `JSONField` | |
| [apps.py](../../apps/api/plane/db/apps.py) | `DbConfig.ready()` 에서 (1) `connection_created` 시그널로 PRAGMA 주입, (2) `_install_sqlite_immediate_transactions()` 몽키패치 설치 | 아래 §3 참조 |
| `db/migrations/` | 원본 0001~0121 (121개) 삭제 후 **fresh `0001_initial` 단일 파일** 재생성 | 업스트림 히스토리 추적 불가 — 의도 (fork-only 운영) |

### 2.2 집계 헬퍼 (신규)

| 파일 | 역할 |
|---|---|
| [plane/utils/sqlite_aggregates.py](../../apps/api/plane/utils/sqlite_aggregates.py) | `JsonGroupArray`, `JsonGroupUuidArray`, `empty_json_array()` — `ArrayAgg` 의 SQLite 대응 Aggregate/헬퍼. `JsonGroupUuidArray` 는 SQLite `UUIDField` 가 32-char hex 로 저장되는 문제를 `SUBSTR` 조합으로 dashed UUID 복원. |

### 2.3 View/쿼리 계층 (ArrayAgg 제거, 10 파일 / 총 45 블록)

| 파일 | 비고 |
|---|---|
| [app/views/workspace/draft.py](../../apps/api/plane/app/views/workspace/draft.py) | DraftIssueLabel/Assignee/Module Subquery + `JsonGroupUuidArray` |
| [app/views/workspace/base.py](../../apps/api/plane/app/views/workspace/base.py) | `total_members` Subquery 에 `output_field=IntegerField()` 명시 (SQLite UUID 오인 방지) |
| [app/views/issue/base.py](../../apps/api/plane/app/views/issue/base.py) | 4 클러스터 × 3 블록 (labels/assignees/modules). 메인 이슈 ViewSet. |
| [app/views/issue/sub_issue.py](../../apps/api/plane/app/views/issue/sub_issue.py) | |
| [app/views/issue/relation.py](../../apps/api/plane/app/views/issue/relation.py) | |
| [app/views/intake/base.py](../../apps/api/plane/app/views/intake/base.py) | 6 클러스터 × 1~3 블록 |
| [app/views/search/base.py](../../apps/api/plane/app/views/search/base.py) | `filter_pages` `project_identifiers` 는 CharField 변형 → `JsonGroupArray("project__identifier")` |
| [app/views/page/base.py](../../apps/api/plane/app/views/page/base.py) | `label_ids` / `project_ids` |
| [app/views/cycle/base.py](../../apps/api/plane/app/views/cycle/base.py) · [cycle/archive.py](../../apps/api/plane/app/views/cycle/archive.py) | `assignee_ids` (Cycle → CycleIssue → Issue → IssueAssignee 체인) |
| [app/views/module/base.py](../../apps/api/plane/app/views/module/base.py) · [module/archive.py](../../apps/api/plane/app/views/module/archive.py) | ModuleMember 기반 `member_ids` |
| [api/views/intake.py](../../apps/api/plane/api/views/intake.py) | 공개 API intake |
| [api/views/issue.py](../../apps/api/plane/api/views/issue.py) | `_agg_ids` 헬퍼 → `JsonGroupUuidArray(field, filter=Q(**kwargs))` (Django 가 `FILTER (WHERE ...)` 절로 변환) |
| [space/views/issue.py](../../apps/api/plane/space/views/issue.py) | labels/assignees/modules + `vote_items` / `reaction_items` (`JsonGroupArray(JSONObject(...))`). 부수: `reaction_items` 내 avatar_url Case 의 copy-paste 버그 (`votes__actor__avatar_asset` → `actor__avatar_asset`) 동반 수정. |
| [space/utils/grouper.py](../../apps/api/plane/space/utils/grouper.py) | `issue_queryset_grouper` 동적 dict + `issue_on_results` vote/reaction items |

관리 커맨드 `db/management/commands/fix_duplicate_sequences.py` 도 `connection.vendor == "postgresql"` 가드 보강.

### 2.4 설정 (`apps/api/plane/settings/`)

| 파일 | 변경 |
|---|---|
| [common.py](../../apps/api/plane/settings/common.py) | `DATABASES` 를 SQLite 단일 dict 로 축약. `dj_database_url` import · `DATABASE_URL` · `POSTGRES_*` · `ENABLE_READ_REPLICA` 블록 전부 제거. PRAGMA/BEGIN IMMEDIATE 는 §3 의 시그널/몽키패치가 담당. |
| [test.py](../../apps/api/plane/settings/test.py) | `CACHES` 를 `plane.tests.cache_compat.DjangoRedisShimLocMemCache` 로 재지정. `CELERY_TASK_ALWAYS_EAGER=True` 는 기존 설정 유지. |

### 2.5 의존성 / 배포 구성

| 대상 | 변경 |
|---|---|
| [requirements/base.txt](../../apps/api/requirements/base.txt) | `psycopg`, `psycopg-binary`, `psycopg-c`, `dj-database-url` 제거 |
| [docker-compose.yml](../../docker-compose.yml) · [docker-compose-local.yml](../../docker-compose-local.yml) | `plane-db` 서비스 + `pgdata` 볼륨 제거, `sqlitedata` 볼륨을 api/worker/beat-worker/migrator 에 마운트 (`/var/lib/plane`) |
| [.env.example](../../.env.example) · [apps/api/.env.example](../../apps/api/.env.example) | `POSTGRES_*` / `DATABASE_URL` 제거, `SQLITE_PATH=/var/lib/plane/plane.sqlite3` 문서화 |
| [deployments/README.md](../../deployments/README.md) (신규) | `deployments/` 는 업스트림 엔터프라이즈 템플릿 원본 보존용이며 본 포크는 사용하지 않음을 명시 |

### 2.6 테스트/도구 자산 (신규)

| 경로 | 역할 |
|---|---|
| [plane/tests/golden_seed.py](../../apps/api/plane/tests/golden_seed.py) | 결정적 fixture 시드. `--scale 20` (기본) / `--scale 100` 지원 |
| [plane/tests/golden_capture.py](../../apps/api/plane/tests/golden_capture.py) | APIClient 로 22 엔드포인트 응답을 JSON 으로 스냅샷 |
| [plane/tests/golden_diff.py](../../apps/api/plane/tests/golden_diff.py) | deepdiff 기반 구조 비교. `TIMESTAMP_KEYS` (created/updated/deleted/last_saved/completed/start_date/target_date) + `RANDOM_SEEDED_KEYS` (background_color) 는 diff 에서 제외 |
| [plane/tests/cache_compat.py](../../apps/api/plane/tests/cache_compat.py) | `DjangoRedisShimLocMemCache` — LocMemCache 에 django-redis 확장 메서드(`keys`, `delete_pattern`, `ttl`) 를 no-op 으로 섀도 |
| [plane/tests/e_write_scenarios.py](../../apps/api/plane/tests/e_write_scenarios.py) | APIClient 기반 W1~W20 쓰기 시나리오 러너 (issue CRUD, module/cycle 링크, page 편집, 검색, 관계 등) |
| [plane/tests/measure_latency.py](../../apps/api/plane/tests/measure_latency.py) | 6 엔드포인트 × N 반복으로 p50/p95/p99 (ms) 측정 |
| [plane/tests/concurrent_writes.py](../../apps/api/plane/tests/concurrent_writes.py) | threading 기반 동시 Issue.create 스트레스. `database is locked` 탐지 |
| `plane/tests/unit/models/test_phase_b_jsonfield.py` | JSONField round-trip (17 테스트) |
| `plane/tests/unit/models/test_phase_d_sqlite.py` | migrate 검증 · PRAGMA 적용 · contrib.postgres 부재 |
| `plane/tests/unit/models/test_phase_e_write_paths.py` | ORDER BY 결정성 · 대소문자 · JSONField 편집 (6 테스트) |
| `plane/tests/unit/models/test_phase_g_residues.py` | runtime/requirements/docker-compose/settings 전수 스캔 가드 (4 테스트) |
| `plane/tests/unit/perf/test_phase_f_queries.py` | 6 엔드포인트 쿼리 수 ≤ ceiling |
| `plane/tests/unit/perf/test_phase_f_concurrency.py` | PRAGMA 가드 (busy_timeout/foreign_keys) |
| `plane/tests/golden/*.json` | 22 엔드포인트 기준선 스냅샷 |

---

## 3. 런타임 불변식 (반드시 지켜야 할 규약)

런타임에서 무너지면 조용히 동작 회귀로 이어질 수 있는 3가지.

### 3.1 `connection_created` 시그널로 PRAGMA 주입

Django 4.2 의 `django.db.backends.sqlite3` 는 `OPTIONS` 에 `init_command` 를 받지 않는다 (5.1 에 추가). 그래서 [plane/db/apps.py](../../apps/api/plane/db/apps.py) 의 `DbConfig.ready()` 가 `connection_created` 시그널을 걸어 매 연결마다 PRAGMA 4개(WAL, synchronous=NORMAL, busy_timeout=5000, foreign_keys=ON) 를 적용한다.

- `plane.db` 앱은 `INSTALLED_APPS` 에 반드시 포함되어야 함 (`ready()` hook 발화 조건)
- 새 스레드가 Django 연결을 만들 때마다 시그널이 재발화 — 스레드 풀 / Celery worker 모두 자동 적용
- **주의**: `:memory:` 테스트 DB 는 SQLite 가 `journal_mode=MEMORY` 로 강제. 시그널은 실행되지만 WAL 은 no-op. 파일 기반 DB 로 측정해야 WAL 이 실제 관측됨.

### 3.2 `BEGIN IMMEDIATE` 몽키패치

같은 `DbConfig.ready()` 에서 `DatabaseWrapper._start_transaction_under_autocommit` 을 `BEGIN IMMEDIATE` 로 교체한다. Django 4.2 기본은 `BEGIN DEFERRED` 이며, `transaction.atomic` 안에서 `SELECT MAX(...) + INSERT` 패턴 (예: `Issue.save()` 의 sequence 생성) 이 동시 실행되면 writer-lock 업그레이드 데드락으로 `SQLITE_BUSY` 를 즉시 반환한다 (busy_timeout 으로 흡수 불가). `BEGIN IMMEDIATE` 는 트랜잭션 시작 시점에 writer lock 을 잡아 경합을 queue 로 변환 → busy_timeout 이 흡수.

- 몽키패치는 `_plane_begin_immediate_installed` 플래그로 idempotent
- **Django 5.1+ 로 업그레이드 시 제거**: `DATABASES["default"]["OPTIONS"]["transaction_mode"] = "IMMEDIATE"` 로 대체
- 효과 실측: `plane/tests/concurrent_writes.py --n 50 --workers 5` → created=50, locked=0 (패치 없으면 28~50% 실패)

### 3.3 `invalidate_cache_directly` 는 Redis 가정

[plane/utils/cache.py:67](../../apps/api/plane/utils/cache.py) 의 `invalidate_cache_directly(..., multiple=True)` 는 `cache.keys("*pattern*")` + `cache.delete_many(...)` 를 호출한다. 이들은 **django-redis 확장 API** 이며 Django 내장 `LocMemCache` / `DummyCache` 에는 존재하지 않는다.

- 프로덕션: `REDIS_URL` 로 연결된 `django_redis.cache.RedisCache` → 정상 동작
- Redis 가 내려가면 레이블/페이지 등 쓰기 경로 엔드포인트가 **500 으로 실패** — 캐시 invalidate 를 best-effort 로 강등하는 패치는 적용하지 **않음** (업스트림 동작 유지)
- 테스트: `settings/test.py` 가 `DjangoRedisShimLocMemCache` 로 우회 — `keys() -> []` / `delete_pattern() -> 0` / `ttl() -> None` 반환으로 invalidate 를 no-op 처리

---

## 4. 성능 베이스라인 (phase-f 실측, 1인 규모 합격 기준 대비)

`golden_seed.py --scale 100` (이슈 100건 / 프로젝트 2개 / 모듈·사이클 4개씩 / 페이지 40개 / 라벨 6개) 기준.

### 4.1 쿼리 수 (`plane/tests/unit/perf/test_phase_f_queries.py`)

| 엔드포인트 | ceiling | 실측 |
|---|---:|---:|
| `issues_list` | ≤ 20 | **12** |
| `issues_list_filtered` (?priority=high) | ≤ 25 | **12** |
| `cycles_list` | ≤ 15 | **4** |
| `modules_list` | ≤ 15 | **2** |
| `pages_list` | ≤ 10 | **4** |
| `search` | ≤ 15 | **8** |

Phase C 의 `ArrayAgg → Subquery(JsonGroupUuidArray)` 치환이 상수 배 증가에 그치고 N+1 패턴을 만들지 않음을 확인.

### 4.2 응답 시간 (APIClient, N=100, warm-up 3회 별도, ms 단위)

| 엔드포인트 | p50 | p95 | p99 | ceiling p95 |
|---|---:|---:|---:|---:|
| `issues_list` | 25.38 | 28.59 | 32.41 | 500 |
| `issues_list_filtered` | 19.66 | 21.25 | 22.80 | 800 |
| `cycles_list` | 13.53 | 14.66 | 17.73 | 300 |
| `modules_list` | 20.14 | 24.22 | 25.74 | 300 |
| `pages_list` | 10.09 | 11.86 | 15.96 | 200 |
| `search` | 11.07 | 16.37 | 19.55 | 400 |

모든 엔드포인트가 ceiling 의 10% 이하. 측정은 HTTP 소켓을 제외한 ORM + 시리얼라이저 경로만 포함.

### 4.3 동시 쓰기

`concurrent_writes.py --n 50 --workers 5` → elapsed 0.82~1.10s · created=50 · in_db=50 · **locked=0**. §3.2 BEGIN IMMEDIATE 패치가 없으면 28~50% 실패.

---

## 5. 잔여 리스크 및 알려진 한계

| # | 항목 | 현재 상태 | 대응 |
|---|---|---|---|
| 1 | **Full-text search** — 원본 Postgres `SearchVector/SearchQuery` 없이 `icontains` 기반 | `app/views/search/base.py` 가 모든 엔티티에서 `icontains` 사용 | 1인 규모 수용. 대량 텍스트/성능 이슈 시 SQLite FTS5 도입 검토 |
| 2 | **JSONField `__contains` 쿼리는 테이블 스캔** | 현재 JSONField 배열 필드(attachments, IssueVersion.assignees/labels/modules 등) 에는 `__contains` 쿼리 없음 | 필요 시 generated column + index. 미발생 상태 |
| 3 | **동시 쓰기 `database is locked`** | WAL + busy_timeout + BEGIN IMMEDIATE 로 해결 (§3.2) | 50 writers/50 creates, 0 locked 실측 |
| 4 | **Pre-signed URL 의존성 (파일 저장소)** | 업스트림 그대로, SQLite 와 무관 | [plan/05-storage.md](plan/05-storage.md) 가 MinIO 네이티브 유지 여부를 결정 |
| 5 | **`connection.vendor == 'postgresql'` 가드** | `db/models/issue.py:210` + `db/management/commands/fix_duplicate_sequences.py:65` 두 곳 · 둘 다 SQLite 에서는 no-op | 새 기능 추가 시 동일 가드 패턴 준수 |
| 6 | **업스트림 Plane 머지 불가** | 마이그레이션 `0001_initial` 하나만 남김 | 포크 전용 운영 확정. 업스트림 기능 이식은 수동 cherry-pick |
| 7 | **Celery result backend** | `django-db` 기본. 1인 규모에서 성능 이슈 없음 | 필요 시 Redis backend 전환 (`CELERY_RESULT_BACKEND=redis://...`) |
| 8 | **Postgres 대비 동작 교차 검증 불가** | 작업 VM 이 이중 가상화 금지로 Postgres 띄우지 못함 | `e_write_scenarios.py` 는 Postgres 환경에서도 실행 가능하도록 작성 — 원본 DB 환경 접근 시 재실행으로 교차 검증 |
| 9 | ~~**Replica 라우팅 "dead code"**~~ | **해소 (2026-04-19)**: `plane/middleware/db_routing.py` + `plane/utils/core/` 전체 + 관련 테스트 + `ReadReplicaControlMixin` 상속 + 24 view 파일의 `use_read_replica` 클래스 속성 52개 제거. BaseAPIView/BaseViewSet MRO 에서 mixin 이 사라졌고 `settings.DATABASES` 에는 여전히 `replica` 별칭이 없음. | `test_phase_g_residues` 가드가 재도입을 감지 |
| 10 | **`invalidate_cache_directly` 가 Redis 다운 시 500** | 업스트림 동작 보존 · 테스트는 §3.3 shim 으로 우회 | 운영에서 Redis HA 가정. 단기 장애 대응 필요하면 별도 리팩터 과제 |
| 11 | **골든 비-2xx 3건** | `workspaces_list` 400 (query param/auth context) · `labels_list` 404 (slug/pid 순서) · `space_projects_list` 404 (공개 라우트 미등록 가능) | Phase E 통과 기준 외 — 기능 단위 검증 필요 시 별도 과제 |

---

## 6. 재검증 절차 (클린 체크아웃에서)

```bash
# 1. env (Windows bash 예시 — Linux/WSL 도 동일)
export DJANGO_SETTINGS_MODULE=plane.settings.test
export SECRET_KEY=dev
export REDIS_URL=redis://localhost:6379/0
export APP_BASE_URL=http://localhost:3000
export WEB_URL=http://localhost:3000
export SQLITE_PATH=/tmp/plane_verify.sqlite3
export DEBUG=0

# 2. fresh DB + seed
cd apps/api
rm -f "$SQLITE_PATH"
.venv/Scripts/python.exe manage.py migrate                    # exit 0
.venv/Scripts/python.exe plane/tests/golden_seed.py --quiet   # scale=20
.venv/Scripts/python.exe plane/tests/golden_seed.py --scale 100 --quiet  # perf 용

# 3. 골든 캡처 + 구조 비교
.venv/Scripts/python.exe plane/tests/golden_capture.py --capture --out /tmp/verify-golden
.venv/Scripts/python.exe plane/tests/golden_diff.py --old plane/tests/golden --new /tmp/verify-golden
# expect diff_count = 0

# 4. 쓰기 시나리오 W1~W20
.venv/Scripts/python.exe plane/tests/e_write_scenarios.py
# expect 20/20 passed

# 5. 유닛 스위트 (models + perf)
.venv/Scripts/python.exe -m pytest plane/tests/unit/models plane/tests/unit/perf -q
# expect 48 passed (이미 알려진 pre-existing 5건은 unit/bg_tasks, unit/utils 에 국한)

# 6. latency (scale=100 DB 에서)
.venv/Scripts/python.exe plane/tests/measure_latency.py --iterations 100
# expect all 6 scenarios "PASS"

# 7. 동시 쓰기
.venv/Scripts/python.exe plane/tests/concurrent_writes.py --n 50 --workers 5
# expect created=50, locked=0

# 8. 잔존 참조 전수 스캔 (gating)
.venv/Scripts/python.exe -m pytest plane/tests/unit/models/test_phase_g_residues.py -q
# expect 4 passed
```

실패 시 §3 의 불변식 (PRAGMA 시그널 발화 · `BEGIN IMMEDIATE` 설치 · cache shim 적재) 을 먼저 확인한다.

---

## 7. 향후 과제 (후속 작업 후보)

1. **Django 5.1 업그레이드 시**: `_install_sqlite_immediate_transactions` 몽키패치를 `DATABASES["default"]["OPTIONS"]["transaction_mode"] = "IMMEDIATE"` 로 대체 (§3.2)
2. **골든 비-2xx 3건** 기능 단위 해결 (§5 #11)
3. **FTS5 검토** (§5 #1) — 100건 수준에서는 불필요
4. **Postgres 교차 검증** — 원본 Postgres 접근 가능한 환경에서 `e_write_scenarios.py` 재실행 (§5 #8)

---

## 8. 연관 문서

- [initial-reference.md](initial-reference.md) — 포크 전체 구조·앱/패키지 레이아웃·의존성·린트·개발 명령
- [plan.md](plan.md) — SQLite 전환 이후 네이티브 배포 상위 계획 (Phase 0~8)
- [plan/10-risks.md](plan/10-risks.md) — 배포 단계 리스크 (§5 와 층이 다름 — 본 문서는 DB 계열, plan/10 은 배포 계열)
- git 이력 — 커밋 `a2542ef..d19501b` 구간이 전환 전체 범위 (26 커밋)
