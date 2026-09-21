# ============================================
# [09] 서비스 실패 복구 설정 (sc.exe failure)
# ============================================
# 옵션:
#   -ServiceName <str>    : 대상 서비스 (기본 "Gitea")
#   -RestartDelay <ms>    : 재시작 지연 (기본 5000)
#   -ResetPeriod <sec>    : 실패 카운터 리셋 주기 (기본 86400)
# ============================================
param(
    [string]$ServiceName,
    [int]$RestartDelay,
    [int]$ResetPeriod
)

if ($ServiceName)  { $SERVICE_NAME     = $ServiceName }
if ($RestartDelay) { $RESTART_DELAY_MS = $RestartDelay }
if ($ResetPeriod)  { $RESET_PERIOD_SEC = $ResetPeriod }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '09-configure-recovery' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Assert-Admin
    Write-Step "서비스 실패 복구 설정"

    $svc = Get-Service $SERVICE_NAME -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Fail "서비스 없음: $SERVICE_NAME. 08-register-service.ps1 먼저 실행."
        throw "SERVICE_NOT_REGISTERED"
    }

    Write-Info "대상 서비스      : $SERVICE_NAME"
    Write-Info "재시작 지연 (ms) : $RESTART_DELAY_MS"
    Write-Info "리셋 주기 (초)   : $RESET_PERIOD_SEC"
    Write-Info "복구 정책        : ${RESTART_DELAY_MS}ms 후 재시작 × 3회"

    $actions = "restart/$RESTART_DELAY_MS/restart/$RESTART_DELAY_MS/restart/$RESTART_DELAY_MS"
    $scOutput = & sc.exe failure $SERVICE_NAME reset= $RESET_PERIOD_SEC actions= $actions 2>&1
    Write-Info "sc.exe failure 출력: $scOutput"

    if ($LASTEXITCODE -ne 0) {
        Write-Fail "sc.exe failure 실패 (exit=$LASTEXITCODE)"
        throw "SC_FAILURE_CMD_FAILED"
    }

    Write-Ok "실패 복구 정책 적용됨"

    Write-Step "현재 복구 설정 조회"
    & sc.exe qfailure $SERVICE_NAME
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
