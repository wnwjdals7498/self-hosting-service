# ============================================
# [10] 일일 백업 스케줄 등록
# ============================================
# 옵션:
#   -Base <path>              : 기본 디렉토리
#   -TaskName <str>           : 스케줄 태스크 이름 (기본 "Gitea Daily Backup")
#   -TriggerTime <str>        : 실행 시각 (기본 "3:00AM")
#   -User <str>               : 실행 계정 (기본 "SYSTEM")
# ============================================
param(
    [string]$Base,
    [string]$TaskName,
    [string]$TriggerTime,
    [string]$User = "SYSTEM"
)

if ($Base)        { $BASE                = $Base }
if ($TaskName)    { $BACKUP_TASK_NAME    = $TaskName }
if ($TriggerTime) { $BACKUP_TRIGGER_TIME = $TriggerTime }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '10-register-backup-schedule' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Assert-Admin
    Write-Step "백업 스케줄 태스크 등록"

    $backupScript = "$SCRIPT_DIR\backup.ps1"
    if (-not (Test-Path $backupScript)) {
        Write-Fail "backup.ps1 없음: $backupScript"
        throw "BACKUP_SCRIPT_MISSING"
    }

    Write-Info "태스크 이름    : $BACKUP_TASK_NAME"
    Write-Info "실행 스크립트  : $backupScript"
    Write-Info "트리거         : 매일 $BACKUP_TRIGGER_TIME"
    Write-Info "실행 계정      : $User (Highest)"

    $existing = Get-ScheduledTask -TaskName $BACKUP_TASK_NAME -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Warn "이미 존재: $BACKUP_TASK_NAME — 재등록합니다."
        Unregister-ScheduledTask -TaskName $BACKUP_TASK_NAME -Confirm:$false
    }

    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`""

    $Trigger = New-ScheduledTaskTrigger -Daily -At $BACKUP_TRIGGER_TIME
    $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

    Register-ScheduledTask `
        -TaskName $BACKUP_TASK_NAME `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -User $User `
        -RunLevel Highest | Out-Null

    Write-Ok "스케줄 등록 완료"

    $task = Get-ScheduledTask -TaskName $BACKUP_TASK_NAME
    Write-Info "상태: $($task.State)"
    $info = Get-ScheduledTaskInfo -TaskName $BACKUP_TASK_NAME
    Write-Info "다음 실행: $($info.NextRunTime)"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
