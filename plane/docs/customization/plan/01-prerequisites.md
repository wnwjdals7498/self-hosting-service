# Phase 0 — 사전 준비 (Windows Server 2025 네이티브)

> **네비게이션**: [목차](../plan.md) · [다음: Phase 1 →](02-infrastructure.md)
>
> 연관: [../../../CLAUDE.md](../../../CLAUDE.md) · [../security-todo.md](../security-todo.md) · [.claude/project-layout.md](../../../.claude/project-layout.md)

**목표**: 호스트 Windows Server 2025 에 Plane 운영 전제(계정·경로·런타임·Redis·보조 도구)를 준비하고, Phase 1~8 의 모든 후속 단계가 깨끗한 환경에서 시작되도록 보장한다.

**확정된 전제**:
- Docker · WSL2 **불사용** (현 VM 에서 중첩 가상화 미허용)
- 전 Phase 가 Windows 네이티브 기준
- 런타임 경로: `D:\Workspace\plane-app` / `plane-data` / `plane-logs`
- 서비스 계정: 전용 `plane` (제한) + `plane-admin` (RDP 관리자)
- Redis 런타임: tporadowski/redis 5.0.14 (보안 TODO 는 [../security-todo.md §1](../security-todo.md))

---

## 1. 호스트 사전 점검

**OS**: Windows Server 2025 Standard, Build 26100 (x64) — 확인 완료.

### 1.1 OS 업데이트

최신 누적 업데이트 적용. 하나라도 보류된 재부팅 있으면 먼저 처리한다.

```powershell
# Server Manager → Tools → Windows Update → Check for updates
# 또는 PowerShell (PSWindowsUpdate 모듈 설치 필요)
Install-Module PSWindowsUpdate -Force -SkipPublisherCheck
Get-WindowsUpdate -Install -AcceptAll -AutoReboot
```

### 1.2 디스크 용량 확인

- C: ≥ 20 GB 여유 (OS · VC++ redist · Windows 업데이트)
- D: ≥ 50 GB 여유 (코드 · 빌드 캐시 · DB · 업로드 · Redis)

현재 측정값(2026-04-19): C: **51 GB free** / D: **472 GB free** — 충분.

### 1.3 PowerShell 실행 정책

아래 설치 스크립트 실행을 위해:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

> 조직 GPO 가 `AllSigned` 를 강제하면 `-Scope Process` 로 세션 한정 적용.

### 1.4 시각 / 로캘

UTC 로 시스템 시각 통일. Celery/세션/로그 타임스탬프 일관성을 위해 필수.

```powershell
Set-TimeZone -Id "UTC"
w32tm /resync
```

---

## 2. 서비스 계정 · RDP 관리 계정

### 2.1 `plane` 전용 서비스 계정 (최소 권한)

Plane API / Celery worker / Celery beat / live / Redis 등 모든 Windows Service 가 이 계정으로 실행된다. **대화형 로그인 거부**, **비밀번호 만료 없음**, 서비스 로그온 권한만 허용.

```powershell
# 관리자 PowerShell 에서 실행
$pw = Read-Host -AsSecureString "plane 계정 비밀번호 (32자+ 권장)"
New-LocalUser -Name "plane" `
  -Password $pw `
  -FullName "Plane Service Account" `
  -Description "Plane 백엔드/워커/Redis 서비스 실행 전용" `
  -PasswordNeverExpires `
  -UserMayNotChangePassword
