# ============================================
# Test 06: app.ini 설정
# ============================================
# 옵션:
#   -Base <path>
#   -PublicIp <str>
#   -HttpPort <int>
#   -SshPort <int>
#   -LogLevel <str>
# ============================================
param(
    [string]$Base,
    [string]$PublicIp,
    [int]$HttpPort,
    [int]$SshPort,
    [string]$LogLevel
)

if ($Base)     { $BASE      = $Base }
if ($PublicIp) { $PUBLIC_IP = $PublicIp }
if ($HttpPort) { $HTTP_PORT = $HttpPort }
if ($SshPort)  { $SSH_PORT  = $SshPort }
if ($LogLevel) { $LOG_LEVEL = $LogLevel }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-06-appini' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 06: app.ini 검증"

    $exists = Test-Path $APPINI_PATH
    if (Test-Result -Name "app.ini 존재" -Passed $exists -Detail $APPINI_PATH) { $pass++ } else { throw "APPINI_MISSING" }

    $content = Get-Content $APPINI_PATH -Raw
    $size = (Get-Item $APPINI_PATH).Length
    Write-Info "파일 크기: $([math]::Round($size / 1KB, 2)) KB / 라인 수: $((Get-Content $APPINI_PATH).Count)"

    $checks = @(
        @{ Name = "HTTP_PORT = $HTTP_PORT";             Pattern = "HTTP_PORT\s*=\s*$HTTP_PORT" },
        @{ Name = "SSH_PORT = $SSH_PORT";               Pattern = "SSH_PORT\s*=\s*$SSH_PORT" },
        @{ Name = "DOMAIN = $PUBLIC_IP";                Pattern = "DOMAIN\s*=\s*$([regex]::Escape($PUBLIC_IP))" },
        @{ Name = "OFFLINE_MODE = true";                Pattern = "OFFLINE_MODE\s*=\s*true" },
        @{ Name = "INSTALL_LOCK = true";                Pattern = "INSTALL_LOCK\s*=\s*true" },
        @{ Name = "SECRET_KEY 설정됨";                  Pattern = "SECRET_KEY\s*=\s*\S+" },
        @{ Name = "INTERNAL_TOKEN 설정됨";              Pattern = "INTERNAL_TOKEN\s*=\s*\S+" },
        @{ Name = "DISABLE_REGISTRATION = true";        Pattern = "DISABLE_REGISTRATION\s*=\s*true" },
        @{ Name = "REQUIRE_SIGNIN_VIEW = true";         Pattern = "REQUIRE_SIGNIN_VIEW\s*=\s*true" },
        @{ Name = "[packages] ENABLED = false";         Pattern = "\[packages\][\s\S]*?ENABLED\s*=\s*false" },
        @{ Name = "[actions] ENABLED = false";          Pattern = "\[actions\][\s\S]*?ENABLED\s*=\s*false" },
        @{ Name = "[mirror] ENABLED = false";           Pattern = "\[mirror\][\s\S]*?ENABLED\s*=\s*false" },
        @{ Name = "[federation] ENABLED = false";       Pattern = "\[federation\][\s\S]*?ENABLED\s*=\s*false" },
        @{ Name = "[mailer] ENABLED = false";           Pattern = "\[mailer\][\s\S]*?ENABLED\s*=\s*false" },
        @{ Name = "DB_TYPE = sqlite3";                  Pattern = "DB_TYPE\s*=\s*sqlite3" },
        @{ Name = "LFS_START_SERVER = false";           Pattern = "LFS_START_SERVER\s*=\s*false" },
        @{ Name = "DEFAULT_BRANCH = main";              Pattern = "DEFAULT_BRANCH\s*=\s*main" },
        @{ Name = "LOG LEVEL = $LOG_LEVEL";             Pattern = "LEVEL\s*=\s*$LOG_LEVEL" }
    )

    foreach ($c in $checks) {
        $match = $content -match $c.Pattern
        if (Test-Result -Name $c.Name -Passed $match) { $pass++ } else { $fail++ }
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
