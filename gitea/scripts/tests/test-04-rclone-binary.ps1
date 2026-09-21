# ============================================
# Test 04: rclone 바이너리
# ============================================
# 옵션:
#   -Base <path>  : 기본 디렉토리
# ============================================
param(
    [string]$Base
)

if ($Base) { $BASE = $Base }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-04-rclone-binary' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 04: rclone.exe 검증"

    $exists = Test-Path $RCLONE_EXE
    if (Test-Result -Name "rclone.exe 존재" -Passed $exists -Detail $RCLONE_EXE) { $pass++ } else { throw "RCLONE_EXE_MISSING" }

    $size = (Get-Item $RCLONE_EXE).Length
    $hasSize = $size -gt 10MB
    if (Test-Result -Name "파일 크기 > 10MB" -Passed $hasSize -Detail "$([math]::Round($size / 1MB, 1)) MB") { $pass++ } else { $fail++ }

    $verOut = & $RCLONE_EXE version 2>&1 | Out-String
    $runs = $verOut -match 'rclone'
    $detail = (($verOut -split "`n") | Select-Object -First 2) -join ' | '
    if (Test-Result -Name "rclone version 실행 가능" -Passed $runs -Detail $detail) { $pass++ } else { $fail++ }

    Write-TestSummary -Pass $pass -Fail $fail
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
    Write-TestSummary -Pass $pass -Fail $fail
} finally {
    Stop-ScriptLog -ExitCode $fail
}
exit $fail
