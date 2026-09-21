# ============================================
# Gitea 호스팅 공통 설정 (기본값 정의)
# ============================================
# 이 파일은 '조건부 기본값' 방식입니다.
# 스크립트가 param()으로 값을 먼저 설정하면 이 파일은 건드리지 않고,
# 설정되지 않은 값만 아래 기본값으로 채웁니다.
#
# 환경별 커스텀은 두 가지 방법:
#   (1) 이 파일의 기본값을 직접 수정
#   (2) 각 setup 스크립트에 -Base, -HttpPort, -PublicIp 등 옵션 전달
#
# 실행 순서:
#   setup/01-create-folders.ps1
#   setup/02-download-gitea.ps1
#   setup/03-download-nssm.ps1
#   setup/04-download-rclone.ps1
#   setup/05-firewall-rules.ps1         (관리자)
#   setup/06-run-setup-wizard.ps1       (최초 1회)
#   setup/07-generate-appini.ps1
#   setup/08-register-service.ps1       (관리자)
#   setup/09-configure-recovery.ps1     (관리자)
#   setup/10-register-backup-schedule.ps1 (관리자)
# ============================================

# --- 환경 값 (param으로 이미 설정되지 않은 경우 기본값) ---
if ([string]::IsNullOrEmpty($PUBLIC_IP))        { $PUBLIC_IP        = "222.234.220.199" }
if ([string]::IsNullOrEmpty($BASE))             { $BASE             = "D:\Workspace\gitea" }
if (-not $HTTP_PORT)                            { $HTTP_PORT        = 18080 }
if (-not $SSH_PORT)                             { $SSH_PORT         = 18022 }
if ([string]::IsNullOrEmpty($GITEA_VERSION))    { $GITEA_VERSION    = "1.23.7" }
if ([string]::IsNullOrEmpty($NSSM_VERSION))     { $NSSM_VERSION     = "2.24" }
if ([string]::IsNullOrEmpty($SERVICE_NAME))     { $SERVICE_NAME     = "Gitea" }
if ([string]::IsNullOrEmpty($BACKUP_TASK_NAME)) { $BACKUP_TASK_NAME = "Gitea Daily Backup" }
if ([string]::IsNullOrEmpty($GDRIVE_REMOTE))    { $GDRIVE_REMOTE    = "jjm-remote" }
if ([string]::IsNullOrEmpty($GDRIVE_FOLDER))    { $GDRIVE_FOLDER    = "Gitea-Backup" }
if ([string]::IsNullOrEmpty($BACKUP_FILENAME))  { $BACKUP_FILENAME  = "gitea-backup.zip" }
if ([string]::IsNullOrEmpty($APP_NAME))         { $APP_NAME         = "My Projects" }
if ([string]::IsNullOrEmpty($LOG_LEVEL))        { $LOG_LEVEL        = "warn" }
if (-not $RESTART_DELAY_MS)                     { $RESTART_DELAY_MS = 5000 }
if (-not $RESET_PERIOD_SEC)                     { $RESET_PERIOD_SEC = 86400 }
if ([string]::IsNullOrEmpty($BACKUP_TRIGGER_TIME)) { $BACKUP_TRIGGER_TIME = "3:00AM" }

# --- 파생 경로 (BASE 기준으로 매번 재계산) ---
$BIN_DIR    = "$BASE\bin"
$CONF_DIR   = "$BASE\custom\conf"
$DATA_DIR   = "$BASE\data"
$REPOS_DIR  = "$BASE\repos"
$LOG_DIR    = "$BASE\logs\gitea"
$BACKUP_DIR = "$BASE\backups"
$SCRIPT_DIR = "$BASE\scripts"

$APPINI_PATH = "$CONF_DIR\app.ini"
$GITEA_EXE   = "$BIN_DIR\gitea.exe"
$NSSM_EXE    = "$BIN_DIR\nssm.exe"
$RCLONE_EXE  = "$BIN_DIR\rclone.exe"
