# Plane v1.3.0 Fork — 초기 참고 (Initial Reference)

> 이 문서는 Plane v1.3.0 원본을 **1인 개인용**으로 경량화·SQLite 전환한 **현재 포크**의 한 장짜리 참고다.
> 원본 Plane 구조, 이 포크에서 확정된 방향, 의존성 스택, 레이아웃, 개발/린트 워크플로우를 한 곳에 모아 `brainstorm.md` + `docs/linting.md` + 분산되어 있던 "코드 구조 설명"을 대체한다.
> 함께 읽을 문서: [plan.md](plan.md) (배포 실행 계획), [sqlite-reference.md](sqlite-reference.md) (DB 전환 결과·불변식).

---

## 1. 이 포크의 방향 (확정된 전제)

원본 Plane 을 그대로 운영하면 Postgres + Redis + RabbitMQ + MinIO + Celery(worker+beat) + 6개 SPA 앱을 들고 가야 한다. 1인 규모에서는 과하다는 판단으로 다음 방향이 확정됐다.

| 항목 | 결정 | 근거 |
|---|---|---|
| 사용자 수 | 1인 전용 | 외부 공유(space), 관리자 UI(admin) 는 선택 사용 |
| 접근 방식 | 외부 접근 허용 (HTTPS) | Cloudflare Tunnel 또는 Caddy 네이티브 |
| 실행 환경 | **네이티브** (Docker 불사용) | 호스트에 systemd 서비스로 직접 기동 |
| DB | **SQLite 단일 파일** | 전환 완료 — [sqlite-reference.md](sqlite-reference.md) |
| Queue/Cache | **Redis 단일 노드** | Celery broker 겸용. RabbitMQ 제거 |
| 파일 저장소 | **로컬 파일시스템** | MinIO 제거. pre-signed URL 의존성 확인 필요 — [plan/05-storage.md](plan/05-storage.md) |
| 기능 범위 | web + api + admin + space + live 유지 | 앱 단위 제거 대신 systemd 로 on-demand 관리 |

자세한 배포 단계는 [plan.md](plan.md) 참고.

---

## 2. 원본 Plane 레이아웃 (변경 없이 이해만)

```
plane/
├── apps/
│   ├── api/          Django 4.2 + DRF + Celery 백엔드 (Python)
│   ├── web/          React Router 7 + Vite 메인 SPA (port 3000)
│   ├── admin/        관리자 대시보드 SPA (port 3001, /god-mode)
│   ├── space/        외부 공개 포털 SPA (port 3002, /spaces)
│   ├── live/         Node + tsdown 실시간 협업 서버 (Yjs, port 3100)
│   └── proxy/        Caddy 역프록시 (Dockerfile + Caddyfile)
├── packages/         @plane/* 내부 공유 패키지 15개 (아래 §3.2)
├── deployments/      업스트림 엔터프라이즈 배포 템플릿 (aio/, cli/, kubernetes/, swarm/)
│                     본 포크는 사용하지 않음 — [deployments/README.md](../../deployments/README.md)
├── docs/
│   └── customization/ 본 포크의 설계/계획 문서
├── docker-compose.yml / docker-compose-local.yml
│                     plane-db(Postgres) 제거, sqlitedata 볼륨 추가 상태
├── turbo.json        모노레포 태스크 orchestration
├── pnpm-workspace.yaml
└── package.json      루트 (workspace host, version: 1.3.0)
```

**모노레포 경계**:
- `pnpm-workspace.yaml` 은 `apps/*` + `packages/*` 를 포함하되 **`apps/api` 와 `apps/proxy` 는 pnpm workspace 에서 제외** — api 는 Python, proxy 는 Caddy 정적 설정이라 Node 의존성이 없음.
- Turbo 는 `apps/api`/`apps/proxy` 를 task 대상에서 자연스럽게 제외.

---

## 3. 앱별 역할과 의존성

### 3.1 `apps/api` (Python, Django)

**진입점**: [manage.py](../../apps/api/manage.py) → `DJANGO_SETTINGS_MODULE=plane.settings.production` (기본). 테스트는 `plane.settings.test`, 개발은 `plane.settings.local`.

**모듈 구조** (`apps/api/plane/`):

