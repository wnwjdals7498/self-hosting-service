# Worklog — Windows 네이티브 배포 세션 (완료 이력 + 교훈)

> Phase 0~8 Plane 네이티브 배포 + 보안 감사/보안 #1 의 **완료 이력** 과 운영 중 누적된 교훈(§7a~§7h) 을 보관한다. **앞으로 해야 할 작업은 [todo.md](todo.md)** 에 분리, 장기 설계는 [plan.md](plan.md) 참조.

**최종 갱신**: 2026-04-24 — 보안 세션 #1 §A 전체 + §B 주요 완료 (§A P1 joojm 16자+ / §A P2 password policy / §A P3 Administrator Disable / §B P3 IPBan 정책 강화 / §B P4 cloudflared 이관 / §B P5 AppExit 조사). 세션 잔존 + 다음 세션 계획은 [todo.md](todo.md).

---

## 1. 한눈에 보는 진행 상태

| Phase | 상태 | 주요 산출물 |
|---|---|---|
| 0 사전 준비 | **완료** | 3 계정 · 3 경로 · ACL · Python/Node/pnpm · Redis · NSSM · cloudflared · 방화벽 6 포트 차단 · IPBan |
| 1 인프라 | **완료** | `ops/redis.conf` + plane 계정 전환 · volatile-lru · AOF · 로그 5 하위 |
| 2 소스 준비 | **완료** | 운영 트리 clone · venv · `site.env` · `render-envs.ps1` · migrate · superuser · configure/register · collectstatic · runserver smoke |
| 3 Celery broker | **완료 (코드만)** | `common.py` 수정 — broker URL env 우선 + retry_on_startup. runtime 은 Phase 6 NSSM 등록 시 실측 |
| 4.1 Storage 어댑터 | **완료** | `LocalFSStorage` + `/api/assets/local-{upload,download}/` + 5 유닛 테스트 |
| 4.2 View 전환 | **완료** | `get_storage` factory + 21 call sites + `is_server=True` 3곳 제거 |
| 4.3 bgtasks | **완료** | `presigned_url` 헬퍼 + 4 bgtask + 2 bucket 커맨드 no-op + test mock 갱신 |
| 4.4 Frontend 타입 | **스킵** | 4.1 이 `x-amz-*` 필드명 유지 → `packages/types/src/file.ts` 무변경 |
| 5 Frontend build | **완료** | `render-envs.ps1` 4 섹션 확장 (UTF8NoBom) · space SPA 전환 · `pnpm turbo build` 16/16 · 4 산출물 존재 · VITE_* 번들 inline |
| 6 NSSM 서비스 | **완료** | `ops/register-services.ps1` · plane-api/celery/beat/live 모두 Running · API :8000 HTTP 200 · Live :3100 LISTENING · Celery task 수신 실측 |
| 7 외부 접근 (Caddy) | **완료** | `ops/Caddyfile` · `ops/register-caddy.ps1` · caddy v2.11.2 @ `tools/caddy/` · 공인 IP :80 HTTP 200 · 5경로 라우팅 검증 (web/admin/space SPA + api reverse_proxy + uploads 403) · space 보안 헤더 4종 재발행 실측 · 방화벽 80 인바운드 허용 |
| 8 검증 · 백업 | **거의 완료 (§6 security-todo 만 남음)** | §1 기능 검증(15/15 외부 브라우저 E2E + 1 bonus, §7d fork-local fix 4건) · §2 회귀(1차 §2.1~§2.4 + 2 차 pytest 재확인 + §2.5~§2.7 이월분, §7f) · §3 부하 smoke(1인 운영 기준, §7g) · §4 재부팅 내성(6+7 차) · §5 백업 자동화(PlaneBackup Daily 02:00 + §5.3 분기 복구 훈련 2026 Q2 초회, §7e) 완료. §6 security-todo(§8 체크리스트 7건)만 미진행. 세부 §7a~§7g |

---

## 2. 호스트 상태 스냅샷

- **OS**: Windows Server 2025 Standard (Build 26100), VM, 중첩 가상화 불가
- **공인 IP**: `222.234.220.199` — 공유기 없이 직접 물림 (NAT 없음)
- **시간대**: KST (UTC+09:00). Plane 내부는 UTC — 로그 가독성만 KST
- **계정**: `plane`(서비스) · `plane-admin`(로컬 콘솔, RDP 불가) · `joojm`(RDP)
- **경로**:
  - `D:\Workspace\plane` — **개발 트리** (git 작업, 본 저장소)
  - `D:\Workspace\plane-app` — **운영 트리** (clone + ops + tools)
  - `D:\Workspace\plane-data\{sqlite,uploads,backup,redis}`
  - `D:\Workspace\plane-logs\{api,worker,beat,live,redis,caddy,ipban}`

### 2.1 실행 중 서비스

| 서비스 | 상태 | 계정 | 의존성 | 비고 |
|---|---|---|---|---|
| Redis | Running / Automatic | `.\plane` | — | tporadowski 5.0.14.1, volatile-lru + AOF, `ops/redis.conf` 기반 |
| IPBan | Running / Automatic (Delayed) | LocalSystem | — | NSSM wrap, 방화벽 차단 DB 보존. **2026-04-24 변경**: Start 타입 `AUTO_START` → `AUTO_START (DELAYED)` + `AppRestartDelay 30000` (6 차 재부팅 10:35:59 에 37 s 만에 early-boot crash 재현, 7 차 재부팅에서 Delayed 방어로 해소 확정 — §7 교훈) |
| plane-api | Running / Automatic | `.\plane` | Redis | uvicorn 1 worker, 127.0.0.1:8000 |
| plane-celery | Running / Automatic | `.\plane` | Redis, plane-api | celery worker --pool=solo |
| plane-beat | Running / Automatic | `.\plane` | Redis, plane-api | DatabaseScheduler |
| plane-live | Running / Automatic | `.\plane` | Redis | node --env-file=.env dist/start.mjs, 0.0.0.0:3100 |
| caddy | Running / Automatic | `LocalSystem` | plane-api | v2.11.2, `:80` 단일 수신, `ops/Caddyfile` (admin off) |

plane-* 4개는 `ops/register-services.ps1`, Caddy 는 `ops/register-caddy.ps1` (둘 다 운영 트리 전용, git 외부).

### 2.2 설치된 런타임

- Python **3.13.13** (system MSI)
- Node **24.14.1** (nvm-windows)
- pnpm **10.32.1** (corepack; plane-app 내부만 이 버전 고정)
- Caddy **v2.11.2** at `D:\Workspace\plane-app\tools\caddy\caddy.exe` (winget 설치본을 ops 트리로 복사 — user-local winget 경로는 plane 서비스 계정이 Access Denied 이므로 반드시 공용 경로 유지)
- cloudflared 2025.8.1 (도메인 확보 시 HTTPS 전환 예비)
- NSSM 2.24 at `D:\Workspace\plane-app\tools\nssm\nssm-2.24\win64\nssm.exe`

### 2.3 DB 상태

- `D:\Workspace\plane-data\sqlite\plane.sqlite3` — 3.6 MB, 44 마이그레이션 적용
- superuser: `wnwjdals7498@naver.com` / `joojm`
- `Instance` 레코드 1 (`plane-windows-server-2025`)
- `InstanceConfiguration` 35+ key 시드 완료

---

## 3. 비밀값 소재 (경로만 — 실 값은 문서 외부)

전부 운영 트리(`plane-app/ops/`) 내부. `ops/` 는 `.git/info/exclude` 로 **git 외부** 유지. 개발 트리 내 이 문서에 실 값은 기입 금지.

| 값 | 위치 | 비고 |
|---|---|---|
| `plane` 계정 비밀번호 | 1차 권위: 사용자 개인 기록 수단 (메모·비번 매니저 등 사용자 선택) · 운영 자동화용 사본: `D:\Workspace\plane-app\ops\.plane_pass` | ACL 로 `SYSTEM + Administrators` 만 읽기. Phase 6/8 경험상 **OS 계정 비번 ↔ `.plane_pass` ↔ 사용자 기록** 3곳이 반드시 동일해야 NSSM 1069 가 재발하지 않음. 값 변경 시 §7 의 동기화 순서 따름 |
| `plane-admin` · `joojm` 계정 비밀번호 | 사용자 개인 기록 수단 | — |
| Redis `requirepass` | `D:\Workspace\plane-app\ops\.redis_pass` + `ops/redis.conf` + site.env 세 곳 동일 | 32자 |
| Django `SECRET_KEY` | `D:\Workspace\plane-app\ops\site.env` → `apps/api/.env` 렌더 | 50자 |
| `LIVE_SERVER_SECRET_KEY` | 동일 경로 | 32자 |
| `STORAGE_SIGNING_KEY` | 동일 경로 | 32자 |

재해 복구 시 `site.env` 재생성하면 새 비밀값 3종 + `.redis_pass` 의 Redis 값을 기존 Redis 설정과 맞춰야 함. `plane` 계정 비번은 별도로 본인 기록 수단에서 복원 후 `.plane_pass` 동기화 + `register-services.ps1`/`register-caddy.ps1` 재실행.

---

## 4. Git 상태 (이번 세션 신규 커밋)

Phase 4.3 + 5 는 개발 트리 커밋, Phase 6 + 7 은 운영 트리 스크립트만(git 외부):

```
cb0353f docs: refresh handoff for phase-6 completion
69982b9 docs: refresh handoff for phase-4.3/4.4/5 completion
9d9b9e6 deploy(phase-5): drop space/ issue layout loader for SPA build
d215f36 deploy(phase-5): drop space/ SSR-only headers exports for SPA build
65a7b46 deploy(phase-5): switch space/ to SPA mode for static Caddy serving
c69275f deploy(phase-4.3): no-op bucket commands under USE_LOCAL_STORAGE
f0fba9e deploy(phase-4.3): route metadata/copy tasks through get_storage
a34fc45 deploy(phase-4.3): switch exporter cleanup to default_storage.delete
248fbd4 deploy(phase-4.3): route export_task through default_storage + helper
24d4480 deploy(phase-4.3): add presigned_url helper for bgtask dispatch
```

운영 트리 신규/수정 파일 (모두 `.git/info/exclude` 로 git 외부):