```

**로컬 보안 정책 (secpol.msc)** 에서 수동으로:
1. `로컬 정책 → 사용자 권한 할당 → 로컬 로그온 거부` 에 `plane` 추가
2. `서비스로 로그온` 권한에 `plane` 추가 (NSSM 이 보통 자동 처리하지만 명시적으로 부여)

### 2.2 `plane-admin` — 로컬 콘솔 전용 관리자 (RDP 불가)

Administrators 그룹에만 포함. **Remote Desktop Users 에는 넣지 않음** — 외부 RDP 로그인 차단. 콘솔 또는 이미 로그인된 세션에서만 쓰는 비상 관리자.

```powershell
$pw = Read-Host -AsSecureString "plane-admin 비밀번호"
New-LocalUser -Name "plane-admin" `
  -Password $pw `
  -FullName "Plane Local Admin (console only)" `
  -Description "로컬 콘솔 전용 관리자 — RDP 불가"

Add-LocalGroupMember -Group "Administrators" -Member "plane-admin"
# Remote Desktop Users 에는 의도적으로 추가하지 않는다 — 외부 RDP 공격면 차단
```

### 2.3 `joojm` — RDP 원격 관리 계정

실제 외부 RDP 접근을 담당. Administrators + Remote Desktop Users.

```powershell
$pw = Read-Host -AsSecureString "joojm 비밀번호"
New-LocalUser -Name "joojm" `
  -Password $pw `
  -FullName "Plane RDP Admin (joojm)" `
  -Description "RDP 원격 관리 계정"

Add-LocalGroupMember -Group "Administrators"       -Member "joojm"
Add-LocalGroupMember -Group "Remote Desktop Users" -Member "joojm"
```

> **기존 RDP allowlist 정책과 정합**: 현재 시스템에 이미 "특정 계정만 RDP 허용" 정책이 있다면 `joojm` 을 해당 목록에 포함. 빌트인 `Administrator` 는 계속 차단 상태 유지.

### 2.4 RDP 활성화 + NLA 강제

```powershell
# RDP 수신 허용
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' `
  -Name "fDenyTSConnections" -Value 0

# NLA 강제
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' `
  -Name "UserAuthentication" -Value 1

# 방화벽 그룹 활성
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
```

> **외부 노출 정책은 Phase 8 외 별도**: 현재는 로컬/내부망 접근만 전제. 공인망에 3389 직접 개방 금지. Cloudflare Access / VPN 뒤로만 배치 — [../security-todo.md §2](../security-todo.md).

---

## 3. 디렉토리 구조

### 3.1 3대 루트 생성

```powershell
"plane-app","plane-data","plane-logs" | ForEach-Object {
  New-Item -ItemType Directory -Path "D:\Workspace\$_" -Force | Out-Null
}

# 데이터 하위
"sqlite","uploads","backup","redis" | ForEach-Object {
  New-Item -ItemType Directory -Path "D:\Workspace\plane-data\$_" -Force | Out-Null
}
```

### 3.2 ACL 설정 (icacls)

상속 제거 후 `plane` 계정 Modify, Administrators/SYSTEM Full. 일반 사용자 차단.

```powershell
$paths = "D:\Workspace\plane-app", "D:\Workspace\plane-data", "D:\Workspace\plane-logs"

foreach ($p in $paths) {
  icacls $p /inheritance:r                              | Out-Null
  icacls $p /grant:r "SYSTEM:(OI)(CI)F"                 | Out-Null
  icacls $p /grant:r "Administrators:(OI)(CI)F"         | Out-Null
  icacls $p /grant:r "plane:(OI)(CI)M"                  | Out-Null
  # 일반 Users 접근 차단 (상속 제거로 이미 기본 차단되지만 명시적으로)
  icacls $p /remove:g "BUILTIN\Users"                   | Out-Null
  icacls $p /remove:g "Authenticated Users"             | Out-Null
}

