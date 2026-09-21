# ============================================
# [05] 방화벽 규칙 설정
# ============================================
# 옵션:
#   -HttpPort <int>     : HTTP 포트
#   -SshPort <int>      : SSH 포트
#   -HttpRuleName <str> : 방화벽 규칙 이름 (기본 "Gitea HTTP")
#   -SshRuleName <str>  : 방화벽 규칙 이름 (기본 "Gitea SSH")
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

Start-ScriptLog -Category 'setup' -Name '05-firewall-rules' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Assert-Admin
    Write-Step "방화벽 규칙 설정 (Inbound TCP)"

    $rules = @(
        @{ Name = $HttpRuleName; Port = $HTTP_PORT; Desc = "웹 접근 + Git HTTP" },
        @{ Name = $SshRuleName;  Port = $SSH_PORT;  Desc = "Git SSH" }
    )

    foreach ($r in $rules) {
        Write-Info "처리 중: $($r.Name) — 포트 $($r.Port) ($($r.Desc))"
        $existing = Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
        if ($existing) {
            $port = (Get-NetFirewallPortFilter -AssociatedNetFirewallRule $existing).LocalPort
            Write-Info "  기존 규칙 포트: $port"
            if ("$port" -ne "$($r.Port)") {
                Write-Warn "  포트가 다름 — 삭제 후 재생성"
                Remove-NetFirewallRule -DisplayName $r.Name
                $existing = $null
            } else {
                Write-Ok "  이미 존재 — 건너뜀"
                continue
            }
        }
        New-NetFirewallRule -DisplayName $r.Name `
            -Direction Inbound -Protocol TCP `
            -LocalPort $r.Port -Action Allow | Out-Null
        Write-Ok "  생성 완료: $($r.Name) (포트 $($r.Port))"
    }

    Write-Ok "방화벽 규칙 설정 완료"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
