# ============================================
# [02] Gitea 바이너리 다운로드
# ============================================
# 옵션:
#   -Base <path>     : 기본 디렉토리
#   -Version <ver>   : Gitea 버전 (기본값 config.ps1)
#   -Url <url>       : 다운로드 URL 직접 지정 (버전 무시)
#   -Force           : 이미 있어도 재다운로드
# ============================================
param(
    [string]$Base,
    [string]$Version,
    [string]$Url,
    [switch]$Force
)

if ($Base)    { $BASE = $Base }
if ($Version) { $GITEA_VERSION = $Version }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '02-download-gitea' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Write-Step "Gitea $GITEA_VERSION 다운로드"

    if (-not (Test-Path $BIN_DIR)) {
        Write-Fail "$BIN_DIR 가 없습니다. 01-create-folders.ps1 먼저 실행."
        throw "BIN_DIR_MISSING"
    }

    if ((Test-Path $GITEA_EXE) -and -not $Force) {
        $currentVer = & $GITEA_EXE --version 2>&1 | Out-String
        Write-Info "이미 존재: $GITEA_EXE"
        Write-Info "현재 버전 출력: $($currentVer.Trim())"
        if ($currentVer -match [regex]::Escape($GITEA_VERSION)) {
            Write-Ok "요청 버전 이미 설치됨 — 건너뜀 (-Force 로 재다운로드)"
            return
        }
        Write-Warn "버전 불일치 — 재다운로드합니다."
    } elseif ($Force -and (Test-Path $GITEA_EXE)) {
        Write-Warn "-Force 지정됨 — 기존 파일 덮어쓰기"
    }

    $downloadUrl = if ($Url) { $Url } else {
        "https://dl.gitea.com/gitea/$GITEA_VERSION/gitea-$GITEA_VERSION-gogit-windows-4.0-amd64.exe"
    }
    Write-Info "URL  : $downloadUrl"
    Write-Info "대상 : $GITEA_EXE"

    $ProgressPreference = 'Continue'
    Invoke-WebRequest -Uri $downloadUrl -OutFile $GITEA_EXE
    Write-Ok "다운로드 완료"

    $size = (Get-Item $GITEA_EXE).Length
    Write-Info "파일 크기: $([math]::Round($size / 1MB, 2)) MB"

    $ver = & $GITEA_EXE --version 2>&1 | Out-String
    Write-Info "설치 버전: $($ver.Trim())"
    Write-Ok "Gitea 준비 완료"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
