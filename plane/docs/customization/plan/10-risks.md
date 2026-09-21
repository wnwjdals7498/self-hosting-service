# 오픈 이슈 & 리스크 (배포 계열)

> **네비게이션**: [← Phase 8](09-verification.md) · [목차](../plan.md)

각 Phase 진행 중 발견한 **배포·운영 계열** 이슈를 누적한다.

> - **DB 계열 리스크**는 본 문서에 쓰지 말 것. SQLite 전환 관련 런타임 불변식·잔여 리스크는 [../sqlite-reference.md §3·§5](../sqlite-reference.md) 에 이미 정리되어 있다.
> - **보안 TODO** 는 [../security-todo.md](../security-todo.md) 로 이월. 본 문서는 "현재 배포에서 즉시 알아야 할 제약" 위주.

---

## 1. 배포 OS — Windows Server 2025 네이티브

**상태**: 확정 — VM 호스트, 중첩 가상화 불가.

**파생 제약**:
- Docker · WSL2 · systemd 사용 불가 → NSSM 로 전환
- gunicorn 사용 불가 → uvicorn `--workers 1` (Phase 6 §3)
- Celery Windows 공식 미지원 → `--pool=solo` (Phase 3 Q1)
- Redis 공식 Windows 미지원 → tporadowski 커뮤니티 포트 5.0.14 ([../security-todo.md §1](../security-todo.md))

**모니터링**: Celery 5.x 의 Windows 동작 변화, tporadowski Redis 의 커뮤니티 유지 상태.

---

## 2. 외부 접근 — 공인 IP 기반 HTTP

**상태**: 도메인 없음. `222.234.220.199` 직접 접근 (HTTP 80).

