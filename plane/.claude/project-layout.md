# Plane Fork — Project Layout

> CLAUDE.md §0 · §2 가 참조하는 "지도". 실제 디렉토리 · 운영 경로 · 문서 경로를 한 장에 모은다.
> **변경 시 사용자 승인 필수**. 본 파일 최신화와 `docs/customization/` 변경 이력 기록을 동시에 수행한다.

최종 갱신: 2026-04-19

---

## 1. 저장소 (소스 트리)

**루트**: `D:\Workspace\plane` — 개발용 워크스페이스. 현재 저장소.

모노레포(pnpm + turbo). 앱·패키지·의존성 상세는 [docs/customization/initial-reference.md](../docs/customization/initial-reference.md) §2~§5.

```
plane/
├── apps/
│   ├── api/         Django 4.2 + DRF + Celery (Python, SQLite 단일)
│   ├── web/         React Router 7 SPA       (port 3000, main)
│   ├── admin/       관리자 대시보드 SPA        (port 3001, /god-mode)
│   ├── space/       외부 공개 포털 SPA         (port 3002, /spaces)
│   ├── live/        Yjs 실시간 협업 서버       (Node,  port 3100)
│   └── proxy/       Caddy 설정 (docker 기반 원본, 네이티브에선 참고만)
├── packages/        @plane/* 내부 공유 패키지 15개
├── deployments/     업스트림 엔터프라이즈 배포 템플릿 (본 포크 미사용)
├── docs/
│   └── customization/   본 포크 설계·계획·보안 문서 (§3)
├── .claude/         AI 협업 보조 (§4)
├── docker-compose.yml       원본 유지 (본 포크 배포엔 불사용)
├── turbo.json / pnpm-workspace.yaml / package.json
└── CLAUDE.md        AI 협업 규칙
```

**모노레포 경계**: `pnpm-workspace.yaml` 은 `apps/*` + `packages/*` 포함, **`apps/api`(Python) 와 `apps/proxy`(Caddy 정적) 는 제외**. Turbo 태스크도 자동 제외된다.

---

## 2. Windows 배포 경로 (운영 환경 — 확정)

Windows Server 2025 네이티브 배포. Docker·WSL2 불사용 (중첩 가상화 불가).

| 경로 | 용도 | 권한 |
|---|---|---|
| `D:\Workspace\plane-app`   | 배포용 소스 · venv · 빌드 산출물         | `plane` 계정 Modify |
| `D:\Workspace\plane-data`  | SQLite DB · 업로드 · 백업 · Redis 데이터 | `plane` 계정 Modify (외부 비공개) |
| `D:\Workspace\plane-logs`  | 앱 로그 (Django/Celery/live)             | `plane` 계정 Modify |

**개발/운영 분리**:
- 개발 트리: `D:\Workspace\plane` (본 저장소)
- 운영 트리: `D:\Workspace\plane-app`
- 동기화 방식은 Phase 2/6 에서 확정 (git pull 기반 권장)

**서비스 실행 계정** (3종 분리):
- `plane` — 로컬 제한 계정, 대화형 로그인 거부, 모든 Plane 서비스(API/Celery/Live/Redis/Caddy) 실행 전용
- `plane-admin` — Administrators, **로컬 콘솔 전용**(Remote Desktop Users 불포함) — 비상 관리자
- `joojm` — Administrators + Remote Desktop Users, RDP 원격 관리 담당

**데이터 하위 경로** (Phase 1 에서 확정):
```
D:\Workspace\plane-data\
├── sqlite\   plane.sqlite3 (+ -wal, -shm)
├── uploads\  Issue/Page 첨부, 프로필/커버 이미지
├── backup\   DB/업로드 백업 (암호화 대상 — security-todo §6)
└── redis\    tporadowski Redis 데이터 (dump.rdb, appendonly.aof)
```

---

## 3. docs/customization/ 문서 구조

본 포크의 설계 · 계획 · 운영 · 보안 문서 일체.

```
docs/customization/
├── initial-reference.md   포크 전체 구조·의존성·린트·커맨드 참고
├── sqlite-reference.md    SQLite 전환 결과·런타임 불변식·리스크
├── plan.md                네이티브 배포 Phase 0~8 목차
├── plan/
│   ├── 01-prerequisites.md     Phase 0 사전 준비 (본 Windows 네이티브)
│   ├── 02-infrastructure.md    Phase 1 SQLite 디렉토리 + Redis 튜닝
│   ├── 03-source-prep.md       Phase 2 venv · pnpm · .env · migrate
│   ├── 04-celery-broker.md     Phase 3 RabbitMQ → Redis broker 전환
│   ├── 05-storage.md           Phase 4 파일 저장소 전환 (목차, 서브폴더 있음)
│   ├── 05-storage/             Phase 4 서브: 01-adapter · 02-views · 03-bgtasks · 04-frontend
│   ├── 06-frontend-build.md    Phase 5 turbo build (4 SPA)
│   ├── 07-systemd.md           Phase 6 서비스 등록 (Windows 에서는 NSSM)
│   ├── 08-external-access.md   Phase 7 Cloudflare Tunnel
│   ├── 09-verification.md      Phase 8 검증 체크리스트
│   └── 10-risks.md             배포 계열 리스크 누적
└── security-todo.md       Phase 범위 밖 보안 TODO 누적
```

> `07-systemd.md` 파일명은 Linux 원안 잔재지만 내용은 NSSM 기반으로 재작성된다. 파일명 변경은 링크 정합성 때문에 보류.

---

## 4. .claude/ 보조 디렉토리

AI 협업용 파일. CLAUDE.md §0 경로 정의를 따른다.

| 경로 | 용도 | 상태 |
|---|---|---|
| `.claude/project-layout.md`     | 본 파일 (지도)                       | ✓ |
| `.claude/commands/`             | 재사용 스크립트 (dev/test/lint/build) | 미생성 |
| `.claude/tests/`                | 하네스 테스트 자산                   | 미생성 |
| `.claude/skills/`               | 재사용 워크플로우 스킬               | 미생성 |
| `.claude/settings.local.json`   | Claude Code 로컬 설정 (커밋 제외 대상) | ✓ |

**미생성 하위 디렉토리**는 필요 발생 시점에 사용자 승인 후 생성한다 (CLAUDE.md §2 레이아웃 규칙).

---

## 5. 변경 이력

| 날짜 | 변경 | 사유 |
|---|---|---|
| 2026-04-19 | 초판 작성 — Windows 네이티브 배포 경로(`D:\Workspace\plane-{app,data,logs}`) · 서비스 계정 정책 · 문서 구조 반영 | Phase 0 개정과 연계 |
| 2026-04-19 | `docs/customization/plan/05-storage/` 서브폴더 4종 추가 | Phase 4 (파일 저장소 전환) 의 A2+B1+C2 구조 |
| 2026-04-19 | 서비스 계정 2종 → 3종 분리 (`plane-admin` 로컬 전용, `joojm` RDP 신설) | 공인 IP 직접 노출 환경 보안 강화 |
