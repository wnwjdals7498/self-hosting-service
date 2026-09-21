# ============================================
# Test 11: rclone 구성 (Google Drive)
# ============================================
# 옵션:
#   -GdriveRemote <str>
#   -GdriveFolder <str>
# ============================================
param(
    [string]$GdriveRemote,
    [string]$GdriveFolder
)

if ($GdriveRemote) { $GDRIVE_REMOTE = $GdriveRemote }
if ($GdriveFolder) { $GDRIVE_FOLDER = $GdriveFolder }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-11-rclone-config' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 11: rclone 원격 '$GDRIVE_REMOTE' 검증"

    if (-not (Test-Path $RCLONE_EXE)) {
        Test-Result -Name "rclone.exe 존재" -Passed $false | Out-Null
        throw "RCLONE_EXE_MISSING"
    }

    $remotes = & $RCLONE_EXE listremotes 2>&1
    Write-Info "등록된 원격:"
    Write-Info ($remotes | Out-String).Trim()

    $hasRemote = "$remotes" -match "^${GDRIVE_REMOTE}:" -or "$remotes" -match "`n${GDRIVE_REMOTE}:"
    if (Test-Result -Name "원격 '$GDRIVE_REMOTE' 등록됨" -Passed $hasRemote) { $pass++ } else {
        Write-Warn "설정하려면: $RCLONE_EXE config"
        throw "RCLONE_REMOTE_NOT_CONFIGURED"
    }

    Write-Info "원격 연결 테스트 (rclone about)..."
    $about = & $RCLONE_EXE about "${GDRIVE_REMOTE}:" 2>&1 | Out-String
    $reachable = $LASTEXITCODE -eq 0
    if (Test-Result -Name "원격 연결 가능" -Passed $reachable -Detail $about.Trim()) { $pass++ } else { $fail++ }

    $lsOut = & $RCLONE_EXE lsd "${GDRIVE_REMOTE}:" 2>&1 | Out-String
    $folderExists = $lsOut -match [regex]::Escape($GDRIVE_FOLDER)
    if ($folderExists) {
        if (Test-Result -Name "백업 폴더 존재: $GDRIVE_FOLDER" -Passed $true) { $pass++ }
    } else {
        Write-Warn "백업 폴더 '$GDRIVE_FOLDER' 없음 — 첫 백업 시 자동 생성됨"
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