**즉시 제약**:
- HTTPS 불가 (Let's Encrypt 는 도메인 필수) → **로그인/세션 쿠키 평문 전송**
- `SESSION_COOKIE_SECURE` · `CSRF_COOKIE_SECURE` 가 `False` 로 동작 (HTTP 에서 강제 불가)
- HSTS 미설정

**완화**:
- 내부망에서만 접근 + RDP 게이트 (Phase 7 §5.1 포트 포워딩 생략 가능)
- Cloudflare Tunnel 임시 도메인 (`<random>.trycloudflare.com`) 으로 HTTPS 우회 가능 — 단 URL 을 화이트리스트 기반 공유

**해소 경로**: 도메인 획득 → Caddy 자동 ACME 또는 Cloudflare Tunnel (Phase 7 §8).

---

## 3. Python 3.13 + Django 4.2

**상태**: Django 4.2 공식 지원은 Python 3.12 까지. Plane 이 Python 3.13 에서 동작하는지는 Phase 2 실측 기준.

**잠재 실패 지점**:
- `pymongo 4.6` — 공식 3.12 까지, wheel 제공 여부
- `channels 4.1` — 공식 3.12 까지 (Plane 은 `plane.asgi` 에서 HTTP protocol 만 등록 — 실 사용은 http 만)
- `cryptography 46` / `lxml 6` / `nh3` — 3.13 wheel 정상 (2026-04 기준)

**폴백**: Phase 2 §2.2 분기 B — Python 3.12 MSI 병행 설치.

---

## 4. admin / space SPA 실 활용도

**상태**: 1인 운영에서 `/god-mode/` 는 초기 설정 후 미사용, `/spaces/` 는 외부 공유 시에만 사용.

**대응**: Phase 6 에서 NSSM 서비스 등록은 SPA 가 아니라 **API 1개만** 필요 (admin/space 는 정적 파일이라 Caddy 가 서빙). `/god-mode/` 경로 자체를 Caddy 에서 Rate-limit 강화 또는 인증 게이트 추가 고려 → [../security-todo.md §3](../security-todo.md).

---

## 5. live 서비스 단독 저장

**상태**: 1인 운영 시 동시 편집 없으므로 live 서비스 자체가 필수 아닌 상황 가능.

**검증 필요 항목** (Phase 8 §1.2):
- live 미기동 시 페이지 편집 저장이 정상 동작하는지 (Tiptap 자체는 클라이언트 저장. REST 저장 경로 독립인지 확인)
- 미기동 시 프론트가 WebSocket 연결 실패 토스트를 띄우는지 → UX 저하 가능

**결정 유예**: 검증 후 live 를 off 할지 결정. 현 Phase 6 은 등록 대상에 포함.

---

## 6. 이메일 (SMTP) 부재

**상태**: `EMAIL_BACKEND=console` 로 시작 (Phase 2 Q3).

**영향**:
- 비밀번호 재설정 불가 (토큰이 콘솔 로그에만 남음 — 운영자가 로그에서 수동 추출 가능하지만 불편)
- 매직 링크 로그인 비활성 (`ENABLE_MAGIC_LINK_LOGIN=0`)
- 이슈/댓글 알림 메일 미발송 (Celery 는 태스크 실행하지만 console backend 로 드롭)

**해소**: SMTP 서버 확보 시 `.env` 의 `EMAIL_BACKEND` 변경 + `EMAIL_HOST` 등 채우기. security-todo §5 로 이월.

---

## 7. Pre-signed URL → LocalFSStorage 전환 후유증 (Phase 4)

**상태**: Phase 4 A2 어댑터가 S3 presigned POST 계약을 유지해 프론트·MCP 호환.

**잠재 이슈**:
- `get_object_metadata` 의 `ContentType` 이 항상 None (로컬 FS 엔 헤더 저장 안 됨) — Phase 4.2 에서 호출부 grep 필수
- 이미지 썸네일 · 메타데이터 감지 등 기능이 `ContentType` 에 의존하면 보정 필요
- 대용량 파일(50MB+) 업로드 시 Django 메모리 사용 — Plane `FILE_SIZE_LIMIT=5MB` 기본값이라 현실 위험 낮음

**대응**: Phase 4.2 §2.3 실측 + 필요 시 `FileAsset.attributes["type"]` 사용.

---

## 8. 백업 암호화 부재

**상태**: Phase 8 §5.1 백업 스크립트가 SQLite + uploads + site.env 를 **평문** 복사.

**위험**:
- `site.env` 가 `REDIS_PASSWORD`, `SECRET_KEY`, `LIVE_SERVER_SECRET_KEY`, `STORAGE_SIGNING_KEY` 평문
- 호스트 침해 시 백업 폴더만 뽑혀도 비밀값 전부 유출

**이월**: [../security-todo.md §6](../security-todo.md) — AES-256 / `age` 암호화 + 키 분리.

---

## 9. `update_bucket` / `create_bucket` 커맨드 회귀

**상태**: Phase 4.3 에서 `USE_LOCAL_STORAGE=1` 시 no-op 분기 추가.

**주의**: 1인 운영에서 이 커맨드 실행할 일 없지만, 누군가 실행 시 분기가 빠지면 AWS_* placeholder 로 S3 접속 시도 → 긴 timeout → 서비스 일시 지연 가능.

**대응**: Phase 4.3 체크리스트 `USE_LOCAL_STORAGE no-op 분기` 필수 확인.

---

## 10. 업데이트 플레이북 드라이런 부재

**상태**: Phase 8 §6.1 플레이북은 문서만. 실제 로드 상태에서 업데이트 순서 실측 1회 필요.

**위험**: 실패 시점에 복구 경로 익숙하지 않을 수 있음.

**대응**: Phase 8 체크리스트에 "1회 드라이런 (no-op 업데이트)" 포함.

---

## 관리 규칙

- 해결된 항목은 **삭제 대신 `[해결] YYYY-MM-DD`** 접두로 존치.
- 새 이슈가 DB/쿼리/마이그레이션 계열이면 `sqlite-reference.md` 에 기록.
- 새 이슈가 보안 계열이면 `security-todo.md` 에 기록.
- 본 문서는 **배포/운영 현실의 제약** 위주.

---

> **네비게이션**: [← Phase 8](09-verification.md) · [목차](../plan.md)
