# ============================================
# Gitea 백업 스크립트
#   - 서비스 중지 → app.ini + gitea.db + repos 압축 → 서비스 재시작
#   - rclone으로 Google Drive 업로드 → 로컬 파일 삭제
# ============================================
# 옵션:
#   -Base <path>         : 기본 디렉토리
#   -ServiceName <str>   : 서비스 이름
#   -GdriveRemote <str>  : rclone 원격 이름 (기본 "gdrive")
#   -GdriveFolder <str>  : 원격 폴더 이름 (기본 "Gitea-Backup")
#   -SkipUpload          : rclone 업로드 생략 (로컬 파일 유지)
# ============================================
param(
    [string]$Base,
    [string]$ServiceName,
    [string]$GdriveRemote,
    [string]$GdriveFolder,
    [switch]$SkipUpload
)

if ($Base)         { $BASE           = $Base }
if ($ServiceName)  { $SERVICE_NAME   = $ServiceName }
if ($GdriveRemote) { $GDRIVE_REMOTE  = $GdriveRemote }
if ($GdriveFolder) { $GDRIVE_FOLDER  = $GdriveFolder }

. "$PSScriptRoot\config.ps1"
. "$PSScriptRoot\common.ps1"

Start-ScriptLog -Category 'backup' -Name 'backup' -Parameters $PSBoundParameters

$exitCode = 0
$started = Get-Date

$BACKUP_FILE = "$BACKUP_DIR\$BACKUP_FILENAME"
$GDRIVE_PATH = "${GDRIVE_REMOTE}:${GDRIVE_FOLDER}"

try {
    Write-Step "백업 시작 — $($started.ToString('yyyy-MM-dd HH:mm:ss'))"

    # --- 사전 체크 ---
    $db = "$DATA_DIR\gitea.db"
    if (-not (Test-Path $APPINI_PATH)) {
        Write-Fail "app.ini 없음: $APPINI_PATH"
        Write-Info "힌트: setup/06 setup-wizard 및 setup/07 generate-appini를 먼저 실행하세요."
        throw "APPINI_MISSING"
    }
    if (-not (Test-Path $db)) {
        Write-Fail "gitea.db 없음: $db"
        Write-Info "힌트: Gitea 서비스가 최소 1회 기동되어 DB가 초기화되었는지 확인하세요."
        throw "DB_MISSING"
    }
    if (-not (Test-Path $REPOS_DIR)) {
        Write-Fail "repos 없음: $REPOS_DIR"
        Write-Info "힌트: setup/01-create-folders를 먼저 실행하세요."
        throw "REPOS_DIR_MISSING"
    }
    if (-not $SkipUpload -and -not (Test-Path $RCLONE_EXE)) {
        Write-Fail "rclone.exe 없음: $RCLONE_EXE"
        Write-Info "힌트: setup/04-download-rclone 실행 또는 -SkipUpload로 로컬 압축만 수행."
        throw "RCLONE_EXE_MISSING"
    }

    # --- 압축 대상 크기 사전 점검 (Compress-Archive의 PS 5.1 2GB 제한 대비) ---
    $repoBytes = (Get-ChildItem $REPOS_DIR -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    if (-not $repoBytes) { $repoBytes = 0 }
    $dbBytes = (Get-Item $db).Length
    $rawTotal = $repoBytes + $dbBytes
    $twoGB = 2GB
    if ($rawTotal -ge $twoGB) {
        Write-Warn ("원시 대상 크기 {0:N2} GB — PowerShell 5.1 Compress-Archive의 2GB 제한을 초과할 수 있습니다." -f ($rawTotal / 1GB))
        Write-Warn "압축이 실패하면 수동으로 7-Zip 또는 .NET ZipFile(큰 파일 지원)을 사용하는 대체 경로를 고려하세요."
    }

    # --- 이전 로컬 백업 정리 ---
    if (Test-Path $BACKUP_FILE) {
        Write-Info "이전 백업 삭제: $BACKUP_FILE"
        Remove-Item $BACKUP_FILE -Force
    }

    # --- 서비스 일시 중지 (SQLite 잠금 방지) ---
    $wasRunning = $false
    $svc = Get-Service $SERVICE_NAME -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq 'Running') {
        $wasRunning = $true
        Write-Info "서비스 중지 중: $SERVICE_NAME"
        Stop-Service $SERVICE_NAME -Force
        Start-Sleep -Seconds 3
        Write-Ok "서비스 중지됨"
    } else {
        Write-Warn "서비스가 실행 중이 아님 (상태: $(if ($svc) { $svc.Status } else { '등록 안 됨' }))"
    }

    try {
        # --- 압축 ---
        Write-Step "압축 생성: $BACKUP_FILE"
        Write-Info "포함:"
        Write-Info "  - $APPINI_PATH"
        Write-Info "  - $db ($([math]::Round((Get-Item $db).Length / 1KB, 1)) KB)"
        $repoSize = (Get-ChildItem $REPOS_DIR -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        Write-Info "  - $REPOS_DIR ($([math]::Round($repoSize / 1MB, 2)) MB)"

        Compress-Archive -Path @($APPINI_PATH, $db, $REPOS_DIR) -DestinationPath $BACKUP_FILE -Force
        $backupSize = (Get-Item $BACKUP_FILE).Length
        Write-Ok "압축 완료 ($([math]::Round($backupSize / 1MB, 2)) MB)"
    } finally {
        if ($wasRunning) {
            Write-Info "서비스 재시작 중: $SERVICE_NAME"
            Start-Service $SERVICE_NAME
            Write-Ok "서비스 재시작됨"
        }
    }

    if ($SkipUpload) {
        Write-Warn "-SkipUpload 지정 — rclone 업로드 생략. 로컬 파일 유지: $BACKUP_FILE"
    } else {
        # --- rclone 업로드 ---
        Write-Step "Google Drive 업로드: $GDRIVE_PATH"
        & $RCLONE_EXE copy $BACKUP_FILE $GDRIVE_PATH --progress
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "rclone 업로드 실패 (exit=$LASTEXITCODE). 로컬 파일 유지: $BACKUP_FILE"
            Write-Info "힌트: '$RCLONE_EXE listremotes'로 '${GDRIVE_REMOTE}:' 설정 확인. 필요 시 '$RCLONE_EXE config'."
            throw "RCLONE_UPLOAD_FAILED"
        }
        Write-Ok "업로드 완료"

        # --- 로컬 파일 삭제 ---
        Remove-Item $BACKUP_FILE -Force
        Write-Info "로컬 백업 파일 삭제됨"

        # --- 원격 확인 ---
        Write-Step "원격 백업 확인"
        $listing = & $RCLONE_EXE ls $GDRIVE_PATH 2>&1
        Write-Info ($listing | Out-String).Trim()
    }

    $done = Get-Date
    $dur = [int]($done - $started).TotalSeconds
    Write-Ok "백업 완료 → $GDRIVE_PATH (${dur}초)"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
