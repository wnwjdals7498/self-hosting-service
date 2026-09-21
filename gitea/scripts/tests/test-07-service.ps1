# ============================================
# Test 07: Windows 서비스
# ============================================
# 옵션:
#   -Base <path>
#   -ServiceName <str>
# ============================================
param(
    [string]$Base,
    [string]$ServiceName
)

if ($Base)        { $BASE         = $Base }
if ($ServiceName) { $SERVICE_NAME = $ServiceName }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-07-service' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 07: 서비스 '$SERVICE_NAME' 검증"

    $svc = Get-Service $SERVICE_NAME -ErrorAction SilentlyContinue
    $exists = $null -ne $svc
    if (Test-Result -Name "서비스 등록됨" -Passed $exists) { $pass++ } else { throw "SERVICE_NOT_REGISTERED" }

    Write-Info "DisplayName: $($svc.DisplayName)"
    Write-Info "Status     : $($svc.Status)"
    Write-Info "StartType  : $($svc.StartType)"

    $running = "$($svc.Status)" -eq 'Running'
    if (Test-Result -Name "서비스 실행 중" -Passed $running -Detail "Status=$($svc.Status)") { $pass++ } else { $fail++ }

    $auto = "$($svc.StartType)" -eq 'Automatic'
    if (Test-Result -Name "자동 시작 설정" -Passed $auto -Detail "StartType=$($svc.StartType)") { $pass++ } else { $fail++ }

    # NSSM 설정 확인
    # NSSM 4.x+는 wide-char(UTF-16) 로 stdout 출력 → 파이프 리다이렉트 시 NUL 바이트가 끼므로 제거
    if (Test-Path $NSSM_EXE) {
        $appPath = ((& $NSSM_EXE get $SERVICE_NAME Application 2>&1) | Out-String).Replace("`0","").Trim()
        $appPathOk = $appPath -eq $GITEA_EXE
        if (Test-Result -Name "NSSM Application = gitea.exe" -Passed $appPathOk -Detail "get=[$appPath] expected=[$GITEA_EXE]") { $pass++ } else { $fail++ }

        $appDir = ((& $NSSM_EXE get $SERVICE_NAME AppDirectory 2>&1) | Out-String).Replace("`0","").Trim()
        $appDirOk = $appDir -eq $BIN_DIR
        if (Test-Result -Name "NSSM AppDirectory = bin" -Passed $appDirOk -Detail "get=[$appDir] expected=[$BIN_DIR]") { $pass++ } else { $fail++ }
    }

    Write-TestSummary -Pass $pass -Fail $fail
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
    Write-TestSummary -Pass $pass -Fail $fail
} finally {
    Stop-ScriptLog -ExitCode $fail
}
exit $fail
