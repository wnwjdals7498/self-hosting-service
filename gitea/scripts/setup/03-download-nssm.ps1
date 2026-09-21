# ============================================
# [03] NSSM 바이너리 다운로드
# ============================================
# 옵션:
#   -Base <path>     : 기본 디렉토리
#   -Version <ver>   : NSSM 버전 (기본값 config.ps1)
#   -Url <url>       : 다운로드 URL 직접 지정
#   -Force           : 이미 있어도 재다운로드
# ============================================
param(
    [string]$Base,
    [string]$Version,
    [string]$Url,
    [switch]$Force
)

if ($Base)    { $BASE = $Base }
if ($Version) { $NSSM_VERSION = $Version }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '03-download-nssm' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Write-Step "NSSM $NSSM_VERSION 다운로드"

    if (-not (Test-Path $BIN_DIR)) {
        Write-Fail "$BIN_DIR 가 없습니다. 01-create-folders.ps1 먼저 실행."
        throw "BIN_DIR_MISSING"
    }

    if ((Test-Path $NSSM_EXE) -and -not $Force) {
        Write-Info "이미 존재: $NSSM_EXE"
        Write-Ok "건너뜀 (-Force 로 재다운로드)"
        return
    }

    $downloadUrl = if ($Url) { $Url } else { "https://nssm.cc/release/nssm-$NSSM_VERSION.zip" }
    $zip = "$BIN_DIR\nssm.zip"
    $tmp = "$BIN_DIR\nssm-temp"

    Write-Info "URL  : $downloadUrl"
    Write-Info "대상 : $NSSM_EXE"

    Invoke-WebRequest -Uri $downloadUrl -OutFile $zip
    Write-Ok "ZIP 다운로드: $zip ($([math]::Round((Get-Item $zip).Length / 1KB, 1)) KB)"

    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    Write-Info "압축 해제: $tmp"

    $src = Get-ChildItem $tmp -Recurse -Filter "nssm.exe" | Where-Object { $_.FullName -match 'win64' } | Select-Object -First 1
    if (-not $src) {
        # fallback: any nssm.exe
        $src = Get-ChildItem $tmp -Recurse -Filter "nssm.exe" | Select-Object -First 1
    }
    if (-not $src) {
        Write-Fail "압축 파일에서 nssm.exe를 찾을 수 없음"
        throw "NSSM_EXE_NOT_FOUND_IN_ZIP"
    }
    Write-Info "찾음: $($src.FullName)"
    Copy-Item $src.FullName $NSSM_EXE -Force
    Write-Ok "복사 완료: $NSSM_EXE"

    Remove-Item $tmp -Recurse -Force
    Remove-Item $zip -Force
    Write-Info "임시 파일 정리 완료"

    Write-Ok "NSSM 준비 완료 ($([math]::Round((Get-Item $NSSM_EXE).Length / 1KB, 1)) KB)"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
