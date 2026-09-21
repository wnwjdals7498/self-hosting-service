# Gitea 셀프 호스팅 계획서

> **환경**: Windows Server 2025 (공인 IP)  
> **목적**: 개인 프로젝트 관리 + Claude Code 연동을 위한 경량 Git 서비스  
> **원칙**: 최소 리소스, 최소 데이터, 스크립트 기반 복구  
> **기본 경로**: `D:\Workspace\gitea\`

---

## 폴더 구조

```
D:\Workspace\gitea\
  ├── bin\                         ← gitea.exe, nssm.exe, rclone.exe
  ├── custom\
  │   └── conf\
  │       └── app.ini              ← 핵심 설정 파일
  ├── data\                        ← SQLite DB, 세션 등
  ├── repos\                       ← Git 리포지토리 저장소
  ├── log\                         ← 로그 파일
  ├── backups\                     ← 로컬 백업 임시 저장
  └── scripts\                     ← backup.ps1, restore.ps1
```

---

## 1단계: 초기 설치 (Quick Start)

### 1-1. 사전 준비

| 항목 | 설명 |
|------|------|
| Git for Windows | 이미 설치됨 (PATH 등록 확인: `git --version`) |
| NSSM | https://nssm.cc → `D:\Workspace\gitea\bin\` 에 배치 |
| Gitea 바이너리 | https://dl.gitea.com/gitea/ → `D:\Workspace\gitea\bin\gitea.exe` 로 배치 |
| rclone | https://rclone.org/downloads/ → `D:\Workspace\gitea\bin\rclone.exe` 로 배치 |

> **출처**: https://docs.gitea.com/enterprise/installation/windows — "Prerequisites" 항목 참조

### 1-2. 폴더 생성 및 설치

```powershell
# 1. 전체 폴더 구조 생성
$base = "D:\Workspace\gitea"
$dirs = @(
    "$base\bin",
    "$base\custom\conf",
    "$base\data",
    "$base\repos",
    "$base\log",
    "$base\backups",
    "$base\scripts"
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Path $d -Force }

# 2. 다운로드한 파일 배치 확인
#    - D:\Workspace\gitea\bin\gitea.exe
#    - D:\Workspace\gitea\bin\nssm.exe
#    - D:\Workspace\gitea\bin\rclone.exe

# 3. 최초 실행 (설정 마법사 진입)
cd $base\bin
.\gitea.exe web --custom-path "$base\custom" --work-path "$base"
```

### 1-3. 웹 설정 마법사 (http://localhost:18080)

| 설정 항목 | 값 |
|-----------|-----|
| 데이터베이스 유형 | **SQLite3** |
| 리포지토리 경로 | `D:\Workspace\gitea\repos` |
| LFS 경로 | *(비워둠 — LFS 비활성화)* |
| 서버 도메인 | `공인 IP 주소` |
| SSH 포트 | `18022` |
| HTTP 포트 | `18080` |
| Gitea Base URL | `http://공인IP:18080/` |
| 관리자 계정 | 설정 마법사에서 생성 |

> 설정 완료 후 `Ctrl+C`로 프로세스 종료  
> `D:\Workspace\gitea\custom\conf\app.ini` 자동 생성됨

---

## 2단계: 외부 접근 설정

### 선택된 옵션: 직접 노출 (공인 IP)

공인 IP가 있으므로 리버스 프록시 없이 Gitea를 직접 노출합니다.  
비표준 포트(18080, 18022) 사용으로 기본 포트 스캔을 회피하고,  
`DISABLE_REGISTRATION + REQUIRE_SIGNIN_VIEW` 설정으로 비인가 접근을 차단합니다.

> HTTPS가 필요해지면 나중에 Caddy 리버스 프록시를 앞에 추가하면 됩니다.

### 2-1. 방화벽 설정

```powershell
# Gitea HTTP 포트 개방
New-NetFirewallRule -DisplayName "Gitea HTTP" `
  -Direction Inbound -Protocol TCP -LocalPort 18080 -Action Allow

# Gitea SSH 포트 개방
New-NetFirewallRule -DisplayName "Gitea SSH" `
  -Direction Inbound -Protocol TCP -LocalPort 18022 -Action Allow
```

### 2-2. 접속 확인

```
브라우저:  http://공인IP:18080
Git SSH:   ssh://git@공인IP:18022/사용자명/리포지토리.git
Git HTTP:  http://공인IP:18080/사용자명/리포지토리.git
```

---

