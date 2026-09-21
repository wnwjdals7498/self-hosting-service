# ============================================
# Test 02: Gitea 바이너리
# ============================================
# 옵션:
#   -Base <path>    : 기본 디렉토리
#   -Version <ver>  : 기대 버전
# ============================================
param(
    [string]$Base,
    [string]$Version
)

if ($Base)    { $BASE = $Base }
if ($Version) { $GITEA_VERSION = $Version }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-02-gitea-binary' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 02: gitea.exe 검증 (기대 버전: $GITEA_VERSION)"

    $exists = Test-Path $GITEA_EXE
    if (Test-Result -Name "gitea.exe 존재" -Passed $exists -Detail $GITEA_EXE) { $pass++ } else { throw "GITEA_EXE_MISSING" }

    $size = (Get-Item $GITEA_EXE).Length
    $hasSize = $size -gt 1MB
    if (Test-Result -Name "파일 크기 > 1MB" -Passed $hasSize -Detail "$([math]::Round($size / 1MB, 2)) MB") { $pass++ } else { $fail++ }

    try {
        $verOut = & $GITEA_EXE --version 2>&1 | Out-String
    } catch {
        $verOut = "실행 실패: $($_.Exception.Message)"
    }
    $runs = $verOut -match 'Gitea'
    if (Test-Result -Name "--version 실행 가능" -Passed $runs -Detail $verOut.Trim()) { $pass++ } else { $fail++ }

    $correctVer = $verOut -match [regex]::Escape($GITEA_VERSION)
    if (Test-Result -Name "기대 버전 일치 ($GITEA_VERSION)" -Passed $correctVer -Detail $verOut.Trim()) { $pass++ } else { $fail++ }

    Write-TestSummary -Pass $pass -Fail $fail
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
    Write-TestSummary -Pass $pass -Fail $fail
} finally {
    Stop-ScriptLog -ExitCode $fail
}
exit $fail
