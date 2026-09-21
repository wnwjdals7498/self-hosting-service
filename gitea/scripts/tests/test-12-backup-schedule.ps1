# ============================================
# Test 12: 백업 스케줄 태스크
# ============================================
# 옵션:
#   -TaskName <str>
# ============================================
param(
    [string]$TaskName
)

if ($TaskName) { $BACKUP_TASK_NAME = $TaskName }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-12-backup-schedule' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 12: 스케줄 태스크 '$BACKUP_TASK_NAME' 검증"

    # SYSTEM 계정으로 등록된 태스크는 비관리자 세션에서 조회 자체가 거부됨 → SKIP 처리
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object System.Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Warn "비관리자 세션 — SYSTEM 계정 태스크 조회 불가. SKIP (exit 0)."
        Write-Warn "관리자 PS에서 단독 실행 권장: D:\Workspace\gitea\scripts\tests\test-12-backup-schedule.ps1"
        Write-TestSummary -Pass 0 -Fail 0
        return
    }

    $task = Get-ScheduledTask -TaskName $BACKUP_TASK_NAME -ErrorAction SilentlyContinue
    if (Test-Result -Name "태스크 등록됨" -Passed ($null -ne $task)) { $pass++ } else { throw "SCHEDULED_TASK_NOT_REGISTERED" }

    Write-Info "State  : $($task.State)"
    Write-Info "Author : $($task.Author)"

    $ready = $task.State -in @('Ready','Running')
    if (Test-Result -Name "태스크 Ready/Running" -Passed $ready -Detail "State=$($task.State)") { $pass++ } else { $fail++ }

    $info = Get-ScheduledTaskInfo -TaskName $BACKUP_TASK_NAME
    Write-Info "NextRunTime: $($info.NextRunTime)"
    Write-Info "LastRunTime: $($info.LastRunTime)"
    Write-Info "LastResult : $($info.LastTaskResult)"

    $hasTrigger = $task.Triggers.Count -gt 0
    if (Test-Result -Name "트리거 설정됨 ($($task.Triggers.Count)개)" -Passed $hasTrigger) { $pass++ } else { $fail++ }

    $action = $task.Actions | Select-Object -First 1
    Write-Info "Execute : $($action.Execute)"
    Write-Info "Args    : $($action.Arguments)"

    $hasPwsh = "$($action.Execute)" -match 'powershell'
    if (Test-Result -Name "powershell.exe 실행" -Passed $hasPwsh) { $pass++ } else { $fail++ }

    $hasBackup = "$($action.Arguments)" -match 'backup\.ps1'
    if (Test-Result -Name "backup.ps1 인자에 포함" -Passed $hasBackup) { $pass++ } else { $fail++ }

    Write-TestSummary -Pass $pass -Fail $fail
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
    Write-TestSummary -Pass $pass -Fail $fail
} finally {
    Stop-ScriptLog -ExitCode $fail
}
exit $fail