## 3단계: 서비스 등록 (자동 재시작)

### 3-1. NSSM으로 Windows 서비스 등록

```powershell
$base = "D:\Workspace\gitea"

# 서비스 생성
& "$base\bin\nssm.exe" install Gitea "$base\bin\gitea.exe" "web --custom-path $base\custom --work-path $base"

# 작업 디렉토리 설정
& "$base\bin\nssm.exe" set Gitea AppDirectory "$base\bin"

# 로그 출력 설정
& "$base\bin\nssm.exe" set Gitea AppStdout "$base\log\gitea-stdout.log"
& "$base\bin\nssm.exe" set Gitea AppStderr "$base\log\gitea-stderr.log"

# 시작 유형: 자동
& "$base\bin\nssm.exe" set Gitea Start SERVICE_AUTO_START

# 실패 시 5초 후 자동 재시작
& "$base\bin\nssm.exe" set Gitea AppRestartDelay 5000

# 서비스 시작
& "$base\bin\nssm.exe" start Gitea
```

> **출처**: https://docs.gitea.com/enterprise/installation/windows — "nssm" 항목 참조

### 3-2. 서비스 실패 복구 (GUI 추가 설정)

1. `services.msc` 열기
2. `Gitea` 서비스 → 속성 → **복구** 탭
3. 첫째/둘째/후속 실패: **서비스 다시 시작**
4. 다시 시작 대기 시간: **5000ms**

### 3-3. 서비스 관리 명령어

```powershell
Get-Service Gitea          # 상태 확인
Restart-Service Gitea      # 재시작
Stop-Service Gitea         # 중지
Start-Service Gitea        # 시작
```

---

## 4단계: 경량화를 위한 커스텀 설정

`D:\Workspace\gitea\custom\conf\app.ini` 전체 내용:

```ini
;; ============================================
;; 기본 설정
;; ============================================
APP_NAME = My Projects
RUN_MODE = prod

[server]
DOMAIN           = 공인IP주소
HTTP_PORT        = 18080
ROOT_URL         = http://공인IP주소:18080/
SSH_PORT         = 18022
START_SSH_SERVER = true
SSH_LISTEN_HOST  = 0.0.0.0
SSH_LISTEN_PORT  = 18022
DISABLE_SSH      = false
LFS_START_SERVER = false
OFFLINE_MODE     = true

;; ============================================
;; 보안: 비인가 접근 차단
;; ============================================
[service]
DISABLE_REGISTRATION              = true
REQUIRE_SIGNIN_VIEW               = true
ENABLE_NOTIFY_MAIL                = false
ENABLE_CAPTCHA                    = false

;; ============================================
;; 불필요 기능 비활성화
;; ============================================
[packages]
ENABLED = false

[mirror]
ENABLED = false

[actions]
ENABLED = false

[federation]
ENABLED = false

[mailer]
ENABLED = false

;; ============================================
;; API (Claude Code 연동용 — 반드시 유지)
;; ============================================
[api]
ENABLE_SWAGGER = false

;; ============================================
;; 데이터베이스
;; ============================================
[database]
DB_TYPE = sqlite3
PATH    = D:\Workspace\gitea\data\gitea.db

;; ============================================
;; 리포지토리
;; ============================================
[repository]
ROOT                    = D:\Workspace\gitea\repos
DEFAULT_BRANCH          = main
ENABLE_PUSH_CREATE_USER = true
DISABLED_REPO_UNITS     = repo.wiki, repo.ext_wiki, repo.ext_issues
DEFAULT_REPO_UNITS      = repo.code, repo.issues, repo.pulls, repo.projects

;; ============================================
;; 로그 (경고 이상만)
;; ============================================
[log]
MODE      = file
LEVEL     = warn
ROOT_PATH = D:\Workspace\gitea\log

;; ============================================
;; 캐시 / 세션 (최소 리소스)
;; ============================================
[cache]
ADAPTER  = memory
INTERVAL = 60

[session]
PROVIDER = file
```

### 비활성화 요약

| 비활성화 | 활성화 유지 |
|---------|------------|
| LFS, 패키지, 미러 | **API** (Claude Code 필수) |
| Actions, Federation | **이슈** (계획 관리 필수) |
| 이메일, 회원가입 | **프로젝트 보드** (진행도 필수) |
| 위키, Swagger UI | **PR** (코드 리뷰) |
| | **SSH** (Git 접근, 포트 18022) |