| 모듈 | 책임 |
|---|---|
| `app/` | 내부 API (`/api/workspaces/...`). views/serializers/urls/permissions/middleware — **실사용 API 주력** |
| `api/` | 공개 API (`/api/v1/...` — API key 인증) · workspace/project/issue CRUD 공개 노출 |
| `space/` | Public-facing 공개 포털 API (`/api/public/...`) — 인증 없이 보기만 가능 |
| `db/` | Django 모델 · 마이그레이션 (SQLite 전환 후 `0001_initial` 단일) · `apps.py` 가 PRAGMA/BEGIN IMMEDIATE 설치 |
| `bgtasks/` | Celery 태스크 (이슈 활동 로그, 이메일, 버전 기록, 파일 복사 등) |
| `authentication/` | 세션/토큰/OAuth/OTP · SSO · API key |
| `analytics/` | 대시보드용 집계 |
| `middleware/` | Request context, throttle, replica routing(비활성 dead code) |
| `settings/` | `common.py` (기반) · `local.py`/`production.py`/`test.py` (override) · `redis.py`/`storage.py`/`mongo.py`/`openapi.py` (함수 helper) |
| `tests/` | golden capture/diff 도구 · e_write_scenarios · measure_latency · concurrent_writes · unit/{models,perf} |
| `utils/` | sqlite_aggregates · cache · filter · pagination 등 순수 helper |

**Python 의존성** ([requirements/base.txt](../../apps/api/requirements/base.txt), 핵심만):

| 카테고리 | 패키지 |
|---|---|
| 프레임워크 | Django 4.2.29 · djangorestframework 3.15.2 |
| 큐 | celery 5.4 · django-celery-beat 2.6 · django-celery-results 2.5 |
| 캐시/큐 broker | redis 5.0 · django-redis 5.4 |
| 파일/스토리지 | boto3 1.34 · django-storages 1.14 · whitenoise 6.11 |
| 실시간 | channels 4.1 · uvicorn 0.29 |
| 기타 | drf-spectacular 0.28 · beautifulsoup4 · lxml · openpyxl · posthog · scout-apm · opentelemetry-* · PyJWT · cryptography · zxcvbn · openai · slack-sdk · pymongo |
| **제거됨** | ~~psycopg~~ · ~~psycopg-binary~~ · ~~psycopg-c~~ · ~~dj-database-url~~ — SQLite 전환 시 삭제 |

개발 전용 ([requirements/local.txt](../../apps/api/requirements/local.txt)): `django-debug-toolbar 4.3`, `ruff 0.9.7`.
테스트 전용 ([requirements/test.txt](../../apps/api/requirements/test.txt)): `pytest 9.0` + django/cov/xdist/mock 플러그인, `factory-boy`, `freezegun`, `httpx`, `requests`, `deepdiff` (별도 추가).

### 3.2 `packages/` (TypeScript, pnpm workspace)

프론트엔드 4개 SPA (`web`/`admin`/`space`/`live`) 가 공유하는 내부 라이브러리. 모두 `@plane/*` 네임스페이스.

| 패키지 | 역할 |
|---|---|
| `ui` | 공용 컴포넌트 (shadcn 파생 + Atlassian pragmatic-drag-and-drop) |
| `editor` | Tiptap 확장 (에디터 기능은 여기서만 수정, 앱에서 직접 import 금지) |
| `services` | API 클라이언트 (axios/fetch wrapper · 각 리소스별 함수 집합) |
| `shared-state` | MobX 스토어들 공유 base |
| `types` | API 응답/요청 타입 정의 |
| `constants` · `decorators` · `hooks` · `i18n` · `logger` · `propel` · `utils` | 각 영역별 유틸리티 |
| `tailwind-config` · `typescript-config` | 공용 설정 |
| `codemods` | 코드 마이그레이션 유틸 |

### 3.3 프론트엔드 SPA 4종

| 앱 | 프레임워크 | 개발 포트 | 스크립트 |
|---|---|---|---|
| `apps/web` | React Router 7 + Vite | 3000 | `pnpm dev` → `react-router dev` |
| `apps/admin` | React Router 7 + Vite | 3001 | 동일 (`/god-mode` 경로) |
| `apps/space` | React Router 7 + Vite | 3002 | 동일 (`/spaces` 경로) |
| `apps/live` | Node + tsdown (Yjs 서버) | 3100 | `tsdown --watch`, 빌드 산출물 `dist/start.mjs` |

**React 18.3** · **React Router 7** 기반 (Next.js 아님). 상태관리 MobX 6 (`observer`, `makeObservable` 기존 패턴 유지). Node ≥22.18.

### 3.4 `apps/proxy`

Caddy 설정 (`Caddyfile.ce` · `Caddyfile.aio.ce`) · `Dockerfile.ce`. 원본은 docker-compose 기반 배포용. 네이티브 배포 시 Caddy 네이티브 설치로 같은 라우팅 구성 가능 — [plan/08-external-access.md](plan/08-external-access.md) 참고.

---

## 4. 개발·빌드·테스트 명령

모노레포 루트에서 Turbo 가 프론트엔드를, 백엔드는 `apps/api` venv 에서 직접 실행.

### 4.1 의존성 설치