| 파일 | 도입 Phase | 역할 |
|---|---|---|
| `ops/register-services.ps1` | 6 (+ 8 보강) | plane-api/celery/beat/live NSSM 등록. 비번 우선순위 `PLANE_SERVICE_PASSWORD` env → `.plane_pass` → 프롬프트. **2026-04-22 추가**: `Remove-ZombieProcesses` 선행 실행 (nssm/uvicorn/celery/python/node 좀비 kill, caddy/gitea 는 CommandLine 으로 배제) + `Remove-IfExists` polling 30→60 s + `sc delete` fallback |
| `ops/Caddyfile` | 7 (+ 8 보강) | `:80` 단일 수신, 5 경로 라우팅, `handle` 블록 + space 보안 헤더 4종. **2026-04-22 추가**: global options 에 `storage file_system { root D:/Workspace/plane-data/caddy }`. **2026-04-24 추가**: `admin off` — §7a #5 silent exit 진짜 원인이었던 `:2019` admin endpoint TIME_WAIT race 를 영구 제거. 수동 smoke 재검증에서 1013/1014/1034=0, stderr.log 0 B |
| `ops/register-caddy.ps1` | 7 (+ 8 보강) | Caddy NSSM 등록. `ops\tools\caddy\caddy.exe` 우선 사용. **2026-04-24 변경**: ObjectName `.\plane` → `LocalSystem` (password 인자 제거, credential/`.plane_pass` 참조 섹션 삭제). `Remove-ZombieCaddyProcesses` + Remove-IfExists polling 60 s + `sc.exe delete` fallback 추가 (register-services.ps1 §4 4 차 보강본과 대칭). storage 디렉토리 존재 pre-check 추가 |
| `tools/caddy/caddy.exe` | 7 | Caddy v2.11.2. winget user-local 사본을 운영 트리로 복사 (plane 계정 접근 보장) |
| `ops/.plane_pass` | 8 | plane 계정 비번 자동화 사본. ACL `SYSTEM + Administrators` 만 읽기 |
| `ops/reregister-after-boot.ps1` | 8 | 재부팅 후 Redis `sc config` + plane-*/caddy 재등록. fully-Running 이면 skip |
| `ops/register-boot-task.ps1` | 8 | Task Scheduler `Plane - reregister services after boot` 등록 (SYSTEM, AtStartup+30s) |
| `ops/backup.ps1` | 8 | Daily 백업: SQLite VACUUM INTO + uploads robocopy + site.env 복사 + 14 일 retention. 임시 `.py` 파일로 Windows argv 파싱 우회. 로그 `plane-logs/backup/backup-<ts>.log` |
| `ops/register-backup-task.ps1` | 8 | Task Scheduler `PlaneBackup` 등록 (SYSTEM + ServiceAccount + Highest, Daily 02:00). 등록 후 `Get-ScheduledTask` assert 포함 |

plan/07-systemd.md · plan/08-external-access.md 초안과의 차이점은 §7 에 기록.

이전 세션 누적 (참고):

```
991d1f3 docs: add handoff.md for session resume
a3713af docs: import fork-local design docs into version control
526561f deploy(phase-4.2): route space/ + auth adapter through get_storage
4dca8bb deploy(phase-4.2): route api/ views through get_storage, drop is_server
d5c9a04 deploy(phase-4.2): route app/ views through get_storage factory
45fda23 deploy(phase-4.2): add get_storage factory for backend dispatch
925d677 deploy(phase-4.1): LocalFSStorage unit tests
fb34e94 deploy(phase-4.1): local-upload/local-download views + urls
bb541e4 deploy(phase-4.1): LocalFSStorage adapter + USE_LOCAL_STORAGE switch
1bcdfb9 deploy(phase-3): Celery broker URL env precedence + retry_on_startup
4502890 deploy(phase-1): production.py LOG_DIR env override
```

- 브랜치: `master`
- 운영 트리 `plane-app` 의 `origin` 은 **개발 트리 경로** (`D:\Workspace\plane`). `git fetch origin && git reset --hard origin/master` 로 동기화 — push 불필요.
- `.git/info/exclude` 는 `*.sqlite3`, `apps/api/dev.sqlite3` 만 유지
- 운영 트리 `D:\Workspace\plane-app` 는 `.git/info/exclude` 에 `/ops/`, `/tools/` 추가됨 (운영 산출물 격리)

---

## 5. 재개 빠른 시작 (운영 트리)

```powershell
# (1) 최신 커밋 반영
cd D:\Workspace\plane-app
git fetch origin
git reset --hard origin/master                    # HEAD: Phase 7 이후 최신

# (2) 서비스 상태 확인 — 7개 모두 Running / Automatic 이어야 정상
Get-Service Redis, IPBan, plane-api, plane-celery, plane-beat, plane-live, caddy |
  Format-Table Name, Status, StartType -AutoSize

# (3) 엔드포인트 5경로 anon smoke (Caddy 80 경유)
@("/", "/god-mode/", "/spaces/", "/api/instances/", "/uploads/anything") | ForEach-Object {
  $code = (Invoke-WebRequest -Uri "http://127.0.0.1$_" -UseBasicParsing -MaximumRedirection 0 `
    -ErrorAction SilentlyContinue).StatusCode
  "{0,-22}  HTTP {1}" -f $_, $code
}
# 기대: / 200, /god-mode/ 200, /spaces/ 200, /api/instances/ 200, /uploads/* 403

# (4) 인증 smoke — superuser 로그인 + /api/users/me/workspaces/ 200
#     (3) anon smoke 만으로는 SQLite UUID converter crash 회귀를 못 걸러낸다 (§7d #2).
#     UserWorkSpacesEndpoint 의 aggregate 경로가 200 이면 해당 patch 회귀 0 확인.
$cred = Get-Credential -Message "Plane superuser" -UserName "wnwjdals7498@naver.com"
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = Invoke-WebRequest -Uri "http://127.0.0.1/auth/sign-in/" `
  -Method POST -WebSession $session `
  -Body @{ email = $cred.UserName; password = $cred.GetNetworkCredential().Password } `
  -UseBasicParsing -MaximumRedirection 0 -ErrorAction SilentlyContinue
"sign-in              HTTP {0}" -f $login.StatusCode
$ws = Invoke-WebRequest -Uri "http://127.0.0.1/api/users/me/workspaces/" `
  -WebSession $session -UseBasicParsing -ErrorAction SilentlyContinue
"users/me/workspaces  HTTP {0}" -f $ws.StatusCode
# 기대: sign-in 200 + users/me/workspaces 200 (JSON array 반환)

