# Phase 8 §6 보안 감사 (2026Q2 스냅샷)

> [security-todo.md](security-todo.md) 의 §1~§7 TODO 중, Phase 0~8 배포가 완료된 실
> 운영 환경에서 각 항목을 재평가한 **감사 스냅샷**이다. 실 변경 작업(비번 재설정 ·
> 방화벽 정책 · DPAPI 이관 등)은 이 문서의 우선순위에 따라 **항목별 별도 세션** 으로
> 분할 수행한다 — 이 세션은 **현황 실측 + 심각도/비용 재평가 + 실행 가이드 초안** 까지만.
>
> 연관: [todo.md](todo.md) (세션별 체크리스트) · [worklog.md](worklog.md) (완료 이력 + 교훈 §7a~§7h) · [security-todo.md](security-todo.md) · [plan/10-risks.md](plan/10-risks.md)

**최종 갱신**: 2026-04-24
**감사 세션 환경**: Opus 4.7 (joojm RDP, Admin PS)
**감사 시점 운영 상태**: 7 서비스 Running / 5 경로 200·200·200·200·403 / 개발 트리 HEAD `4f304bb`

### 세션 중 감사 전 복구한 이상 1 건

감사 시작 시 `Get-Service` 결과 `caddy`/`IPBan` 이 Stopped. 조사: 2026-04-24 15:40:19 에 6 서비스가 SCM 7034 로 동시 종료 → 직후 plane-* 4 개는 NSSM 재설치·재기동 성공, **caddy 만 재기동 실패 + IPBan 은 재기동 시도 없음**. 원인은 구 caddy 프로세스 **PID 14764** (parent PID 13344 NSSM wrapper 가 이미 증발한 orphan) 가 `:80` 을 계속 점유 중이라 새 NSSM 이 bind 실패 → throttle. 5 경로 loopback smoke 가 정상 200/200/200/200/403 으로 나온 것은 이 orphan 이 `:80` 에서 여전히 서빙 중이었기 때문 — **관리 주체 없는 프로세스**였다.

복구 절차: `Stop-Process 14764 -Force` → `:80` 해제 polling (500ms 단위, 30s cap) → `Start-Service caddy IPBan` → 7 서비스 Running + `:80` owner = PID 15748 caddy.exe (NSSM 정상 관리) + 5 경로 smoke 재확인. 소요 10 초 미만. `IPBan` 은 §7a Delayed Auto Start 방어 적용본이 그대로이며 `AppExit Default Restart` 가 발동 안 한 이유는 별도 추적 (§B 권고 P5 신규 TODO).

---

## 감사 범위

todo.md 의 보안 세션 체크리스트 (원본은 security-audit-2026Q2.md §8)(A~G) 를 1:1 로 따른다. 각 항목 구조:

1. **현 상태** — 실측 스냅샷 (수치/ACL/설정값)
2. **핵심 발견** — 이 세션에서 새로 확인된 사실
3. **권고 (실행 가이드 초안)** — 변경 절차 요약
4. **심각도 × 구현비용 × 실행 세션 예상**

| # | 항목 | 심각도 | 구현비용 | 다음 세션 우선순위 |
|---|---|---|---|---|
| A | joojm 계정 강화 | **High** | ~3h | **1 순위** (§B 와 병합) |
| B | 외부 RDP/HTTP 방어 | **Critical** | ~4h | **1 순위** (§A 와 병합) |
| C | 도메인 + HTTPS 전환 | Medium | ~5h + 도메인 비용 | 3 순위 (도메인 확보 후) |
| D | 업로드 AV 스캔 | Medium | ~4h | 4 순위 |
| E | 비밀값 DPAPI 이관 | Medium | ~2h | 2 순위 |
| F | 백업 AES-256 암호화 | High | ~3h | 2 순위 (§E 와 함께 묶기) |
| G | Redis → Memurai 전환 | Low (현재) | ~4h + 공식 문서 재조사 | 보류 (심각 신규 CVE 발생 시) |