```bash
# 루트 (frontend)
pnpm install

# backend
cd apps/api
python -m venv .venv
# Linux/WSL: source .venv/bin/activate
# Windows bash: .venv/Scripts/activate
pip install -r requirements/local.txt    # dev
pip install -r requirements/test.txt     # test 도 필요 시
```

### 4.2 개발 실행

| 대상 | 명령 |
|---|---|
| 프론트엔드 전체 병렬 | `pnpm dev` (= `turbo run dev --concurrency=18`) |
| 백엔드 개발 서버 | `cd apps/api && .venv/*/python manage.py runserver` |
| Celery worker | `cd apps/api && celery -A plane worker -l info` |
| Celery beat | `cd apps/api && celery -A plane beat -l info` |

### 4.3 빌드

```bash
pnpm build                  # turbo run build — 4 SPA 병렬
# 산출물: apps/{web,admin,space}/build/  +  apps/live/dist/
```

### 4.4 테스트

| 대상 | 명령 |
|---|---|
| 프론트엔드 | `pnpm turbo test` (현재 각 패키지의 `test` 스크립트 기준) |
| 백엔드 유닛 | `pytest plane/tests/unit/models plane/tests/unit/perf -q` |
| 백엔드 골든 | `python plane/tests/golden_capture.py --capture --out /tmp/x && python plane/tests/golden_diff.py --old plane/tests/golden --new /tmp/x` |
| 백엔드 쓰기 시나리오 | `python plane/tests/e_write_scenarios.py` |
| 백엔드 latency | `python plane/tests/measure_latency.py --iterations 100` |
| 백엔드 동시 쓰기 | `python plane/tests/concurrent_writes.py --n 50 --workers 5` |

pytest 설정([pytest.ini](../../apps/api/pytest.ini)): `--reuse-db --nomigrations`, markers `unit`/`contract`/`smoke`/`slow`.

Phase F/G 에서 `plane/tests/unit/` 에 추가된 스위트 총 48개 통과. 자세한 실행 절차는 [sqlite-reference.md §6](sqlite-reference.md).

---

## 5. 린트·포맷 (oxlint + oxfmt, 루트 단일)

Plane v1.3.0 은 ESLint/Prettier 대신 **oxlint 1.51** + **oxfmt 0.35** (Rust 기반, ESLint 대비 50~100배 빠름) 를 루트 단일 설정 (`.oxlintrc.json`, `.oxfmtrc.json`) 으로 운영한다.

### 5.1 활성 플러그인

`react`, `typescript`, `jsx-a11y`, `import`, `promise`, `unicorn`, `oxc` · 카테고리 `correctness=error` / `suspicious=warn` / `perf=warn`.

### 5.2 핵심 off 규칙

`react/react-in-jsx-scope`, `react/prop-types`, `unicorn/filename-case`, `unicorn/no-null`, `unicorn/prevent-abbreviations`.
Unused vars 는 `_` prefix (`^_` pattern) 허용.

### 5.3 명령

| 목적 | 명령 |
|---|---|
| 전체 린트 | `pnpm check:lint` (= `turbo run check:lint`) |
| 자동 수정 | `pnpm fix:lint` |
| 특정 패키지만 | `pnpm turbo run check:lint --filter=@plane/ui` |
| 타입체크 | `pnpm check:types` |
| 포맷 체크 | `pnpm check:format` |

### 5.4 범위

대상: `apps/{web,admin,space,live}` + 모든 `packages/*` (TypeScript/JavaScript 전체).
제외: `node_modules/`, `dist/`, `build/`, `.next/`, `.turbo/`, config 파일 (`*.config.{js,mjs,cjs,ts}`), public/coverage/storybook-static.

### 5.5 pre-commit

husky + lint-staged 로 `.md/.css/.json` 은 oxfmt, `.ts/.tsx/.js/.jsx/.cjs/.mjs/.cts/.mts` 는 `oxlint --fix --deny-warnings` 가 스테이지된 파일에 자동 적용. 실패 시 커밋 중단.

### 5.6 Python (백엔드) 린트

Python 쪽은 **ruff** 단일 (`apps/api/pyproject.toml`) — line-length 120, indent 4 space, double quote, `pycodestyle(E) + pyflakes(F)` 기본 활성, McCabe ≤10, 임포트 정렬 `known-first-party=["plane"]`. 실행: `cd apps/api && ruff check . && ruff format --check .`.

### 5.7 eslint-disable 호환

oxlint 는 기존 `// eslint-disable-next-line ...` 주석을 그대로 인식한다. 기존 suppression 은 유효하지만 남발하지 않는다.

---

## 6. 런타임 구성 (포크 현재 상태 스냅샷)