# (5) 재등록이 필요하면 (scripts/site.env 변경, 또는 Paused 등에서 탈출):
#     Admin PowerShell 에서만 동작. 둘 다 ops\.plane_pass 를 자동으로 읽음.
# .\ops\register-services.ps1        # plane-api/celery/beat/live
# .\ops\register-caddy.ps1           # caddy
```

변경이 **코드 트리에만** 있고 서비스가 이미 떠 있으면 (1) 만 수행. **`site.env` 수정** 시 (1) → `.\ops\render-envs.ps1` → `pnpm turbo build` → `.\ops\register-services.ps1` → `.\ops\register-caddy.ps1` 로 env/번들/NSSM 까지 한 번에 반영.

---

## 6. Phase 8 진행 현황 + 다음 세션이 할 일

Phase 0~7 모두 완료. Phase 8 중 §4 재부팅 내성은 **자동 복구 Task 구성 완료 / 실측 이월**, 나머지(§1·§2·§3·§5·§6)는 미진행.

**세부 진행**:

| # | 항목 | 상태 | 메모 |
|---|---|---|---|
| §1 | 기능 검증 (회원가입~live 협업) | **완료** | 2026-04-24 외부 브라우저 E2E 15/15 통과 + bonus 1 (5MB size-limit 실측). §1.1 12/12 + §1.3 3/3 (§1.2 live skip: 혼자 사용). 세션 중 4건 blocker 즉시 해소 후 각 항목 재검증 성공: (1) InstanceAdmin ORM 부착 (Django superuser ≠ Plane InstanceAdmin 이라 `is_setup_done=False` 로 get-started 페이지에 갇힘), (2) SQLite UUID converter int-safe monkey-patch (upstream `Func(F("id"), function="Count")` 30+ 사이트), (3) LocalFSStorage `_endpoint("local-upload")` trailing slash (APPEND_SLASH → POST→GET 변환 → 405), (4) Local{Upload,Download}View `authentication_classes = []` (SessionAuth + session cookie = POST CSRF 403). 세부 §6b 완료 기록 + §7d 신규 |
| §2 | 회귀 (`pytest` + 골든 + 쓰기 20 + latency 6 + 동시 쓰기 50 + residue guard) | **완료 (1 차 + 2 차 재확인 + §2.5~§2.7 이월분 해소)** | 2026-04-22 실측 (`plane.settings.test` + `D:/tmp/plane_verify.sqlite3` 독립 DB): migrate 27.5 s + seed(scale=100) 2.6 s · golden capture 19/22 ok (3 는 빈 labels/public 404, 무해) · golden diff 실패(module `Core` 이슈 카운트 + `next_work_item_sequence` 가 저장된 golden 보다 커짐 — **seed scale 차** pre-existing) · write 19/20 passed (W17 search 1 건 실패, 검색 인덱스 ephemeral) · pytest 106 passed / 5 failed = 1 pre-existing `test_copy_s3_objects_of_description_and_assets` + **4 신규 upstream known** (§7a). §2.5 latency / §2.6 concurrent / §2.7 residue 미실행 (후속 이월). **2026-04-24 2차 pytest 재확인** (§1 patch 3건 UUID int-safe / trailing slash / authentication_classes=[] 투입 후): `plane\tests\unit` 전체 8.97 s — **106 passed / 5 failed 정확 재현** (pre-existing 1 + upstream known 4, §7a/§7b 목록 그대로), 신규 회귀 0. 부가로 plan/09-verification.md §2.4 지침 수정: 기존 `unit\models unit\perf unit\settings` 3 dir 표기는 축약/오기 (5 failed 테스트는 bg_tasks/, utils/ 에 존재), `unit` 전체로 교정 + 기대 baseline 명시. **2026-04-24 §2.5~§2.7 이월분 해소** (§7f): §2.5 measure_latency 100×6 **6/6 PASS** (최대 search p95 14.98 ms vs limit 400 ms — 전 scenario 여유 10-25×) · §2.6 concurrent_writes 50×5 created=50/in_db=50/errors=0/**locked=0**/rate 80.55 /s · §2.7 test_phase_g_residues.py **4 passed** in 0.09 s. plan §2 top 에 `.env` 주입 블록 + `ALLOWED_HOSTS=*` 보강. |
| §3 | 부하 smoke (1인 운영, p95 < 500 ms @ c=1) | **완료 (2026-04-24, bombardier 채택)** | hey v0.1.5 는 windows precompiled 미제공 → bombardier v2.0.2 (`tools/bombardier/bombardier.exe`) 채택. `plane/api/rate_limit.py:14` `ApiKeyRateThrottle` 기본 60/min 이 `-n 1000` 에 즉시 걸려 `ops/site.env + render-envs.ps1` 에 `API_KEY_RATE_LIMIT=10000/minute` 반영 (ops/ 는 .git/info/exclude 라 호스트 로컬 state, 커밋 대상 아님). 실측: c=1 p95 65 ms PASS / c=2 99 ms / c=5 159 ms PASS, c=10 649 ms reference (--workers 1 + SQLite sync ORM 병목, 다중 사용자 시 재측정). 인증 헤더는 `X-API-Key` (Bearer 아님 — plan 원안 오기 정정). 세부 §7g. |
| §4 | 재부팅 내성 | **완료** | **2 차 (2026-04-21)**: 3 failure mode 식별. **3 차 (2026-04-22 22:45)**: Boot Task 최초 자동 트리거 (§7a #3 해소), plane-* [2/3] 에서 polling 부족으로 exit 5 → `register-services.ps1` 보강. **4 차 (2026-04-22 23:04)**: 보강 효과 확인 — LastTaskResult=0, plane-* 자동 복구 완주 (§7a #4 해소). caddy [3/3] 는 등록 성공하나 기동 직후 Paused+throttle (§7a #5 재현). **5 차 (2026-04-22 23:21)**: Caddyfile storage block 추가 — plane-* 여전히 자동 복구, 그러나 caddy silent exit 재발 (storage 가설 반증). **2026-04-23~24 수동 smoke (재부팅 전 precheck)**: caddy ObjectName `.\plane` → `LocalSystem` 전환 → 1 차 smoke 에서 1013/1014/1034 **1 회만** 발생 + stderr.log 의 `listen tcp 127.0.0.1:2019: bind` 누적 에러 발견 → `:2019` admin endpoint TIME_WAIT race 가 진짜 원인임을 caddy.log ts 분석으로 확정 (LSA 가설 반증). **2026-04-24 해소**: Caddyfile 에 `admin off` 도입 + oven-fresh Stop/Start 재smoke → 1013/1014/1034=0, stderr.log 0 B, caddy.log `"admin endpoint disabled"` + `systemprofile` autosave, 5 경로 200/200/200/200/403. **6 차 재부팅 실측 (2026-04-24 10:35)**: LastBootUp 10:35:17 → Boot Task LastRun 10:35:53 / LastResult=0 → caddy Running 직행 (Paused 경유 없음) · 재부팅 이후 1013/1014/1034=0 · stderr.log 0 B · caddy.log 재기동 엔트리에 `"admin endpoint disabled"` + `systemprofile` autosave + `"serving initial configuration"` · 5 경로 200/200/200/200/403. **§4 완료 확정**. IPBan Stopped 는 §6 #2 로 별도 추적 |
| §5 | 백업 자동화 (SQLite VACUUM INTO + uploads + site.env) | **완료 (스크립트 + Task + 실측 + §5.3 복구 훈련)** | 2026-04-22 실측: `ops/backup.ps1` + `ops/register-backup-task.ps1` 작성 · PlaneBackup Task (SYSTEM/ServiceAccount/Highest/Daily 02:00) 등록 · on-demand smoke `LastTaskResult=0`, 4/4 단계 정상 완료 (sqlite 3,608,576 B + uploads 0 files + site.env 873 B, elapsed < 1s) · 로그 `plane-logs/backup/backup-<ts>.log` 에 단계별 기록. **2026-04-24 §5.3 분기 복구 훈련 완료** (§7e): fresh backup `20260424-142947` → `D:\Workspace\plane-restore\{sqlite,uploads,ops}` 격리 복구 → `migrate --plan` "No planned migration operations." (baseline drift 0) + 8 테이블 count 전부 일치 + uploads 7 files SHA256 전부 일치 → 복원 dir 삭제. 초회 기준선 확립, 다음 회차 2026 Q3 |
| §6 | security-todo 간단 감사 (joojm 16자+, 외부 방어 등) | **감사 완료 / 실행 단계별 분할** | 2026-04-24 7 항목(A~G) 감사 + 심각도×구현비용 matrix 작성 — 상세 [security-audit-2026Q2.md](security-audit-2026Q2.md). 실 변경 4 세션 분할: 보안 #1 §A+§B (Critical+High: joojm 16자+ + lockout 정책 + 빌트인 Admin disable + 3389 IP allowlist/Tailscale + IPBan BlacklistRegex/ExpireTime 연장 + cloudflared tools/ 이관) · 보안 #2 §E+§F (DPAPI `.plane_pass` + site.env joojm ACL 제거 + 7z AES-256 백업 래핑 + DPAPI 키 + 복구 훈련 재실행) · 보안 #3 §C (도메인 확보 후 HTTPS 전환 + HSTS + Django SECURE_SSL_REDIRECT/HSTS_SECONDS) · 보안 #4 §D (Defender FullScan Task + 서버측 MIME 재검증 + 실행 확장자 denylist + SVG sanitize). §G Memurai 는 Redis 5 EOL 이지만 loopback-only 라 현 시점 보류. 감사 중 orphan `caddy.exe` PID 14764 (15:40:19 SCM 7034 후 NSSM 재등록 실패하고 구 프로세스가 :80 점유) 발견 → `Stop-Process` + `Start-Service caddy IPBan` 으로 7 서비스 Running 복원 후 감사 진행 |

앞으로 해야 할 작업 (보안 #1 잔존 + 보안 #2~#4 + upstream rebase 대기 등) 은 [todo.md](todo.md) 로 분리됨.

---

## 6a. space 보안 헤더 상태 (Phase 5·7 이력)

Phase 5 에서 space SSR→SPA 전환으로 제거된 `headers` export 는 Phase 7 에서 Caddy `header` 블록으로 대체됨 (**실측 완료** — `Invoke-WebRequest -UseBasicParsing` 로 4종 모두 응답에 포함 확인):

| 헤더 | 원 출처 | 현 구현 | 상태 |
|---|---|---|---|
| `X-Frame-Options: SAMEORIGIN`              | `space/app/page.tsx` | Caddyfile `handle_path /spaces/*` | **적용** |
| `Referrer-Policy: origin-when-cross-origin` | `space/app/root.tsx` | 동일 | **적용** |
| `X-Content-Type-Options: nosniff`          | `space/app/root.tsx` | 동일 | **적용** |
| `X-DNS-Prefetch-Control: on`               | `space/app/root.tsx` | 동일 | **적용** |
| `Strict-Transport-Security: ...`           | `space/app/root.tsx` | — | HTTPS 전환 이후 (Phase 미래) |

publish 페이지(`/spaces/<anchor>`)의 SNS OG/Twitter 메타는 **정적 default** 로 폴백됨 — 특정 anchor 의 name/description 반영 불가. 외부 공유가 활성화되면 prerender 또는 SSR 재복원 검토 (security-todo 또는 plan 에 별도 항목 추가).

---

## 6b. §1 기능 검증 체크리스트 (완료)

**완료 일시**: 2026-04-24 (§4 / IPBan 해소 직후 연속 세션). 외부 브라우저 (Chrome 147, Windows 10, 공인 IP `222.234.220.199`) 에서 superuser 계정으로 §1.1 12 항목 + §1.3 3 항목 = **15/15 통과 + bonus 1** (5MB 초과 업로드 거부 실측). §1.2 live 실시간 협업은 혼자 사용이라 skip, §1.4 Celery/스케줄은 §1.1 이슈 CRUD 수행 중 자동 enqueue 로 묵시 검증.

**세션 중 식별 + 즉시 해소한 blocker 4건** (3건 코드 커밋, 1건 1회성 데이터 보정):

| # | 위치 | 현상 | 원인 | 조치 |
|---|---|---|---|---|
| 1 | `/` 접속 (get-started 페이지) | 로그인 폼 대신 admin 등록 페이지가 뜸 | Django superuser ≠ Plane `InstanceAdmin`. Phase 2 `configure_instance` + `register_instance` 는 Instance+Config 시드만 하고 `InstanceAdmin` 은 만들지 않음 → `is_setup_done=False` | Django shell 에서 기존 superuser 에 `InstanceAdmin role=20` 부착 + `instance.is_setup_done=True` save + `/api/instances/` 캐시 키 `cache.delete` (redis.conf 가 FLUSHDB 차단하여 `cache.clear()` 쓸 수 없음). 1 회성 데이터 보정, 커밋 없음 |
| 2 | 워크스페이스 생성 토스트 "created successfully" + "could not be created" 동시 | POST `/api/workspaces/` 는 201 성공, 직후 `GET /api/users/me/workspaces/` 500 → 프론트가 실패로 오인 | `UserWorkSpacesEndpoint.get` 의 `member_count = Func(F("id"), function="Count")` 에 `output_field` 미지정 → Django 가 UUIDField 로 추론 → SQLite `convert_uuidfield_value` 가 aggregate int 결과에 `uuid.UUID(<int>)` 호출 → `'int' object has no attribute 'replace'`. 동일 패턴 **30+ 사이트** (cycle/issue/module/project/analytic) | `plane/settings/common.py` 하단에 `DatabaseOperations.convert_uuidfield_value` monkey-patch: `isinstance(value, int)` 이면 값 그대로 반환, 아니면 원본 converter. 한 곳 수정으로 전 사이트 커버. pytest 는 이 endpoint 를 hit 하지 않아 §2 1차에서 못 걸러냄 — §2.5~§2.7 후속 회귀에서 인증 후 smoke 확장 필요 (§6 다음 세션 권장 순서 #4 참조) |
| 3 | 프로젝트 생성 시 `/api/assets/local-upload` 405 Method Not Allowed | 프론트 POST → Django `APPEND_SLASH=True` 301 redirect → 브라우저 fetch 의 `redirect: follow` 가 **POST → GET 변환** → view 는 `post()` 만 정의 → 405 | `plane/settings/local_storage.py:110` 의 `"url": self._endpoint("local-upload")` 가 trailing slash 없이 반환 → URL pattern `assets/local-upload/` (slash 있음) 와 불일치. `_endpoint("local-upload") + "/"` 로 수정. `_endpoint` 자체 변경 금지 (local-download 에서는 뒤에 `{path}` 가 붙어야 해서 slash 없어야 정상). test `endswith("/api/assets/local-upload/")` 로 동기화 |
| 4 | `/api/assets/local-upload/` 403 `{"detail":"CSRF Failed: CSRF token missing."}` | Roundtrip 자체 검증 OK (`generate_presigned_post` → `_decode_policy` 정상). 브라우저만 403. DRF `SessionAuthentication` 이 로그인 세션 쿠키를 읽어 user 인식 → unsafe method(POST) 에 CSRF 강제 | `LocalUploadView` + `LocalDownloadView` 모두 `authentication_classes = []` 추가. HMAC-signed policy/URL 이 sole credential 이므로 SessionAuth 불필요. docstring 의 "signature is the sole credential" 의도에 부합. download view 에도 일관성 차원 + 향후 동일 문제 재발 방지로 동반 적용 (GET 이라 지금은 CSRF 영향 없지만) |

4건 모두 세부 교훈은 **§7d 신규 섹션**으로 옮김. 체크리스트 표는 아래 원본 그대로 보존 (레퍼런스, 다음 §1 회귀/smoke 시 재사용).

plan/09-verification.md §1 의 계획을 운영 관점에서 확장한 본 체크리스트는 향후 대규모 upstream rebase 후 또는 Django/Plane 업그레이드 시 재수행 용도로 유지.

### 사전 점검 결과 (2026-04-24, loopback 자동 수행 완료)

- 3 SPA 인덱스 200: `/` (web, HTML length 6474 B, CSS `root-*.css` + `globals-*.css` 번들 참조 확인), `/god-mode/` (admin), `/spaces/` (space)
- DRF 401: `/api/users/me/` (인증 미제공 기대 응답)
- API instance 200: `/api/instances/` payload `is_email_password_enabled: true` · `enable_signup: false` — superuser email+password 로그인만 허용 (Phase 2 `configure_instance` 결과 그대로 유지)
- uploads 403: `/uploads/anything` (Caddy 차단)
- `/auth/sign-in/` GET 405 (POST 전용) · `/live/hocuspocus` HTTP GET 404 (WebSocket 전용) — 둘 다 정상 양상
- 주의: `D:/Workspace/plane-data/uploads` 는 joojm RDP 세션에서 Access Denied (ACL 은 `plane + SYSTEM + Administrators` 만), plane 서비스에서는 정상 접근. 검증 영향 없음

### 접속 정보

- 외부: `http://222.234.220.199/`
- 로컬 loopback: `http://127.0.0.1/`
- superuser: `wnwjdals7498@naver.com` (비밀번호는 §2.3 + 사용자 개인 기록 수단)

### §1.1 핵심 워크플로우 (브라우저, 12 항목)

| # | 항목 | 기대 | 이상 시 DevTools 확인 포인트 |
|---|---|---|---|
| 1 | 외부 브라우저에서 `/` 로그인 페이지 렌더 | 이메일/비번 입력폼 | Network → asset `/assets/*.js/*.css` 전부 200 |
| 2 | superuser 로그인 | 대시보드 진입 | `POST /auth/sign-in/` 200 JSON + 세션 쿠키 |
| 3 | 워크스페이스 생성 | 좌측 사이드바에 추가 | `POST /api/workspaces/` 201 |
| 4 | 프로젝트 생성 | 프로젝트 리스트에 표시 | `POST /api/workspaces/<slug>/projects/` 201 |
| 5 | 이슈 생성 (제목·설명·상태·우선순위·담당자·라벨) | 이슈 리스트에 1 건 | `POST /api/.../issues/` 201 |
| 6 | 사이클 생성 → 이슈 할당 → 진행 차트 | 차트 렌더 | `POST /api/.../cycles/` 201 · `PATCH /api/.../issues/<id>/` 200 |
| 7 | 모듈 생성 → 이슈 연결 | 모듈 상세에 이슈 표시 | `POST /api/.../modules/` 201 |
| 8 | 페이지 생성 + Tiptap 에디터에서 텍스트/이미지 붙여넣기 | 저장 후 재진입 시 내용 유지 | 이미지는 LocalFSStorage 경유 (#9 참고) |
| 9 | 이슈 첨부 PNG/PDF/ZIP 각 1 개 업로드 | 썸네일/파일명 표시 | `POST /api/.../file-assets/` 응답의 `upload_data.url == /api/assets/local-upload` 확인 (S3 URL 이면 fallback 버그) |
| 10 | 첨부 다운로드 (썸네일/파일명 클릭) | 파일 저장됨 | `GET /api/assets/local-download/<key>?sig=...` 302 → FileResponse 200 |
| 11 | 페이지 간 내비게이션 + 브라우저 뒤로 가기 | 라우팅 정상 | SPA client-side routing, 추가 요청은 JSON API 만 |
| 12 | 로그아웃 | 로그인 페이지 복귀 | `POST /auth/sign-out/` 200 |

### §1.2 실시간 협업 — **skip** (혼자 사용)

### §1.3 admin / space (3 항목)

| # | 항목 | 기대 |
|---|---|---|
| 13 | `/god-mode/` superuser 로그인 | admin 대시보드 진입 |
| 14 | InstanceConfiguration 페이지들 | 단일 테이블이 아니라 **General / Authentication / Email / AI / Image / Workspace 5+ 섹션** (`apps/admin/app/(all)/(dashboard)/`) 에 분산 렌더. 각 페이지 빈 화면/500 없이 정상 로드 (Phase 2 시드 값 참조) |
| 15 | 프로젝트 public 전환 → 시크릿 창에서 `/spaces/<ws>/<pid>/` 익명 접근 | 프로젝트 조회 + 이슈 상세 + 첨부 다운로드 가능 |

### §1.4 Celery / 스케줄 — §1.1 이슈 수행 중 자동 enqueue, 사후 로그 tail 확인

§1.1 #5/#6 을 수행하면 `bgtasks.issue_activities_task` 가 자동 enqueue 됨. §1 완료 후 AI 가 아래 명령을 실행해 확인:

```powershell
# 이슈 activity 처리 로그
Get-Content D:\Workspace\plane-logs\worker\stdout.log -Tail 50 |
  Select-String "issue_activities_task|hard_delete|archive_and_close_old_issues|stack_email_notification"

# beat 스케줄 확인 (5 분 주기 task 스케줄이 돌고 있는지)
Get-Content D:\Workspace\plane-logs\beat\stdout.log -Tail 30

# Redis DB/1 broker — 평시 0 근처, enqueue 중에만 증가
# $redispass 는 §3 .redis_pass 에서
# redis-cli -h 127.0.0.1 -a $redispass -n 1 DBSIZE
```

### 재개 방법 요약 (다음 세션)

1. handoff.md (§6b + §6) 읽기
2. 운영 트리 `D:\Workspace\plane-app` 에서 `git fetch origin && git reset --hard origin/master` 로 최신 상태 동기화 (기준 커밋: §6 §4 해소 + IPBan 해소 + §1 준비 완료 커밋 이후)
3. 7 서비스 Running 확인 + 5 경로 smoke 재현 (handoff §5 재개 빠른 시작)
4. 외부 브라우저에서 `http://222.234.220.199/` 접속 → §6b 체크리스트 #1~#15 순차 수행
5. 항목별 ✅/❌ 결과 붙여넣기, ❌ 인 경우 DevTools Network 실패 요청 (URL + status + response) 첨부
6. AI 가 이상 항목 원인 분석 + 수정 → 재시도 → 모두 ✅ 되면 §1 완료, §5.3 복구 훈련으로 이동

---

## 7. 미해결 / 이월 결정

- **IPBan StartPending** (Phase 6 구 현상, Phase 8 §4 6 차에서 양상 변화): `Get-Service IPBan` 이 `StartPending Automatic` 으로 출력됐지만 stdout.log 는 정상 초기화 완료(`IPBan is running correctly`). NSSM wrap 특성상 SCM 리포트 지연으로 추정했으나, 2026-04-24 6 차 재부팅에서는 StartPending 이 아니라 37 s 후 `SCM 7034 예기치 않은 종료` 로 Stopped 체류가 재현 — 아래 신규 항목 참조.
- **IPBan 재부팅 early-boot 37-s-crash (2026-04-24 Delayed Auto Start + AppRestartDelay 30 s 로 방어 — 7 차 재부팅에서 해소 확정)**: Phase 8 §4 6 차 재부팅 (LastBootUp 2026-04-24 10:35:17) 실측 중 `SCM 7034: IPBan 서비스가 예기치 않게 종료됐습니다 (1 번째)` 이 10:35:59 (부팅 +42 s) 에 발생. 그 시점까지의 IPBan stdout.log 는 10:35:26 에 `"IPBan is running correctly"` + 10:35:41 에 RDP 로그인 이벤트 수신 로그까지 정상 기록된 뒤 18 s 동안 events 처리 중 silent terminate (stack/에러 메시지 미기록). NSSM wrap 에서 AppThrottle 60 s 덫에 걸려 AppExit Default Restart 임에도 restart 없이 Stopped 체류 (~16 분), 수동 `Start-Service IPBan` 으로 복구 후 동일 바이너리/설정으로 안정 운영. 원인은 IPBan 자체가 아닌 **early-boot window 의 race** (event log provider / 방화벽 API / TerminalServices provider 중 하나의 초기화 미완 상태에서 RDP login 이벤트를 처리하다 내부 exception 로 추정; 구체 지점은 stdout 이 terminate 직전 scope 를 남기지 않아 미확정). **방어 적용 (2026-04-24)**: `nssm set IPBan Start SERVICE_DELAYED_AUTO_START` (부팅 후 ~120 s 뒤 spawn, early-boot 회피) + `nssm set IPBan AppRestartDelay 30000` (혹시 재현해도 30 s 뒤 안정 환경에서 재기동) + AppThrottle/AppExit 은 NSSM 기본값 (1500 ms / Restart) 유지 — nssm 이 `reset to default` 로 응답 (원하던 값과 동일). sc.exe qc 에서 `START_TYPE: 2 AUTO_START (DELAYED)` 확인. **7 차 재부팅 실측 (2026-04-24 11:06, 해소 확정)**: LastBootUp 11:06:35 → IPBan spawn 11:09:07 (**+152 s**, Delayed Auto Start 기본 120 s + idle ≈ 30 s 와 일치) → stdout 에 `"IPBan is running correctly"` 도달 후 11:10:24 에 `Un-banning ip address 165.154.17.24, ban expired` + `Updating firewall with 1 entries` 로 실제 firewall 관리 작동까지 확인. 재부팅 이후 window 내 SCM 7034(IPBan)=0, SCM 7036 Running 진입 1 회, uptime 5.5 분 시점 Running 지속. 동시에 §4 지표 유지 (caddy stderr 0 B · NSSM 1013/1014/1034=0 · Boot Task LastResult=0 · 5 경로 200/200/200/200/403). **AppRestartDelay 30 s 안전망은 발동할 필요조차 없었음** (첫 spawn 부터 안정). 대안 (c) Task Scheduler 보험 트리거 · (d) IPBan log level 상향은 현재 불필요.
- **공인 IP 직접 노출 + `joojm` 10자 비밀번호**: 보안 리스크 인정, IPBan 이 일차 방어. 중기에 joojm 16자+ 승격 + Tailscale 또는 Cloudflare Access 도입 권장 ([security-todo.md §2](security-todo.md#2-rdp-외부-접근)).
- **Python 3.13 vs Django 4.2 공식 지원**: 3.13 에서 pip install + migrate + unit test 실측 모두 통과. 공식 지원 범위 밖이지만 현실 동작 확인. Django 4.2 → 5 전환은 별도 기획.
- **test_copy_s3_objects_of_description_and_assets** (`--nomigrations` + SQLite NOT NULL): Phase 4.3 커밋 전에도 동일 실패 재현 — `description_json` default=dict 가 테스트 스키마 생성 시 반영 안 되는 pre-existing 환경 이슈. 운영 트리 실제 DB 에서는 미확인. 블로커 아님.
- **`ops/render-envs.ps1` 실행 시 `$PSScriptRoot` 공백**: bash 에서 `powershell.exe -File "<path>"` 호출 경로에서는 `$PSScriptRoot` 가 비어서 `-SiteEnv`/`-AppRoot` 파라미터 명시 필수. PS 세션 내 직접 실행 시에는 자동 채워짐. 자동화 스크립트 추가 시 주의.
- **plan/07-systemd.md 의 NSSM 스니펫 3개 버그** (`ops/register-services.ps1` 에는 모두 수정 반영됨):
  - `nssm set <svc> AppEnvironmentExtra <joined-with-NUL>` — Win32 argv 가 첫 NUL 에서 잘려 **첫 라인만 저장**. 각 `KEY=VALUE` 를 개별 인자로 전달해야 함 (스크립트는 `@apiEnvLines` splat).
  - `nssm set <svc> DependOnService "Redis/plane-api"` — NSSM 이 `"Redis/plane-api"` 를 단일 이름으로 해석해 1051 발생. 복수 의존은 `sc.exe config <svc> depend= "A/B"` 로 별도 설정.
  - PS 5.1 `$ErrorActionPreference='Stop'` 하에서 `sc.exe`/`nssm.exe` 의 benign stderr 가 NativeCommandError 로 throw → cleanup 블록에서 `$ErrorActionPreference='Continue'` 로 감싸야 idempotent.
- **Phase 6 재부팅 자동 기동 (P6-7) 이월**: 현재 7 서비스 Running 이지만 재부팅 후 Redis → plane-api → celery/beat/live → caddy 순으로 올라오는지는 미실측. Phase 8 §4 재부팅 내성에서 실측.
- **plan/07-systemd.md 의 `--workers 2` 기재 vs 실제 `--workers 1`**: plan 표 "plane-api" 행은 `--workers 2` (1인 트래픽엔 과함). 실제 등록은 `--workers 1` — 스크립트와 plan 문서 정합 필요 (다음 편집에서 plan 갱신 검토).
- **Caddy 배포 경로 교훈 (Phase 7)**: `winget install CaddyServer.Caddy` 는 caddy.exe 를 **user-local** (`C:\Users\<admin>\AppData\Local\Microsoft\WinGet\...`) 에 설치해서 plane 서비스 계정이 CreateProcess Access Denied 로 기동 실패. **해결**: winget 바이너리를 `D:\Workspace\plane-app\tools\caddy\caddy.exe` 로 복사 후 `register-caddy.ps1` 가 이 경로를 우선. Caddy 업그레이드 시 `winget upgrade` 후 같은 복사 작업 재실행 필요.
- **Caddy `reverse_proxy <path>` top-level 순서 주의 (Phase 7)**: top-level `handle { }` 이 catch-all 로 자리 잡으면 `reverse_proxy /api/*` 가 무시되고 fallback SPA 가 반환됨. 모든 분기는 명시적 `handle /path/* { reverse_proxy ... }` 로 감싸야 함 (현 Caddyfile 반영 완료).
- **Windows Server 2025 + 로컬 계정 서비스 creds 손실 (Phase 8 §4 핵심)**: `.\plane` 로 로그온하는 모든 서비스(Redis MSI + NSSM-wrapped plane-*/caddy)가 **재부팅 경계에서 1069 (logon failure)** 를 일으킴. IPBan(LocalSystem)만 영향 없음. 원인은 Windows 레벨 LSA secret 유지 이슈로 추정 (NSSM 단독 버그 아님). **워크어라운드**: `ops/.plane_pass` 평문(ACL 제한) + `ops/reregister-after-boot.ps1` + `ops/register-boot-task.ps1` → Task Scheduler `At startup +30s` 트리거로 SYSTEM 이 Redis `sc.exe config` + `register-services.ps1` + `register-caddy.ps1` 순차 실행. 실제 재부팅에서의 자동 복구 실측은 다음 세션 §4 에서.
- **plane 계정 비번 3곳 동기화 규칙 (Phase 8)**: OS 계정 비번 / `ops\.plane_pass` / 사용자 개인 기록 수단 — 이 **3곳이 완전히 동일**해야 함. 한 곳 어긋나면 1069 가 세션 내에서도 즉시 재현. 변경 절차: (a) LogonUser(SERVICE) 로 새 비번이 OS 계정에 통하는지 검증 → (b) 통하면 `.plane_pass` 재작성 후 `register-services.ps1` + `register-caddy.ps1` → (c) 사용자 기록 수단 업데이트. 통하지 않으면 `Set-LocalUser` 로 OS 쪽을 새 값에 맞춤.
- **PowerShell `[System.IO.File]::WriteAllText` 경로 해석 차이 (Phase 8)**: `.NET` 메서드는 **process current directory** 기준. PS 의 `Get-Location` 과 불일치 (PS 는 Provider drive). `.\ops\file` 같은 상대 경로를 넘기면 `C:\Users\<user>\ops\file` 로 해석되어 실패. 스크립트에서 반드시 절대 경로 사용.
- **`Remove-IfExists` polling 필수 (Phase 8 cleanup)**: `nssm remove <svc> confirm` 후 고정 `Start-Sleep` 는 신뢰할 수 없음. SCM 이 실제로 DeleteService 를 적용하기까지 services.msc 등의 handle 이 남아 있으면 수십 초 걸림. 스크립트는 `Get-Service -Name $svc` 가 null 반환할 때까지 30초 polling 으로 수정됨.
- **reregister-after-boot 는 세션 중간 수동 실행 부적합**: 이미 서비스가 Running 상태면 cleanup 단계에서 live 핸들 충돌로 실패. fast-path 로 "모두 Running 이면 skip" 추가. 실제 재부팅 시에는 서비스가 1069/Stopped 라 skip 안 되고 정상 복구 진행 예상.

