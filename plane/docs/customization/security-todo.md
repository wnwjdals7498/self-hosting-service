# 보안 TODO — 후속 기획 누적

> 현재 `plan/` 범위(Phase 0~8 네이티브 배포) **이후**로 미뤄둔 보안 이슈를 누적한다.
> 새 이슈는 해당 섹션에 추가. 해결된 항목은 삭제 대신 `[해결] YYYY-MM-DD` 접두로 존치 (이력 유지).
>
> 연관 문서: [../../CLAUDE.md](../../CLAUDE.md) · [plan/10-risks.md](plan/10-risks.md) · [sqlite-reference.md §5](sqlite-reference.md)

최종 갱신: 2026-04-19

---

## 1. Redis 런타임 — tporadowski/redis 5.0.14 (Windows 포트)

**배경**: Windows Server 2025 에는 Redis 공식 지원이 없어 커뮤니티 포트(`tporadowski/redis`, upstream Redis 5.0.14 기반) 채택 — [plan/01-prerequisites.md §6](plan/01-prerequisites.md).

**알려진 위험**:
- Redis 5.x 자체가 **2023-04 EOL** — 업스트림 CVE 패치 중단
- 포트 저장소는 2022년 이후 커밋 없음
- **TLS 미지원** (Redis 6 부터 도입)
- Redis 6/7 의 ACL · client-side caching · I/O threads 등 보안·성능 기능 부재
- Windows 전용 메모리 매니저 구현이라 업스트림과 행동 미세 차이 가능성