| 요소 | 현재 |
|---|---|
| DB | SQLite 3.38+ · `SQLITE_PATH=/var/lib/plane/plane.sqlite3` (Docker) 또는 `<BASE_DIR>/plane.sqlite3` (default) |
| 연결 초기화 | [plane/db/apps.py](../../apps/api/plane/db/apps.py) `DbConfig.ready()` — PRAGMA 주입 + `BEGIN IMMEDIATE` 몽키패치 |
| 캐시 | 운영: django-redis / 테스트: [plane/tests/cache_compat.py](../../apps/api/plane/tests/cache_compat.py) 의 `DjangoRedisShimLocMemCache` |
| Celery broker | `REDIS_URL` 기반 (plan [Phase 3](plan/04-celery-broker.md) 에서 `CELERY_BROKER_URL` env override 도입 예정) |
| 파일 저장소 | 현재 `STORAGES["default"]=S3Storage` 하드코딩 (plan [Phase 4](plan/05-storage.md) 에서 `USE_LOCAL_STORAGE` env 분기 추가 예정) |
| docker-compose | `plane-db` 제거, `sqlitedata` 볼륨 마운트. `plane-redis`, `plane-mq`, `plane-minio`, `proxy` 등은 원본 유지 |
| deployments/ | 업스트림 원본 그대로 — 본 포크 사용 안 함 |

자세한 불변식·리스크는 [sqlite-reference.md](sqlite-reference.md).

---

## 7. 제거 후보 (원본 vs 이 포크에서 쓰지 않는 것)

### 앱 단위

- `apps/space` (외부 공개 포털) — 1인이면 기동 안 해도 무방 · systemd 단위로 on/off
- `apps/admin` — 초기 설정 후 `systemctl stop` 가능
- `apps/live` — 동시 편집 불필요하면 미기동. Tiptap 자체는 클라이언트라 저장은 동작

### 인프라

- ~~Postgres~~ → **SQLite** (전환 완료)
- ~~RabbitMQ~~ → **Redis 단일** (plan Phase 3)
- ~~MinIO~~ → **로컬 FS** 가능성 검토 (plan Phase 4)
- ~~Celery Beat~~ 선택적 제거 (OS cron 대체)

### 기능/패키지 다이어트 (후순위, 범위 미확정)

- i18n 단일 언어 고정 → web 번들 축소
- OAuth provider 제거 (email/password 만)
- `@plane/propel` (분석) 제거
- Storybook 빌드 제외

---

## 8. 확인 필요 리스크 (해결되지 않은 것만)

SQLite 계열은 [sqlite-reference.md §5](sqlite-reference.md) 가 전담. 그 외 배포/기능 계열:

1. **배포 OS**: Linux(WSL2 포함) 전제. Windows 네이티브 시 Celery 5.4 공식 미지원
2. **Pre-signed URL 의존성**: [plan/05-storage.md](plan/05-storage.md) 에서 조사 후 로컬 FS 가부 결정
3. **live 서비스 단독 저장**: 혼자 쓸 때 live 없이 페이지 저장이 정상 동작하는지 실측 필요
4. **이메일 전송**: Celery 태스크 기반, SMTP 미설정 시 콘솔 백엔드로 우회
5. **보안**: `DEBUG=0`, `SECRET_KEY` 엔트로피, `ALLOWED_HOSTS` 제한, `/god-mode` Cloudflare Access 권장
6. **공개 Space 라우트**: 현재 골든에서 `/api/public/workspaces/{slug}/projects/` 404 — 라우트 등록 여부 재확인 필요

---

## 9. 커스터마이즈 규칙 (이 포크 운영 원칙)

- **레이아웃 변경**은 [.claude/project-layout.md](../../.claude/project-layout.md) 최신화 + 이용자 승인 후. 임의 경로 생성 금지.
- 원본 Plane 구조 변경 (앱 제거, 인프라 교체 등) 은 본 `docs/customization/` 하위에 이력 기록.
- 의존성 추가/메이저 업그레이드는 반드시 질문 후 승인.
- Tiptap 확장 편집은 `packages/editor` 에서만. 앱에서 직접 import 금지.
- 신규 컴포넌트도 기존 MobX `observer` 패턴 준수.
- 테스트/린트/타입체크는 작업 완료 전 필수 (`pnpm check` + backend `ruff check + pytest`).

---

## 10. 연관 문서 & 이력

- [plan.md](plan.md) — 배포 실행 계획 (Phase 0~8)
- [sqlite-reference.md](sqlite-reference.md) — SQLite 전환 결과·런타임 불변식·리스크
- 루트 [README.md](../../README.md) — 원본 Plane 소개 (unchanged)
- 루트 [CLAUDE.md](../../CLAUDE.md) — AI 협업 지침
- git 이력: `a2542ef` = v1.3.0 import baseline. 그 이후 커밋이 전부 포크 커스터마이징.
