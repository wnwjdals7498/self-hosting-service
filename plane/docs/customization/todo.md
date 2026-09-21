# TODO — 앞으로 할 작업

> [worklog.md](worklog.md) 는 **과거 이력 + 교훈** 보관. 이 파일은 **앞으로 해야 할** 작업을 세션 단위 체크리스트로.
>
> 연관: [security-audit-2026Q2.md](security-audit-2026Q2.md) (§6 감사 결과) · [security-todo.md](security-todo.md) (원본 TODO 기획 대기열) · [plan.md](plan.md) (Phase 0~8 원안)

**최종 갱신**: 2026-04-24 (보안 #1 §A 전체 + §B 주요 완료 후)

---

## 다음 세션 권장 순서

1. **보안 #1 잔존 — IPBan-watchdog Task 등록** (`~15m`, micro-session) — [worklog §7h](worklog.md)
   - SYSTEM + LogonType=ServiceAccount + RunLevel=Highest (handoff §7c 교훈 재사용)
   - Trigger: `At startup` + `Every 5m`
   - Action: `powershell.exe -NoProfile -Command "if ((Get-Service IPBan).Status -ne 'Running') { Start-Service IPBan }"`
   - 신규 스크립트 `ops/register-ipban-watchdog.ps1` (운영 트리 local)
2. **보안 #2 — §E DPAPI + §F 백업 암호화** (`~5h`) — [security-audit-2026Q2.md](security-audit-2026Q2.md)
   - `.plane_pass` DPAPI LocalMachine 래핑 + register-services.ps1 + reregister-after-boot.ps1 수정
   - `site.env` joojm FullControl 제거
   - 7-Zip 설치 + backup.ps1 5단계 AES-256 래핑 + DPAPI `.backup_key.dpapi`
   - §5.3 복구 훈련 암호화 반영본으로 재실행
3. **보안 #3 — §C 도메인 확보 후 HTTPS** (`~5h` + 외부 도메인 비용)
   - 도메인 구매 + DNS A 레코드 + 방화벽 443 allow
   - Caddyfile HTTPS 블록 + `auto_https on` + HSTS 재추가
   - site.env PUBLIC_SCHEME=https + Django SECURE_SSL_REDIRECT/HSTS_SECONDS + ALLOWED_HOSTS 도메인으로 좁히기
   - render-envs.ps1 → pnpm turbo build → register-services.ps1 → register-caddy.ps1
4. **보안 #4 — §D AV + MIME 재검증** (`~4h`)
   - Defender 주간 FullScan Task (SYSTEM/Highest, handoff §7c 교훈)
   - 서버측 MIME 재검증 (python-magic)
   - 실행 확장자 denylist
   - SVG sanitize (nh3)

---

## 보안 세션 체크리스트

### 보안 #1 — §A + §B (Critical + High) — 진행 중

- [x] §A P2 password policy (MinPwdLen=16 / Complexity=1 / LockoutBadCount=10 / Reset+Duration=15m / History=5) — Windows 자동 추가 `AllowAdministratorLockout=1`
- [x] §A P3 빌트인 Administrator `Disable-LocalUser` — Enabled=False, `EnableAdminAccount=0`
- [x] §A P1 joojm 16자+ — RDP Ctrl+Alt+End → "Change a password", `PasswordLastSet 2026-04-24 17:18:43` 갱신, 서비스 무영향
- [x] §B P3 IPBan 정책 강화 — ExpireTime 1d→7d + BlacklistRegex `administrator|admin|root|user|guest|test|fknpoc*` (Joo\* 은 FullName 오탐 회피로 제외)
- [x] §B P4 cloudflared v2025.8.1 → `tools/cloudflared/` 공용 경로 (plane RX ACL, Caddy 패턴)
- [x] §B P5 AppExit Restart 미발동 원인 조사 (silent exit + SCM intentional stop 가설)
- [ ] **IPBan-watchdog Task 등록** — 다음 micro-session
- 보류 §A P4 joojm Admins 그룹 분리 — Q3=b, 별도 세션 재평가 (plane-admin 비번 16자+ 승격 후)
- 보류 §B P1 또는 P2 RDP 3389 allowlist/Tailscale — Q4=c, IPBan 강화만으로 임시 방어. 30일 4625 15,786건 중 Administrator 9,292건은 §A P3 로 소거 기대 → 공격 밀도 단기 감소 예상 → 감소 확인 후 재결정

### 보안 #2 — §E + §F (~5h)

- [ ] §E P1 `.plane_pass` DPAPI LocalMachine 래핑
  - `Security.Cryptography.ProtectedData::Protect` + base64 → `ops/.plane_pass.dpapi`
  - `register-services.ps1` + `reregister-after-boot.ps1` 의 읽기 경로 수정 (Unprotect)
  - 기존 평문 `ops/.plane_pass` 삭제
- [ ] §E P2 `site.env` joojm FullControl 제거 (`icacls /remove:g FKNPOC83BVCHY1L\joojm`)
- 반려 §E P3 `.redis_pass` DPAPI — ACL 이상 실익 없음 (해당 ACL 현 상태 유지 감사만)
- [ ] §F P1 7-Zip 설치 + backup.ps1 5단계 AES-256 래핑
  - `winget install 7zip.7zip`
  - `.backup_key.dpapi` 생성 (DPAPI LocalMachine, 32자 랜덤키)
  - backup.ps1 에 5단계 `7z a -t7z -mhe=on -p$key` 추가 + 평문 디렉토리 Remove
  - retention 을 `.7z` 파일 기반으로 변경
- [ ] §F P2 §5.3 복구 훈련 재실행 (암호화 반영본, handoff §7e 패턴)
- 이월 원격 오프사이트 백업 (rclone → B2/S3) — 별도 세션

### 보안 #3 — §C HTTPS 전환 (~5h + 외부 도메인 비용)

- [ ] 도메인 확보 (가비아/Cloudflare Registrar 등) + DNS A 레코드 `222.234.220.199`
- [ ] 방화벽 443 TCP 인바운드 Allow (`New-NetFirewallRule`)
- [ ] Caddyfile 변경
  - global options 에 `email <admin email>` (Let's Encrypt 알림)
  - `:80 { redir https://{host}{uri} 308 }` 블록 분리
  - `{domain} { ... }` 블록 신설 + HSTS 헤더 재추가 + 기존 handle 블록 유지
- [ ] site.env
  - `PUBLIC_HOST=<domain>`, `PUBLIC_SCHEME=https`
  - `ALLOWED_HOSTS=<domain>,127.0.0.1` (도메인으로 좁히기)
  - `SECURE_SSL_REDIRECT=1`, `SECURE_HSTS_SECONDS=31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS=1`
- [ ] render-envs.ps1 → pnpm turbo build → register-services.ps1 → register-caddy.ps1
- [ ] HTTPS smoke + 브라우저 인증서 valid 확인
- 이월 HSTS preload submit (hstspreload.org, 안정화 후)

### 보안 #4 — §D AV + MIME 재검증 (~4h)

- [ ] Defender 주간 FullScan Task (`ops/register-defender-fullscan-task.ps1` 신규)
  - SYSTEM + ServiceAccount + Highest, Weekly Sunday 03:00
  - `MpCmdRun.exe -Scan -ScanType 2 -DisableRemediation`
- [ ] 서버측 MIME 재검증 (python-magic 또는 magika)
  - `apps/api/plane/app/views/asset/v2.py` + `api/asset.py` + `space/asset.py` POST 3곳
  - `LocalFSStorage._save` override 에서 magic byte sniff
- [ ] 실행 확장자 denylist (.exe .bat .cmd .ps1 .msi .scr .com .jar .lnk .vbs .js .wsf .hta)
- [ ] SVG sanitize (nh3 / bleach) — 이미지 커버/페이지 inline
- 이월 MpCmdRun 동기 스캔 통합 — 성능 영향 큼, Celery 비동기 offload 설계 후

### 보류 — §G Redis → Memurai

Redis 5 EOL 이지만 `bind 127.0.0.1` loopback-only 라 외부 CVE 표면 제한. Plane upstream 이 Redis 6+ 기능 요구하거나 심각 신규 CVE 발표 시 재평가 — [security-audit-2026Q2.md §G](security-audit-2026Q2.md)

---

## 운영 보강 TODO (낮은 우선순위)

- [ ] **Upstream known issue 4 건** (Plane v1.3.0, [worklog §7b](worklog.md)) — upstream 이 수정하면 rebase 로 흡수. 로컬 패치 금지 원칙.
  - `plane/utils/url.py::contains_url` 500-자 truncation vs 1000-자 test 모순 (3 failed)
  - `plane/bgtasks/work_item_link_task.py::validate_url_ip` scheme 검증 순서 버그 (1 failed)
- [ ] **§1 세션 관측 보강** (우선순위 낮음)
  - `reregister-after-boot.ps1` AppEnvironmentExtra 소실 감지 ([worklog §7a](worklog.md))
  - `§5 재개 빠른 시작` smoke 에 인증 후 `/api/users/me/workspaces/` GET 200 단계 — 이미 반영됨, 회귀 시 재점검
- [ ] **튜닝 후속** (운영 범위 확장 시에만) — `uvicorn --workers N` 증설 시 §3 c=10 재측정 ([worklog §7g](worklog.md))
- [ ] **§5.3 분기 복구 훈련** — 다음 회차 2026 Q3 (2026-07-01 이후)
  - `file_assets` 9 vs 실파일 7 gap 은 미완 stub 여부 확인 (무해하지만 housekeeping task 도입 검토)

---

## 외부 프로젝트 (Plane 배포 문맥 바깥)

- **Plane MCP 서버 자체 제작** — Plane 배포의 본 목적. makeplane/plane-mcp-server 기반 커스터마이즈 (fork). 이 문서 범위 밖, `D:\Workspace\plane-mcp-server/` 별도 프로젝트 참조.