> **출처**: https://docs.gitea.com/administration/config-cheat-sheet — 전체 설정 항목 참조  
> **출처**: https://github.com/go-gitea/gitea/blob/main/custom/conf/app.example.ini — 비활성화 가능 항목 참조

---

## 5단계: 백업 설정

### 전략: 최소 데이터 압축 → Google Drive 덮어쓰기

```
[백업 대상 — 3개만]
  ├── app.ini       ← 설정 (수 KB)
  ├── gitea.db      ← SQLite DB (이슈, 사용자, 프로젝트)
  └── repos\        ← Git 리포지토리 (bare repos)

[백업 제외 — 스크립트로 재구축]
  ├── bin\           ← gitea.exe, nssm.exe, rclone.exe (재다운로드)
  ├── log\           ← 불필요
  ├── sessions\      ← 불필요
  └── cache\         ← 자동 재생성
```

### 5-1. rclone 초기 설정 (최초 1회)

```powershell
# rclone 설정 시작 (대화형)
D:\Workspace\gitea\bin\rclone.exe config

# 아래 순서대로 진행:
# 1. n (new remote)
# 2. 이름 입력: gdrive
# 3. Storage 선택: Google Drive (번호 입력)
# 4. client_id, client_secret: 비워두기 (Enter)
# 5. scope: 1 (Full access)
# 6. service_account_file: 비워두기 (Enter)
# 7. 브라우저에서 Google 로그인 → 권한 허용
# 8. Configure as team drive: n
# 9. 확인 후 q (quit)
```

> **출처**: https://rclone.org/drive/ — "Standard setup" 항목 참조

### 5-2. 백업 스크립트 (`D:\Workspace\gitea\scripts\backup.ps1`)

```powershell
# ============================================
# Gitea 백업 스크립트
# 압축 → Google Drive 덮어쓰기
# ============================================

$BASE        = "D:\Workspace\gitea"
$BACKUP_DIR  = "$BASE\backups"
$BACKUP_FILE = "$BACKUP_DIR\gitea-backup.zip"
$RCLONE      = "$BASE\bin\rclone.exe"
$GDRIVE_PATH = "gdrive:Gitea-Backup"

$DATE = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Output "[$DATE] 백업 시작..."

# 1. 이전 로컬 백업 삭제
if (Test-Path $BACKUP_FILE) { Remove-Item $BACKUP_FILE -Force }

# 2. Gitea 서비스 중지 (SQLite 잠금 방지)
Stop-Service Gitea -Force
Start-Sleep -Seconds 3

# 3. 최소 데이터만 압축
Compress-Archive -Path @(
    "$BASE\custom\conf\app.ini",
    "$BASE\data\gitea.db",
    "$BASE\repos"
) -DestinationPath $BACKUP_FILE -Force

# 4. Gitea 서비스 재시작
Start-Service Gitea

# 5. Google Drive에 덮어쓰기 업로드
& $RCLONE copy $BACKUP_FILE $GDRIVE_PATH --progress

# 6. 로컬 백업 파일 삭제 (Google Drive에만 보관)
Remove-Item $BACKUP_FILE -Force

# 7. 완료 로그
$DATE2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Output "[$DATE2] 백업 완료 → Google Drive ($GDRIVE_PATH)"
```

### 5-3. 자동 백업 스케줄 (매일 새벽 3시)

```powershell
$BASE = "D:\Workspace\gitea"

$Action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-ExecutionPolicy Bypass -File $BASE\scripts\backup.ps1"

$Trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM

$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
  -TaskName "Gitea Daily Backup" `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -User "SYSTEM" `
  -RunLevel Highest
```

### 5-4. 수동 백업 / 확인

```powershell
# 수동 백업 실행
powershell -ExecutionPolicy Bypass -File D:\Workspace\gitea\scripts\backup.ps1

# Google Drive 백업 확인
D:\Workspace\gitea\bin\rclone.exe ls gdrive:Gitea-Backup

# Google Drive 백업 용량 확인
D:\Workspace\gitea\bin\rclone.exe size gdrive:Gitea-Backup
```

---

## 6단계: 복구 스크립트

`D:\Workspace\gitea\scripts\restore.ps1`:

```powershell
# ============================================
# Gitea 전체 환경 복구 스크립트
# 사전 조건: Git for Windows 설치 완료
# ============================================
param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,  # 백업 zip 경로 또는 "gdrive"

    [string]$GiteaVersion = "1.23.7",
    [string]$NssmVersion  = "2.24"
)

$BASE = "D:\Workspace\gitea"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Gitea 복구 시작" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. 폴더 구조 생성
Write-Host "[1/8] 폴더 구조 생성..." -ForegroundColor Yellow
$dirs = @(
    "$BASE\bin", "$BASE\custom\conf", "$BASE\data",
    "$BASE\repos", "$BASE\log", "$BASE\backups", "$BASE\scripts"
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Path $d -Force | Out-Null }

# 2. Gitea 다운로드
Write-Host "[2/8] Gitea $GiteaVersion 다운로드..." -ForegroundColor Yellow
$giteaUrl = "https://dl.gitea.com/gitea/$GiteaVersion/gitea-$GiteaVersion-gogit-windows-4.0-amd64.exe"
Invoke-WebRequest -Uri $giteaUrl -OutFile "$BASE\bin\gitea.exe"

# 3. NSSM 다운로드
Write-Host "[3/8] NSSM 다운로드..." -ForegroundColor Yellow
$nssmUrl = "https://nssm.cc/release/nssm-$NssmVersion.zip"
Invoke-WebRequest -Uri $nssmUrl -OutFile "$BASE\bin\nssm.zip"
Expand-Archive -Path "$BASE\bin\nssm.zip" -DestinationPath "$BASE\bin\nssm-temp" -Force
Copy-Item "$BASE\bin\nssm-temp\nssm-$NssmVersion\win64\nssm.exe" "$BASE\bin\nssm.exe" -Force
Remove-Item "$BASE\bin\nssm-temp" -Recurse -Force
Remove-Item "$BASE\bin\nssm.zip" -Force

# 4. rclone 다운로드
Write-Host "[4/8] rclone 다운로드..." -ForegroundColor Yellow
$rcloneUrl = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
Invoke-WebRequest -Uri $rcloneUrl -OutFile "$BASE\bin\rclone.zip"
Expand-Archive -Path "$BASE\bin\rclone.zip" -DestinationPath "$BASE\bin\rclone-temp" -Force
$rcloneExe = Get-ChildItem "$BASE\bin\rclone-temp" -Recurse -Filter "rclone.exe" | Select-Object -First 1
Copy-Item $rcloneExe.FullName "$BASE\bin\rclone.exe" -Force
Remove-Item "$BASE\bin\rclone-temp" -Recurse -Force
Remove-Item "$BASE\bin\rclone.zip" -Force

# 5. 백업 파일 가져오기
Write-Host "[5/8] 백업 데이터 복원..." -ForegroundColor Yellow
if ($BackupFile -eq "gdrive") {
    Write-Host "  → Google Drive에서 다운로드..." -ForegroundColor Gray
    Write-Host "  → rclone 설정이 안 되어 있으면 먼저: $BASE\bin\rclone.exe config" -ForegroundColor Gray
    & "$BASE\bin\rclone.exe" copy "gdrive:Gitea-Backup/gitea-backup.zip" "$BASE\backups\" --progress
    $BackupFile = "$BASE\backups\gitea-backup.zip"
}

Expand-Archive -Path $BackupFile -DestinationPath "$BASE\restore-temp" -Force

# app.ini 복원
$iniSrc = Get-ChildItem "$BASE\restore-temp" -Recurse -Filter "app.ini" | Select-Object -First 1
if ($iniSrc) { Copy-Item $iniSrc.FullName "$BASE\custom\conf\app.ini" -Force }

# SQLite DB 복원
$dbSrc = Get-ChildItem "$BASE\restore-temp" -Recurse -Filter "gitea.db" | Select-Object -First 1
if ($dbSrc) { Copy-Item $dbSrc.FullName "$BASE\data\gitea.db" -Force }

# 리포지토리 복원
$repoSrc = Get-ChildItem "$BASE\restore-temp" -Recurse -Directory -Filter "repos" | Select-Object -First 1
if ($repoSrc) { Copy-Item "$($repoSrc.FullName)\*" "$BASE\repos\" -Recurse -Force }

Remove-Item "$BASE\restore-temp" -Recurse -Force

# 6. Windows 서비스 등록
Write-Host "[6/8] Windows 서비스 등록..." -ForegroundColor Yellow
& "$BASE\bin\nssm.exe" install Gitea "$BASE\bin\gitea.exe" "web --custom-path $BASE\custom --work-path $BASE"
& "$BASE\bin\nssm.exe" set Gitea AppDirectory "$BASE\bin"
& "$BASE\bin\nssm.exe" set Gitea AppStdout "$BASE\log\gitea-stdout.log"
& "$BASE\bin\nssm.exe" set Gitea AppStderr "$BASE\log\gitea-stderr.log"
& "$BASE\bin\nssm.exe" set Gitea Start SERVICE_AUTO_START
& "$BASE\bin\nssm.exe" set Gitea AppRestartDelay 5000

# 7. 방화벽 규칙
Write-Host "[7/8] 방화벽 규칙 설정..." -ForegroundColor Yellow
New-NetFirewallRule -DisplayName "Gitea HTTP" `
  -Direction Inbound -Protocol TCP -LocalPort 18080 -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Gitea SSH" `
  -Direction Inbound -Protocol TCP -LocalPort 18022 -Action Allow -ErrorAction SilentlyContinue