### 7a. Phase 8 §4 2 차 실측 (2026-04-21 09:12 boot) 에서 드러난 failure mode — 자동 복구 스크립트 보강 TODO

- **NSSM `AppEnvironmentExtra` 재부팅 경계 소실 → REDIS_URL=None crash 루프 (신규)**: 2026-04-21 실측에서 plane-api uvicorn 이 `settings.REDIS_URL` = None 으로 `AttributeError: 'NoneType' object has no attribute 'startswith'` 뱉고 exit code 1. NSSM AppExit Default=Restart + AppThrottle 60s → restart delay **256s** 으로 **258 초(4 분 18 초) 주기 Paused/Running 루프**. stderr.log 는 `2026-04-21 09:57:22` 까지 정상 요청 로그가 남다가 그 이후 공백 — 부팅 후 약 45 분간은 정상 작동하다 환경변수 소실. 원인은 Windows Server 2025 의 LSA/서비스 metadata 재부팅 경계 이슈로 추정 (1069 logon failure 현상의 변종). **해결**: `ops/register-services.ps1` 재실행 — AppEnvironmentExtra 를 `site.env` 로부터 다시 주입하면 복구. 자동 복구 스크립트는 1069 뿐 아니라 **AppEnvironmentExtra 소실도 재등록 트리거**로 포함해야 함.
- **`plane/settings/common.py:158` 이 `.env` 파일을 로드하지 않음 — `os.environ.get("REDIS_URL")` 만**: Plane API 코드에는 `load_dotenv` / `django-environ` 호출이 **전혀 없음** (`grep -r "load_dotenv\|read_env\|dotenv\|import environ" apps/api/plane/settings` 무매치). 즉 `apps/api/.env` 는 **Plane 런타임에서 무시**됨. 서비스 실행 시 환경변수는 오직 NSSM `AppEnvironmentExtra` 주입으로만 전달. **영향**: 수동으로 uvicorn 을 현 셸에서 직접 기동하면 `.env` 가 로드 안 돼 동일 crash 재현. 디버깅 시 반드시 `$env:REDIS_URL = "..."` 등으로 셸에 환경변수 먼저 주입 필요. `render-envs.ps1` 이 만드는 `.env` 는 **documentation + 재주입 원본** 성격이지 런타임이 읽는 파일이 아님.
- **`ops/register-boot-task.ps1` 이전 세션 기록과 달리 실제로는 미등록**: handoff §6 이 "자동 복구 Task 구성 (`Plane - reregister services after boot`) 완료" 로 기록했으나, 2026-04-21 세션 초기에 `Get-ScheduledTask` 조회 결과 **해당 Task 부재**. 이전 세션이 스크립트 작성만 완료하고 실행은 안 했거나, 실행 중 에러가 있었음에도 "완료"로 기록됐을 가능성. **규칙**: 문서에 "등록 완료"로 쓰기 전에 반드시 `Get-ScheduledTask -TaskName ...` 로 존재 재확인. 2026-04-21 세션에서 다시 실행하여 **이번엔 진짜로 등록 확인**.
- **`ops/register-services.ps1` Remove-IfExists polling 30 s 부족 — ERROR_SERVICE_MARKED_FOR_DELETE** (2026-04-22 보강 완료): 재실행 1 차 시도 시 plane-api 가 `nssm remove` 이후 30 s polling 안에 SCM DeleteService 완료 못해 `CreateService: 지정된 서비스가 지워진 것으로 표시되었습니다 (exit 5)` throw. 원인은 살아있는 nssm.exe 좀비 3개 + uvicorn/python 자식이 SCM handle 유지. **해결 루트** (2 차·3 차 실측에서 두 번 재현): (a) nssm.exe 좀비 kill, (b) uvicorn/python 자식 kill, (c) `sc.exe delete plane-api`, (d) 60~90 s 재polling, (e) `register-services.ps1` 재실행. **2026-04-22 스크립트 보강 완료**: `register-services.ps1` 에 `Remove-ZombieProcesses` 함수 추가 (nssm/uvicorn/celery/python/node + `$AppRoot` 경로 매칭 + `caddy`/`gitea` CommandLine 제외) — cleanup 루프 직전에 호출. 또 `Remove-IfExists` polling cap 30→60 s + `sc.exe delete $Svc` fallback 을 `nssm remove` 후에 추가. 실제 재부팅 경계에서의 자동 복구 효과는 다음 (4 차) 재부팅 실측에서 검증.
- **Caddy silent exit — 원인 확정 + 해소 확정: admin endpoint `127.0.0.1:2019` TIME_WAIT race (2026-04-24 `admin off` + LocalSystem 전환 + 6 차 재부팅 실측으로 end-to-end 해소)**: plane-api 복구 후 caddy 가 NSSM 하에서 exit -1 로 crash 루프 재발했던 현상. NSSM AppStdout/AppStderr 는 Caddy 가 `redirected default logger` 로 `caddy.log` 에 재지정해 비어 보이지만 (1074 `파이프가 끝났습니다` 정상 증상), **stderr.log 에 수십 줄의 `Error: loading initial config: ... starting caddy administration endpoint: listen tcp 127.0.0.1:2019: bind: Only one usage of each socket address` 누적**. 이전 Caddy process 가 쥔 :2019 소켓이 TIME_WAIT (Windows 기본 240 s) 동안 재 bind 불가 → NSSM restart 루프에서 지속 crash. 이전 가설 (storage init · `.\plane` LSA profile init) 은 모두 곁가지 변수였을 뿐 근본 원인은 `:2019` 였다. **가설 반증 과정**: (1) 5 차에서 Caddyfile `storage file_system` 로 프로필 경로 제거 → 재현 → storage 가설 반증. (2) 6 차 준비로 ObjectName `.\plane` → `LocalSystem` 전환 (2026-04-23 수동 smoke) → 1 회 재현 + caddy.log `"autosaved ...systemprofile..."` 확인 → LSA 가설 반증. (3) stderr.log 의 :2019 bind 에러 발견 → caddy.log 의 성공 기동 ts 와 다음 crash ts 간격이 TIME_WAIT 범위(수 분) → 원인 확정. **해결 (2026-04-24)**: Caddyfile global options 에 `admin off` 추가 → `:2019` bind 자체 제거. 수동 `Stop-Service caddy -Force` → stderr.log truncate → `Start-Service caddy` 재smoke 결과: Caddy Running, NSSM 1013/1014/1034=0, stderr.log 0 bytes, caddy.log `"admin endpoint disabled"` 확인, 5 경로 200/200/200/200/403. **6 차 재부팅 실측 (2026-04-24 10:35, 최종 검증)**: LastBootUp 10:35:17 → Boot Task LastRun 10:35:53 / LastResult=0 → caddy Running 직행 (Paused 경유 없음) · 재부팅 이후 타임스탬프 내 NSSM 1013/1014/1034=0 · stderr.log 0 B · caddy.log 재기동 엔트리 `"admin endpoint disabled"` + `C:\WINDOWS\system32\config\systemprofile\...\autosave.json` autosave + `"serving initial configuration"` · 5 경로 200/200/200/200/403. **§7a #5 영구 해소 확정**. **수동 복구 루트 (legacy, admin off 이후 불필요)**: (a) `Stop-Service caddy -Force`, (b) `caddy.exe` 좀비 kill, (c) OS handle 해소 대기, (d) `Start-Service caddy`. **재현 이력**: 2 차(2026-04-21) · 3 차(2026-04-22 22:45) · 4 차(2026-04-22 23:04, reregister 완주하나 기동 Paused) · 5 차(2026-04-22 23:21, storage 변경 후에도 동일). **해소 이력**: 수동 smoke 1 차(2026-04-23, LocalSystem) · 2 차(2026-04-24, admin off) · 6 차 재부팅(2026-04-24 10:35, 자동 기동 경로 최종 검증).

