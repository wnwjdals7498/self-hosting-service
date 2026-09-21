# ============================================
# [04] rclone 바이너리 다운로드
# ============================================
# 옵션:
#   -Base <path>  : 기본 디렉토리
#   -Url <url>    : 다운로드 URL 직접 지정
#   -Force        : 이미 있어도 재다운로드
# ============================================
param(
    [string]$Base,
    [string]$Url,
    [switch]$Force
)

if ($Base) { $BASE = $Base }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '04-download-rclone' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Write-Step "rclone 다운로드"

    if (-not (Test-Path $BIN_DIR)) {
        Write-Fail "$BIN_DIR 가 없습니다. 01-create-folders.ps1 먼저 실행."
        throw "BIN_DIR_MISSING"
    }

    if ((Test-Path $RCLONE_EXE) -and -not $Force) {
        $ver = & $RCLONE_EXE version 2>&1 | Select-Object -First 1
        Write-Info "이미 존재: $RCLONE_EXE"
        Write-Info "버전: $ver"
        Write-Ok "건너뜀 (-Force 로 재다운로드)"
        return
    }

    $downloadUrl = if ($Url) { $Url } else { "https://downloads.rclone.org/rclone-current-windows-amd64.zip" }
    $zip = "$BIN_DIR\rclone.zip"
    $tmp = "$BIN_DIR\rclone-temp"

    Write-Info "URL  : $downloadUrl"
    Write-Info "대상 : $RCLONE_EXE"

    Invoke-WebRequest -Uri $downloadUrl -OutFile $zip
    Write-Ok "ZIP 다운로드 ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"

    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $src = Get-ChildItem $tmp -Recurse -Filter "rclone.exe" | Select-Object -First 1
    if (-not $src) {
        Write-Fail "압축 파일에서 rclone.exe를 찾을 수 없음"
        throw "RCLONE_EXE_NOT_FOUND_IN_ZIP"
    }
    Write-Info "찾음: $($src.FullName)"
    Copy-Item $src.FullName $RCLONE_EXE -Force
    Write-Ok "복사 완료"

    Remove-Item $tmp -Recurse -Force
    Remove-Item $zip -Force
    Write-Info "임시 파일 정리 완료"

    $ver = & $RCLONE_EXE version 2>&1 | Select-Object -First 1
    Write-Ok "rclone 준비 완료: $ver"
    Write-Warn "Google Drive 연결은 수동 설정 필요:  $RCLONE_EXE config"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
