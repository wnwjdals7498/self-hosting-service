# ============================================
# [11] 로그 로테이션 주간 스케줄 등록
# ============================================
# 옵션:
#   -Base <path>              : 기본 디렉토리
#   -TaskName <str>           : 스케줄 태스크 이름 (기본 "Gitea Log Rotation")
#   -TriggerTime <str>        : 실행 시각 (기본 "4:00AM")
#   -WeeklyDay <str>          : 요일 (기본 Sunday)
#   -User <str>               : 실행 계정 (기본 "SYSTEM")
#   -RetentionDays <int>      : 보존일수 (기본 30)
#   -MaxPerCategory <int>     : 카테고리 상한 (기본 100)
# ============================================
param(
    [string]$Base,
    [string]$TaskName = "Gitea Log Rotation",
    [string]$TriggerTime = "4:00AM",
    [string]$WeeklyDay = "Sunday",
    [string]$User = "SYSTEM",
    [int]$RetentionDays = 30,
    [int]$MaxPerCategory = 100
)

if ($Base) { $BASE = $Base }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '11-register-log-rotation-schedule' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Assert-Admin
    Write-Step "로그 로테이션 스케줄 태스크 등록"

    $rotateScript = "$SCRIPT_DIR\rotate-logs.ps1"
    if (-not (Test-Path $rotateScript)) {
        Write-Fail "rotate-logs.ps1 없음: $rotateScript"
        throw "ROTATE_SCRIPT_MISSING"
    }

    Write-Info "태스크 이름      : $TaskName"
    Write-Info "실행 스크립트    : $rotateScript"
    Write-Info "트리거           : 매주 $WeeklyDay $TriggerTime"
    Write-Info "실행 계정        : $User (Highest)"
    Write-Info "RetentionDays    : $RetentionDays"
    Write-Info "MaxPerCategory   : $MaxPerCategory"

    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Warn "이미 존재: $TaskName — 재등록합니다."
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    $argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$rotateScript`" -RetentionDays $RetentionDays -MaxPerCategory $MaxPerCategory"

    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument $argLine

    $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $TriggerTime
    $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -User $User `
        -RunLevel Highest | Out-Null

    Write-Ok "스케줄 등록 완료"

    $task = Get-ScheduledTask -TaskName $TaskName
    Write-Info "상태: $($task.State)"
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Info "다음 실행: $($info.NextRunTime)"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
