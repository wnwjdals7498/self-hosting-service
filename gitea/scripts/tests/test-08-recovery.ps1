# ============================================
# Test 08: 서비스 실패 복구 설정
# ============================================
# 옵션:
#   -ServiceName <str>
#   -RestartDelay <ms>
#   -ResetPeriod <sec>
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

Start-ScriptLog -Category 'tests' -Name 'test-08-recovery' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 08: 복구 정책 검증 (delay=${RESTART_DELAY_MS}ms, reset=${RESET_PERIOD_SEC}s)"

    $svc = Get-Service $SERVICE_NAME -ErrorAction SilentlyContinue
    if (Test-Result -Name "서비스 존재" -Passed ($null -ne $svc)) { $pass++ } else { throw "SERVICE_NOT_REGISTERED" }

    $out = (& sc.exe qfailure $SERVICE_NAME 2>&1 | Out-String)
    Write-Info "sc.exe qfailure 출력:"
    Write-Info $out.Trim()

    # sc.exe qfailure 출력은 OS 언어에 따라 "RESTART" 또는 "다시 시작" / "재시작"으로 번역됨
    $hasRestart = $out -match '(?i)restart|다시\s*시작|재시작'
    if (Test-Result -Name "RESTART 액션 존재 (영/한 매칭)" -Passed $hasRestart) { $pass++ } else { $fail++ }

    $hasDelay = $out -match "$RESTART_DELAY_MS"
    if (Test-Result -Name "재시작 지연 ${RESTART_DELAY_MS}ms" -Passed $hasDelay) { $pass++ } else { $fail++ }

    $hasReset = $out -match "$RESET_PERIOD_SEC"
    if (Test-Result -Name "리셋 주기 ${RESET_PERIOD_SEC}초" -Passed $hasReset) { $pass++ } else { $fail++ }

    Write-TestSummary -Pass $pass -Fail $fail
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
    Write-TestSummary -Pass $pass -Fail $fail
} finally {
    Stop-ScriptLog -ExitCode $fail
}
exit $fail
