# Plane v1.3.0 개인용 경량화 실행 계획 (목차)

> 이 문서는 포크의 **Windows Server 2025 네이티브 배포 실행 계획 목차**다. 각 Phase 는 `plan/` 서브폴더의 파일로 분리되어 있고 순서대로 진행한다.
> 포크 전체 상태·코드 구조·의존성은 [initial-reference.md](initial-reference.md), SQLite 전환 결과·런타임 불변식·DB 리스크는 [sqlite-reference.md](sqlite-reference.md), Phase 범위 밖 보안 TODO 는 [security-todo.md](security-todo.md).

> **SQLite 전환은 완료** (git `a2542ef..d19501b`, 26 커밋). DB 는 파일 기반 SQLite 단일 전제.

---

## 0. 확정된 전제

| 항목 | 결정 | 출처 |
|---|---|---|
| 사용자 수 | 1인 전용 | — |
| **배포 OS** | **Windows Server 2025 Standard (Build 26100)**, VM 호스트 — 중첩 가상화 불가 | Q 확정 |
| 실행 환경 | **Windows 네이티브** (Docker · WSL2 불사용) | Q 확정 |
| 런타임 경로 | `D:\Workspace\plane-app` (코드) · `plane-data` (DB/업로드/Redis/백업) · `plane-logs` | Q1-보강 |
| 서비스 계정 | `plane` 제한 계정 (서비스 실행) + `plane-admin` 관리자 (RDP) | Q4 |
| DB | **SQLite** 단일 파일 · `D:\Workspace\plane-data\sqlite\plane.sqlite3` | 전환 완료 |
| Queue/Cache | **tporadowski/redis 5.0.14** (Windows 포트) — broker + cache 겸용, DB `/0` cache · `/1` broker | Q2 |
| Celery worker | `--pool=solo` · result backend 없음 | Phase 3 Q1·Q2 |
| 파일 저장소 | **LocalFSStorage** (A2 presigned-like 어댑터) — app/ · api/ · space/ · bgtasks 전면 | Phase 4 A2+B1+C2 |
| 프론트 서빙 | **Caddy 네이티브** 단일 80 포트 + path prefix 라우팅 | Phase 7 |
| 외부 접근 | **공인 IP `222.234.220.199`** (HTTP) · 도메인 + HTTPS 는 후속 | Q1 |
| 프로세스 매니저 | **NSSM 2.24** | Q4 대응 |
| 중앙 설정 | `D:\Workspace\plane-app\ops\site.env` + `render-envs.ps1` | Q1 구현 |

---

## 1. Phase 목차

| # | Phase | 내용 | 코드 수정 | 링크 |
|---|---|---|---|---|
| 0 | 사전 준비 | Windows 계정 · 경로 · ACL · Python · Node · pnpm · Redis MSI · NSSM · VC++ · cloudflared · 방화벽 | — | [01-prerequisites.md](plan/01-prerequisites.md) |
| 1 | 인프라 네이티브 | Redis conf 이전 · 계정 전환 · DB 번호 분리 · 로그 디렉토리 · PRAGMA 자동 적용 | ✓ production.py `LOG_DIR` | [02-infrastructure.md](plan/02-infrastructure.md) |
| 2 | 소스 준비 | 운영 저장소 clone · venv · pnpm · `site.env` + `render-envs.ps1` · migrate · superuser · configure/register_instance · collectstatic | — | [03-source-prep.md](plan/03-source-prep.md) |
| 3 | Celery broker 전환 | RabbitMQ → Redis · `broker_connection_retry_on_startup` | ✓ common.py | [04-celery-broker.md](plan/04-celery-broker.md) |
| 4 | 파일 저장소 (서브폴더) | `LocalFSStorage` 어댑터 · upload/download endpoint · view 호환 · bgtasks · 프론트 타입 | ✓ 다수 | [05-storage.md](plan/05-storage.md) |
| 4.1 |   └ adapter | `LocalFSStorage` + HMAC + URL endpoint | ✓ | [05-storage/01-adapter.md](plan/05-storage/01-adapter.md) |
| 4.2 |   └ views | app/·api/·space/ 호환 실측 + MCP round-trip | — | [05-storage/02-views.md](plan/05-storage/02-views.md) |
| 4.3 |   └ bgtasks | export/cleanup boto3 → default_storage | ✓ | [05-storage/03-bgtasks.md](plan/05-storage/03-bgtasks.md) |
| 4.4 |   └ frontend | 타입 완화 (선택) | (선택) | [05-storage/04-frontend.md](plan/05-storage/04-frontend.md) |
| 5 | 프론트엔드 빌드 | render-envs 확장 · turbo build · 산출물 고정 | — | [06-frontend-build.md](plan/06-frontend-build.md) |
| 6 | 서비스 등록 (NSSM) | plane-api (uvicorn) · plane-celery · plane-beat · plane-live | — | [07-systemd.md](plan/07-systemd.md) |
| 7 | 외부 접근 | Caddy 네이티브 + 공인 IP 80 + 방화벽 · 포트 포워딩 · 도메인/HTTPS 이월 | — | [08-external-access.md](plan/08-external-access.md) |
| 8 | 검증 | 기능 · 회귀 · 부하 · 재부팅 · 백업 Task Scheduler · 업데이트/롤백 플레이북 | — | [09-verification.md](plan/09-verification.md) |
| — | 리스크 | Windows 네이티브 · IP 기반 HTTP 상황 특유 오픈 이슈 | — | [10-risks.md](plan/10-risks.md) |

---

## 2. 실행 순서 요약

**선행**: SQLite 전환은 종료 상태 ([sqlite-reference.md](sqlite-reference.md)). 본 목차는 그 위에서 시작.

1. Phase 0 (의존성 · 계정 · 경로 · 방화벽)
2. Phase 1 (Redis conf 이전 + DB 분리 + 로그 디렉토리; production.py 수정)
3. Phase 2 (clone · venv · site.env · render-envs · migrate · superuser · configure/register · collectstatic)
4. Phase 3 (common.py Celery broker 수정 + Redis /1 실효)
5. Phase 4 (서브폴더 순서: 4.1 → 4.2 → 4.3 → 4.4)
6. Phase 5 (render-envs 확장 + `pnpm turbo build`)
7. Phase 6 (NSSM 4개 서비스 등록)
8. Phase 7 (Caddy + 방화벽 + 공인 IP 노출)
9. Phase 8 (검증 · 백업 자동화 · 업데이트 플레이북)

각 Phase 완료 시 체크박스 채우고, 발견된 배포 계열 이슈는 [10-risks.md](plan/10-risks.md) 에 누적 기록. DB 계열 이슈는 [sqlite-reference.md §5](sqlite-reference.md) 만 갱신.

---

## 3. 관련 문서

- [initial-reference.md](initial-reference.md) — 포크 전체 구조·앱/패키지 레이아웃·의존성·린트·개발 명령
- [sqlite-reference.md](sqlite-reference.md) — SQLite 전환 결과·런타임 불변식·DB 리스크
- [security-todo.md](security-todo.md) — Phase 범위 밖 보안 TODO (Redis EOL · RDP · 업로드 검증 · 백업 암호화 등)
- [.claude/project-layout.md](../../.claude/project-layout.md) — 소스 트리 + Windows 배포 경로 지도
- [plan/](plan/) — Phase별 상세 문서 폴더 (4 는 서브폴더 `plan/05-storage/` 포함)