# 검증
icacls D:\Workspace\plane-data
```

### 3.3 결과 구조

```
D:\Workspace\
├── plane\                   (개발용 저장소 — 본 리포지토리)
├── plane-app\               (운영 배포 트리 — Phase 2 에서 배치)
├── plane-data\
│   ├── sqlite\
│   ├── uploads\
│   ├── backup\
│   └── redis\
└── plane-logs\
```

---

## 4. Python 3.13 (이미 설치됨 — 검증)

**현재 확인값**: `python --version` → `Python 3.13.13`.

### 4.1 체크리스트

- [ ] `Install for all users` 옵션으로 설치되었는지 (`C:\Program Files\Python313\python.exe`)
- [ ] `py launcher` 존재: `py -0` 실행 시 설치된 인터프리터 목록 출력
- [ ] PATH 에 `python`·`pip` 노출: `where.exe python`
- [ ] 시스템 pip 최신화: `python -m pip install --upgrade pip setuptools wheel`

### 4.2 Django 4.2 공식 지원 범위 주의

Django 4.2 는 **공식적으로 Python 3.12 까지** 지원. Python 3.13 에서는 대부분 동작하지만 `requirements/base.txt` 의 C 확장(`lxml`, `cryptography`, `nh3`, `pymongo`)이 wheel 제공 여부에 따라 실패할 수 있다. 실측은 [Phase 2](03-source-prep.md) 에서 `pip install -r requirements/local.txt` 로 수행한다. 실패 시 **Python 3.12 MSI 추가 설치**(3.13 과 병존) 로 회귀.

### 4.3 가상환경

`apps/api/.venv` 생성은 [Phase 2](03-source-prep.md) 에서. Phase 0 에서는 인터프리터 존재만 확인.

---

## 5. Node.js + pnpm

### 5.1 Node 24.14.1 (nvm-windows 관리 — 이미 설치됨)

**현재 확인값**:
- `node --version` → `v24.14.1`
- `nvm list` → `* 24.14.1 (Currently using 64-bit executable)`

`package.json` `engines.node: >=22.18.0` 조건 충족. 업그레이드/다운그레이드 불필요.

### 5.2 pnpm 10.32.1 (corepack 경유)

Node 24 는 corepack 을 내장 (0.34.6 확인됨). `package.json` 의 `packageManager: pnpm@10.32.1+sha512...` 필드가 정확한 버전을 고정한다.

```powershell
corepack enable
corepack prepare pnpm@10.32.1 --activate
pnpm --version    # 10.32.1
```

> corepack 이 신규 shim 을 생성할 때 WindowsDefender 가 SmartScreen 차단을 띄울 수 있다. `Unblock-File` 또는 관리자 권한 재실행으로 해결.

---

## 6. Redis — tporadowski/redis 5.0.14

**공식 Redis 는 Windows 미지원**. 커뮤니티 포트 사용. 보안 제약·중기 전환 후보는 [../security-todo.md §1](../security-todo.md) 에 이월.

### 6.1 설치

최신 릴리스: https://github.com/tporadowski/redis/releases (2026-04 기준 `5.0.14.1`)

```powershell
$url = "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.msi"
$msi = "$env:TEMP\Redis-x64-5.0.14.1.msi"
Invoke-WebRequest -Uri $url -OutFile $msi

# 방화벽 예외 생성 억제 (외부 노출 방지), 포트 고정
msiexec.exe /i $msi /qn ADD_FIREWALL_RULE="" PORT=6379
```

> MSI 는 설치 완료 시 Windows Service `Redis` 를 LocalSystem 으로 자동 등록한다. Phase 1 에서 **`plane` 계정 실행**으로 변경 + 데이터 경로 이전 + requirepass 설정을 수행.

### 6.2 기본 경로

- 설치 위치: `C:\Program Files\Redis\`
- 서비스 설정: `C:\Program Files\Redis\redis.windows-service.conf`
- 데이터 파일: `C:\Program Files\Redis\` (기본) → Phase 1 에서 `D:\Workspace\plane-data\redis\` 로 이전

### 6.3 설치 직후 검증

```powershell
redis-cli ping      # PONG
Get-Service Redis   # Status: Running
```

---

## 7. 보조 도구

### 7.1 Git for Windows

```powershell
git --version       # 이미 설치됨 예상 (워크스페이스가 git 저장소)
# 미설치 시:
winget install --id Git.Git -e --source winget
```

### 7.2 NSSM (Phase 6 에서 사용 — 사전 다운로드)

Linux systemd 대체. `apps/api`, Celery, `apps/live` 를 Windows Service 로 등록하기 위한 래퍼.

**다운로드 경로 — 아래 순서로 시도** (nssm.cc 가 간헐적으로 503):

```powershell
# (a) 공식 nssm.cc — 정공법
$zip = "$env:TEMP\nssm.zip"
Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath "D:\Workspace\plane-app\tools\nssm" -Force

