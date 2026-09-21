# ============================================
# Test 09: HTTP 연결
# ============================================
# 옵션:
#   -HttpPort <int>
#   -PublicIp <str>
#   -SkipExternal         : 공인 IP 테스트 건너뛰기
# ============================================
param(
    [int]$HttpPort,
    [string]$PublicIp,
    [switch]$SkipExternal
)

if ($HttpPort) { $HTTP_PORT = $HttpPort }
if ($PublicIp) { $PUBLIC_IP = $PublicIp }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'test-09-http-connectivity' -Parameters $PSBoundParameters

$pass = 0; $fail = 0
try {
    Write-Step "Test 09: HTTP 연결 검증 (포트 $HTTP_PORT)"

    $localUrl = "http://localhost:$HTTP_PORT"
    Write-Info "로컬 테스트: $localUrl"

    try {
        $r = Invoke-WebRequest -Uri $localUrl -UseBasicParsing -TimeoutSec 10
        $code = $r.StatusCode
        Write-Info "StatusCode: $code"
        $ok = $code -in @(200, 301, 302, 303)
        if (Test-Result -Name "로컬 HTTP 응답 (2xx/3xx)" -Passed $ok -Detail "StatusCode=$code, Length=$($r.RawContentLength)") { $pass++ } else { $fail++ }

        $hasGitea = $r.Content -match '(?i)gitea'
        if (Test-Result -Name "응답에 'gitea' 문자열 포함" -Passed $hasGitea) { $pass++ } else { $fail++ }
    } catch {
        if (Test-Result -Name "로컬 HTTP 응답 (2xx/3xx)" -Passed $false -Detail $_.Exception.Message) {} else { $fail++ }
    }

    $portListen = Test-NetConnection -ComputerName localhost -Port $HTTP_PORT -InformationLevel Quiet -WarningAction SilentlyContinue
    if (Test-Result -Name "포트 $HTTP_PORT LISTEN" -Passed $portListen) { $pass++ } else { $fail++ }

    if (-not $SkipExternal -and $PUBLIC_IP -ne "CHANGE_ME") {
        $extUrl = "http://${PUBLIC_IP}:$HTTP_PORT"
        Write-Info "외부 테스트: $extUrl (타임아웃 15초)"
        try {
            $r = Invoke-WebRequest -Uri $extUrl -UseBasicParsing -TimeoutSec 15
            $ok = $r.StatusCode -in @(200, 301, 302, 303)
            if (Test-Result -Name "공인 IP HTTP 응답" -Passed $ok -Detail "StatusCode=$($r.StatusCode)") { $pass++ } else { $fail++ }
        } catch {
            if (Test-Result -Name "공인 IP HTTP 응답" -Passed $false -Detail $_.Exception.Message) {} else { $fail++ }
        }
    } else {
        Write-Warn "외부 접속 테스트 건너뜀 (PublicIp 미설정 or -SkipExternal)"
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