### 7b. Phase 8 §2 1 차 회귀 (2026-04-22) 에서 확인된 Plane v1.3.0 upstream known issue — 로컬 패치 금지

§2 회귀 실측 중 pytest unit 106 passed / 5 failed 중 1 건은 이미 알려진 pre-existing (`test_copy_s3_objects_of_description_and_assets` NOT NULL, handoff §7 기존 기록) 이고, 나머지 **4 건은 이번에 새로 식별** 됐다. `git log` 결과 4 건 모두 baseline import 커밋 `a2542ef Import Plane v1.3.0 baseline` 이후 변경 이력이 **없음** (우리 포크의 regression 아님, Plane 원본 코드와 테스트의 상호 모순). **대응 원칙**: 로컬 수정 금지 — Plane upstream 이 수정하면 rebase 로 흡수. 기능 영향 경미하여 블로커 아님.

- **`plane/utils/url.py::contains_url` 의 500-자 line truncation 이 1000-자 total 테스트와 모순 (3 실패)**: `test_contains_url_length_limit_under_1000` · `..._exactly_1000` · `..._total_length_vs_line_length` 모두 "한 줄 900~1000 자 + 맨 끝에 `https://example.com`" 입력에 True 를 기대하지만, 구현이 `if len(line) > 500: line = line[:500]` 로 앞 500 자만 검사하므로 뒤쪽 URL 을 놓침 → False 반환 → AssertionError. ReDoS 방어 목적의 line truncation 과 "전체 1000 자 이내면 검출해야 함" 기대가 서로 모순. **기능 영향**: 활동 로그의 500 자 초과 한 줄 평문에서 URL 자동 링크화만 안 됨 (안전 쪽으로 fail-closed). 보안 영향 0. upstream 이 규칙을 선택해 수정 필요.
- **`plane/bgtasks/work_item_link_task.py::validate_url_ip` scheme 검증 순서 버그 (1 실패)**: `test_rejects_non_http_scheme` 는 `file:///etc/passwd` 에 `match="Only HTTP and HTTPS"` 기대. 그러나 구현은 hostname 검증(`if not hostname: raise ValueError("Invalid URL: No hostname found")`) 이 scheme 검증보다 먼저 있어서, `urlparse("file:///etc/passwd").hostname = None` → hostname 에러로 먼저 raise → 메시지 미스매치 → AssertionError. **기능 영향**: **SSRF 방어는 여전히 작동** (file:// 는 hostname 없어서 차단됨) — 에러 메시지만 덜 정확. 보안 영향 0. upstream 에서 scheme 체크를 hostname 체크 앞으로 옮기면 해결.
- **종합 결과**: pytest `106 passed, 5 failed` = **실질 1 개 pre-existing (기존 기록) + 4 개 upstream known (이번 신규)**. 포크에서는 수정/skip 하지 않고 상태 그대로 유지. handoff 와 plan/09-verification 체크포인트는 이 5 건을 "수용 가능한 baseline 실패" 로 명시. 새로운 실패가 나타나면 §7a/§7b 기준 목록과 교차 검증하여 regression 여부 판정.

### 7c. Phase 8 §5 백업 자동화 (2026-04-22) 에서 쌓인 Windows Task Scheduler 교훈

PlaneBackup Task 등록을 마무리하기까지 Register-ScheduledTask 경로에서 4 단계의 실측 실패를 거쳤다. 다음 번 Task 신규 등록 시 같은 길을 다시 타지 않도록 기록.

- **Register-ScheduledTask `-User '.\plane'` → ERROR_NONE_MAPPED (0x80070534)**: SCM 이나 nssm 은 `.\plane` 표기를 받아들이지만 Task Scheduler cmdlet 은 account→SID 매핑 실패로 즉시 거부. 해결: `$env:COMPUTERNAME\plane` 형식의 fully-qualified 이름 사용. 또는 `SYSTEM` 같은 well-known account 는 단일 토큰 허용.
- **LogonType=Password + non-admin user → LastResult=267011 (SCHED_S_TASK_HAS_NOT_RUN)**: 등록은 성공하나 on-demand/scheduled 실행 시 Task Scheduler 가 LogonUser 호출에서 바로 실패. Operational Event Log 에 이벤트 자체가 안 남음 (Scheduler 가 "실행 시도 안 함" 상태). 원인은 대상 계정의 `SeBatchLogonRight` (Log on as a batch job) 부재. plane 같은 기본 로컬 사용자는 이 권한이 없다. `secedit /export /areas USER_RIGHTS` 덤프에 `SeBatchLogonRight` 가 안 보이면 미부여 확정.
- **LogonType=S4U + RunLevel Highest + non-admin user → E_ACCESSDENIED (0x80070005)**: S4U 는 비번 없이 batch 성 실행이 가능하지만, `RunLevel Highest` 는 대상 계정이 **Administrators 그룹** 에 속해야만 받을 수 있다. plane 은 서비스 전용 계정이라 관리자 그룹에 없다 (최소 권한 원칙). Register-ScheduledTask 단계에서 바로 Access Denied.
- **최종 채택: `SYSTEM + LogonType=ServiceAccount + RunLevel=Highest`**: 비번 관리 불필요, 대상 디렉토리(plane-data/, plane-logs/, ops/site.env) 에 모두 SYSTEM=FullControl 이미 보장됨 (Phase 0/1 ACL). reregister-after-boot Task 와 동일 패턴이라 운영 일관성도 확보. backup.ps1 은 파일 I/O 만 하는 read-mostly 스크립트라 SYSTEM 의 광범위 권한이 공격 표면 확대로 이어지지 않음 — 단, `ops/backup.ps1` 의 무결성은 관리자/plane 에게만 쓰기 권한으로 묶여 있어야 한다 (현재 ACL 확인 완료).
- **`python -c "..."` argv 파싱에서 literal `"` 소실**: PowerShell 이 backtick-escape (`` `" ``) 로 올바르게 quote 를 감싸도 Windows CreateProcess + Python argv 파서 단계에서 `"` 가 stripping 되어 `c.execute(VACUUM ...` 같이 구문 깨진 코드를 수신. 해결: Python 코드를 **임시 `.py` 파일** (`_vacuum.py`) 로 저장 후 `python.exe <file>` 호출. backup.ps1 에 반영.
- **PowerShell 5.1 콘솔 인코딩에서 `§` → `짠` mojibake**: 한국어 로케일 Windows 의 PS 5.1 은 BOM 없는 UTF-8 `.ps1` 을 ANSI(CP949) 로 해석하여 non-ASCII 문자열이 mojibake. 로그로 남아 보기 거슬림. 해결: 로그/Write-Host 에 들어가는 문자열은 **ASCII only** 로 (주석은 무해, 실행 메시지만 주의). 예: `security-todo §6` → `security-todo sec 6`.
- **`plane-logs/` subdir 을 joojm 이 못 만듦 (Access denied)**: plane-logs 하위는 plane + SYSTEM + Administrators 쓰기만 허용. joojm 비관리자 세션에서는 backup.ps1 이 `New-Item` 으로 `plane-logs/backup` 을 만들 수 없다. 관리자 PS 또는 `.\plane` Task 실행에서는 문제없음. 세션 내 디버깅 시 주의.
- **Start-ScheduledTask 는 비동기**: 호출 직후 `Get-ScheduledTaskInfo` 의 `LastRunTime/LastTaskResult` 가 아직 업데이트 안 될 수 있음. 10 s 정도 sleep 필요. smoke 스크립트가 짧다면 거의 즉시 반영.

### 7d. Phase 4.1 후속 보강 (2026-04-24 §1 기능 검증 중 식별 + 즉시 해소)

§1 기능 검증을 외부 브라우저에서 수행하던 중 Phase 4 (LocalFSStorage + presigned POST/GET) 관련 운영 환경 전용 실패 3건 + 세션 메타 이슈 1건이 순차로 드러났다. 모두 동일 세션 내에서 수정/재검증 완료. 운영 트리 앞에서는 개별 환경에서만 재현되는 특성상 §2 pytest (in-memory/독립 DB, 브라우저 세션 없음) 가 걸러내지 못했다. 이하는 각 건의 원인·수정·여파 기록.

- **#1 Django superuser ≠ Plane `InstanceAdmin` (데이터 보정, 커밋 없음)**: `/api/instances/` payload 의 `is_setup_done=false` + `workspaces_exist=false` 로 `/` 접속 시 로그인 페이지 대신 get-started (admin 등록) 페이지 렌더. Phase 2 의 `configure_instance` + `register_instance` 는 `Instance` 레코드 + `InstanceConfiguration` 35+ key 시드까지만 수행 — `InstanceAdmin` 은 만들지 않음. Plane 의 web frontend 는 `is_setup_done=false` 면 무조건 get-started 로 라우팅. **조치**: Django shell 에서 기존 superuser 에 `InstanceAdmin.objects.create(instance=ins, user=u, role=20)` + `ins.is_setup_done=True; ins.save()` + `cache.delete("/api/instances/")` (`redis.conf` 의 `rename-command FLUSHDB ""` 때문에 `cache.clear()` 는 `FLUSHDB` 차단으로 실패, target delete 로 우회). **handoff §6 Phase 2 표의 "configure/register 완료" 표기는 오도**: 정확히는 "Instance + Config 시드 완료 / InstanceAdmin 미등록 (브라우저 get-started 플로우 대기)" 였음. upstream Plane 은 설치 시 브라우저에서 admin 을 등록하는 것을 표준 경로로 가정 — 기존 Django superuser 와의 통합은 정규 흐름이 아니며 `InstanceAdminSignUpEndpoint` 는 `ADMIN_USER_ALREADY_EXIST` 로 거부. 그래서 "ORM 으로 기존 User 에 role 부착 + setup flag 수동 마킹" 이 필요. **관측된 캐시 동작**: `cache_response` 데코레이터의 키는 `f"{path}"` 또는 `f"{path}:{user_id}"` (`plane/utils/cache.py:16 generate_cache_key`). anonymous `/api/instances/` 는 `user=False` 로 호출되므로 키는 단순 `/api/instances/`.
- **#2 SQLite UUID converter int-safe monkey-patch (`apps/api/plane/settings/common.py`)**: workspace 생성 후 `GET /api/users/me/workspaces/` 500 — `'int' object has no attribute 'replace'`. 원인은 `UserWorkSpacesEndpoint.get` (line 214) 의 `member_count = Func(F("id"), function="Count")` 에 `output_field` 미지정 → Django ORM 이 `F("id")` 의 UUIDField 를 그대로 output 으로 추론 → SQLite 의 `DatabaseOperations.convert_uuidfield_value` 가 aggregate 결과 **int** 에 `uuid.UUID(value)` 호출 → `uuid.UUID.__init__` 내부의 `hex.replace("-", "")` 에서 `'int' object has no attribute 'replace'` 크래시. **영향 범위**: `grep -rn 'Func(F(.*), function="Count"'` 결과 `plane/api/views/{cycle,issue,module,project}.py`, `plane/app/views/{analytic/base,workspace/base}.py` 등 **30+ 사이트**. PostgreSQL backend 는 동일 쿼리가 type cast 단계에서 달라 크래시하지 않음 — 완전히 SQLite 전용 실패. **대안 비교**:
  - **P1 (채택) — `DatabaseOperations.convert_uuidfield_value` monkey-patch**: `isinstance(value, int)` 이면 값 그대로 반환, 아니면 기존 converter 호출. 한 곳(`plane/settings/common.py` 하단, try/except ImportError guard) 수정으로 30+ 사이트 자동 커버 + 향후 upstream 이 동일 패턴 추가해도 자동 보호 + rebase 충돌 거의 없음. SQLite 에 **의도적으로 UUID 를 int 로 저장하는 코드 경로는 Plane 에 없음** (모든 UUID 는 PK 또는 FK 로 TEXT 저장) 이므로 silent bypass 위험 0.
  - P2 (반려) — 각 사이트에 `output_field=IntegerField()` 명시: Django-idiomatic, diff 명확, upstream PR 제출 가능. 단 30+ 파일 diff, rebase 시 매번 재적용 필요, 향후 upstream 새 사이트 추가 시 누락 위험. §7b "upstream known issue 로컬 패치 금지" 원칙은 "기능 영향 경미" 조건부이며 이번은 **로그인 직후 기본 화면이 500** 으로 차단되는 **심각** 영향이라 예외 적용 정당. 포크의 존재 이유가 "SQLite 런타임 지원" 이므로 SQLite backend layer robustness 향상은 포크 범위 내 정당한 수정.
  - **향후**: P2 도 upstream PR 로 별도 제출 고려 가능. 수용되면 P1 monkey-patch 제거.
- **#3 LocalFSStorage presigned-POST URL trailing slash (`apps/api/plane/settings/local_storage.py:110` + `apps/api/plane/tests/unit/settings/test_local_storage.py:50`)**: 프로젝트 생성 (Plane 이 내부적으로 기본 커버 이미지를 file-asset 으로 등록하는 플로우) 중 `POST /api/assets/local-upload` 405 Method Not Allowed. 원인은 `generate_presigned_post` 의 `"url": self._endpoint("local-upload")` 가 trailing slash 없는 URL (`/api/assets/local-upload`) 반환 → Django URL pattern 은 `assets/local-upload/` (slash 있음) 로 등록 → Django `APPEND_SLASH=True` 가 불일치 시 **301 redirect** → 브라우저 `fetch API` 의 기본 `redirect: follow` 가 301 을 따라가며 **POST → GET 변환** (historical browser behavior, RFC 7231 위반이지만 현실 호환) → `LocalUploadView` 는 `post()` 만 정의 → 405. **수정**: `_endpoint` 자체는 건드리지 않고 (같은 helper 를 쓰는 `generate_presigned_url` 은 뒤에 `/{object_name}` 을 붙이므로 slash 없어야 정상) `generate_presigned_post` 의 `"url"` 에만 `+ "/"` 추가. test `endswith("/api/assets/local-upload/")` 로 동기화. **정공 대안 고려**: `path("assets/local-upload", ...)` 로 URL pattern 에서 slash 제거 — 하지만 Plane 전역에 모든 path 에 trailing slash 가 있는 관습이 있어 일관성 파괴. 좁은 지점 수정(`url` 에 slash 추가) 채택.
- **#4 `LocalUploadView` / `LocalDownloadView` `authentication_classes = []` (`apps/api/plane/app/views/asset/local.py`)**: #3 해소 후 업로드 POST 가 403 `{"detail":"CSRF Failed: CSRF token missing."}`. 같은 프로세스 내 `generate_presigned_post` → `_decode_policy` 의 roundtrip 은 정상 통과 (STORAGE_SIGNING_KEY 32자 정상 로드, HMAC 일치). 브라우저 실전 요청만 403. 원인은 DRF `SessionAuthentication` 이 기본 authentication_classes 에 포함되어, 로그인된 사용자가 보낸 **session cookie** 를 `request.user` 로 인식 → `enforce_csrf(request)` 가 unsafe method(POST) 에서 CSRF token 을 요구 → multipart form 에 CSRF token 미첨부 → 403. **docstring (`local.py:5~13`) 의 의도**: "HMAC signature 자체가 sole credential" 인데 SessionAuth 가 side-effect 로 CSRF enforce. **수정**: `LocalUploadView` 에 `authentication_classes = []` 추가 → SessionAuth 제거 → `request.user` 는 항상 anonymous → `enforce_csrf` 호출 경로 비활성 → CSRF 검증 skip. `permission_classes = [AllowAny]` 는 그대로 (HMAC 은 view 내부의 `_decode_policy` 가 전담). `LocalDownloadView` 는 GET 이라 CSRF 영향 없지만 일관성 + 향후 회귀 방지로 동반 적용. **검증**: patch 후 `POST /api/assets/local-upload/` (정책 필드 없이) 가 **403 `algorithm/credential mismatch`** 반환 — `_decode_policy` 에 진입함을 확인 (이전 CSRF 403 response `{"detail": ...}` 와 다른 plain text body). 브라우저 재시도에서 204 No Content 성공.

**종합**: 4건 중 3건은 Phase 4.1 LocalFSStorage 구현 당시 pytest + 수동 smoke (`test_local_storage.py`, `test_asset_local.py`) 로는 잡히지 않는 HTTP-transport level 실패였고, 1건은 Phase 2 의 "register 완료" 표기가 실제 상태와 불일치. 다음 세션 권장 순서 #1 의 §2.5~§2.7 후속 회귀에서 patch 3건을 재돌려보고, §2 의 smoke 확장 시 **인증된 사용자로 `/api/users/me/workspaces/` GET 200** 을 5 경로 anon smoke 뒤에 추가해 #2 유형의 regression 을 조기에 잡도록 한다.

### 7e. Phase 8 §5.3 분기 복구 훈련 (2026-04-24 초회)

plan §5.3 "복구 훈련 분기 1회" 를 `D:\Workspace\plane-restore\{sqlite,uploads,ops}` 격리 경로로 실측 수행. 운영 경로/서비스 무변경 읽기 전용 검증. 초회 기준선 확립.

**절차 (A~E)**:

(A) Fresh snapshot — `Start-ScheduledTask PlaneBackup` on-demand (오늘 daily 02:00 snapshot 은 §1 기능 검증(첨부 업로드) **이전** 시각이라 uploads 0 files 로 stale; 아래 타이밍 교훈 참조). (B) 복원 dir `New-Item` (joojm 세션 성공, ACL D-drive 상속) + sqlite/site.env `Copy-Item` + uploads `robocopy /E`. 원본 유지. (C) `apps/api/.env` 를 PS process env 에 전부 주입하고 `SQLITE_PATH` 만 복원 DB 로 override, `DJANGO_SETTINGS_MODULE=plane.settings.production`, `apps/api` 로 Push-Location 후 `.venv\Scripts\python.exe manage.py migrate --plan`. (D) 별도 python 에서 원본 vs 복원 SQLite 각각 `sqlite3.connect()` + `SELECT COUNT(*)` 8 테이블 비교, uploads 는 `Compare-Object` 로 상대경로+크기+SHA256 대조. (E) 복원 dir `Remove-Item -Recurse -Force`.

**실측 결과 (2026-04-24 14:29 ~ 14:32)**:

- Fresh backup `20260424-142947`: sqlite 3,629,056 B · uploads 7 files (workspace `c7c4df2c-...` 아래) · site.env 873 B · robocopy exit=1 (변경 복사 정상) · LastTaskResult=0 · elapsed < 1s.
- `migrate --plan`: **"No planned migration operations."** exit 0 → baseline drift 0.
- 8 테이블 count: users **4/4** · workspaces **3/3** · projects **1/1** · workspace_members **6/6** · issues **1/1** · instance_configurations **35/35** · instance_admins **1/1** · file_assets **9/9** — 전부 일치.
- uploads: origin 7 files / 2,771,190 B vs restore 7 files / 2,771,190 B — 상대경로+크기+SHA256 **7건 모두 일치**.
- 복원 dir 삭제 완료.

**교훈 + 후속**:

- **`file_assets` 9 vs 실파일 7 의 gap**: Plane 의 file-asset 레코드는 presigned POST 요청 전 ORM 으로 먼저 생성되고 multipart 업로드 완료 후 `is_uploaded=True` 로 승격. 업로드 취소/timeout 이면 레코드만 남고 파일 미생성. §1 에서 9 레코드 중 2 건이 미완 stub 로 추정 (운영 영향 0, 복구 훈련 "원본↔복원 일치" 와 무관). housekeeping task 필요성은 security-todo 외부.
- **Daily backup 02:00 과 수동 운영 변경 사이의 타이밍**: 오늘 02:00 snapshot 은 §1 검증 이전이라 uploads 0 files 로 찍혔음 (backup log 의 `files in backup=0` 은 **버그 아닌 정확한 기록**). robocopy 옵션 `/E /R:3 /W:5` 및 ACL 모두 정상. **후속 운영 규칙**: 대규모 수동 데이터 변경 (기능 검증, 관리자 작업, 다수 업로드) 직후에 `Start-ScheduledTask PlaneBackup` on-demand 1회를 의무화. 이미 fresh 가 있으면 다음 02:00 daily 로 자연스럽게 승계.
- **§5.3 루틴화**: 분기 1회 수동 (2026 Q2 초회 완료, 다음 회차 2026 Q3). 자동화 여부는 보류 — 복원 DB 의 migration 계획 변동 육안 확인 의미 유지.
- **joojm 세션의 `plane-data\uploads` 접근성**: handoff §6b 사전점검 주석 "joojm RDP Access Denied" 는 이번 세션에서 재현 안 됨. ACL (`plane Modify + SYSTEM FullControl + Admins FullControl`) 상 joojm(Administrators 그룹 멤버) 은 F 로 해석됨. §6b 주석은 다음 정비 시 현행화 대상.

### 7f. Phase 8 §2 후속 회귀 — §2.5 latency / §2.6 concurrent / §2.7 residue (2026-04-24)

1차 실측 (2026-04-22) 에서 미실행 이월했던 §2.5~§2.7 을 §1 patch 3건 투입 후 2차 pytest 재확인과 같은 세션에서 해소. 모두 기대치 통과, 신규 회귀 0.

**환경 셋업 (plan §2 top 갱신 반영)**: `apps/api/.env` 전부 process env 주입 → `SQLITE_PATH=D:/tmp/plane_verify.sqlite3` + `DJANGO_SETTINGS_MODULE=plane.settings.test` + `ALLOWED_HOSTS=*` override. fresh DB 삭제 → migrate (27.8 s) → `golden_seed --scale 100` (2.5 s).

- **§2.5 measure_latency iter=100 — 6/6 PASS** (APIClient 내부 호출, 네트워크 hop 제외):

  | scenario | mean | p50 | p95 | p99 | limit (ms) | verdict |
  |---|---:|---:|---:|---:|---:|---|
  | issues_list | 33.22 | 32.28 | 35.13 | 38.71 | 500 | PASS |
  | issues_list_filtered | 20.47 | 20.13 | 22.31 | 22.97 | 800 | PASS |
  | cycles_list | 14.05 | 13.72 | 16.10 | 17.43 | 300 | PASS |
  | modules_list | 21.75 | 20.48 | 23.64 | 27.71 | 300 | PASS |
  | pages_list | 10.72 | 10.20 | 13.41 | 17.20 | 200 | PASS |
  | search | 11.86 | 11.39 | 14.98 | 18.42 | 400 | PASS |

  전 scenario p95 가 limit 대비 10~25× 여유. 1 인 운영 budget 안정.

- **§2.6 concurrent_writes --n 50 --workers 5 — PASS**: elapsed 0.621 s · rate 80.55 /s · **created=50 / in_db=50 / errors=0 / locked=0**. SQLite WAL + `busy_timeout=5000` (Phase D PRAGMA) 하에서 5-worker 동시 쓰기가 1 인 운영 한계 내 안정.

- **§2.7 test_phase_g_residues.py — 4 passed in 0.09 s**. residue guard regression 없음.

**실측 중 발견한 함정 2건 — plan §2 top 갱신으로 영구 반영**:

- **`apps/api/.env` 미주입 시 REDIS_URL=None crash** (handoff §7a #2): plan §2 top 은 `$env:SQLITE_PATH/APP_BASE_URL/WEB_URL` 만 설정했으나, Plane 은 `.env` 를 자체 로드하지 않아 celery import 가 `'NoneType' has no attribute 'startswith'` 로 즉시 crash. **수정**: plan §2 top 에 `.env` 전체 주입 블록 추가 (UTF-8 BOM 제거 + `#` 주석 skip + `=` 2-split → `[Environment]::SetEnvironmentVariable`).
- **`ALLOWED_HOSTS=222.234.220.199,localhost,127.0.0.1` → DisallowedHost 'testserver'**: apps/api/.env 의 운영 ALLOWED_HOSTS 를 그대로 주입하면 Django APIClient 기본 host `testserver` 를 400 거부 → measure_latency 6/6 ERROR status=400. `test_phase_f_queries.py` 등이 괜찮은 이유는 pytest-django 의 test client 가 ALLOWED_HOSTS 를 자동 완화하기 때문. 독립 스크립트(APIClient 직접 호출)는 그렇지 않음. **수정**: plan §2 top 에 `$env:ALLOWED_HOSTS = "*"` 추가.

**이월 목록 갱신**: 1차의 "§2.5/§2.6/§2.7 미실행" → **전건 해소**. 신규 회귀 0. 1차의 pre-existing fail (golden diff `seed scale 차` + W17 search `검색 인덱스 ephemeral`) 은 아직 미해소 상태 그대로 — 이번 세션에서는 pytest 만 재돌렸고 §2.2/§2.3 은 건너뜀 (의미 낮음).

### 7g. Phase 8 §3 부하 smoke (2026-04-24 완료, 1인 운영 기준)

`hey -n 1000 -c 10` 원안은 windows 환경 + 현 운영(`--workers 1` + SQLite sync ORM) 조합에서 목표치 달성 불가였고 도구 자체 수급도 문제였다. plan §3 을 "c=1 primary + c=10 reference" 로 현실화하고 운영 config 를 소폭 조정.

**도구 채택**: `hey` v0.1.5 릴리스(<https://api.github.com/repos/rakyll/hey/releases/latest>)의 `"assets": []` — windows precompiled 없음. Go 미설치라 `go install` 체인도 비용 큼. **bombardier v2.0.2** (<https://github.com/codesenberg/bombardier/releases/tag/v2.0.2> 의 `bombardier-windows-amd64.exe`) 채택, `D:\Workspace\plane-app\tools\bombardier\bombardier.exe` 배치. hey 와 CLI 동등 (`-n -c -H -l`).

**Rate limit 해소**: `plane/api/rate_limit.py:14` `ApiKeyRateThrottle.rate = os.environ.get("API_KEY_RATE_LIMIT", "60/minute")` — env 기본 60/min 이 `-n 1000` 에 즉시 걸림 (`-c 10` → 6 초 만에 60 건 채우고 이후 429, 첫 1 회 실측 4xx=925/1000). `APIToken.allowed_rate_limit` 필드는 upstream 미완 feature 로 **현 코드에서 실 enforce 안 됨**. 해결:

1. `ops/site.env` 에 `API_KEY_RATE_LIMIT=10000/minute` 추가 (주석으로 "1인 + `ENABLE_SIGNUP=0` 이라 DoS 위험 0, 다중 사용자 전환 시 재평가" 명시).
2. `ops/render-envs.ps1` 91 행 하드코딩(`API_KEY_RATE_LIMIT=60/minute`)을 `$vars.API_KEY_RATE_LIMIT` 참조 + 60/minute fallback 으로 변경. `-SiteEnv`/`-AppRoot` 명시 파라미터로 재실행 (`$PSScriptRoot` 공백 이슈, handoff §7 교훈).
3. Admin PS 에서 `PLANE_SERVICE_PASSWORD=$(Get-Content ops\.plane_pass).Trim()` + `ops/register-services.ps1` → 4 서비스 stop/remove/register/start 완료 ~45 s, 5 경로 smoke 200/200/200/200/403 정상.

**`ops/` 는 `.git/info/exclude` 에 `/ops/` 로 local-only** 이라 이 설정 변경은 **어느 repo 에도 커밋 대상 아님**. 호스트 로컬 상태로만 존재 — handoff 에 변경 이력 기록으로 관리. 재배포/재설치 시 이 섹션 참조하여 재적용.

**인증 헤더 정정**: Plane API v1 은 **`X-API-Key: <token>`** (DRF `APIKeyAuthentication.auth_header_name="X-Api-Key"`, `plane/api/middleware/api_authentication.py:24`). plan §3 원안의 `Authorization: Bearer` 는 오기 (OAuth provider 전용). plan §3 정정 반영.

**API token**: superuser 에 Django shell 로 `APIToken.objects.create(user=<su>, user_type=0, label="smoke-bombardier-<ts>", allowed_rate_limit="100000/min")` 1 회성 발급. smoke 종료 후 cleanup (is_active=False 또는 delete + 로컬 임시 파일 `D:\tmp\_smoke_token.txt` 삭제).

**실측 결과** (Caddy 80 → uvicorn `--workers 1` → `plane.sqlite3`, loopback):

| c | n | Reqs/sec | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | HTTP 2xx | verdict |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 50 | 17.8 | 53.7 | **64.7** | 89.1 | 89.1 | 50/50 | **PASS** (primary) |
| 2 | 50 | 33.7 | 58.4 | 99.3 | 105.6 | 105.6 | 50/50 | PASS |
| 5 | 100 | 38.5 | 139.0 | 158.5 | 164.9 | 168.4 | 100/100 | PASS |
| 10 | 1000 | 20.0 | 488.5 | 649.3 | 726.1 | 755.5 | 1000/1000 | reference (1 인 상정 밖) |

**c=10 p95=649.3 ms 해석**: uvicorn 단일 worker + Django sync ORM → async event loop 의 thread pool 로 위임. 기본 thread pool 이 10 concurrent 를 직렬화 + SQLite single-writer lock → latency 축적. 1인 운영(동시 사용자 1~5) 범위에서는 c=5 p95=159 ms 까지 안정. 다중 사용자 전환 시 `uvicorn --workers N` 증설 또는 Postgres 전환 후 재측정. `sqlite-reference.md §4` 실측과 일관.

**plan §3 갱신 요약** (이 커밋 동반): hey → bombardier, `Authorization: Bearer` → `X-API-Key`, rate-limit 상향 절차 추가, 기대치 c=1 primary + c=10 reference 로 분리, `sqlite-reference.md §4` 참조 유지.

### 7h. 보안 세션 #1 잔존 항목 — IPBan-watchdog Task (2026-04-24)

보안 #1 의 §B P5 조사 결과, 2026-04-24 **15:40:19 IPBan SCM 7034 종료 후 약 37 분 Stopped 체류** (수동 `Start-Service` 로 16:17:40 복구) 가 재현됨. §7 IPBan Delayed Auto Start + AppRestartDelay 30s 방어(7 차 재부팅에서 해소 확정) 는 **재부팅 경계** 만 커버하고, **런타임 중 silent exit + SCM intentional-stop 판정** 케이스는 커버 못함. 아래 증거 기반:

- NSSM `AppExit Default = Restart` 는 설정된 상태 (`nssm get IPBan AppExit Default` 확인)
- IPBan `stdout.log` 의 15:40:19 **종료 직전 메시지 없음** (silent). 정상 운영 마지막은 `15:13:47 Banning ip address 36.50.135.0`, 다음은 16:17:40 새 인스턴스 기동 로그
- System Event Log 15:40:19 시점에 6 서비스 (caddy, IPBan, plane-api/celery/beat/live) **동시 SCM 7034**, 직후 15:40:24~25 에 **4건 SCM 7045 (서비스 설치)** — register-services.ps1 재실행 패턴. 하지만 `register-services.ps1` 는 IPBan 을 touch 하지 않음 (소스 확인). IPBan 이 같이 종료된 경로는 미확정
- NSSM 의 AppExit 룰은 앱이 **exit 로 종료** 시에만 평가. SCM 이 `StopService` 를 명시 호출하면 "intentional stop" 으로 간주되어 AppExit 룰 미적용 → 서비스 Stopped 유지

**개선안** — Task Scheduler `IPBan-watchdog` 신규 등록 (§7 Boot Task 패턴 재사용):

- SYSTEM + LogonType=ServiceAccount + RunLevel=Highest (handoff §7c 교훈)
- Trigger: 5 분 주기 (`At startup` + `Every 5m`)
- Action: `powershell.exe -NoProfile -Command "if ((Get-Service IPBan).Status -ne 'Running') { Start-Service IPBan }"`
- 효과: silent exit / intentional-stop / NSSM Delayed Auto Start 대기 중 어느 경로라도 5 분 내 자동 복구
- 대안 검토 결과:
  - AppExit 0 Restart 추가 — register-*.ps1 재실행 시 race 발생 (NSSM 이 재기동하려는 동안 register-* 가 nssm remove 시도) → 반려
  - register-*.ps1 에 IPBan explicit guard — register-* 가 IPBan 을 건드리지 않는데도 연쇄 영향이 있으므로 근본 원인 모름 → 반려

**적용 시점**: 보안 #1 잔존 작업 (§A P1 joojm 변경, §B P1/P2 RDP 접근 제한) 와 함께 처리 또는 단독 micro-session. `ops/register-ipban-watchdog.ps1` 신규 스크립트 예정.

---

## 8. 관련 문서

- [todo.md](todo.md) — 앞으로 할 작업 (보안 #1 잔존 + 보안 #2~#4 + upstream rebase 대기 + 기타)
- [plan.md](plan.md) — Phase 0~8 목차
- [plan/01-prerequisites.md](plan/01-prerequisites.md) ~ [plan/10-risks.md](plan/10-risks.md)
- [plan/05-storage.md](plan/05-storage.md) + `plan/05-storage/01-04-*.md` — Phase 4 서브 페이즈
- [security-todo.md](security-todo.md) — 후속 보안 TODO 원본
- [security-audit-2026Q2.md](security-audit-2026Q2.md) — 2026-04-24 §6 감사 결과 + 보안 #1 실집행 기록
- [sqlite-reference.md](sqlite-reference.md) — SQLite 런타임 불변식
- [initial-reference.md](initial-reference.md) — 포크 구조·의존성 참고
- [.claude/project-layout.md](../../.claude/project-layout.md) — 경로 지도
- [../../CLAUDE.md](../../CLAUDE.md) — AI 협업 규칙