# (b) nssm.cc 503 시: Chocolatey 로 우회 (관리자 PS)
Set-ExecutionPolicy Bypass -Scope Process -Force
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
choco install nssm -y
# choco 기본 설치 위치를 본 plan 경로 규격으로 맞추기:
New-Item -ItemType Directory -Path "D:\Workspace\plane-app\tools\nssm\nssm-2.24\win64" -Force | Out-Null
Copy-Item "C:\ProgramData\chocolatey\lib\NSSM\tools\nssm.exe" `
  "D:\Workspace\plane-app\tools\nssm\nssm-2.24\win64\nssm.exe" -Force

# (c) winget 대안 (패키지 ID 가 버전 고정 시)
# winget install NSSM.NSSM -e --accept-package-agreements --accept-source-agreements

# 확인
Test-Path "D:\Workspace\plane-app\tools\nssm\nssm-2.24\win64\nssm.exe"
```

> `setx /M PATH` 로 PATH 에 추가할 필요 없음 — Phase 6 NSSM 호출이 **전체 경로** 로 수행됨.

### 7.3 Visual C++ 재배포 패키지 (2015-2022 x64)

일부 Python wheel(`cryptography`, `lxml`) · Redis · Node 네이티브 모듈이 요구.

```powershell
winget install --id Microsoft.VCRedist.2015+.x64 -e
```

### 7.4 cloudflared — Phase 7 예비 (설치만)

```powershell
winget install --id Cloudflare.cloudflared -e
cloudflared --version
```

---

## 8. 방화벽 사전 정책

### 8.1 인바운드 — 내부 서비스 포트 전면 차단

외부 노출은 Cloudflare Tunnel (Phase 7) 경유만. 로컬 loopback 만 허용한다.

