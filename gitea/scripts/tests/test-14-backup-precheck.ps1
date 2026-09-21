# ============================================
# Test 14: backup.ps1 / restore.ps1 사전 체크 & 안전장치 정적 검증
# ============================================
# 이 테스트는 부작용 없이(관리자 불필요·네트워크 불필요) 실행 가능.
#   - 정적(소스 패턴) 검증: Setter iter3의 5건 버그 수정이 소스에 실제 반영됐는지
#   - 실측(라이브) 검증: Gitea 미설치 환경에서 backup.ps1 -SkipUpload 실행 →
#     exit=1 + "APPINI_MISSING" 힌트 출력
#
# 옵션:
#   -Base <path>   : 기본 디렉토리 (run-all-tests.ps1 forward 호환)
#   -SkipLive      : 실측 실행 단계 생략(Gitea가 정상 설치된 환경용)
# ============================================
param(
    [string]$Base,
    [switch]$SkipLive
)

if ($Base) { $BASE = $Base }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-14-backup-precheck' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 14: backup/restore 사전 체크 & 안전장치 검증"

    $backupScript  = "$SCRIPT_DIR\backup.ps1"
    $restoreScript = "$SCRIPT_DIR\restore.ps1"

    if (Test-Result -Name "backup.ps1 존재"  -Passed (Test-Path $backupScript)  -Detail $backupScript)  { $pass++ } else { $fail++; throw "BACKUP_SCRIPT_MISSING" }
    if (Test-Result -Name "restore.ps1 존재" -Passed (Test-Path $restoreScript) -Detail $restoreScript) { $pass++ } else { $fail++; throw "RESTORE_SCRIPT_MISSING" }

    $backupSrc  = Get-Content $backupScript  -Raw
    $restoreSrc = Get-Content $restoreScript -Raw

    # --- [정적-1] restore.ps1 사이드 백업 (Setter iter3 버그 #1) ---
    $hasSafetyRoot   = $restoreSrc -match 'restore-safety-'
    $hasSafetyCopy   = $restoreSrc -match 'safetyRoot' -and $restoreSrc -match 'Copy-Item'
    if (Test-Result -Name "restore.ps1: restore-safety-<ts> 사이드 백업 블록 존재" -Passed ($hasSafetyRoot -and $hasSafetyCopy)) { $pass++ } else { $fail++ }

    # --- [정적-2] restore.ps1 try/finally로 restore-temp 정리 (버그 #2) ---
    # Expand-Archive 이후 어디서든 finally에서 tmp를 제거해야 함
    # 라인 단위로 Expand-Archive 이후에 finally 블록과 Remove-Item $tmp가 나오는지 확인
    $reLines = $restoreSrc -split "`r?`n"
    $expandIdx  = -1
    $finallyIdx = -1
    $removeIdx  = -1
    for ($i = 0; $i -lt $reLines.Count; $i++) {
        if ($expandIdx  -lt 0 -and $reLines[$i] -match '\bExpand-Archive\b')     { $expandIdx  = $i }
        if ($expandIdx  -ge 0 -and $finallyIdx -lt 0 -and $reLines[$i] -match '\bfinally\s*\{') { $finallyIdx = $i }
        if ($finallyIdx -ge 0 -and $removeIdx  -lt 0 -and $reLines[$i] -match 'Remove-Item\s+\$tmp') { $removeIdx = $i }
    }
    $hasTryFinallyTmp = ($expandIdx -ge 0) -and ($finallyIdx -gt $expandIdx) -and ($removeIdx -gt $finallyIdx)
    $tfDetail = "expand=$expandIdx finally=$finallyIdx remove=$removeIdx"
    if (Test-Result -Name "restore.ps1: Expand-Archive try/finally로 restore-temp 정리" -Passed $hasTryFinallyTmp -Detail $tfDetail) { $pass++ } else { $fail++ }

    # --- [정적-3] backup.ps1 SkipUpload 시 rclone 가드 스킵 (버그 #3) ---
    $hasSkipUploadGuard = $backupSrc -match '-not\s+\$SkipUpload\s+-and\s+-not\s+\(Test-Path\s+\$RCLONE_EXE\)'
    if (Test-Result -Name "backup.ps1: -SkipUpload 시 rclone 가드 스킵" -Passed $hasSkipUploadGuard) { $pass++ } else { $fail++ }

    # --- [정적-4] backup.ps1 에러 힌트 라인들 (버그 #4) ---
    $hintAppIni = $backupSrc  -match '힌트:.*setup-wizard'
    $hintDb     = $backupSrc  -match '힌트:.*DB.*초기화|DB가 초기화'
    $hintRepos  = $backupSrc  -match '힌트:.*create-folders'
    $hintRclone = $backupSrc  -match '힌트:.*(download-rclone|SkipUpload)'
    $hintUpload = $backupSrc  -match '힌트:.*(listremotes|rclone config)'
    $hintRestoreFile = $restoreSrc -match '힌트:.*(gdrive|로컬 경로)'
    $hintsOk = $hintAppIni -and $hintDb -and $hintRepos -and $hintRclone -and $hintUpload -and $hintRestoreFile
    $hintDetail = ("appini={0} db={1} repos={2} rclone={3} upload={4} restoreFile={5}" -f `
        $hintAppIni, $hintDb, $hintRepos, $hintRclone, $hintUpload, $hintRestoreFile)
    if (Test-Result -Name "backup/restore.ps1: Write-Info 힌트 6종 추가" -Passed $hintsOk -Detail $hintDetail) { $pass++ } else { $fail++ }

    # --- [정적-5] backup.ps1 Compress-Archive 2GB 사전 경고 (버그 #5) ---
    $has2GB   = $backupSrc -match '2GB|\$twoGB\s*=\s*2GB'
    $hasRaw   = $backupSrc -match 'rawTotal'
    $hasCAref = $backupSrc -match 'Compress-Archive'
    if (Test-Result -Name "backup.ps1: 2GB/Compress-Archive 사전 경고 로직" -Passed ($has2GB -and $hasRaw -and $hasCAref)) { $pass++ } else { $fail++ }

    # --- [정적-6] 구조 건전성: try/catch/finally가 짝 맞음 ---
    $backupTry     = ([regex]::Matches($backupSrc,  '\btry\s*\{')).Count
    $backupFinally = ([regex]::Matches($backupSrc,  '\bfinally\s*\{')).Count
    $restoreTry    = ([regex]::Matches($restoreSrc, '\btry\s*\{')).Count
    $restoreFinally= ([regex]::Matches($restoreSrc, '\bfinally\s*\{')).Count
    if (Test-Result -Name "backup.ps1 try>=finally" -Passed ($backupTry -ge $backupFinally -and $backupTry -gt 0)   -Detail "try=$backupTry finally=$backupFinally")   { $pass++ } else { $fail++ }
    if (Test-Result -Name "restore.ps1 try>=finally" -Passed ($restoreTry -ge $restoreFinally -and $restoreTry -gt 0) -Detail "try=$restoreTry finally=$restoreFinally") { $pass++ } else { $fail++ }

    # --- [실측] Gitea 미설치/불완전 상태에서 backup.ps1 -SkipUpload 실행 ---
    #   * Gitea가 설치되어 있어 app.ini가 존재하면 이 단계는 서비스를 건드리므로 스킵.
    #   * -SkipLive로 명시적 스킵 가능.
    $giteaInstalled = Test-Path $APPINI_PATH
    if ($SkipLive) {
        Write-Info "-SkipLive 지정 — 실측 단계 생략"
    } elseif ($giteaInstalled) {
        Write-Warn "app.ini 존재($APPINI_PATH) — 실측 단계 건너뜀(사이드이펙트 방지)"
    } else {
        Write-Step "실측: Gitea 미설치 상태에서 backup.ps1 -SkipUpload"
        $pwsh = (Get-Command powershell.exe).Source
        $stdoutTmp = New-TemporaryFile
        $stderrTmp = New-TemporaryFile
        try {
            $p = Start-Process -FilePath $pwsh `
                -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$backupScript,'-SkipUpload') `
                -NoNewWindow -Wait -PassThru `
                -RedirectStandardOutput $stdoutTmp.FullName `
                -RedirectStandardError  $stderrTmp.FullName
            $liveExit = $p.ExitCode
            $liveOut  = (Get-Content $stdoutTmp.FullName -Raw) + "`n" + (Get-Content $stderrTmp.FullName -Raw)
        } finally {
            Remove-Item $stdoutTmp.FullName, $stderrTmp.FullName -Force -ErrorAction SilentlyContinue
        }

        Write-Info "실측 exit code: $liveExit"
        # 사전 체크 실패 = 빠른 exit=1
        if (Test-Result -Name "실측: backup.ps1 -SkipUpload 사전 체크 실패 시 exit=1" -Passed ($liveExit -eq 1)) { $pass++ } else { $fail++ }

        $hasAppIniMissing = $liveOut -match 'APPINI_MISSING|app\.ini 없음'
        if (Test-Result -Name "실측: 출력에 APPINI_MISSING/app.ini 없음 포함" -Passed $hasAppIniMissing) { $pass++ } else { $fail++ }

        $hasHintEmitted = $liveOut -match '힌트:.*(setup-wizard|generate-appini)'
        if (Test-Result -Name "실측: 에러 힌트 메시지 실제 출력" -Passed $hasHintEmitted) { $pass++ } else { $fail++ }
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
