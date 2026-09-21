# ============================================
# Test 05: 방화벽 규칙
# ============================================
# 옵션:
#   -HttpPort <int>
#   -SshPort <int>
#   -HttpRuleName <str>
#   -SshRuleName <str>
# ============================================
param(
    [int]$HttpPort,
    [int]$SshPort,
    [string]$HttpRuleName = "Gitea HTTP",
    [string]$SshRuleName  = "Gitea SSH"
)

if ($HttpPort) { $HTTP_PORT = $HttpPort }
if ($SshPort)  { $SSH_PORT  = $SshPort }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-05-firewall' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 05: 방화벽 규칙 검증 (HTTP=$HTTP_PORT, SSH=$SSH_PORT)"

    $rules = @(
        @{ Name = $HttpRuleName; Port = $HTTP_PORT },
        @{ Name = $SshRuleName;  Port = $SSH_PORT }
    )

    foreach ($r in $rules) {
        $rule = Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
        $exists = $null -ne $rule
        if (Test-Result -Name "규칙 존재: $($r.Name)" -Passed $exists) { $pass++ } else { $fail++; continue }

        $enabled = "$($rule.Enabled)" -eq 'True'
        if (Test-Result -Name "규칙 활성화: $($r.Name)" -Passed $enabled -Detail "Enabled=$($rule.Enabled)") { $pass++ } else { $fail++ }

        $dir = "$($rule.Direction)" -eq 'Inbound'
        if (Test-Result -Name "Inbound: $($r.Name)" -Passed $dir -Detail "Direction=$($rule.Direction)") { $pass++ } else { $fail++ }

        $action = "$($rule.Action)" -eq 'Allow'
        if (Test-Result -Name "Allow: $($r.Name)" -Passed $action -Detail "Action=$($rule.Action)") { $pass++ } else { $fail++ }

        $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
        $portOk = "$($portFilter.LocalPort)" -eq "$($r.Port)"
        if (Test-Result -Name "포트 일치: $($r.Name) = $($r.Port)" -Passed $portOk -Detail "LocalPort=$($portFilter.LocalPort)") { $pass++ } else { $fail++ }

        $protoOk = "$($portFilter.Protocol)" -eq 'TCP'
        if (Test-Result -Name "TCP 프로토콜: $($r.Name)" -Passed $protoOk -Detail "Protocol=$($portFilter.Protocol)") { $pass++ } else { $fail++ }
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