```powershell
# Plane API(8000), web(3000), admin(3001), space(3002), live(3100), Redis(6379)
$ports = 8000,3000,3001,3002,3100,6379
foreach ($p in $ports) {
  $name = "Block Inbound tcp/$p (Plane)"
  Remove-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
  New-NetFirewallRule -DisplayName $name `
    -Direction Inbound -LocalPort $p -Protocol TCP -Action Block -Profile Any | Out-Null
}
```

### 8.2 아웃바운드

기본 허용 유지 — Celery → Redis(로컬), Cloudflare Tunnel(443), SMTP(외부), OAuth(HTTPS) 호출 필요.

### 8.3 RDP (3389)

Phase 0 시점에는 LAN 내부에서만 사용. 외부망 개방 금지. Phase 외부 접근 설정 시 [../security-todo.md §2](../security-todo.md) 재검토.

---

## 9. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P0-1 | OS 누적 업데이트 + 재부팅 | — | §1.1 | Build 26100 최신 패치 |
| P0-2 | 디스크 C/D 여유 확인 | — | §1.2 | C ≥ 20 GB · D ≥ 50 GB |
| P0-3 | PowerShell 실행 정책 `RemoteSigned` (CurrentUser) | — | §1.3 | 설치 스크립트 실행 가능 |
| P0-4 | 시각대 UTC 통일 · `w32tm /resync` | — | §1.4 | `Get-TimeZone` → UTC |
| P0-5 | `plane` 서비스 계정 생성 · 로컬 로그온 거부 · 서비스 로그온 허용 | — | §2.1 | LocalUser `plane` |
| P0-6a | `plane-admin` 생성 · Administrators 만 (RDP 제외) | — | §2.2 | LocalUser 콘솔 전용 |
| P0-6b | `joojm` 생성 · Administrators + Remote Desktop Users | — | §2.3 | LocalUser RDP 전용 |
| P0-7 | RDP 수신 허용 + NLA 강제 + 방화벽 그룹 활성 | P0-6b | §2.4 | 3389/tcp 수신 |
| P0-8 | 3 루트 + `plane-data` 하위 4종 생성 | — | §3.1 | 7개 디렉토리 |
| P0-9 | ACL `icacls /inheritance:r` + plane:M · Admin:F · Users 제거 | P0-5, P0-8 | §3.2 | 3 루트 ACL 적용 |
| P0-10 | Python 3.13 설치 검증 (`py -0`, PATH, pip upgrade) | — | §4.1 | `python --version` = 3.13.x |
| P0-11 | Node 24 (nvm-windows) 확인 | — | §5.1 | `node --version` = v24.x |
| P0-12 | `corepack enable` + `corepack prepare pnpm@10.32.1 --activate` | P0-11 | §5.2 | `pnpm --version` = 10.32.1 |
| P0-13 | Redis MSI (tporadowski 5.0.14.1) 설치 | — | §6.1 | Windows Service `Redis` 등록 |
| P0-14 | Git 설치 확인 (없으면 winget) | — | §7.1 | `git --version` |
| P0-15 | NSSM 2.24 다운로드 + 압축 해제 + PATH | — | §7.2 | `nssm.exe` 실행 가능 |
| P0-16 | Visual C++ Redistributable 2015-2022 x64 | — | §7.3 | winget 설치 완료 |
| P0-17 | cloudflared 설치 (Phase 7 예비) | — | §7.4 | `cloudflared --version` |
| P0-18 | 내부 포트 6개 인바운드 차단 (8000/3000/3001/3002/3100/6379) | — | §8.1 | 6 Firewall Rule `Action=Block` |

---

## 10. 단위별 테스트

각 WBS 완료 시 아래 명령으로 즉시 검증.

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P0-1 | `Get-HotFix \| Sort InstalledOn -Desc \| Select -First 1` | 최근 30일 이내 |
| P0-2 | `Get-PSDrive C, D \| Select Name, Free` | C Free ≥ 20 GB · D Free ≥ 50 GB |
| P0-3 | `Get-ExecutionPolicy -Scope CurrentUser` | `RemoteSigned` |
| P0-4 | `Get-TimeZone \| Select Id` | `UTC` |
| P0-5 | `Get-LocalUser plane \| Select Enabled` | `True` |
| P0-6a | `Get-LocalGroupMember Administrators \| ? Name -match plane-admin` · `Get-LocalGroupMember 'Remote Desktop Users' \| ? Name -match plane-admin` | 1건 · **0건** |
| P0-6b | `Get-LocalGroupMember Administrators \| ? Name -match joojm` · `Get-LocalGroupMember 'Remote Desktop Users' \| ? Name -match joojm` | 1건 · 1건 |
| P0-7 | `Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server' fDenyTSConnections` | `0` |
| P0-8 | `"plane-app","plane-data","plane-logs" \| % { Test-Path "D:\Workspace\$_" }` | `True` ×3 |
| P0-9 | `icacls D:\Workspace\plane-data` | `plane:(OI)(CI)(M)` 포함 |
| P0-10 | `python --version` / `python -c "import sqlite3;print(sqlite3.sqlite_version)"` | 3.13.x / 3.45+ |
| P0-11 | `node --version` | v24.x |
| P0-12 | `pnpm --version` | 10.32.1 |
| P0-13 | `redis-cli ping` · `Get-Service Redis` | `PONG` · `Running` |
| P0-14 | `git --version` | 2.x |
| P0-15 | `Test-Path "D:\Workspace\plane-app\tools\nssm\nssm-2.24\win64\nssm.exe"` | `True` |
| P0-16 | `Get-Package -Name "*Visual C++*2015-2022*"` | 1건 이상 |
| P0-17 | `cloudflared --version` | 버전 출력 |
| P0-18 | `Get-NetFirewallRule -DisplayName "Block Inbound tcp/*" \| Measure` | Count = 6 |

