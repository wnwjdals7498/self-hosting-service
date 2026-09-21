# ============================================
# Gitea 전체 환경 복구 스크립트
# ============================================
# 사전 조건: Git for Windows 설치됨
# 사용법:
#   .\restore.ps1 -BackupFile "C:\path\to\gitea-backup.zip"
#   .\restore.ps1 -BackupFile "gdrive"    ← Google Drive에서 다운로드
# ============================================
param(
    [Parameter(Mandatory=$true)][string]$BackupFile,
    [switch]$SkipDownload,
    [switch]$SkipFirewall
)

. "$PSScriptRoot\config.ps1"
. "$PSScriptRoot\common.ps1"

Start-ScriptLog -Category 'restore' -Name 'restore' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Assert-Admin
    Write-Step "Gitea 복구 시작"
    Write-Info "BackupFile    : $BackupFile"
    Write-Info "Gitea 버전    : $GITEA_VERSION"
    Write-Info "NSSM 버전     : $NSSM_VERSION"
    Write-Info "Base          : $BASE"

    # --- 1. 폴더 구조 ---
    Write-Step "[1/8] 폴더 구조 생성"
    & "$PSScriptRoot\setup\01-create-folders.ps1"
    if ($LASTEXITCODE -ne 0) { throw "폴더 생성 실패" }

    if (-not $SkipDownload) {
        # --- 2. Gitea 다운로드 ---
        Write-Step "[2/8] Gitea 다운로드"
        & "$PSScriptRoot\setup\02-download-gitea.ps1"
        if ($LASTEXITCODE -ne 0) { throw "Gitea 다운로드 실패" }

        # --- 3. NSSM 다운로드 ---
        Write-Step "[3/8] NSSM 다운로드"
        & "$PSScriptRoot\setup\03-download-nssm.ps1"
        if ($LASTEXITCODE -ne 0) { throw "NSSM 다운로드 실패" }

        # --- 4. rclone 다운로드 ---
        Write-Step "[4/8] rclone 다운로드"
        & "$PSScriptRoot\setup\04-download-rclone.ps1"
        if ($LASTEXITCODE -ne 0) { throw "rclone 다운로드 실패" }
    } else {
        Write-Info "[2-4/8] 바이너리 다운로드 건너뜀 (-SkipDownload)"
    }

    # --- 5. 백업 데이터 복원 ---
    Write-Step "[5/8] 백업 데이터 복원"
    if ($BackupFile -eq "gdrive") {
        Write-Info "Google Drive에서 다운로드..."
        $remotePath = "${GDRIVE_REMOTE}:${GDRIVE_FOLDER}/$BACKUP_FILENAME"
        Write-Info "원격: $remotePath"
        & $RCLONE_EXE copy $remotePath $BACKUP_DIR --progress
        if ($LASTEXITCODE -ne 0) { throw "rclone 다운로드 실패" }
        $BackupFile = "$BACKUP_DIR\$BACKUP_FILENAME"
    }

    if (-not (Test-Path $BackupFile)) {
        Write-Fail "백업 파일 없음: $BackupFile"
        Write-Info "힌트: 로컬 경로를 전달했는지, 또는 'gdrive'를 지정했는지 확인하세요."
        throw "BACKUP_FILE_MISSING"
    }
    Write-Info "백업 파일: $BackupFile ($([math]::Round((Get-Item $BackupFile).Length / 1MB, 2)) MB)"

    # --- 기존 데이터 안전장치: data/repos 덮어쓰기 전 사이드 백업 ---
    $safetyStamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $safetyRoot  = "$BASE\restore-safety-$safetyStamp"
    $existingDb  = "$DATA_DIR\gitea.db"
    $reposHasItems = (Test-Path $REPOS_DIR) -and ((Get-ChildItem $REPOS_DIR -Force -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)
    $iniExists = Test-Path $APPINI_PATH
    $dbExists  = Test-Path $existingDb
    if ($iniExists -or $dbExists -or $reposHasItems) {
        New-Item -ItemType Directory -Path $safetyRoot -Force | Out-Null
        if ($iniExists) {
            Copy-Item $APPINI_PATH "$safetyRoot\app.ini" -Force
            Write-Info "기존 app.ini 사이드 백업: $safetyRoot\app.ini"
        }
        if ($dbExists) {
            Copy-Item $existingDb "$safetyRoot\gitea.db" -Force
            Write-Info "기존 gitea.db 사이드 백업: $safetyRoot\gitea.db"
        }
        if ($reposHasItems) {
            Copy-Item "$REPOS_DIR" "$safetyRoot\repos" -Recurse -Force
            Write-Info "기존 repos 사이드 백업: $safetyRoot\repos"
        }
        Write-Warn "복원 실패 시 위 경로에서 수동 복구 가능. 성공 시에는 자동 삭제되지 않으므로 필요 없으면 직접 제거."
    }

    $tmp = "$BASE\restore-temp"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    try {
        Expand-Archive -Path $BackupFile -DestinationPath $tmp -Force
        Write-Ok "압축 해제: $tmp"

        # app.ini 복원
        $iniSrc = Get-ChildItem $tmp -Recurse -Filter "app.ini" | Select-Object -First 1
        if ($iniSrc) {
            Copy-Item $iniSrc.FullName $APPINI_PATH -Force
            Write-Ok "app.ini 복원: $APPINI_PATH"
        } else { Write-Warn "app.ini를 백업에서 찾을 수 없음" }

        # gitea.db 복원
        $dbSrc = Get-ChildItem $tmp -Recurse -Filter "gitea.db" | Select-Object -First 1
        if ($dbSrc) {
            Copy-Item $dbSrc.FullName "$DATA_DIR\gitea.db" -Force
            Write-Ok "gitea.db 복원 ($([math]::Round((Get-Item "$DATA_DIR\gitea.db").Length / 1KB, 1)) KB)"
        } else { Write-Warn "gitea.db를 백업에서 찾을 수 없음" }

        # repos 복원
        $repoSrc = Get-ChildItem $tmp -Recurse -Directory -Filter "repos" | Select-Object -First 1
        if ($repoSrc) {
            Copy-Item "$($repoSrc.FullName)\*" $REPOS_DIR -Recurse -Force
            $cnt = (Get-ChildItem $REPOS_DIR -Directory).Count
            Write-Ok "repos 복원 (최상위 엔트리 $cnt 개)"
        } else { Write-Warn "repos를 백업에서 찾을 수 없음" }
    } finally {
        if (Test-Path $tmp) {
            try { Remove-Item $tmp -Recurse -Force -ErrorAction Stop } catch { Write-Warn "restore-temp 정리 실패: $tmp ($($_.Exception.Message))" }
        }
    }

    # --- 6. 서비스 등록 ---
    Write-Step "[6/8] 서비스 등록"
    & "$PSScriptRoot\setup\08-register-service.ps1"
    if ($LASTEXITCODE -ne 0) { throw "서비스 등록 실패" }

    # --- 7. 방화벽 ---
    if (-not $SkipFirewall) {
        Write-Step "[7/8] 방화벽 규칙"
        & "$PSScriptRoot\setup\05-firewall-rules.ps1"
        if ($LASTEXITCODE -ne 0) { throw "방화벽 설정 실패" }
    } else {
        Write-Info "[7/8] 방화벽 건너뜀 (-SkipFirewall)"
    }

    # --- 8. 복구 정책 ---
    Write-Step "[8/8] 서비스 복구 정책"
    & "$PSScriptRoot\setup\09-configure-recovery.ps1"
    if ($LASTEXITCODE -ne 0) { throw "복구 정책 설정 실패" }

    Write-Ok "복구 완료! → http://localhost:$HTTP_PORT"
    Write-Warn "rclone 재설정이 필요하면: $RCLONE_EXE config"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