상세는 아래 §A~§G. 매트릭스 전체는 [§8 심각도 × 구현비용 매트릭스](#8-심각도--구현비용-매트릭스) 에.

---

## §A joojm 계정 강화

### 현 상태

**`Get-LocalUser joojm`**:
- `Enabled = True`, `PasswordRequired = True`, `PasswordExpires = <empty>` (만료 없음)
- `PasswordLastSet = 2026-04-07` (17 일 전)
- `LastLogon = 2026-04-24 11:07:11` (오늘 RDP 재로그인)
- `FullName = "Joo Jeong Min"`, `Description = "Admin"`

**그룹 멤버십** (`Get-LocalGroupMember`):
- **Administrators**: `FKNPOC83BVCHY1L\joojm`, `FKNPOC83BVCHY1L\plane-admin`
- Users · Remote Desktop Users · docker-users · OpenSSH Users 도 joojm 소속

**비밀번호 길이**: **10 자** (worklog §7 에 기재된 값, 감사 중 값 자체는 미노출)

**`SeRemoteInteractiveLogonRight`**: `*S-1-5-32-544 (Administrators)`, `*S-1-5-32-555 (Remote Desktop Users)` — joojm 양쪽 모두 소속이라 RDP 가능.

### 핵심 발견

**발견 1 — 시스템 password/lockout 정책 전 항목 공백** (`secedit /export /areas SECURITYPOLICY` 의 `[System Access]` 섹션 원문):

```
MinimumPasswordLength = 0
PasswordComplexity = 0
MaximumPasswordAge = -1
LockoutBadCount = 0
PasswordHistorySize = 0
```

즉 **OS 레벨 비번 강제 정책이 하나도 걸려있지 않다**. IPBan 만이 실질적 방어.

**발견 2 — 공격자가 joojm 의 FullName 과 호스트명을 타겟팅 중**:

최근 30 일 Security Event Log `4625` (로그온 실패) 분석 결과 총 **15,786 회**, 일평균 **526 회**.

Top TargetUserName 15:

| Count | UserName | 해석 |
|---|---|---|
| 9,292 | Administrator | 빌트인 admin — Enabled=True 지만 Deny* 로 무력화 |
| 2,252 | FKNPOC83BVCHY1L | 호스트명 그대로 |
| **1,505** | **Joo Jeong Min** | joojm 의 FullName (공백 포함 그대로) |
| 1,337 | fknpoc | 호스트명 축약/소문자 |
| 490 | jeong | joojm FullName 부분 |
| 110 | ADMIN |   |
| 98 | USER |   |
| 40 | Joo |   |
| 24 | plane | plane 서비스 계정도 시도됨 |
| 15 | administrador |   |

**joojm (정확명) 시도: 0 회** — username 자체는 공격자에게 유출되지 않음. 하지만 FullName "Joo Jeong Min" 과 hostname 파생이 모두 수백~천 단위로 카운트 — **RDP NLA 응답 또는 SMB/NetBIOS 에서 FullName 이 열거 가능**한 상태로 추정 (정확한 누출 경로는 이 세션 범위 밖). 공격자가 `joojm` 을 사전 단어에서 뽑아낼 확률은 낮지만, **FullName 기반 공격은 이미 진행 중**.

Top Source IP (30d): `121.134.9.141 (KR) 2,249`, `91.238.181.10 (BG) 1,190`, `91.238.181.8 728`, `103.179.96.116 (VN) 410`, ... — 지역 분산. IPBan 이 누적 670 건 ban, 251 건 unban (ExpireTime 1 일 이후 자동 해제).

**발견 3 — Administrators 그룹 멤버십 분리 가능**:

현재 Administrators 멤버는 joojm + plane-admin 2 인. plane-admin 은 `SeDenyRemoteInteractiveLogonRight` 에 속해 RDP 불가하지만 콘솔 로그인은 가능 (VM 직접 접속 시). 따라서 joojm 을 Administrators 에서 내리고 관리자 작업은 `runas /user:plane-admin` 으로 승격하는 **최소 권한 모델**이 가능. plane-admin 의 비번 또한 16 자+ 로 같이 승격해야 의미 있음.

*trade-off*: joojm 이 docker-users / OpenSSH Users 에 별도 속해 있어 Docker/SSH 세션은 영향 없음. 단, `pip install`, NSSM 재등록, `Get-Service` stop/start 등 매 작업마다 runas 프롬프트가 필요해 실무 편의성 감소. 운영 1 인 환경에선 편의성 손실이 커서 이번 순위는 낮춤 (P4).

### 권고 (실행 가이드 초안)

**P1 — joojm 비밀번호 16 자+ 로 재설정 (즉시)**:

```
# (1) RDP 세션에서 Ctrl+Alt+Del → "Change a password" 로 인터랙티브 변경
#     (net user joojm <새비번> 은 명령줄 history 에 남으므로 금지)
# (2) 변경 후 확인
net user joojm   # PasswordLastSet 가 오늘 날짜인지
# (3) joojm 비번은 plane 계정과 달리 서비스 의존성 없음 —
#     사용자 개인 기록 수단에만 저장. ops/*.pass 에 저장 금지.
# (4) 기존 열려있던 RDP 세션들은 next logon 시 재인증 — 필요 시 전부 끊기
query session
```

**P2 — 시스템 password/lockout 정책 도입**:

```
# (a) 최소 길이 + 복잡도 — secedit 템플릿으로
secedit /export /cfg $env:TEMP\sec.inf
# sec.inf 편집: MinimumPasswordLength=16, PasswordComplexity=1
# LockoutBadCount 는 plane 계정과 충돌 우려 — plane 만 제외하려면 그룹 정책
# 이 필요한데 로컬 PC 레벨에선 계정별 lockout 정책 분리 불가.
# 대안: LockoutBadCount 는 10 (여유) + LockoutDuration 15 분 (관리자가 수동
# 복구할 시간 확보) + plane 서비스가 비번 오류로 자동 복구되는지 §7 교훈으로
# 재검증 필요.
secedit /configure /cfg $env:TEMP\sec.inf /db $env:TEMP\sec.sdb
# (b) 변경 후 확인
secedit /export /cfg $env:TEMP\sec.inf
# MinimumPasswordLength = 16, PasswordComplexity = 1, LockoutBadCount = 10
```

*주의*: LockoutBadCount 도입 전 **plane 계정이 lockout 에 민감한지 실측** 필요. NSSM 재기동 루프에서 비번 오인식이 10 회 연속 누적되면 plane 계정 잠김 → 서비스 전체 다운 → 3곳 동기화 (§7) 복구 절차 필요. 다음 세션에서 격리 실측 후 도입.

**P3 — 빌트인 Administrator 비활성**:

```
# Deny* 로 이미 로그온 불가하지만 공격자 시도 9,292 회 중.
# Disable 하면 공격자가 "계정 없음" 응답을 받아 시도 자체 감소.
Disable-LocalUser -Name Administrator
# 비상 관리자는 plane-admin 이 대체 (콘솔 전용, RDP 불가).
# plane-admin 의 비번도 같이 16 자+ 로 승격 (ops/.plane_pass 의 plane 계정
# 과 혼동 금지 — plane-admin 비번은 사용자 개인 기록 수단에만).
```

**P4 — joojm Admins 그룹 분리 (선택, 편의성 trade-off)**:

```
# 평시 joojm 은 Users + Remote Desktop Users 로 충분.
Remove-LocalGroupMember -Group Administrators -Member joojm
# 관리자 작업 시:
runas /user:plane-admin "powershell"
# docker-users, OpenSSH Users 는 별도 그룹이라 영향 없음.
# 단 plane-admin 이 RDP 불가라 runas 프롬프트가 실행될 때 credential dialog
# 가 RDP 세션 내에서 뜬다 — 실측 필요 (CredUI 가 RDP 에서 정상 동작하는지).
```

### 우선순위

- **심각도**: **High** (비번 10자 + OS 정책 공백 + FullName 타겟팅 확인)
- **구현비용**: P1 0.5h + P2 1h (+ plane lockout 실측 1h) + P3 0.1h + P4 0.5h + 회귀 smoke 1h = **약 3~4h**
- **예상 실행**: 다음 보안 세션 #1 (P1+P3 먼저, P2 는 plane 계정 lockout 실측 이후)

### [실집행] 2026-04-24 보안 세션 #1

**P2 (password policy) 완료**:

`secedit /export /areas SECURITYPOLICY` → `[System Access]` 편집 (UTF-16 LE BOM) → `secedit /configure /db ... /cfg ... /areas SECURITYPOLICY /log ... /quiet` (exit 0, `The task has completed successfully`). 변경된 키:

| 키 | pre | post |
|---|---|---|
| `MinimumPasswordLength` | 0 | **16** |
| `PasswordComplexity` | 0 | **1** |
| `LockoutBadCount` | 0 | **10** |
| `ResetLockoutCount` | (없음) | **15** |
| `LockoutDuration` | (없음) | **15** |
| `PasswordHistorySize` | 0 | **5** |

*자동 추가된 키* — `AllowAdministratorLockout = 1` (Windows Server 2025 default, LockoutBadCount 활성 시 Administrators 그룹 구성원도 lockout 대상). 이것은 **joojm 도 lockout 될 수 있음** 을 의미 — 하지만 IPBan 이 5회 실패에서 IP 차단하므로 10회 누적 전에 공격 IP 가 끊겨 실 joojm lockout 확률은 낮음. joojm 16자+ 재설정(P1) + IPBan BlacklistRegex(§B P3) 조합으로 mitigated.

plane 계정 lockout 누적 위험 사전 분석 (실집행 전 수행):
- Security 4625 30 일 plane-targeted 24건 전수 분석 (`LogonProcessName`, `LogonType`, `IpAddress` 추출)
- 전부 **로컬** (`IpAddress = "-"`), LogonProcessName 전부 **Advapi** (LogonUser API), LogonType 분포 5 (Service) 20건 · 4 (Batch) 3건 · 2 (Interactive) 1건
- 일평균 Type 5 실패 0.67 건 — `LockoutBadCount=10 + LockoutObservationWindow=15m` 안전 마진 크게 확보
- 외부 공격자의 plane username 시도 0건 (공격자는 plane 을 모름)

**P3 (빌트인 Administrator Disable) 완료**:

`Disable-LocalUser -Name Administrator` → `Enabled=False`, `secedit EnableAdminAccount=0` 일치 확인. Administrators 그룹 멤버십은 그대로 (`Get-LocalGroupMember` 에 여전히 나오나 disable 된 사용자는 로그온 불가). 유효 관리자는 joojm + plane-admin 2 인.

**P1 (joojm 16자+ 재설정) 완료**:

RDP 세션에서 Ctrl+Alt+End (또는 RDP 메뉴 "Send Ctrl+Alt+Del") → "Change a password" 경로로 사용자 인터랙티브 변경. 정책 (MinimumPasswordLength=16 / PasswordComplexity=1 / PasswordHistorySize=5) 이 **enforce 상태에서** 새 비번 수용됨 → 16자+ 복잡도 충족 확인.

확인: `Get-LocalUser joojm` → `PasswordLastSet = 2026-04-24 17:18:43`, `LastLogon = 2026-04-24 17:18:43` (기존 PasswordLastSet `2026-04-07` 에서 갱신). 새 비번은 사용자 개인 기록 수단에만 보관 (ops/*.pass 또는 파일 기록 금지 — joojm 은 plane 계정과 달리 서비스 의존성 없음). 5 경로 smoke 200/200/200/200/403 정상, 서비스 무영향.

**P4 (joojm Admins 그룹 분리) — Q3=b 보류**:

사용자 결정으로 이 세션에선 진행 안 함. 1인 운영 편의성 trade-off 가 커서 별도 세션에서 재평가. plane-admin 비번 16자+ 승격(사용자 개인 기록 수단 갱신) 과 함께 묶어 결정 예정.

### 현 상태

**방화벽 인바운드 Allow 규칙** (`Get-NetFirewallRule -Direction Inbound -Enabled True` 중 well-known 포트):

| DisplayName | Action | Profile | Proto | LocalPort | RemoteAddress |
|---|---|---|---|---|---|
| 원격 데스크톱 - 사용자 모드(TCP-In) | Allow | Any | TCP | 3389 | **Any** |
| 원격 데스크톱 - 사용자 모드(UDP-In) | Allow | Any | UDP | 3389 | **Any** |
| OpenSSH SSH Server (sshd) | Allow | **Private** | TCP | 22 | Any |
| Allow Inbound tcp/80 (Plane Caddy) | Allow | Any | TCP | 80 | Any |

- SSH 22 는 **Private 프로필만 Enabled** — 공인 IP 는 Public 프로필로 매핑되어 **실질 차단** (이 환경에선 OK).
- 443 규칙 **없음** (HTTPS 미도입 — §C).

**IPBan 설정** (`ipban.config`):
- `FailedLoginAttemptsBeforeBan = 5`
- `ExpireTime = 01:00:00:00` (1 일)
- `Whitelist`, `WhitelistRegex`, `Blacklist`, `BlacklistRegex`, `UserNameWhitelist` 전부 **비어있음**
- `FailedLoginAttemptsBeforeBanUserNameWhitelist = 20`
- `ClearBannedIPAddressesOnRestart = false`

**IPBan 운영 통계** (`plane-logs/ipban/stdout.log`, 누적):
- `Banning ip address` 670 건
- `Un-banning ip address` 251 건
- `Login failure` 1,518 건
- 최근 tail 200 줄 기준 ban 34 건 (수 시간 내)

**VPN/터널 현황**:
- **Tailscale: 없음**
- **Cloudflare WARP: 없음**
- `cloudflared.exe` 는 winget user-local 경로 (`C:\Users\joojm\AppData\Local\Microsoft\WinGet\Links\cloudflared.exe`) 에만 존재 — **joojm 전용 설치**로 plane 서비스 계정 접근 불가. worklog §2.2 의 "cloudflared 2025.8.1" 기재와 현 상태는 "있긴 하지만 운영 사용 불가" 로 일치하지 않음. Caddy winget 교훈(§7)과 동일 — `tools/cloudflared/` 공용 경로로 이관 필요.

### 핵심 발견

**발견 1 — 3389 Any 노출이 최대 리스크 지점**:

§A 발견 2 의 30일 15,786 회 4625 중 **대부분이 RDP 경유** (port 3389 분석은 별도 세션에서 netlogon 확인 가능하지만 현 정황상 거의 확정). IPBan 이 일일 평균 22 건 ban 으로 단기 방어하지만, ExpireTime 1 일 + 공격자 IP 순환으로 **지속적 tarpit 상태**.

**발견 2 — IPBan ExpireTime 1 일은 짧음**:

공격자가 하루 후 같은 IP 로 재시도 가능. 중간 수준 공격자는 수백 IP pool 을 rotate 하지만, **long-tail 단일 IP 반복 공격** (상위 5 IP 가 30 일 동안 1 만 회 이상 시도) 에 대해서는 ExpireTime 을 7~30 일로 늘리는 편이 효과적.

**발견 3 — BlacklistRegex 공백**:

§A 발견 2 의 Top UserName 대부분이 **이 시스템에 존재하지 않는 계정** (Administrator 는 Disable 후, FKNPOC83BVCHY1L/fknpoc 은 hostname). 존재하지 않는 계정 시도는 **1 회만으로 ban** 해도 오탐 위험 없음. IPBan 의 `BlacklistRegex` 는 그런 목적으로 설계됨.

**발견 4 — 세션 초반 IPBan Stopped 동안 `AppExit Default Restart` 미발동**:

15:40:19 에 SCM 7034 로 IPBan 종료 후 **AppExit Default Restart + AppRestartDelay 30s 가 작동하지 않았다**. 수동 `Start-Service` 로만 복구됨. 이전 §7a 교훈은 "7 차 재부팅 실측으로 해소 확정"이었는데 이번은 재부팅이 아닌 "누군가의 register-services.ps1/register-caddy.ps1 재실행이 IPBan 도 SCM 종료" 시나리오. `register-*.ps1` 이 IPBan 을 touch 하지 않는데 왜 동시 종료됐는지 별건 조사 필요.

### 권고 (실행 가이드 초안)

**P1 — RDP 3389 Remote IP allowlist (최고 ROI)**:

```
# joojm 접속 IP 가 고정이면 가장 즉효.
# 예: 회사 1.2.3.0/24 + 집 5.6.7.8/32
Set-NetFirewallRule -DisplayName "원격 데스크톱 - 사용자 모드(TCP-In)" `
  -RemoteAddress @("1.2.3.0/24","5.6.7.8/32")
Set-NetFirewallRule -DisplayName "원격 데스크톱 - 사용자 모드(UDP-In)" `
  -RemoteAddress @("1.2.3.0/24","5.6.7.8/32")
# 반영 확인
Get-NetFirewallRule -DisplayName "원격 데스크톱*" | Get-NetFirewallAddressFilter
```

*선결 조건*: joojm 의 접속 출처 IP 가 고정이어야 함. 유동 (KT 인터넷 등) 이면 **P2 Tailscale** 필수.

**P2 — Tailscale 도입 (중장기, 유동 IP 대응)**:

```
# (a) winget install -e --id Tailscale.Tailscale
# (b) 콘솔 로그인 후 tailscale up --auth-key=<one-time key>
#     (Windows Service 로 tailscaled 가 등록됨, operator=joojm 권장)
# (c) joojm 의 기기 (노트북/폰) 에 Tailscale 설치, 동일 tailnet
# (d) RDP 규칙의 RemoteAddress 를 Tailnet 대역 100.64.0.0/10 으로 축소
Set-NetFirewallRule -DisplayName "원격 데스크톱 - 사용자 모드(TCP-In)" `
  -RemoteAddress "100.64.0.0/10"
# (e) joojm 기기에서 tailscale ssh 또는 MagicDNS 호스트명으로 RDP 접속
#     (예: mstsc.exe /v:fknpoc83bvchy1l.tail-xxxx.ts.net)
```

비용: Free tier (3 users / 100 devices) 로 충분.

**P3 — IPBan 정책 강화**:

```
<!-- tools/ipban/ipban.config -->
<!-- (a) ExpireTime 1d → 7d -->
<add key="ExpireTime" value="7.00:00:00" />
<!-- (b) Blacklist 에 미사용 UserName 패턴 추가 (1 회 시도 즉시 ban) -->
<add key="BlacklistRegex" value="^(administrator|admin|ADMIN|root|user|USER|guest|test|fknpoc.*|FKNPOC.*)$" />
<!-- "Joo Jeong Min", "jeong", "Joo" 는 joojm FullName 이므로 제외
     (본인이 로컬 로그인 시 FullName 이 display 되는 경우를 고려 - 오탐 회피). -->
<!-- (c) 반영: IPBan 서비스 재기동 -->
```

```powershell
Restart-Service IPBan
```

**P4 — cloudflared 공용 경로 이관**:

```powershell
$src = "C:\Users\joojm\AppData\Local\Microsoft\WinGet\Links\cloudflared.exe"
$dst = "D:\Workspace\plane-app\tools\cloudflared"
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Copy-Item $src "$dst\cloudflared.exe" -Force
# ACL 은 tools/caddy 와 동일 — plane 서비스 계정 read+execute 보장 확인
icacls $dst /inheritance:r /grant "NT AUTHORITY\SYSTEM:(OI)(CI)F" `
  "BUILTIN\Administrators:(OI)(CI)F" "FKNPOC83BVCHY1L\plane:(OI)(CI)RX"
```

**P5 — IPBan AppExit Restart 미발동 별건 조사** (신규 TODO):

15:40:19 SCM 7034 이후 `AppExit Default Restart` + `AppRestartDelay 30s` 가 작동하지 않은 원인 조사. `nssm get IPBan AppExit Default` / `nssm get IPBan AppThrottle` 현재 값 확인 필요. IPBan.exe 자체가 exit code 0 (정상 종료 시그널) 로 빠졌다면 NSSM 은 restart 하지 않음 — stdout.log 의 종료 직전 메시지 분석 필요.

### 우선순위

- **심각도**: **Critical** (3389 Any + 10자 비번 결합이 가장 직접적 공격면)
- **구현비용**: P1 0.5h · P2 3h · P3 0.5h · P4 0.2h · P5 1h (조사만) = **약 4h**
- **예상 실행**: 다음 보안 세션 #1 (§A 와 같은 세션에서 P1+P3 먼저, P2 는 Tailscale 도입 결정 후)

### [실집행] 2026-04-24 보안 세션 #1

**P3 (IPBan 정책 강화) 완료**:

`tools/ipban/ipban.config.bak-20260424-170647` 원본 백업 후 XML 편집:

| 키 | pre | post |
|---|---|---|
| `ExpireTime` | `01:00:00:00` (1 d) | **`7.00:00:00`** (7 d) |
| `BlacklistRegex` | `""` | `^(administrator\|admin\|ADMIN\|Administrator\|root\|ROOT\|user\|USER\|guest\|GUEST\|test\|TEST\|fknpoc.*\|FKNPOC.*)$` |
| `FailedLoginAttemptsBeforeBan` | 5 | **5 (유지)** |

`Restart-Service IPBan` → Running 확인, stdout.log 에 `"IPBan is running correctly"` 도달 후 `"Updating firewall with 0 entries"` (기존 ban 은 ipban.sqlite 에서 load, ExpireTime 변경된 값으로 재평가). `Joo Jeong Min`, `jeong`, `Joo` 는 joojm FullName 파생이므로 blacklist 제외 — 본인이 RDP 로그인 실패 시 오탐 회피.

**P4 (cloudflared tools/ 이관) 완료**:

winget Links `C:\Users\joojm\AppData\Local\Microsoft\WinGet\Links\cloudflared.exe` 는 SymbolicLink. Target resolve → `C:\Users\joojm\AppData\Local\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe` (68,513,948 bytes, v2025.8.1).

`D:\Workspace\plane-app\tools\cloudflared\cloudflared.exe` 로 복사. ACL (`icacls /inheritance:r /grant`):
- `NT AUTHORITY\SYSTEM:(OI)(CI)F`
- `BUILTIN\Administrators:(OI)(CI)F`
- `FKNPOC83BVCHY1L\plane:(OI)(CI)RX`

Caddy 이관과 동일 패턴. `cloudflared --version` → `cloudflared version 2025.8.1 (built 2025-08-21-1534 UTC)` 정상. 현 시점 cloudflared 는 등록 서비스 없음 — 도메인 확보(§C) 및 Cloudflare Access 도입 결정 시에만 활용.

**P5 (IPBan AppExit Restart 미발동 조사) 진행 — 개선안은 다음 세션 이월**:

- NSSM `AppExit Default = Restart` 정상 설정 확인 (`nssm get IPBan AppExit Default`)
- stdout.log 의 15:40:19 종료 **직전 메시지 없음** (silent exit). 정상 운영 마지막 라인 `2026-04-24 15:13:47.8778|WARN|IPBan|Banning ip address: 36.50.135.0`, 다음 라인은 **16:17:40 의 새 인스턴스 기동** (세션 시작 시 수동 `Start-Service IPBan` 복구)
- SCM 7034 (15:40:19) → 7036 (Running, 16:17:40) 사이 **재기동 시도 이벤트 없음** — AppRestart 자체가 발동 안 했거나 발동했으나 AppThrottle 넘지 못하고 실패
- **가설**: 15:40:19 동시 종료가 register-services.ps1 / register-caddy.ps1 재실행 시퀀스에서 **SCM 의 "intentional stop"** 으로 기록되어 NSSM 의 AppExit 룰 무관하게 서비스가 `SERVICE_STOPPED` 유지. AppExit 은 exit code 기반 판정이지만 SCM 이 `StopService` 를 명시 호출하면 AppExit 경로로 가지 않음 (NSSM doc 참조)
- **확정하려면**: `nssm get IPBan AppThrottle` / `AppRestartDelay` 의 raw 값 + 15:40:19 전후 System/Application event 전수 + **register-*.ps1 이 IPBan 을 어떻게 건드렸는지** 추적 필요. register-services.ps1 소스에는 IPBan touch 코드 없음 → 원인은 다른 경로 (예: `nssm set plane-* DependOnService Redis/IPBan` 같은 의존성이 있다면 plane-* restart 시 IPBan 도 연쇄 영향)
- **개선안 후보**:
  (a) NSSM `AppExit 0 Restart` 추가 — exit 0 도 재기동 (단 register-*.ps1 재실행 시 race)
  (b) 별도 감시 Task (`IPBan-watchdog`) 를 Task Scheduler 에 등록하여 `Get-Service IPBan` 이 Stopped 이면 Start (§7 Boot Task 패턴 재사용)
  (c) register-*.ps1 에 "IPBan 을 건드리지 않도록" explicit guard + 종료 시 `Start-Service IPBan` 명시 호출
- **현 세션 결론**: 현상 기록 + 개선안 (b) 를 다음 보안 세션(보안 #1 남은 작업 또는 후속)에 추가. worklog §7h 신규 교훈으로 편입

**P1 (RDP 3389 Remote IP allowlist) — Q4=c 보류**:

사용자 결정으로 이 세션에선 진행 안 함. joojm 접속 출처 IP 의 고정 여부 확정 또는 Tailscale 도입 결정 후 별도 세션 진행. **현 상태 Critical 완화 수단은 §B P3 IPBan 강화**만으로. 30일 15,786 건 공격 중 가장 많은 Administrator (9,292건) 는 §A P3 Disable-LocalUser 로 목록에서 사라짐 (공격자가 계속 시도해도 account 부재 응답) → 공격 밀도 단기 감소 기대.

**P2 (Tailscale 도입) — Q4=c 보류와 동일**.

---

## §C 도메인 + HTTPS 전환

### 현 상태

**현 Caddyfile** (`ops/Caddyfile`):
- `:80` 단일 수신, HTTPS/`:443` 없음
- `admin off` (§7a #5 교훈 반영)
- `storage file_system { root "D:/Workspace/plane-data/caddy" }` (§7a #5 교훈 반영)
- space SPA 4종 보안 헤더 (X-Frame-Options · Referrer-Policy · X-Content-Type-Options · X-DNS-Prefetch-Control)
- **`Strict-Transport-Security` 헤더 없음** — 주석에 "HTTPS 전환 후 추가" 의도 명시됨. **HTTP 에서 HSTS 를 보내는 것은 오류**이므로 현 상태 올바름.

**site.env** 관련 키:

```
PUBLIC_HOST=222.234.220.199
PUBLIC_SCHEME=http
#   PUBLIC_HOST=plane.example.com
#   PUBLIC_SCHEME=https
```

**Django 보안 설정** (`apps/api/plane/settings/`):
- `common.py:33 ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")` — default `"*"` (위험)
- `common.py:312 SESSION_COOKIE_SECURE = secure_origins` (env 유도 변수)
- `common.py:325 CSRF_COOKIE_SECURE = secure_origins`
- `common.py:327 CSRF_TRUSTED_ORIGINS = cors_allowed_origins`
- `production.py:15 SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` — Caddy 가 보내는 `X-Forwarded-Proto` 존중 (정상)
- `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` 전부 **미정의** — HTTPS 전환 시 Django 측에도 추가 필요

### 핵심 발견

**발견 1 — HSTS 누락은 현 HTTP 상태에선 의도적으로 맞음**:

Caddyfile 주석 "Strict-Transport-Security 는 HTTPS 전환 후 추가" 는 정확. HTTP 응답에 HSTS 헤더를 포함하면 브라우저가 host 를 HSTS 목록에 등록 → 이후 HTTP 접속이 **브라우저 측에서 HTTPS 로 강제 upgrade** 되어 도메인 없는 상태에선 접근 불가. 전환 시점까지 유지.

**발견 2 — ALLOWED_HOSTS=`"*"` 는 도메인 확보 전까진 필요악**:

현재 운영은 공인 IP 직접 접근 (`http://222.234.220.199/`) + 로컬 loopback (`http://127.0.0.1/`). `ALLOWED_HOSTS` 를 구체화하려면 두 값을 명시해야 하는데 한국 ISP 는 IP 변동 가능성 존재. 도메인 확보 후 `plane.example.com, 127.0.0.1` 로 좁히는 것이 자연스러움.

**발견 3 — Caddy `auto_https`**:

Caddy 는 site 블록에 domain 이 명시되면 **자동으로 Let's Encrypt ACME HTTP-01 challenge** 수행. `:80` 표기는 IP/포트 기반이라 ACME 불가. 전환 시 `{domain}` 표기 + `:80 { redir https://{host}{uri} }` 분리 또는 `{domain}, {domain}:80 { ... redir_if_http }` 통합 필요.

### 권고 (실행 가이드 초안)

**P1 — 도메인 확보 (외부 의존성)**:

- 가비아/Cloudflare Registrar/Freenom 등에서 도메인 구매
- DNS A 레코드 → `222.234.220.199`
- CAA 레코드 `letsencrypt.org` 추가 권장 (인증서 발급자 제한)
- AAAA 없음 (IPv6 미운영)

**P2 — 방화벽 443 인바운드 Allow**:

```powershell
New-NetFirewallRule -DisplayName "Allow Inbound tcp/443 (Plane Caddy HTTPS)" `
  -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

**P3 — Caddyfile HTTPS 전환 (예시 diff)**:

```
# BEFORE (현 상태)
:80 {
  ...
}

# AFTER
{
  log { ... }
  storage file_system { root "D:/Workspace/plane-data/caddy" }
  admin off
  # email 은 Let's Encrypt 알림 수신 용. 미지정 시 경고.
  email admin@plane.example.com
}

# HTTP → HTTPS 영구 redirect
:80 {
  redir https://{host}{uri} 308
}

# HTTPS site — Caddy 가 자동 ACME 발급 + 갱신
plane.example.com {
  request_body { max_size 50mb }
  header {
    # HTTPS 상태에서만 안전
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    # preload 는 submit 후 추가 (hstspreload.org)
  }

  # (기존 handle 블록들 그대로 — /uploads/*, /api/*, /auth/*, /static/*, /live/*,
  #  handle_path /spaces/*, handle_path /god-mode/*, fallback handle)
  ...
}
```

**P4 — site.env 전환**:

```
PUBLIC_HOST=plane.example.com
PUBLIC_SCHEME=https
# 추가
ALLOWED_HOSTS=plane.example.com,127.0.0.1
# CSRF_TRUSTED_ORIGINS 는 cors_allowed_origins 유도 변수 → WEB_URL 기반 이미 갱신됨
```

**P5 — Django 보안 env 추가**:

```
# site.env 에 추가
SECURE_SSL_REDIRECT=1
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=1
SECURE_HSTS_PRELOAD=0     # preload submit 후 1 로 승격
```

*주의*: `SECURE_SSL_REDIRECT=1` 은 Caddy 가 이미 308 redirect 하므로 중복이지만, Django 응답 path 를 거치는 경우 방어 추가 (defense-in-depth). `SECURE_PROXY_SSL_HEADER` 는 production.py 에 이미 정의.

**P6 — 재빌드 + 재등록**:

```powershell
cd D:\Workspace\plane-app
.\ops\render-envs.ps1                        # site.env → apps/*/.env
pnpm turbo build                             # VITE_* 번들에 새 URL inline
.\ops\register-services.ps1                  # plane-* 4개 재등록 + env 재주입
.\ops\register-caddy.ps1                     # caddy 재등록
# HTTPS smoke
Invoke-WebRequest -Uri "https://plane.example.com/" -SkipCertificateCheck:$false
```

**P7 — HSTS preload submit (선택, 안정화 후)**:

`hstspreload.org` 에 submit → 브라우저 bundle 에 등록 → 취소 절차 복잡. 최소 1 주 soak 후.

### 우선순위

- **심각도**: **Medium** (현 HTTP 상태에서도 Plane 인증은 세션 쿠키 + HMAC 기반 정상 작동. 다만 MITM 위험 + 세션 탈취 가능성 상시)
- **구현비용**: 도메인 확보 (외부) + P2~P7 약 5h
- **예상 실행**: 3 순위 — 도메인 확보 후 별도 세션

---

## §D 업로드 AV 스캔

### 현 상태

**Windows Defender** (`Get-MpComputerStatus`):
- `AntivirusEnabled = True`, `AMServiceEnabled = True`
- `RealTimeProtectionEnabled = True`, `OnAccessProtectionEnabled = True`
- `IoavProtectionEnabled = True` (인터넷 다운로드 파일 자동 스캔)
- `BehaviorMonitorEnabled = True`
- `AntivirusSignatureLastUpdated = 2026-04-24 03:07:39` (최신)
- **`FullScanAge = 4294967295` (UInt32.MaxValue)** — **full scan 수행 이력 없음**
- `ExclusionPath / ExclusionExtension / ExclusionProcess = 0 entries` — uploads 디렉토리도 실시간 보호 대상

**`MpCmdRun.exe`**: `C:\Program Files\Windows Defender\MpCmdRun.exe` 존재 (on-demand 스캔 CLI 사용 가능).

**Plane 업로드 파이프라인 방어**:
- `settings.FILE_SIZE_LIMIT` HMAC content-length-range — §1 검증에서 5MB bonus 실측 확인
- USER_AVATAR/USER_COVER 는 MIME allowlist (`image/jpeg|png|webp|jpg|gif`) — `apps/api/plane/app/views/asset/v2.py:127~141`
- 일반 이슈 첨부(ATTACHMENT) 는 `request.data.get("type", "image/jpeg")` 를 그대로 수용 — **서버측 MIME allowlist 없음**
- magic byte 검증 (`python-magic` 등) **없음**
- 확장자 allowlist/denylist **없음**
- SVG 인라인 스크립트 sanitize **없음**
- 이미지 재인코딩 **없음**
- 업로드 완료 후 AV 스캔 **없음**

### 핵심 발견

**발견 1 — Defender 실시간 보호가 사실상 기본 방어로 작동 중**:

`OnAccessProtectionEnabled = True` + `IoavProtectionEnabled = True` 이면 plane 이 `default_storage.save()` 로 `D:\Workspace\plane-data\uploads\` 에 파일 쓰는 순간 Defender 가 **동기 차단** 가능. 악성 signature 검출 시 write 자체가 실패하며 plane 은 IOError 로 500 반환. 즉, 이미 Defender 서명 DB 에 있는 위협은 현 상태에서 차단됨.

**발견 2 — 하지만 "차단 후 응답" 이지 "업로드 전 검증" 이 아니다**:

Defender 는 파일이 FS 에 쓰일 때 트리거. 악성 파일이 업로드되어 짧은 시간 동안 FS 에 존재한 뒤 차단 → plane DB 에는 FileAsset 레코드가 먼저 생성 → `_decode_policy` 통과 → 실제 FS write 시점에 Defender 개입. **레코드와 FS 상태 불일치** 가능 (DB 에 asset 있는데 파일 없음). 백엔드에서 IOError 처리 경로 확인 필요.

**발견 3 — FullScan 한 번도 수행 안 됨**:

`FullScanAge = UInt32.MaxValue`. Defender 는 QuickScan 만 수행 중. 과거 저장된 파일 전수 검사 이력 없음 → 업로드된 파일이 signature 업데이트 전에 삽입됐다면 지금까지도 미검출 상태로 FS 에 상주 가능. `MpCmdRun -Scan -ScanType 2` (FullScan) 를 월 1회 수행 권장.

**발견 4 — MIME 서버측 재검증 부재가 주 리스크**:

클라이언트가 `type="image/png"` 로 선언하고 실제론 `.exe` 바이너리를 업로드 → Caddy 는 `/uploads/*` 403 차단하지만, presigned-download 는 HMAC 통과 시 `FileResponse` 로 반환 (`local.py:178 content_type="application/octet-stream"` 로 고정). 즉 content_type override 는 되어 있으나 **실 파일 내용이 실행 파일일 경우 로컬 저장 후 사용자가 열면 위협** — 서버 자체 공격은 아니지만 user-to-user XSS/malware distribution 벡터.

### 권고 (실행 가이드 초안)

**P1 — FullScan 월 1회 예약 Task 추가**:

```powershell
# ops/register-scan-task.ps1 신규 (worklog §7c 교훈: SYSTEM + LogonType=ServiceAccount + RunLevel=Highest)
$action = New-ScheduledTaskAction -Execute "C:\Program Files\Windows Defender\MpCmdRun.exe" `
  -Argument "-Scan -ScanType 2 -DisableRemediation"
$trigger = New-ScheduledTaskTrigger -At "03:00" -Weekly -DaysOfWeek Sunday
Register-ScheduledTask -TaskName "PlaneDefenderWeeklyFullScan" `
  -Action $action -Trigger $trigger `
  -User "SYSTEM" -RunLevel Highest
```

**P2 — 서버측 MIME 재검증 (`python-magic` / `magika`)**:

```python
# apps/api/plane/app/views/asset/v2.py / api/asset.py / space/asset.py
# presigned POST 발급 전에 확장자 + 클라이언트 선언 type 을 화이트리스트 검증
ALLOWED_TYPES = {"image/*", "application/pdf", "text/plain", "application/zip", "video/mp4", ...}
# 실 파일 magic byte 검증은 업로드 완료 후 LocalFSStorage.save override 에서
# python-magic 로 sniff → 불일치 시 파일 삭제 + FileAsset 레코드 soft delete
```

*영향 범위*: `v2.py` + `api/asset.py` + `space/asset.py` 의 POST 3곳 + `LocalFSStorage._save` override 1곳.

**P3 — 실행 가능 확장자 denylist**:

```python
DENIED_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".msi", ".scr", ".com",
                     ".jar", ".lnk", ".vbs", ".js", ".wsf", ".hta"}
# asset_key 생성 전 체크
if os.path.splitext(name)[1].lower() in DENIED_EXTENSIONS:
    return Response({"error": "Executable files are not allowed."}, status=400)
```

**P4 — MpCmdRun 동기 스캔 통합 (선택, 성능 영향 큼)**:

```python
# LocalFSStorage._save(name, content) 직후
subprocess.run(
    [r"C:\Program Files\Windows Defender\MpCmdRun.exe", "-Scan", "-ScanType", "3", "-File", full_path],
    check=True, timeout=30,
)
# 실패 (non-zero exit) 이면 파일 삭제 + IOError
```

성능: 1~3s/파일. 대용량 업로드 (50MB 제한) 에선 10s+. Celery 로 비동기 offload 권장. 우선 구현은 P2+P3 만으로 충분 — Defender 실시간 보호가 backstop.

**P5 — SVG sanitize (Tiptap 에디터 직접 임베드 경로)**:

`nh3` (bleach 후속) 또는 `bleach` 로 SVG 의 `<script>`, 이벤트 핸들러(`onload` 등) 제거. 이슈 커버/페이지 이미지 모두 해당.

### 우선순위

- **심각도**: **Medium** (Defender 실시간 보호가 최저선 방어. 다만 FullScan 이력 0 + 서버측 MIME 검증 부재는 중기 위험)
- **구현비용**: P1 0.3h · P2 2h · P3 0.5h · P4 1h · P5 0.5h = **약 4h**
- **예상 실행**: 4 순위 (§E/§F 이후)

---

## §E 비밀값 DPAPI 이관

### 현 상태

**3개 secret 파일** (`ops/`):

| 파일 | 크기 | ACL | 사용 방식 |
|---|---|---|---|
| `.plane_pass` | 11 B | SYSTEM + Administrators (FullControl) | `register-services.ps1` 가 `Get-Content` 로 읽어 `$planePlain` → NSSM set credential. `reregister-after-boot.ps1` (SYSTEM Task) 도 참조. 실행 후 메모리에서 제거 |
| `.redis_pass` | 32 B | SYSTEM + Admins (FC) + **plane (Read)** | redis.conf 의 `requirepass` 값 생성 시 참조. `site.env` 의 `REDIS_URL` 내부에 평문 embed — render-envs.ps1 이 apps/*/.env 로 전사 |
| `site.env` | 1,291 B | plane (Modify) + Admins (FC) + SYSTEM (FC) + **joojm (FullControl)** | `SECRET_KEY`, `LIVE_SERVER_SECRET_KEY`, `STORAGE_SIGNING_KEY`, `REDIS_URL` (pass 포함), `DATABASE_URL` 평문. render-envs.ps1 input |

**SDDL 요약**:
- `.plane_pass`: `O:BAG:S-1-5-21-...D:PAI(A;;FA;;;SY)(A;;FA;;;BA)` (inheritance 차단 + SYSTEM/Admins 만)
- `.redis_pass`: 위 + `(A;;FR;;;<plane SID>)` (plane 은 FR=Read)
- `site.env`: inheritance 허용 상태 (`D:AI`), joojm 에게 `0x1301bf` (Modify+) 허용

**register-services.ps1 L57~L64** 의 읽기 경로:

```powershell
# Priority: PLANE_SERVICE_PASSWORD env > ops/.plane_pass > interactive prompt.
$passFile = Join-Path $PSScriptRoot ".plane_pass"
if ($env:PLANE_SERVICE_PASSWORD) {
  $planePlain = $env:PLANE_SERVICE_PASSWORD
  Remove-Item Env:\PLANE_SERVICE_PASSWORD -ErrorAction SilentlyContinue
  ...
}
```

### 핵심 발견

**발견 1 — `.plane_pass` DPAPI 전환은 명확한 실익**:

현재는 평문 11 B + ACL. **호스트 파일 유출 (백업 복사본, 디스크 탈취)** 시 재사용 가능. DPAPI LocalMachine scope 로 래핑하면 **같은 호스트에서만 복호화 가능** → 백업/디스크 유출 시 키만 유출돼도 무력. 코드 변경도 `register-services.ps1` + `reregister-after-boot.ps1` 의 읽기 경로 1 곳씩.

**발견 2 — `.redis_pass` 는 DPAPI 실익 없음**:

plane 서비스가 실행 중일 때 자신의 계정으로 Unprotect 해야 하므로 ACL 만으로 제공되는 보호와 차이 거의 없음. LocalMachine scope 는 Admins 가 Unprotect 가능 → 현 ACL 과 공격자 그룹이 동일. **변경 권장 안 함**.

**발견 3 — `site.env` 는 ACL 타이트닝이 더 효과적**:

현재 joojm 이 FullControl 소유. joojm 계정 탈취 시 (§A 공격자 타겟 현황 고려) site.env 의 평문 secrets 전부 유출. DPAPI 래핑은 render-envs.ps1 이 Unprotect 해야 하므로 scope 가 LocalMachine 이 되어 joojm 탈취 + Admins 승격 시 결국 복호 가능 → 실익 작음. 대신 **joojm 의 FullControl 을 제거**하고 필요 시 `runas /user:plane-admin` 으로 편집하면 공격면 축소.

**발견 4 — NSSM 은 환경변수를 이미 레지스트리에 SYSTEM-only 로 저장**:

NSSM `AppEnvironmentExtra` 는 `HKLM\SYSTEM\CurrentControlSet\Services\<svc>\Parameters\AppEnvironmentExtra` 에 REG_MULTI_SZ 로 저장됨. ACL 기본은 SYSTEM + Admins Read. 즉, **서비스 등록 후 site.env 는 런타임에 더 이상 필요 없음** (§7a 의 "Plane 코드가 .env 로드 안 함" 교훈과 결합 → site.env 는 documentation + 재등록 원본 성격). 중기적으로 site.env 를 DPAPI 로 래핑하고 render-envs.ps1 만 Unprotect 하는 방식이 가능.

### 권고 (실행 가이드 초안)

**P1 — `.plane_pass` DPAPI LocalMachine 이관**:

```powershell
# 쓰기 (초기 이관 시)
$plain = Get-Content ops\.plane_pass -Raw
$plain = $plain.Trim()
$bytes = [Text.Encoding]::UTF8.GetBytes($plain)
$protected = [Security.Cryptography.ProtectedData]::Protect(
  $bytes, $null, [Security.Cryptography.DataProtectionScope]::LocalMachine)
[Convert]::ToBase64String($protected) | Set-Content ops\.plane_pass.dpapi -NoNewline
Remove-Item ops\.plane_pass -Force   # 평문 삭제
icacls ops\.plane_pass.dpapi /inheritance:r `
  /grant "NT AUTHORITY\SYSTEM:(F)" "BUILTIN\Administrators:(F)"

# register-services.ps1 / reregister-after-boot.ps1 L58~L64 수정
$passFile = Join-Path $PSScriptRoot ".plane_pass.dpapi"
if (Test-Path $passFile) {
  $b64 = (Get-Content $passFile -Raw).Trim()
  $protected = [Convert]::FromBase64String($b64)
  $plainBytes = [Security.Cryptography.ProtectedData]::Unprotect(
    $protected, $null, [Security.Cryptography.DataProtectionScope]::LocalMachine)
  $planePlain = [Text.Encoding]::UTF8.GetString($plainBytes)
  # ...
}
```

**P2 — `site.env` ACL 타이트닝**:

```powershell
# joojm FullControl 제거 — 편집은 runas 경유
icacls ops\site.env /remove:g "FKNPOC83BVCHY1L\joojm"
# 편집 필요 시:
runas /user:plane-admin "notepad D:\Workspace\plane-app\ops\site.env"
```

**P3 — `site.env` DPAPI 래핑 (중장기)**:

민감 필드만 선별해 DPAPI base64 encode 후 `site.env` 에 저장. render-envs.ps1 이 `DPAPI:` prefix 감지 시 Unprotect. 기존 평문 키와 혼용 가능:

```
# site.env 예
SECRET_KEY=DPAPI:AQAAANCMnd8BFdERjHoAwE/Cl...
REDIS_URL=DPAPI:AQAAANCMnd8BFdERjHoAwE/Cl...
PUBLIC_HOST=222.234.220.199   # 비민감 그대로
```

구현 범위: render-envs.ps1 에 헬퍼 함수 `Unwrap-Dpapi` 추가 (~20 lines) + 이관 스크립트 1개.

**P4 — `.redis_pass` 는 현 ACL 유지**:

DPAPI 래핑 효과 없음. 다만 ACL 이 의도대로 유지되는지 (`plane: Read` 만) 감사 주기마다 재확인.

### 우선순위

- **심각도**: **Medium** (현 ACL 상태에서 호스트 루트 탈취 시 어차피 전량 유출. DPAPI 는 백업/디스크 유출 시나리오에만 추가 보호)
- **구현비용**: P1 1h + P2 0.2h + P3 1h + 회귀 smoke 0.5h = **약 2~3h**
- **예상 실행**: 2 순위 (§F 백업 암호화와 묶음 — 백업에 secrets 가 포함되므로 두 항목 순차 처리가 논리적)

---

## §F DB · 업로드 백업 암호화

### 현 상태

**`ops/backup.ps1`** 145 lines 4 단계:

1. `[1/4] sqlite VACUUM INTO` — WAL checkpoint 포함 일관 덤프 (임시 `.py` 파일 argv 회피, §7c 교훈)
2. `[2/4] uploads robocopy` — `/E /R:3 /W:5 /NFL /NDL /NJH /NJS /NP`, exit 0~7 성공
3. (site.env 복사) — `Copy-Item -LiteralPath $SiteEnv`
4. `[4/4] retention sweep` — yyyyMMdd-HHmmss 패턴 매칭 14일 초과 삭제

**산출물 (`D:\Workspace\plane-data\backup\`)**:
- 일자별 디렉토리 (예: `20260424-020002/`)
- `plane.sqlite3` (VACUUM 덤프)
- `uploads/` (robocopy 미러)
- `site.env` (복사본)

**ACL** (backup root): plane (Modify) + Admins + SYSTEM. joojm 접근 없음 — site.env 의 joojm FullControl 과 달리 양호.

**암호화 툴 가용성**:
- **7z / age / gpg / openssl 전부 PATH 에 없음**
- BitLocker feature 미설치 (`Get-BitLockerVolume` cmdlet 부재)

**PlaneBackup Task**:
- SYSTEM + ServiceAccount + Highest (worklog §7c 교훈으로 확정)
- Daily 02:00
- 2026-04-22 등록 완료, 2026-04-23 / 2026-04-24 정기 run 확인

### 핵심 발견

**발견 1 — 14일치 누적 평문은 호스트 탈취 시 재해**:

백업 세트 3개 (2026-04-23/04-24) 중 `20260424-142947` 는 수동 smoke 흔적으로 uploads 실 파일 포함. 정기 백업은 `02:00`. site.env 는 현 backup.ps1 L111 의 Copy-Item 으로 매번 포함 — **14일치 × {sqlite + uploads + site.env}** 가 평문. **민감도 순위**:
- **Critical**: site.env (SECRET_KEY / STORAGE_SIGNING_KEY / REDIS_URL / DATABASE_URL). 14 일치 유출 시 동일 SECRET_KEY 로 서명된 모든 세션/토큰 무력화 필요 — Django SECRET_KEY rotate + 모든 세션 invalidate.
- **High**: plane.sqlite3. 사용자 계정/InstanceAdmin/workspace/issue 본문/권한/OAuth 토큰/cache entries 등 전체 앱 상태.
- **Medium**: uploads/. 파일별 민감도 다르지만 이슈 첨부는 잠재적으로 확장 가능.

**발견 2 — 7z 설치만 하면 최소 작업으로 AES-256 가능**:

`7z a -t7z -mhe=on -p<key>` 한 줄로 AES-256 + 헤더 암호화 (파일명 포함). backup.ps1 의 4 단계 직후 5단계로 추가하거나, 최종 디렉토리 출력을 7z 로 즉시 래핑하면 중간 평문 존재 시간 최소화.

**발견 3 — 원격 오프사이트 백업 미도입**:

백업이 같은 호스트의 `D:\` 에 존재. 디스크 장애 / 호스트 탈취 시 백업도 함께 소실. rclone + S3/B2/OneDrive 등 오프사이트 복제는 별도 후속 TODO (security-todo.md §6 "원격 오프사이트 백업" 미해결).

### 권고 (실행 가이드 초안)

**P1 — 7-Zip 설치 + backup.ps1 암호화 단계 추가**:

```powershell
# (a) 7-Zip 설치 (winget 또는 수동)
winget install 7zip.7zip
# (b) 암호화 키 생성 + DPAPI 저장 (§E P1 과 동일 패턴)
$key = [Web.Security.Membership]::GeneratePassword(32, 8)
$keyBytes = [Text.Encoding]::UTF8.GetBytes($key)
$protected = [Security.Cryptography.ProtectedData]::Protect(
  $keyBytes, $null, [Security.Cryptography.DataProtectionScope]::LocalMachine)
[Convert]::ToBase64String($protected) | Set-Content ops\.backup_key.dpapi -NoNewline
icacls ops\.backup_key.dpapi /inheritance:r `
  /grant "NT AUTHORITY\SYSTEM:(F)" "BUILTIN\Administrators:(F)"
# (c) 같은 키를 사용자 개인 기록 수단 (비번 매니저) 에도 저장 —
#     DPAPI LocalMachine 은 호스트가 파괴되면 복호화 불가
# (d) backup.ps1 [5/5] 단계 추가:
```

```powershell
# backup.ps1 [5/5] — 암호화 래핑 + 평문 디렉토리 삭제
$keyFile = Join-Path $PSScriptRoot ".backup_key.dpapi"
$b64 = (Get-Content $keyFile -Raw).Trim()
$protected = [Convert]::FromBase64String($b64)
$keyBytes = [Security.Cryptography.ProtectedData]::Unprotect(
  $protected, $null, [Security.Cryptography.DataProtectionScope]::LocalMachine)
$key = [Text.Encoding]::UTF8.GetString($keyBytes)

$7z = "C:\Program Files\7-Zip\7z.exe"
$archive = "$target.7z"
& $7z a -t7z -mhe=on "-p$key" $archive $target
if ($LASTEXITCODE -ne 0) { throw "7z failed" }
Remove-Item $target -Recurse -Force   # 평문 삭제
Write-Log ("[5/5] encrypted: {0} ({1} MB)" -f $archive, `
  [math]::Round((Get-Item $archive).Length / 1MB, 2))

# retention 은 .7z 파일 기반으로 변경
```

**P2 — 복구 훈련 절차 암호화 반영** (worklog §5.3 이월 항목):

```powershell
# 복구 테스트 (분기 1 회)
$keyBytes = [Security.Cryptography.ProtectedData]::Unprotect(
  [Convert]::FromBase64String((Get-Content ops\.backup_key.dpapi).Trim()),
  $null, [Security.Cryptography.DataProtectionScope]::LocalMachine)
$key = [Text.Encoding]::UTF8.GetString($keyBytes)
& $7z x "D:\Workspace\plane-data\backup\20260601-020002.7z" `
  -o"D:\Workspace\plane-restore" "-p$key"
# 이후 migrate --plan no-change 확인 등 (worklog §5.3 원안 유지)
```

**P3 — 원격 오프사이트 백업 (중장기)**:

rclone + B2/S3/OneDrive. 암호화된 `.7z` 만 업로드 → end-to-end 암호 유지. Backblaze B2 Free tier 10GB 로 충분 시작.

```powershell
rclone sync D:\Workspace\plane-data\backup remote:plane-backup `
  --include "*.7z" --log-level INFO
```

### 우선순위

- **심각도**: **High** (site.env 평문 14일치 = SECRET_KEY rotate 필요한 재해급 유출 시나리오)
- **구현비용**: 7z 설치 0.2h + backup.ps1 수정 1h + 복구 훈련 1h + 회귀 smoke 0.5h = **약 3h**
- **예상 실행**: 2 순위 (§E 와 같은 세션)

---

## §G Redis → Memurai 전환 (버전 호환 확인까지만)

### 현 상태

**현 Redis** (`"C:\Program Files\Redis\redis-server.exe"`):
- `Redis server v=5.0.14.1 sha=ec77f72d:0 malloc=jemalloc-5.2.1-redis bits=64 build=5627b8177c9289c`
- tporadowski/redis Windows 포트, upstream Redis 5.0.14 기반 (2023-04 EOL)

**redis.conf 주요 설정** (`ops/redis.conf`):

```
bind 127.0.0.1
port 6379
protected-mode yes
requirepass i1cu3TzbmprOw1Ozs7BPsfQNuTFg7GYM
dir D:/Workspace/plane-data/redis
maxmemory 512mb
maxmemory-policy volatile-lru
appendonly yes
appendfsync everysec
save 3600 1
save 300 100
save 60 10000
dbfilename dump.rdb
rename-command FLUSHALL ""
rename-command FLUSHDB ""
```

**AOF/RDB 산출물** (`D:\Workspace\plane-data\redis\`):
- `appendonly.aof` 37,205,205 bytes (37 MB, 2026-04-24 16:25 갱신)
- `dump.rdb` 1,979 bytes (2026-04-24 15:46)

**서비스 등록 형식**: MSI 인스톨러가 `redis-server.exe --service-run <conf>` 직접 등록 — NSSM wrap 아님.

### 핵심 발견

**발견 1 — Memurai 최신 안정 버전 = Redis 7.4.7 API 호환** (출처: [www.memurai.com/get-memurai](https://www.memurai.com/get-memurai)):

- **Memurai for Redis 4.2.2** (Stable) = Redis API 호환성 **7.4.7**
- **Memurai for Redis 8.2-rc1** (RC) = Redis API 호환성 **8.2.5**
- 사이트 문구: "Full compatibility with all Redis features" + "LRU eviction, persistence, transactions, LUA scripting, high availability, Pub/Sub, cluster, and the Modules API"
- Developer Edition: 개발/테스트 전용, 10일 후 자동 종료 + 10 IP 제한 + RAM 50%
- Enterprise Edition: production 용, 무제한, Premium support

Redis 5.0 → 7.x 는 **Redis 공식 upgrade path** 로 **AOF/RDB read-forward 호환**. 즉 Memurai 4.2.2 는 현 AOF 파일을 그대로 load 가능 (Redis 7 이 Redis 5 AOF 를 수용). 단, 첫 기동 후 rewrite 시 **Redis 7 포맷으로 overwrite** → 이후 Redis 5 롤백 불가. 마이그레이션 전 AOF 파일 별도 백업 필수.

**발견 2 — 설정 directive 호환 (공식 Redis 변천 기준)**:

- `bind`, `port`, `protected-mode`, `requirepass`, `dir`, `maxmemory`, `appendonly`, `appendfsync`, `save`, `dbfilename` — Redis 5/7 공통, 동일 의미
- `maxmemory-policy volatile-lru` — Redis 4+ 부터 동일 의미, Redis 7 에서도 deprecate 없음
- `rename-command FLUSHALL ""`, `FLUSHDB ""` — Redis 7 에서도 지원 (ACL 로 대체 가능하지만 legacy 호환 유지)
- Redis 6 도입 ACL 시스템: Memurai 7 호환이므로 사용 가능하지만 **requirepass 는 ACL 의 `default user` password 로 매핑되어 backward compat 유지**

**발견 3 — Windows 메모리 매니저 차이 (실운영 영향)**:

tporadowski 는 jemalloc-5.2.1 을 Windows 에 포팅. Memurai 는 커뮤니티 정보상 Windows-native allocator 사용 (정확 정보는 Memurai docs 확인 필요 — 이 세션 범위 밖, 404 재현). 일반적으로 Memurai 가 안정적이지만 동일 워크로드에서 메모리 단편화 특성이 다를 수 있음 — 512 MB maxmemory 우리 환경에선 실측 차이 미미할 전망.

**발견 4 — 서비스 등록 방식 차이**:

tporadowski 는 `--service-run` 자체 지원. Memurai 는 Windows Service 기본 제공 (memurai.exe + 별도 config 경로). 전환 시 **Redis MSI 제거 → Memurai 설치 → conf 경로 조정 → plane-api 의 REDIS_URL 은 `127.0.0.1:6379` 그대로 유지 가능** (포트 동일, 비번 동일).

### 권고 (실행 가이드 초안 — 실제 전환은 Memurai docs 재조사 후 별도 세션)

**P1 — 호환성 재확인 (다음 세션)**:

- Memurai docs 사이트 (`docs.memurai.com`) 접근 복원 후 다음 문서 인용 확정:
  - Redis 5 persistence 파일 호환성 공식 언급
  - redis.conf directive 지원 매트릭스
  - Migration from Redis 가이드
- 이 세션에선 `www.memurai.com/get-memurai` 랜딩만 접근 가능 (버전/edition 표만 발췌)

**P2 — 마이그레이션 drill (staging 필요)**:

현 호스트에서 직접 진행 시 롤백 불가 리스크. 별도 VM 또는 디렉토리로 복제:

```powershell
# (a) 현 Redis 정지 + AOF 백업
Stop-Service Redis
Copy-Item D:\Workspace\plane-data\redis\appendonly.aof `
  D:\Workspace\plane-data\redis\appendonly.aof.redis5-backup
# (b) Memurai 설치 (Developer 는 10d 제한 — 검증용으론 충분)
# (c) Memurai conf 작성 (현 redis.conf 거의 그대로 복사)
# (d) Memurai 서비스 기동 → AOF load 성공 여부 확인
#     redis-cli -h 127.0.0.1 -a <pass> --no-auth-warning INFO keyspace
# (e) plane-api 접속 smoke — Celery task enqueue + cache get/set
# (f) 롤백 경로 확인: Memurai 정지 → AOF backup 복원 → Redis 5 재기동
```

**P3 — 실 전환 (Go/No-Go 시점)**:

Redis 5 의 신규 CVE 가 보고되거나 Plane upstream 이 Redis 6+ 전제 기능을 쓰기 시작하는 시점 이후. 현 시점엔 **보류**.

### 우선순위

- **심각도**: **Low** (현 Redis 5 EOL 이지만 `bind 127.0.0.1` + ACL 로 loopback-only 운영 → 외부 CVE 표면 제한. Plane 이 Redis 6+ 기능 요구 안 함)
- **구현비용**: 호환성 재조사 1h + 마이그레이션 drill 2h + 실 전환 1h (staging 검증 후) = **약 4h**
- **예상 실행**: 보류 — 심각 신규 CVE 또는 Plane upstream 의존성 변화 시 재평가

---

## §8 심각도 × 구현비용 매트릭스

수직: 심각도 ↑, 수평: 구현비용 →

```
심각도
  Critical │ §B (4h)                                          │
           │                                                  │
       High│ §A (3~4h)                  §F (3h)               │
           │                                                  │
     Medium│ §E (2~3h)    §D (4h)       §C (5h + 도메인)      │
           │                                                  │
        Low│                            §G (4h, 보류)         │
           └──────────────────────────────────────────────────┘
              <1h       1~3h             3~5h       5h+
                        구현비용
```

### 다음 세션 권장 순서 (재정렬)

1. **보안 세션 #1: §A + §B** (joojm 16자 + lockout 정책 + 빌트인 Admin disable + 3389 IP allowlist 또는 Tailscale + IPBan BlacklistRegex + ExpireTime 연장 + cloudflared 이관). Critical + High 를 한 번에, 약 **4~5h**. plane 계정 lockout 실측 먼저 수행.
2. **보안 세션 #2: §E + §F** (DPAPI `.plane_pass` 이관 + site.env ACL 타이트닝 + 7z 설치 + backup.ps1 5단계 암호화 + 복구 훈련 — worklog §5.3 이월 동시 해소). 약 **5h**.
3. **보안 세션 #3: §C** (도메인 확보 후). 외부 의존성으로 일정 별도. 약 **5h**.
4. **보안 세션 #4: §D** (Defender FullScan Task + 서버측 MIME 재검증 + 실행 확장자 denylist + SVG sanitize). 약 **4h**.
5. **§G 보류**: 심각 신규 CVE 또는 Plane upstream 의존성 변화 시 재평가.

각 세션 완료 시 이 문서에 `[완료] YYYY-MM-DD` 접두 + 결과 요약 블록 추가 (security-todo.md 의 이력 유지 규칙 준수).

---

## §9 출처

- **Memurai 버전/호환성** (§G 발견 1): `https://www.memurai.com/get-memurai` — "Memurai for Redis 4.2.2 (Stable, Redis API 7.4.7)" · "Memurai for Redis 8.2-rc1 (RC, Redis API 8.2.5)" · "Full compatibility with all Redis features" 문구 인용. Developer/Enterprise edition 비교표는 같은 페이지.
- **Memurai docs 상세 문서** (§G P1): `https://docs.memurai.com/` — 2026-04-24 세션에서 `/en/compatibility`, `/en/migrating-from-redis`, `/en/configuration` 전부 HTTP 404 반환 (리다이렉트 이슈로 추정). 다음 세션에 재시도.
- **Plane 소스 인용**:
  - `apps/api/plane/settings/common.py:33` (ALLOWED_HOSTS default `"*"`)
  - `apps/api/plane/settings/common.py:312,325,327` (SESSION/CSRF_COOKIE_SECURE, CSRF_TRUSTED_ORIGINS)
  - `apps/api/plane/settings/production.py:15` (SECURE_PROXY_SSL_HEADER)
  - `apps/api/plane/app/views/asset/v2.py:127~141` (USER_AVATAR MIME allowlist)
  - `apps/api/plane/app/views/asset/local.py:75,130~132,178` (size range, Content-Type override)
- **IPBan 설정 원문**: `tools/ipban/ipban.config` 의 `FailedLoginAttemptsBeforeBan=5`, `ExpireTime=01:00:00:00`, `FirewallRulePrefix=IPBan_`.
- **Windows Event Log**: Security 4625 (30d 집계), System SCM 7034/7036/7045 (2026-04-24 15:40 동시 종료).
- **시스템 도구 출력**: `secedit /export /areas SECURITYPOLICY` (password policy), `Get-MpComputerStatus` (Defender), `Get-NetFirewallRule -Direction Inbound` (방화벽), `Get-NetTCPConnection -LocalPort 80` (포트 owner), `Get-LocalUser joojm` + `Get-LocalGroupMember Administrators` (계정).
- **자체 문서 상호 참조**:
  - [worklog.md §7a](worklog.md) (Phase 8 §4 failure mode 교훈 — caddy admin off, IPBan Delayed Auto Start, NSSM AppEnvironmentExtra 소실)
  - [worklog.md §7c](worklog.md) (Task Scheduler SYSTEM+ServiceAccount+Highest 교훈)
  - [security-todo.md](security-todo.md) (원본 TODO 체크리스트, 본 감사와 1:1 매핑)
  - [plan/08-external-access.md](plan/08-external-access.md) §8 (HTTPS 전환 원 계획)

