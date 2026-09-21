# ============================================
# [06] Gitea 설정 마법사 실행 (최초 1회)
# ============================================
# 이 스크립트는 gitea.exe를 포그라운드로 실행합니다.
# 브라우저에서 http://localhost:<HTTP_PORT> 로 접속해 설정 마법사를 완료한 뒤,
# Ctrl+C로 프로세스를 종료하세요.
# ============================================
# 옵션:
#   -Base <path>      : 기본 디렉토리
#   -HttpPort <int>   : (참고용 — gitea.exe 자체는 app.ini 마법사 값 따름)
#   -Force            : app.ini가 이미 있어도 강제 실행
# ============================================
param(
    [string]$Base,
    [int]$HttpPort,
    [switch]$Force
)

if ($Base)     { $BASE      = $Base }
if ($HttpPort) { $HTTP_PORT = $HttpPort }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '06-run-setup-wizard' -Parameters $PSBoundParameters

$exitCode = 0
try {
    if (-not (Test-Path $GITEA_EXE)) {
        Write-Fail "gitea.exe가 없습니다. 02-download-gitea.ps1 먼저 실행."
        throw "GITEA_EXE_MISSING"
    }

    if ((Test-Path $APPINI_PATH) -and -not $Force) {
        Write-Warn "app.ini가 이미 존재합니다: $APPINI_PATH"
        Write-Warn "-Force 없이는 진행하지 않습니다. (기존 설정 덮어쓰지 않도록 보호)"
        $answer = Read-Host "계속하시겠습니까? (y/N)"
        if ($answer -ne 'y') { return }
    }

    Write-Step "Gitea 웹 프로세스 시작 (포그라운드)"
    Write-Info ""
    Write-Info "▶ 브라우저에서 http://localhost:$HTTP_PORT 접속"
    Write-Info "▶ 설정 마법사 완료 후 이 창에서 Ctrl+C 로 종료"
    Write-Info ""
    Write-Info "실행 명령: $GITEA_EXE web --custom-path `"$BASE\custom`" --work-path `"$BASE`""
    Write-Info ""

    Push-Location $BIN_DIR
    try {
        & $GITEA_EXE web --custom-path "$BASE\custom" --work-path "$BASE"
    } finally {
        Pop-Location
    }

    Write-Ok "설정 마법사 프로세스 종료됨"

    if (Test-Path $APPINI_PATH) {
        Write-Ok "app.ini 생성됨: $APPINI_PATH"
        Write-Info "다음: setup/07-generate-appini.ps1 로 경량화 설정 적용"
    } else {
        Write-Warn "app.ini가 생성되지 않았습니다. 마법사를 완료했는지 확인하세요."
    }
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