**단기 완화 — Phase 1 에서 강제**:
- [ ] `bind 127.0.0.1` 고정, 외부 인터페이스 미바인드
- [ ] Windows 방화벽: 6379/tcp 인바운드 차단 (로컬 loopback 만)
- [ ] `requirepass` 설정 (32자 이상 랜덤)
- [ ] Redis 데이터 디렉토리 (`D:\Workspace\plane-data\redis\`) ACL: `plane` 계정 전용 R/W
- [ ] `protected-mode yes`
- [ ] `rename-command` 으로 `FLUSHALL`/`CONFIG`/`DEBUG`/`KEYS` 등 봉인

**중기 전환 후보** (별도 기획 시작 시 이 섹션을 `docs/customization/plan-redis-migration/` 로 승격):
- **Memurai Developer Edition** — Redis 7.2 호환, 비상업/개인 무료, 보안 패치 지속. Windows 운영에서 가장 권장.
- **원격 관리형 Redis** (Upstash Free, Redis Cloud Free) — 호스트 전환 부담 없이 최신 엔진
- **WSL1 + Redis** — WSL1 은 중첩 가상화 불필요. 시스템 콜 제약으로 Redis 동작 여부 실측 필요
- **KeyDB Windows 빌드** — 활성 상태 확인 필요

---

## 2. RDP 외부 접근

**배경**: 공유기 없이 공인 IP 를 호스트가 직접 물림 → Windows 방화벽이 유일한 경계. RDP 접근 계정 분리 상태:
- `plane-admin` (Administrators 만) — Remote Desktop Users 불포함 → RDP 로그인 불가, 콘솔 전용
- `joojm` (Administrators + Remote Desktop Users) — RDP 로그인 가능. 비밀번호 길이 10자, **공인 IP 에 직접 노출되는 유일한 관리자 RDP 공격면**
- 빌트인 `Administrator` 는 로그인 차단 상태 유지

**즉시 확보된 완화**:
- plane-admin 이 RDP 로 올 수 없음 → 관리자 계정 2개 중 하나는 외부 공격에서 격리
- NLA 강제 (Phase 0 §2.4 완료 시)

**남은 TODO**:
- [ ] `joojm` 비밀번호 길이 16+ 로 승격 (현재 10자) — GPU brute force 저항
- [ ] **IPBan (DigitalRuby/IPBan) 설치** — Event Log 기반 RDP/SMB brute force 자동 차단. 공인 IP 직접 노출 환경의 최우선 방어
- [ ] 방화벽: 3389/tcp 인바운드를 특정 IP allowlist 로 제한 (본인 접속 IP 가 고정이면)
- [ ] 장기: Tailscale 설치 + RDP 를 Tailnet 전용으로 전환, 3389 외부 차단
- [ ] 로그인 실패 lockout 정책 (5회/15분)
- [ ] RDP 세션 유휴 타임아웃 (15분)
- [ ] 도메인 확보 후 Cloudflare Access SSO 로 `joojm` RDP 게이트
- [ ] 빌트인 `Administrator` 비활성화 또는 이름 변경 + 극장기 비밀번호

---

## 3. `/god-mode` (admin SPA) 접근 제한

**배경**: `apps/admin` 은 운영 전체 권한. 외부 노출 시 표적.

**TODO**:
- [ ] Cloudflare Access 정책 — 특정 이메일/IP 만 접근
- [ ] `apps/admin` 서비스(NSSM) 기본 비활성, 필요 시점에만 수동 기동
- [ ] `/god-mode/*` Cloudflare Rate Limit
- [ ] admin 세션 만료 주기 단축 (기본 대비 1/4)
- [ ] admin 로그인 성공/실패 로그를 별도 로그 파일로 분리

---

## 4. 파일 업로드 검증

**배경**: 이슈/페이지 첨부, 프로필/커버 이미지, 에디터 inline 업로드. Phase 4 로컬 FS 전환 시 호스트 파일시스템이 직접 노출된다.

**TODO**:
- [ ] mime type 서버측 재검증 (`python-magic` 또는 `magika` 등 매직바이트 기반)
- [ ] 실행 가능 확장자(`.exe`, `.bat`, `.ps1`, `.msi`, `.scr`, `.com`, `.jar`, `.lnk`) 거부
- [ ] 업로드 경로 path traversal 방어 (`..`, 절대경로, 예약 이름(`CON`, `PRN`, `AUX`, `NUL`, `COM1~9`, `LPT1~9`))
- [ ] 파일 크기 하드 리밋 (`FILE_SIZE_LIMIT` env 실작동 검증)
- [ ] AV 스캔 — Windows Defender `MpCmdRun.exe -Scan -File` 프로그래매틱 호출
- [ ] 업로드 디렉토리 ACL: 실행 권한 제거, Web 서빙은 MIME override 로 `application/octet-stream` 강제 또는 `X-Content-Type-Options: nosniff`
- [ ] SVG 업로드 시 인라인 스크립트 제거 (nh3 또는 bleach)
- [ ] 이미지 재인코딩 (Pillow, ImageMagick) 로 메타데이터·페이로드 제거

---

## 5. SECRET_KEY · 자격증명 관리

**TODO**:
- [ ] SECRET_KEY 엔트로피 ≥ 256 bit (`openssl rand -hex 32` 또는 `[System.Web.Security.Membership]::GeneratePassword(50, 15)`)
- [ ] SECRET_KEY 회전 주기 (연 1회, 세션 무효화 수용)
- [ ] `.env` 파일 ACL: `plane` 계정 전용 R, 일반 사용자 접근 거부
- [ ] OAuth client secret · SMTP 패스워드 · API 키는 **Windows Credential Manager** 또는 **DPAPI** 로 보관 (env 평문 회피 — 중기 과제)
- [ ] `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` 실제 도메인으로 타이트하게 (와일드카드 금지)
- [ ] Django `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` 모두 production 에서 활성

---

## 6. DB · 업로드 백업 암호화

**배경**: `D:\Workspace\plane-data\backup\` 에 SQLite 덤프 + 업로드 tarball 이 누적. 평문 저장 시 호스트 침해만으로 전량 유출.

**TODO**:
- [ ] 백업 파일 AES-256 암호화 (7-Zip AES / `age` / `age-keygen`)
- [ ] 암호 키는 백업 미디어와 **분리 보관** (Credential Manager 또는 별도 저장소)
- [ ] 원격 오프사이트 백업 (rclone → S3/B2/rsync.net) — 도입 검토
- [ ] 드라이브 수준 암호화 — BitLocker 상태 확인 및 활성
- [ ] 백업 복구 훈련 (분기 1회, 체크리스트화)

---

## 7. Celery 태스크 격리

**배경**: bgtasks 내 외부 HTTP 호출·파일 쓰기·이메일 발송 존재. SSRF / 스팸 남용 경로.

**TODO**:
- [ ] Celery worker 서비스 계정은 `plane` (최소 권한)
- [ ] 웹훅·외부 API 호출 URL **allowlist** (사내망/메타데이터 엔드포인트(`169.254.169.254`) 차단)
- [ ] 이메일 발송 전용 별도 큐 + rate limit (남용 대응)
- [ ] 태스크 입력 PII 로깅 금지 (§8 와 연계)

---

## 8. 로그 PII 마스킹

**배경**: `python-json-logger` 전역 구조화 로그. 요청/응답에 이메일·이름·토큰 포함 가능.

**TODO**:
- [ ] request body 로깅 대상 필드 whitelist/blacklist (기본은 blacklist: `password`, `token`, `secret`, `authorization`)
- [ ] `Authorization` / `Cookie` 헤더 자동 마스킹 필터
- [ ] 로그 보관 기간 정책 (예: 30일 온라인 / 90일 아카이브) 및 자동 압축·삭제 스크립트
- [ ] 로그 파일 ACL — `plane` R/W, `Administrators` 읽기 전용
- [ ] 로그 전송 시 (외부 수집기 사용 시) TLS 강제

---

## 관리 규칙

- 본 문서는 "기획 대기열". 실제 구현은 해당 이슈가 독자 계획으로 승격될 때 별도 `plan-*/` 서브폴더로 분리.
- 항목이 Phase 0~8 `plan/` 범위에서 해결되면 여기서 **삭제 대신 `[해결] YYYY-MM-DD`** 표기로 이력 유지.
- Redis 대체(§1) 는 중기 전환이 확정되는 시점에 별도 마이그레이션 plan 생성.
