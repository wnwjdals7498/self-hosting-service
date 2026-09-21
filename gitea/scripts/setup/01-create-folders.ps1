# ============================================
# [01] 폴더 구조 생성
# ============================================
# 옵션:
#   -Base <path>   : 기본 디렉토리 (기본값 config.ps1 참조)
# ============================================
param(
    [string]$Base
)

if ($Base) { $BASE = $Base }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '01-create-folders' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Write-Step "폴더 구조 생성 (base: $BASE)"

    $dirs = @(
        @{ Path = $BIN_DIR;             Desc = "바이너리 (gitea/nssm/rclone)" },
        @{ Path = $CONF_DIR;            Desc = "app.ini 위치" },
        @{ Path = $DATA_DIR;            Desc = "SQLite DB" },
        @{ Path = $REPOS_DIR;           Desc = "Git 리포지토리" },
        @{ Path = $BACKUP_DIR;          Desc = "백업 임시 파일" },
        @{ Path = $SCRIPT_DIR;          Desc = "스크립트" },
        @{ Path = $LOG_DIR;             Desc = "Gitea 런타임 로그 (logs/gitea)" },
        @{ Path = "$BASE\logs\setup";   Desc = "setup 실행 로그" },
        @{ Path = "$BASE\logs\tests";   Desc = "테스트 실행 로그" },
        @{ Path = "$BASE\logs\backup";  Desc = "백업 실행 로그" },
        @{ Path = "$BASE\logs\restore"; Desc = "복구 실행 로그" }
    )

    foreach ($d in $dirs) {
        if (Test-Path $d.Path) {
            Write-Info "존재함: $($d.Path) ($($d.Desc))"
        } else {
            New-Item -ItemType Directory -Path $d.Path -Force | Out-Null
            Write-Ok "생성: $($d.Path) ($($d.Desc))"
        }
    }

    Write-Ok "폴더 구조 완료"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
