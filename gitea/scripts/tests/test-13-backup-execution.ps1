# ============================================
# Test 13: 백업 스크립트 실제 실행 (E2E)
# ============================================
# 경고: 이 테스트는 backup.ps1을 실제 실행합니다.
#   - Gitea 서비스가 잠시(수 초) 중지됨
#   - Google Drive에 파일이 업로드됨 (덮어쓰기)
# ============================================
# 옵션:
#   -Base <path>
#   -ServiceName <str>
#   -GdriveRemote <str>
#   -GdriveFolder <str>
#   -SkipUpload          : 업로드 없이 압축까지만
# ============================================
param(
    [string]$Base,
    [string]$ServiceName,
    [string]$GdriveRemote,
    [string]$GdriveFolder,
    [switch]$SkipUpload
)

if ($Base)         { $BASE          = $Base }
if ($ServiceName)  { $SERVICE_NAME  = $ServiceName }
if ($GdriveRemote) { $GDRIVE_REMOTE = $GdriveRemote }
if ($GdriveFolder) { $GDRIVE_FOLDER = $GdriveFolder }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-13-backup-execution' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 13: backup.ps1 E2E 실행"
    Write-Warn "⚠ 이 테스트는 실제 백업을 수행합니다."

    # backup.ps1은 Stop-Service/Start-Service가 필요하므로 관리자 권한 필수 → 비관리자면 SKIP
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object System.Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Warn "비관리자 세션 — backup.ps1은 Stop-Service/Start-Service 권한 필요. SKIP (exit 0)."
        Write-Warn "관리자 PS에서 단독 실행 권장: D:\Workspace\gitea\scripts\tests\test-13-backup-execution.ps1"
        Write-TestSummary -Pass 0 -Fail 0
        return
    }

    $backupScript = "$SCRIPT_DIR\backup.ps1"
    if (-not (Test-Path $backupScript)) {
        Test-Result -Name "backup.ps1 존재" -Passed $false | Out-Null
        throw "BACKUP_SCRIPT_MISSING"
    }

    $started = Get-Date
    Write-Info "실행 시각: $($started.ToString('yyyy-MM-dd HH:mm:ss'))"

    # backup.ps1에 같은 파라미터 전달
    $forwardArgs = @{}
    foreach ($k in $PSBoundParameters.Keys) { $forwardArgs[$k] = $PSBoundParameters[$k] }
    & $backupScript @forwardArgs
    $ec = $LASTEXITCODE
    $dur = [int]((Get-Date) - $started).TotalSeconds
    Write-Info "소요 시간: ${dur}초 / 종료 코드: $ec"

    if (Test-Result -Name "backup.ps1 정상 종료 (exit 0)" -Passed ($ec -eq 0)) { $pass++ } else { $fail++ }

    if (-not $SkipUpload) {
        $listing = & $RCLONE_EXE ls "${GDRIVE_REMOTE}:${GDRIVE_FOLDER}" 2>&1 | Out-String
        Write-Info "원격 파일 목록:"
        Write-Info $listing.Trim()

        $hasBackup = $listing -match [regex]::Escape($BACKUP_FILENAME)
        if (Test-Result -Name "Google Drive에 $BACKUP_FILENAME 존재" -Passed $hasBackup) { $pass++ } else { $fail++ }

        $localLeft = Test-Path "$BACKUP_DIR\$BACKUP_FILENAME"
        if (Test-Result -Name "로컬 임시 파일 제거됨" -Passed (-not $localLeft)) { $pass++ } else { $fail++ }
    } else {
        Write-Info "-SkipUpload — 원격 검증 건너뜀"
    }

    $svc = Get-Service $SERVICE_NAME -ErrorAction SilentlyContinue
    $running = $svc -and "$($svc.Status)" -eq 'Running'
    if (Test-Result -Name "백업 후 서비스 실행 상태 유지" -Passed $running -Detail "Status=$($svc.Status)") { $pass++ } else { $fail++ }

    Write-TestSummary -Pass $pass -Fail $fail
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
    Write-TestSummary -Pass $pass -Fail $fail
} finally {
    Stop-ScriptLog -ExitCode $fail
}
exit $fail
