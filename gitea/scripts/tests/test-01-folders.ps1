# ============================================
# Test 01: 폴더 구조
# ============================================
# 옵션:
#   -Base <path>  : 기본 디렉토리
# ============================================
param(
    [string]$Base
)

if ($Base) { $BASE = $Base }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-01-folders' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 01: 폴더 구조 검증 (base=$BASE)"

    $dirs = @(
        @{ Path = $BIN_DIR;             Name = "bin" },
        @{ Path = $CONF_DIR;            Name = "custom\conf" },
        @{ Path = $DATA_DIR;            Name = "data" },
        @{ Path = $REPOS_DIR;           Name = "repos" },
        @{ Path = $BACKUP_DIR;          Name = "backups" },
        @{ Path = $SCRIPT_DIR;          Name = "scripts" },
        @{ Path = $LOG_DIR;             Name = "logs\gitea" },
        @{ Path = "$BASE\logs\setup";   Name = "logs\setup" },
        @{ Path = "$BASE\logs\tests";   Name = "logs\tests" },
        @{ Path = "$BASE\logs\backup";  Name = "logs\backup" },
        @{ Path = "$BASE\logs\restore"; Name = "logs\restore" }
    )

    foreach ($d in $dirs) {
        $ok = Test-Path $d.Path
        if (Test-Result -Name "$($d.Name) 폴더 존재" -Passed $ok -Detail $d.Path) { $pass++ } else { $fail++ }
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
