# ============================================
# Test 10: SSH 포트 연결
# ============================================
# 옵션:
#   -SshPort <int>
#   -PublicIp <str>
#   -SkipExternal
# ============================================
param(
    [int]$SshPort,
    [string]$PublicIp,
    [switch]$SkipExternal
)

if ($SshPort)  { $SSH_PORT  = $SshPort }
if ($PublicIp) { $PUBLIC_IP = $PublicIp }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-10-ssh-connectivity' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 10: SSH 포트 $SSH_PORT 검증"

    Write-Info "Test-NetConnection localhost:$SSH_PORT"
    $result = Test-NetConnection -ComputerName localhost -Port $SSH_PORT -WarningAction SilentlyContinue
    Write-Info "RemoteAddress   : $($result.RemoteAddress)"
    Write-Info "TcpTestSucceeded: $($result.TcpTestSucceeded)"
    Write-Info "PingSucceeded   : $($result.PingSucceeded)"

    $ok = $result.TcpTestSucceeded
    if (Test-Result -Name "로컬 SSH 포트 오픈" -Passed $ok -Detail "localhost:$SSH_PORT") { $pass++ } else { $fail++ }

    if (-not $SkipExternal -and $PUBLIC_IP -ne "CHANGE_ME") {
        Write-Info "외부 테스트: ${PUBLIC_IP}:${SSH_PORT}"
        $result2 = Test-NetConnection -ComputerName $PUBLIC_IP -Port $SSH_PORT -WarningAction SilentlyContinue
        Write-Info "TcpTestSucceeded: $($result2.TcpTestSucceeded)"
        $ok2 = $result2.TcpTestSucceeded
        if (Test-Result -Name "공인 IP SSH 포트 오픈" -Passed $ok2 -Detail "${PUBLIC_IP}:$SSH_PORT") { $pass++ } else { $fail++ }
    } else {
        Write-Warn "외부 SSH 테스트 건너뜀 (PublicIp 미설정 or -SkipExternal)"
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