---

## 11. 요구사항 검증 체크리스트

이 Phase 가 [../plan.md](../plan.md) §0 의 상위 전제 중 어느 것을 충족시키는지.

- [ ] **Windows 네이티브 배포** — P0-10~P0-17 의 런타임 전부 Windows 바이너리. Docker/WSL2 사용 0
- [ ] **서비스 계정 3종 분리** — P0-5 `plane`(서비스 실행) · P0-6a `plane-admin`(로컬 비상) · P0-6b `joojm`(RDP) 독립. plane-admin 은 Remote Desktop Users 에 불포함
- [ ] **런타임 경로 확정** — P0-8, P0-9 로 `D:\Workspace\plane-{app,data,logs}` 격리
- [ ] **Redis 로컬 bind 전제** — P0-13 설치 + P0-18 의 6379 인바운드 차단 → 외부 노출 방지 (상세 구성은 Phase 1)
- [ ] **외부 서비스 포트 노출 차단** — P0-18 로 8000/3000/3001/3002/3100 차단. 외부 접근은 Phase 7 Caddy 80 만
- [ ] **Python 3.13 채택** — P0-10 검증 완료. Django 4.2 호환 실측은 Phase 2
- [ ] **보안 TODO 이월** — RDP MFA · Redis TLS 부재 → [../security-todo.md §1, §2](../security-todo.md)

---

## 12. 체크포인트

Phase 1 로 넘어가기 전 아래 전부 통과해야 한다.

```powershell
# --- 계정 ---
Get-LocalUser plane, plane-admin, joojm | Select Name, Enabled
Get-LocalGroupMember Administrators         | Where-Object Name -match "plane-admin|joojm"
Get-LocalGroupMember "Remote Desktop Users" | Where-Object Name -match "joojm"
# plane-admin 은 Remote Desktop Users 에 들어가면 안 됨:
Get-LocalGroupMember "Remote Desktop Users" | Where-Object Name -match "plane-admin"
# → 결과가 비어 있어야 정상

# --- 경로 & ACL ---
"plane-app","plane-data","plane-logs" | ForEach-Object {
  Test-Path "D:\Workspace\$_"
}
icacls D:\Workspace\plane-data     # plane:(OI)(CI)(M) 포함 확인

# --- 런타임 ---
python --version      # Python 3.13.x
node --version        # v24.x
pnpm --version        # 10.32.1

# --- Redis ---
redis-cli ping        # PONG
Get-Service Redis     # Status: Running

# --- 보조 도구 ---
git --version
cloudflared --version
Test-Path "D:\Workspace\plane-app\tools\nssm\nssm-2.24\win64\nssm.exe"

# --- 방화벽 ---
Get-NetFirewallRule -DisplayName "Block Inbound tcp/*" | Format-Table DisplayName, Action
```

- [ ] 계정 2개 존재, 그룹 소속 정상
- [ ] 디렉토리 3+4개 생성, ACL 적용
- [ ] Python/Node/pnpm 버전 출력 정상
- [ ] Redis PING/PONG, 서비스 Running
- [ ] NSSM/cloudflared/git 확인
- [ ] 내부 포트 6개 인바운드 차단 규칙 존재

---

## 10. 남긴 TODO → 후속 기획

Phase 0 에서 **의도적으로 미처리** 하고 [../security-todo.md](../security-todo.md) 로 이월:

- Redis(tporadowski 5.0.14) EOL · TLS 부재 → Memurai 등으로 중기 전환 (§1)
- RDP 외부 노출 시 Cloudflare Access / Zero Trust (§2)
- `plane-admin` MFA (§2)
- 백업/자격증명 DPAPI/Credential Manager 이관 (§5·§6)

---

> **네비게이션**: [목차](../plan.md) · [다음: Phase 1 →](02-infrastructure.md)
