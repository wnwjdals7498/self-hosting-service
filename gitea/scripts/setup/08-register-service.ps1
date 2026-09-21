# ============================================
# [08] NSSM으로 Gitea를 Windows 서비스로 등록
# ============================================
# 옵션:
#   -Base <path>          : 기본 디렉토리
#   -ServiceName <str>    : Windows 서비스 이름 (기본 "Gitea")
#   -DisplayName <str>    : 서비스 표시 이름
#   -RestartDelay <ms>    : 실패 시 재시작 지연 (ms)
#   -Force                : 기존 서비스 있으면 묻지 않고 재설치
# ============================================
param(
    [string]$Base,
    [string]$ServiceName,
    [string]$DisplayName = "Gitea Self-Hosted",
    [int]$RestartDelay,
    [switch]$Force
)

if ($Base)         { $BASE             = $Base }
if ($ServiceName)  { $SERVICE_NAME     = $ServiceName }
if ($RestartDelay) { $RESTART_DELAY_MS = $RestartDelay }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '08-register-service' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Assert-Admin
    Write-Step "Windows 서비스 '$SERVICE_NAME' 등록"

    if (-not (Test-Path $NSSM_EXE)) { Write-Fail "nssm.exe 없음. 03-download-nssm.ps1 먼저 실행."; throw "NSSM_EXE_MISSING" }
    if (-not (Test-Path $GITEA_EXE)) { Write-Fail "gitea.exe 없음. 02-download-gitea.ps1 먼저 실행."; throw "GITEA_EXE_MISSING" }
    if (-not (Test-Path $APPINI_PATH)) { Write-Fail "app.ini 없음. 06~07 먼저 실행."; throw "APPINI_MISSING" }

    $existing = Get-Service $SERVICE_NAME -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Warn "서비스 이미 등록됨: $SERVICE_NAME (상태: $($existing.Status))"
        if (-not $Force) {
            $answer = Read-Host "재설치하시겠습니까? (y/N)"
            if ($answer -ne 'y') { Write-Info "중단."; return }
        } else {
            Write-Info "-Force 지정 — 재설치 진행"
        }

        Write-Info "기존 서비스 중지 및 제거 중..."
        & $NSSM_EXE stop $SERVICE_NAME | Out-Null
        Start-Sleep -Seconds 2
        & $NSSM_EXE remove $SERVICE_NAME confirm | Out-Null
        Write-Ok "기존 서비스 제거됨"
    }

    Write-Info "등록 실행 파일   : $GITEA_EXE"
    Write-Info "작업 디렉토리    : $BIN_DIR"
    Write-Info "커스텀 경로      : $BASE\custom"
    Write-Info "작업 경로        : $BASE"
    Write-Info "재시작 지연 (ms) : $RESTART_DELAY_MS"

    # NSSM AppParameters는 Gitea에 그대로 커맨드라인으로 전달되므로
    # $BASE에 공백이 있어도 안전하도록 각 경로 인자를 이중따옴표로 감싼다.
    $nssmArgs = 'web --custom-path "{0}\custom" --work-path "{0}"' -f $BASE
    & $NSSM_EXE install $SERVICE_NAME $GITEA_EXE $nssmArgs
    & $NSSM_EXE set $SERVICE_NAME AppDirectory $BIN_DIR
    & $NSSM_EXE set $SERVICE_NAME AppStdout    "$LOG_DIR\gitea-stdout.log"
    & $NSSM_EXE set $SERVICE_NAME AppStderr    "$LOG_DIR\gitea-stderr.log"
    & $NSSM_EXE set $SERVICE_NAME Start        SERVICE_AUTO_START
    & $NSSM_EXE set $SERVICE_NAME AppRestartDelay $RESTART_DELAY_MS
    & $NSSM_EXE set $SERVICE_NAME DisplayName  $DisplayName
    & $NSSM_EXE set $SERVICE_NAME Description  "Gitea Git service on Windows (managed by NSSM)"

    Write-Ok "NSSM 설정 완료"

    Write-Step "서비스 시작"
    Start-Service $SERVICE_NAME
    Start-Sleep -Seconds 3

    $svc = Get-Service $SERVICE_NAME
    Write-Info "현재 상태: $($svc.Status) / StartType: $($svc.StartType)"

    if ($svc.Status -eq 'Running') {
        Write-Ok "서비스가 정상 실행 중입니다."
    } else {
        Write-Warn "서비스가 실행 중이 아닙니다. 로그 확인: $LOG_DIR\gitea-stderr.log"
    }
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