# 8. 서비스 시작
Write-Host "[8/8] Gitea 서비스 시작..." -ForegroundColor Yellow
& "$BASE\bin\nssm.exe" start Gitea

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " 복구 완료!" -ForegroundColor Green
Write-Host " http://localhost:18080" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host " [주의] rclone Google Drive 재설정 필요 시:" -ForegroundColor Yellow
Write-Host "   $BASE\bin\rclone.exe config" -ForegroundColor Yellow
```

### 복구 실행 방법

```powershell
# 로컬 백업 파일로 복구
.\restore.ps1 -BackupFile "C:\다운로드\gitea-backup.zip"

# Google Drive에서 직접 다운로드 후 복구
.\restore.ps1 -BackupFile "gdrive"

# 특정 Gitea 버전으로 복구
.\restore.ps1 -BackupFile "gdrive" -GiteaVersion "1.24.0"
```

---

## 체크리스트

### 설치 완료

- [ ] `D:\Workspace\gitea\` 폴더 구조 생성 완료
- [ ] `gitea.exe`, `nssm.exe`, `rclone.exe` → `bin\`에 배치 완료
- [ ] `http://localhost:18080` 접속 가능
- [ ] 관리자 계정 로그인 성공

### 외부 접근

- [ ] `http://공인IP:18080` 외부에서 접속 가능
- [ ] `ssh://git@공인IP:18022` Git SSH 접속 가능
- [ ] 회원가입 버튼 없음 확인
- [ ] 비로그인 시 로그인 페이지로 리다이렉트 확인

### 서비스

- [ ] `Get-Service Gitea` 상태: Running
- [ ] 서버 재부팅 후 자동 시작 확인
- [ ] 서비스 강제 종료 후 자동 재시작 확인

### 경량화

- [ ] 패키지/위키/Actions 메뉴 없음 확인
- [ ] API 접근 가능 (`/api/v1`)
- [ ] 이슈 + 프로젝트 보드 동작 확인

### 백업

- [ ] `rclone config` 완료 (Google Drive 연결)
- [ ] 수동 백업 실행 성공
- [ ] Google Drive `Gitea-Backup/gitea-backup.zip` 확인
- [ ] 작업 스케줄러 `Gitea Daily Backup` 등록 확인
- [ ] 복구 스크립트 테스트 (테스트 환경에서)

---

## 출처

| 항목 | 출처 URL | 참조 위치 |
|------|----------|-----------|
| Gitea Windows 설치 | https://docs.gitea.com/enterprise/installation/windows | Prerequisites, NSSM 항목 |
| Gitea 설정 Cheat Sheet | https://docs.gitea.com/administration/config-cheat-sheet | 전체 app.ini 설정 항목 |
| Gitea 커스텀 설정 | https://docs.gitea.com/administration/customizing-gitea | CustomPath, app.ini 위치 |
| Gitea app.ini 예제 | https://github.com/go-gitea/gitea/blob/main/custom/conf/app.example.ini | 비활성화 가능 항목 |
| Gitea FAQ | https://docs.gitea.com/help/faq | DISABLE_REGISTRATION 등 |
| rclone Google Drive | https://rclone.org/drive/ | Standard setup 항목 |
| rclone 다운로드 | https://rclone.org/ | Downloads 항목 |

---

## 다음 단계 (이 계획 완료 후)

1. **Claude Code 연동**: Gitea API 토큰 생성 → Claude Code에서 이슈 읽기/쓰기 테스트
2. **프로젝트 템플릿**: 이슈 템플릿 + 프로젝트 보드 구조 설계
3. **작업 명세 포맷**: Claude Code가 파싱할 마크다운 명세 구조 설계
4. **HTTPS 전환 (선택)**: Caddy 리버스 프록시로 Let's Encrypt 자동 인증서
