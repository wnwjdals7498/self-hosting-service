# ============================================
# Test 03: NSSM 바이너리
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

Start-ScriptLog -Category 'tests' -Name 'test-03-nssm-binary' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 03: nssm.exe 검증"

    $exists = Test-Path $NSSM_EXE
    if (Test-Result -Name "nssm.exe 존재" -Passed $exists -Detail $NSSM_EXE) { $pass++ } else { throw "NSSM_EXE_MISSING" }

    $size = (Get-Item $NSSM_EXE).Length
    $hasSize = $size -gt 100KB
    if (Test-Result -Name "파일 크기 > 100KB" -Passed $hasSize -Detail "$([math]::Round($size / 1KB, 1)) KB") { $pass++ } else { $fail++ }

    # NSSM 2.24는 `nssm version`이 GUI 경로로 빠져 콘솔 출력이 비어 행업되는 이슈가 있어
    # 파일 버전 리소스(ProductName/FileDescription/ProductVersion)를 기준으로 검증한다.
    $vi = (Get-Item $NSSM_EXE).VersionInfo
    $verTag = "$($vi.ProductName) / $($vi.FileDescription) / $($vi.ProductVersion)"
    $runs = ("$($vi.ProductName) $($vi.FileDescription)") -match '(?i)NSSM|non-sucking'
    if (Test-Result -Name "nssm 버전 리소스 확인" -Passed $runs -Detail $verTag) { $pass++ } else { $fail++ }

    Write-TestSummary -Pass $pass -Fail $fail
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
    Write-TestSummary -Pass $pass -Fail $fail
} finally {
    Stop-ScriptLog -ExitCode $fail
}
exit $fail
