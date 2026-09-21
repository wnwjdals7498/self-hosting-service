# Gitea 셀프 호스팅 (Windows Server 2025)

공인 IP가 있는 Windows Server에서 Gitea를 경량화 설정으로 직접 노출하는 자동화 스크립트 세트입니다.
개인 프로젝트 + Claude Code 연동용 Git 서비스로 설계됨.

- **OS**: Windows Server 2025
- **DB**: SQLite3 (외부 의존 최소화)
- **포트**: HTTP `18080`, SSH `18022` (기본 포트 회피)
- **백업**: 매일 03:00 → Google Drive (rclone)
- **로그 로테이션**: 매주 일요일 04:00

---

## 목차

1. [주요 기능](#주요-기능)
2. [요구사항](#요구사항)
3. [폴더 구조](#폴더-구조)
4. [빠른 시작](#빠른-시작)
5. [상세 설치 단계](#상세-설치-단계)
6. [설정 변경](#설정-변경)
7. [운영 — 계정 · 서비스 · 백업 · 로그](#운영--계정--서비스--백업--로그)
8. [테스트](#테스트)
9. [트러블슈팅](#트러블슈팅)
10. [복구](#복구)
11. [참고 문서](#참고-문서)

---

## 주요 기능

- **원자 단위 10개 setup 스크립트** + 마스터 러너로 순차 자동 실행
- **config.ps1 조건부 기본값** 패턴 — 스크립트 `param()`이 우선, 없으면 기본값
- **모든 스크립트가 상세 로그 자동 기록** — Start-Transcript 기반, 호출 파라미터/효과 설정까지 기록
- **14개 단위 테스트** + E2E 테스트 + JSON 요약
- **Google Drive 백업** — rclone 연동, 로컬 압축 후 원격 덮어쓰기
- **로그 로테이션** — 30일 초과 or 카테고리별 100개 초과 자동 정리
- **전체 복구 스크립트** — 빈 서버에서 `restore.ps1 -BackupFile gdrive` 한 방

---

## 요구사항

| 항목 | 설명 |
|------|------|
| OS | Windows Server 2025 (Windows 10/11도 동작) |
| PowerShell | 5.1+ (기본 탑재) |
| 권한 | 관리자 PowerShell (setup 5/8/9/10 단계) |
| 네트워크 | 공인 IP + 인바운드 포트 18080/18022 허용 |
| Git for Windows | 사전 설치 필요 (`git --version` 확인) |
| 브라우저 | Gitea 마법사 + rclone OAuth용 |
| Google 계정 | rclone Google Drive 원격용 |

---

## 폴더 구조

```
D:\Workspace\gitea\
├── README.md                   ← 이 파일
├── plan.md                     ← 설계 계획서
├── .gitignore
│
├── bin/                        ← 바이너리 (gitignored)
│   ├── gitea.exe
│   ├── nssm.exe
│   └── rclone.exe
├── custom/conf/app.ini         ← Gitea 설정 (gitignored, 비밀값 포함)
├── data/gitea.db               ← SQLite DB (gitignored)
├── repos/                      ← Git 리포지토리 (gitignored)
├── backups/                    ← 백업 임시 (gitignored)
│
├── logs/                       ← 모든 실행 로그
│   ├── gitea/                  ← Gitea 런타임 (tracked)
│   ├── setup/                  ← 설치 스크립트 (gitignored — 매번 갱신)
│   ├── tests/                  ← 테스트 (tracked)
│   ├── backup/                 ← 백업 (tracked)
│   ├── restore/                ← 복구 (tracked)
│   ├── logs-rotation/          ← 로테이션 결과 (tracked)
│   └── agent-team/             ← 개발 파이프라인 보고서 (tracked)
│
└── scripts/
    ├── config.ps1              ← 공통 설정 (조건부 기본값)
    ├── common.ps1              ← 로깅 · 테스트 헬퍼
    ├── run-all-setup.ps1       ← 마스터 러너 (1~10 순차)
    ├── backup.ps1              ← 수동/자동 백업
    ├── restore.ps1             ← 전체 환경 복구
    ├── rotate-logs.ps1         ← 로그 로테이션
    │
    ├── setup/
    │   ├── 01-create-folders.ps1
    │   ├── 02-download-gitea.ps1
    │   ├── 03-download-nssm.ps1
    │   ├── 04-download-rclone.ps1
    │   ├── 05-firewall-rules.ps1            (관리자)
    │   ├── 06-run-setup-wizard.ps1          (대화형, 브라우저)
    │   ├── 07-generate-appini.ps1
    │   ├── 08-register-service.ps1          (관리자)
    │   ├── 09-configure-recovery.ps1        (관리자)
    │   ├── 10-register-backup-schedule.ps1  (관리자)
    │   └── 11-register-log-rotation-schedule.ps1 (관리자)
    │
    └── tests/
        ├── run-all-tests.ps1
        ├── test-01-folders.ps1
        ├── test-02-gitea-binary.ps1
        ├── test-03-nssm-binary.ps1
        ├── test-04-rclone-binary.ps1
        ├── test-05-firewall.ps1
        ├── test-06-appini.ps1
        ├── test-07-service.ps1
        ├── test-08-recovery.ps1
        ├── test-09-http-connectivity.ps1
        ├── test-10-ssh-connectivity.ps1
        ├── test-11-rclone-config.ps1
        ├── test-12-backup-schedule.ps1
        ├── test-13-backup-execution.ps1     (E2E)
        └── test-14-backup-precheck.ps1
```

---

## 빠른 시작

### 1. 프로젝트 가져오기

```powershell
# Git clone 또는 ZIP 다운로드 후 D:\Workspace\gitea\ 에 배치
cd D:\Workspace\gitea
```

### 2. config.ps1 편집

```powershell
notepad D:\Workspace\gitea\scripts\config.ps1
```

최소 수정 항목:

```powershell
$PUBLIC_IP = "222.234.220.199"   # 실제 공인 IP로 변경
$GDRIVE_REMOTE = "gdrive"         # rclone config에서 지을 원격 이름
```

### 3. 관리자 PowerShell에서 마스터 러너 실행

```powershell
D:\Workspace\gitea\scripts\run-all-setup.ps1 -PublicIp "222.234.220.199"
```

진행 중 두 번의 대화형 단계:
- **Step 6 Gitea 마법사**: 브라우저에서 `http://localhost:3000` → 설정 완료 후 Ctrl+C
- **rclone config**: 프롬프트가 뜨면 y 선택 → gdrive 원격 등록

### 4. 전체 테스트 검증

```powershell
D:\Workspace\gitea\scripts\tests\run-all-tests.ps1 -IncludeE2E
```

전체 PASS=14 FAIL=0 나오면 완료.

---

## 상세 설치 단계

마스터 러너가 내부적으로 아래 순서로 호출합니다. 개별 단계를 직접 실행하려면 각 스크립트 호출.

### Step 1~4 — 인프라 (비관리자 가능)

```powershell
.\setup\01-create-folders.ps1       # 폴더 구조 생성
.\setup\02-download-gitea.ps1       # gitea.exe ~112MB
.\setup\03-download-nssm.ps1        # nssm.exe 서비스 래퍼
.\setup\04-download-rclone.ps1      # rclone.exe ~72MB
```

옵션:
```powershell
.\setup\02-download-gitea.ps1 -Version 1.24.0 -Force
.\setup\02-download-gitea.ps1 -Url https://example.com/custom-gitea.exe
```

### Step 5 — 방화벽 (관리자)

```powershell
.\setup\05-firewall-rules.ps1
# 또는 포트 오버라이드:
.\setup\05-firewall-rules.ps1 -HttpPort 3000 -SshPort 2222
```

### Step 6 — Gitea 설정 마법사 (대화형)

```powershell
.\setup\06-run-setup-wizard.ps1
```

브라우저에서 `http://localhost:3000` 접속. 마법사 입력 값 (plan.md 기준):

| 항목 | 값 |
|------|-----|
| Database Type | SQLite3 |
| DB Path | `D:\Workspace\gitea\data\gitea.db` |
| Repository Root Path | `D:\Workspace\gitea\repos` |
| LFS Root Path | (비워둠) |
| Server Domain | 실제 공인 IP |
| SSH Server Port | `18022` |
| HTTP Port | `18080` |
| Gitea Base URL | `http://<공인IP>:18080/` |
| Log Root Path | `D:\Workspace\gitea\logs\gitea` |
| 관리자 계정 | 생성 **(스킵 금지 — 아래 주의사항 참고)** |

"Install Gitea" 클릭 → PowerShell 창에서 Ctrl+C로 종료.

> **⚠ 관리자 계정을 반드시 마법사에서 만드세요.** 이 프로젝트는 Step 7에서
> `DISABLE_REGISTRATION=true`를 적용하므로 이후 웹 가입이 불가능합니다.
> 마법사에서 스킵했거나 비번을 잊은 경우 CLI로 생성 가능 —
> [운영 → 관리자 계정 관리 (CLI)](#관리자-계정-관리-cli) 참고.

### Step 7 — 경량화 app.ini 덮어쓰기

```powershell
.\setup\07-generate-appini.ps1
```

마법사가 만든 app.ini에서 `INSTALL_LOCK` / `SECRET_KEY` / `INTERNAL_TOKEN` / `JWT_SECRET`은 **보존**하고,
나머지는 plan.md의 경량화 설정으로 덮어씁니다. 주요 변경점:

- `DISABLE_REGISTRATION = true` (회원가입 차단)
- `REQUIRE_SIGNIN_VIEW = true` (비로그인 접근 차단)
- `START_SSH_SERVER = true` (SSH 포트 바인딩)
- `OFFLINE_MODE = true`
- `[packages/actions/mirror/federation/mailer] ENABLED = false`
- API는 유지 (Claude Code 연동용)
- `SECRET_KEY`가 Gitea 1.20+ 마법사에서 누락되는 경우 `gitea generate secret`로 자동 생성

### Step 8~10 — 서비스 · 복구 · 스케줄 (관리자)

```powershell
.\setup\08-register-service.ps1       # NSSM으로 Windows 서비스 등록
.\setup\09-configure-recovery.ps1     # 실패 시 5초 후 × 3회 재시작
.\setup\10-register-backup-schedule.ps1  # 매일 03:00 백업
.\setup\11-register-log-rotation-schedule.ps1  # 매주 일 04:00 로그 정리
```

### rclone Google Drive 연결 (한 번만, 수동)

```powershell
D:\Workspace\gitea\bin\rclone.exe config
```

진행:
```
n              ← new remote
<원격 이름>     ← config.ps1의 $GDRIVE_REMOTE 값과 일치해야 함
drive          ← Storage 타입
<Enter>         ← client_id 비움
<Enter>         ← client_secret 비움
1              ← Full access scope
<Enter>         ← service_account_file 비움
n              ← advanced config
y              ← 브라우저 자동 인증 (OAuth)
<브라우저 OAuth 완료>
n              ← Team Drive 아님
y              ← 저장
q              ← quit
```

**중요**: `config password`를 물을 때 반드시 **n** 선택. y 선택하면 config 암호화되어 자동 백업이 password 프롬프트에서 멈춤.

확인:
```powershell
D:\Workspace\gitea\bin\rclone.exe listremotes
# → <원격 이름>: 출력되면 OK
```

---

## 설정 변경

### config.ps1 주요 기본값

```powershell
$PUBLIC_IP        = "222.234.220.199"    # 공인 IP
$HTTP_PORT        = 18080
$SSH_PORT         = 18022
$GITEA_VERSION    = "1.23.7"
$NSSM_VERSION     = "2.24"
$SERVICE_NAME     = "Gitea"
$BACKUP_TASK_NAME = "Gitea Daily Backup"
$GDRIVE_REMOTE    = "jjm-remote"          # rclone config에서 지은 이름
$GDRIVE_FOLDER    = "Gitea-Backup"
$BACKUP_FILENAME  = "gitea-backup.zip"
$APP_NAME         = "My Projects"
$LOG_LEVEL        = "warn"
$RESTART_DELAY_MS = 5000
$RESET_PERIOD_SEC = 86400
$BACKUP_TRIGGER_TIME = "3:00AM"
```

### 스크립트 옵션으로 오버라이드

config.ps1을 건드리지 않고도 각 스크립트에 옵션 전달 가능:

```powershell
# 마스터 러너
.\scripts\run-all-setup.ps1 `
    -PublicIp "10.0.0.1" `
    -HttpPort 3000 -SshPort 2222 `
    -GiteaVersion 1.24.0 `
    -ServiceName MyGitea `
    -TriggerTime "4:00AM" `
    -From 7 -To 10 `
    -Force -ContinueOnError

# 개별 스크립트
.\scripts\setup\08-register-service.ps1 -ServiceName GiteaProd -RestartDelay 10000

# 테스트
.\scripts\tests\run-all-tests.ps1 -Base D:\gitea-test -IncludeE2E -Filter "01,05,07"
```

---

## 운영 — 계정 · 서비스 · 백업 · 로그

### 관리자 계정 관리 (CLI)

마법사에서 관리자 계정을 스킵했거나, 비밀번호를 잊었거나, 계정을 추가/변경해야 할 때
`gitea admin user` 서브커맨드를 사용합니다. SQLite 잠금 충돌을 피하려면 **서비스 중지 후 실행** 권장.

#### 신규 관리자 생성

```powershell
Stop-Service Gitea
Start-Sleep -Seconds 2

D:\Workspace\gitea\bin\gitea.exe admin user create `
  --admin `
  --username joojm `
  --password "원하는_8자이상_비밀번호" `
  --email your-email@example.com `
  --must-change-password=false `
  -c "D:\Workspace\gitea\custom\conf\app.ini" `
  -w "D:\Workspace\gitea"

Start-Service Gitea
```

| 옵션 | 설명 |
|------|------|
| `--admin` | 관리자 권한 부여 |
| `--username` | 로그인 ID (영문/숫자/하이픈/언더스코어) |
| `--password` | **8자 이상 필수** |
| `--email` | 알림 꺼놨으니 아무거나 OK |
| `--must-change-password=false` | 첫 로그인 시 비번 강제 변경 해제 |
| `-c` / `-w` | 설정 파일 + 작업 디렉토리 (중요) |

#### 사용자 목록 조회

```powershell
D:\Workspace\gitea\bin\gitea.exe admin user list `
  -c "D:\Workspace\gitea\custom\conf\app.ini" `
  -w "D:\Workspace\gitea"
```

#### 비밀번호 변경

```powershell
Stop-Service Gitea
D:\Workspace\gitea\bin\gitea.exe admin user change-password `
  --username joojm `
  --password "새_비밀번호" `
  -c "D:\Workspace\gitea\custom\conf\app.ini" `
  -w "D:\Workspace\gitea"
Start-Service Gitea
```

#### 관리자 권한 부여/회수

```powershell
# 권한 부여
D:\Workspace\gitea\bin\gitea.exe admin user generate-access-token --username joojm --admin `
  -c "D:\Workspace\gitea\custom\conf\app.ini" -w "D:\Workspace\gitea"

# 권한 회수 (일반 사용자로 변경)
D:\Workspace\gitea\bin\gitea.exe admin user must-change-password --username joojm `
  -c "D:\Workspace\gitea\custom\conf\app.ini" -w "D:\Workspace\gitea"
```

> **참고**: `DISABLE_REGISTRATION=true`로 회원가입을 막아놨기 때문에 새 사용자는
> 항상 CLI로 생성해야 합니다. `--admin` 플래그 없이 호출하면 일반 사용자로 생성됩니다.

### 서비스 관리

```powershell
Get-Service Gitea                    # 상태 확인
Restart-Service Gitea                # 재시작
Stop-Service Gitea                   # 중지
Start-Service Gitea                  # 시작
sc.exe qfailure Gitea                # 실패 복구 정책 조회
```

### 수동 백업

```powershell
D:\Workspace\gitea\scripts\backup.ps1

# 업로드 없이 압축만
D:\Workspace\gitea\scripts\backup.ps1 -SkipUpload

# 다른 원격으로
D:\Workspace\gitea\scripts\backup.ps1 -GdriveRemote other-remote
```

### 백업 스케줄 조회 (관리자)

```powershell
Get-ScheduledTask -TaskName "Gitea Daily Backup"
Get-ScheduledTaskInfo -TaskName "Gitea Daily Backup"
```

### 로그 관리

```powershell
# 기본 (30일 초과 + 카테고리별 100개 초과 정리)
D:\Workspace\gitea\scripts\rotate-logs.ps1

# 드라이런으로 미리 확인
D:\Workspace\gitea\scripts\rotate-logs.ps1 -DryRun

# 보관 기간 / 개수 변경
D:\Workspace\gitea\scripts\rotate-logs.ps1 -RetentionDays 14 -MaxPerCategory 50

# 스케줄에 의해 매주 일요일 04:00 자동 실행 (Step 11에서 등록)
```

---

## 테스트

### 전체 실행

```powershell
# E2E 제외 (빠름, 약 20초)
D:\Workspace\gitea\scripts\tests\run-all-tests.ps1

# E2E 포함 (실제 백업까지, 약 25초 추가)
D:\Workspace\gitea\scripts\tests\run-all-tests.ps1 -IncludeE2E

# 특정 테스트만
D:\Workspace\gitea\scripts\tests\run-all-tests.ps1 -Filter "01,05,07,09"
```

### 테스트 목록

| # | 파일 | 검증 내용 | 관리자 |
|---|------|-----------|--------|
| 01 | test-01-folders | 폴더 구조 11개 | - |
| 02 | test-02-gitea-binary | gitea.exe 버전 일치 | - |
| 03 | test-03-nssm-binary | VersionInfo 기반 검증 | - |
| 04 | test-04-rclone-binary | rclone version 실행 | - |
| 05 | test-05-firewall | 방화벽 규칙 2개 | - |
| 06 | test-06-appini | 경량화 설정 18개 항목 | - |
| 07 | test-07-service | 서비스 등록 + NSSM 설정 | - |
| 08 | test-08-recovery | sc.exe qfailure 정책 | - |
| 09 | test-09-http-connectivity | HTTP 응답 + 포트 LISTEN | - |
| 10 | test-10-ssh-connectivity | SSH 포트 오픈 | - |
| 11 | test-11-rclone-config | 원격 등록 + 연결 | - |
| 12 | test-12-backup-schedule | 태스크 등록 상태 | **O** |
| 13 | test-13-backup-execution | E2E backup.ps1 실행 | **O** |
| 14 | test-14-backup-precheck | backup/restore 정적 검증 | - |

12/13은 SYSTEM 계정 태스크 조회 및 서비스 제어 권한이 필요하므로 비관리자 세션에서는 자동 SKIP됩니다.

### 결과 파일

- 개별 로그: `logs\tests\test-XX-*_<타임스탬프>.log`
- JSON 요약: `logs\tests\run-all-summary_<타임스탬프>.json`

---

## 트러블슈팅

이번 설치 과정에서 실제로 마주친 이슈와 해결 내역. 같은 증상 재현 시 참고.

### 1. `run-all-setup.ps1`의 PUBLIC_IP가 로그에 `CHANGE_ME`로 찍힘

**증상**: 관리자 PS로 `-PublicIp 1.2.3.4` 넘겼는데 로그 헤더 "효과 설정 값" 섹션에 `PUBLIC_IP = CHANGE_ME`.

**원인**: 마스터 러너가 `$Base`만 dot-source 전에 치환하고 `$PublicIp`는 개별 스크립트에서만 치환.

**영향**: 로깅 헤더만 표시 오류. 실제로는 07-generate-appini가 파라미터를 받아 제대로 적용.

**근본 해결**: `config.ps1`의 `$PUBLIC_IP` 기본값을 실제 IP로 박으면 모든 로그가 올바르게 표시.

### 2. Step 7 실패 — `SECRET_OR_TOKEN_MISSING`

**증상**: Step 7에서 `SECRET_KEY 또는 INTERNAL_TOKEN 없음` 오류.

**원인**: Gitea 1.20+ 마법사는 `SECRET_KEY`를 app.ini에 쓰지 않음 (`INTERNAL_TOKEN`만 씀).

**해결**: 07 스크립트가 `SECRET_KEY` 없으면 `gitea generate secret SECRET_KEY`로 64자 자동 생성 (적용됨).

### 3. 비관리자 세션에서 backup.ps1 실행 실패

**증상**: `Stop-Service` 권한 거부 → SQLite 잠금 해제 안 됨 → `Compress-Archive` "스트림 열 수 없습니다" 실패.

**해결**: backup.ps1은 관리자 권한으로만 실행. 스케줄 태스크는 SYSTEM 계정으로 돌기 때문에 무인 실행 OK.

### 4. rclone 업로드 실패 — `didn't find section in config file ("gdrive")`

**증상 A**: `Enter configuration password:` 프롬프트가 뜨고 바로 실패.

**원인 A**: `rclone config` 마법사 중 "configure a config password?"에서 y 선택 → config 암호화.

**해결 A**:
```powershell
D:\Workspace\gitea\bin\rclone.exe config
# s (Set configuration password) → r (Remove password) → 현재 비번 → q
```

**증상 B**: 프롬프트 없는데 섹션 못 찾음.

**원인 B**: config.ps1의 `$GDRIVE_REMOTE` 값 (`"gdrive"`)과 rclone에 등록된 실제 원격 이름 불일치.

**해결 B**: config.ps1의 `$GDRIVE_REMOTE`를 실제 이름으로 수정. 예: `"jjm-remote"`.

### 5. test-03 `nssm version` 10초 행업

**증상**: `& nssm.exe version` 이 10초 이상 응답 없음.

**원인**: NSSM 2.24는 `version` 서브커맨드가 GUI 경로로 빠져 콘솔 출력 0바이트.

**해결**: `(Get-Item $NSSM_EXE).VersionInfo.ProductName` 같은 파일 버전 리소스 기반으로 변경 (적용됨, 171ms).

### 6. test-07 NSSM 경로 비교 실패

**증상**: `NSSM Application = gitea.exe` FAIL. 로그에 글자 사이 공백 `D : \ W ...`.

**원인**: NSSM이 UTF-16LE로 stdout 출력 → 파이프 리다이렉트 시 NUL 바이트가 끼어 `Length = 2 × 예상`.

**해결**: `.Replace("`0","").Trim()`로 NUL 제거 후 비교 (적용됨).

### 7. test-08 `RESTART 액션 존재` FAIL (한국어 Windows)

**증상**: `sc.exe qfailure` 출력이 "다시 시작"으로 번역되어 영문 "RESTART" 패턴 미매칭.

**해결**: 정규식에 한국어 추가 — `(?i)restart|다시\s*시작|재시작` (적용됨).

### 8. test-10 파싱 에러

**증상**:
```
':' 뒤에 올바른 변수 이름 문자가 없습니다. ${}를 사용하여 이름을 지정하십시오.
```

**원인**: PowerShell 문자열 보간에서 `"$PUBLIC_IP:$SSH_PORT"`의 `:` 이후를 스코프 지정자로 해석.

**해결**: `"${PUBLIC_IP}:${SSH_PORT}"` 로 중괄호 감쌈 (적용됨).

### 9. test-12/13 비관리자에서 FAIL

**증상**: SYSTEM 계정 태스크 조회 거부, Stop-Service 거부.

**해결**: 두 테스트에 관리자 권한 체크 추가 → 비관리자면 SKIP (exit 0, 경고 메시지) (적용됨).

---

## 복구

빈 서버에서 전체 환경 재구축:

```powershell
# Git for Windows 사전 설치 필요
# scripts/ 폴더만 있으면 됨 (다른 폴더는 restore가 생성)

# Google Drive에서 다운로드 후 복구
D:\Workspace\gitea\scripts\restore.ps1 -BackupFile gdrive

# 로컬 zip 파일로 복구
D:\Workspace\gitea\scripts\restore.ps1 -BackupFile C:\backups\gitea-backup.zip

# 다운로드 건너뛰기 (바이너리 이미 있음)
D:\Workspace\gitea\scripts\restore.ps1 -BackupFile gdrive -SkipDownload
```

**주의**:
- 복구 시 기존 `data/repos/app.ini`는 `restore-safety-<ts>/`로 사이드 백업됨 (데이터 손실 방지).
- `restore-temp/`는 작업 후 try/finally로 자동 정리.
- rclone은 재설정 필요: `D:\Workspace\gitea\bin\rclone.exe config`.

---

## 참고 문서

- **[plan.md](plan.md)** — 설계 계획서 (폴더 구조, 포트 선택 근거, app.ini 전체 내용)
- **[logs/agent-team/README.md](logs/agent-team/README.md)** — 개발 파이프라인 이터레이션 3회 보고서
  - iter1: exit 전파 버그, 테스트 패턴 동기화
  - iter2: NSSM/wizard 공백 경로, test-03 행업 해결
  - iter3: backup/restore 엣지 케이스, 로그 로테이션 실구현

### 외부 링크

| 항목 | URL |
|------|-----|
| Gitea Windows 설치 | https://docs.gitea.com/enterprise/installation/windows |
| Gitea app.ini 설정 | https://docs.gitea.com/administration/config-cheat-sheet |
| Gitea app.example.ini | https://github.com/go-gitea/gitea/blob/main/custom/conf/app.example.ini |
| NSSM 다운로드 | https://nssm.cc/ |
| rclone Google Drive | https://rclone.org/drive/ |
| rclone 다운로드 | https://rclone.org/downloads/ |

---

## 라이선스 · 저작자

개인 프로젝트 용도. 재배포 시 원 저자 표기만 유지하면 자유 사용.
