# ============================================
# 전체 테스트 실행기
# ============================================
# 사용법:
#   .\run-all-tests.ps1                         ← 01~12 실행 (E2E 제외)
#   .\run-all-tests.ps1 -IncludeE2E             ← 13 (실제 백업) 포함
#   .\run-all-tests.ps1 -Filter "01,05"         ← 특정 테스트만
#   .\run-all-tests.ps1 -Base D:\gitea2         ← 모든 테스트에 -Base 전달
#   .\run-all-tests.ps1 -PublicIp 1.2.3.4 -HttpPort 8080
# ============================================
param(
    [switch]$IncludeE2E,
    [string]$Filter = "",
    [string]$Base,
    [string]$PublicIp,
    [int]$HttpPort,
    [int]$SshPort,
    [string]$ServiceName,
    [string]$TaskName,
    [string]$GdriveRemote,
    [string]$GdriveFolder,
    [switch]$SkipExternal
)

if ($Base)     { $BASE = $Base }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'tests' -Name 'run-all-tests' -Parameters $PSBoundParameters

$overallFail = 0
try {
    Write-Step "전체 테스트 실행"

    # 각 테스트에 전달할 파라미터 (관련 없는 건 무시됨)
    $forward = @{}
    foreach ($k in 'Base','PublicIp','HttpPort','SshPort','ServiceName','TaskName','GdriveRemote','GdriveFolder','SkipExternal') {
        if ($PSBoundParameters.ContainsKey($k)) { $forward[$k] = $PSBoundParameters[$k] }
    }

    $all = Get-ChildItem "$PSScriptRoot\test-*.ps1" | Sort-Object Name

    if (-not $IncludeE2E) {
        $all = $all | Where-Object { $_.Name -notmatch 'test-13-' }
        Write-Info "E2E 테스트 제외 (-IncludeE2E로 포함)"
    }

    if ($Filter) {
        $nums = $Filter.Split(',') | ForEach-Object { $_.Trim() }
        $all = $all | Where-Object {
            $f = $_.Name
            foreach ($n in $nums) { if ($f -match "test-$n-") { return $true } }
            return $false
        }
        Write-Info "필터 적용: $Filter ($(($all).Count)개 매치)"
    }

    Write-Info "실행 대상: $(($all).Count)개 테스트"
    if ($forward.Count -gt 0) {
        Write-Info "하위 전달 파라미터: $(($forward.Keys) -join ', ')"
    }

    $results = @()
    foreach ($t in $all) {
        Write-Host ""
        Write-Host ">>> $($t.Name)" -ForegroundColor Yellow
        $start = Get-Date

        # 각 테스트에 맞는 파라미터만 전달 (PowerShell이 자동으로 에러 처리하지 않도록)
        # → 단순 splatting: 관련 없는 파라미터는 해당 스크립트에서 무시되지 않음(에러됨).
        # → 따라서 각 테스트가 받을 수 있는 key만 전달.
        $testParams = @{}
        $scriptContent = Get-Content $t.FullName -Raw
        foreach ($k in $forward.Keys) {
            # 해당 스크립트의 param() 블록에 $k가 존재하는지 체크
            if ($scriptContent -match "\[\w+(\[\])?\]\s*\`$$k\b") {
                $testParams[$k] = $forward[$k]
            }
        }

        & $t.FullName @testParams
        $ec = $LASTEXITCODE
        $dur = [int]((Get-Date) - $start).TotalMilliseconds
        $results += [PSCustomObject]@{
            Test       = $t.Name
            Result     = if ($ec -eq 0) { "PASS" } else { "FAIL" }
            ExitCode   = $ec
            DurationMs = $dur
            Params     = ($testParams.Keys -join ',')
        }
        if ($ec -ne 0) { $overallFail++ }
    }

    Write-Host ""
    Write-Host "==================== 전체 요약 ====================" -ForegroundColor Cyan
    $results | Format-Table -AutoSize | Out-String | Write-Host
    Write-Host "====================================================" -ForegroundColor Cyan

    $passCount = ($results | Where-Object { $_.ExitCode -eq 0 }).Count
    $failCount = ($results | Where-Object { $_.ExitCode -ne 0 }).Count
    Write-TestSummary -Pass $passCount -Fail $failCount

    # 집계 로그 파일 생성 (JSON)
    $summaryDir = "$BASE\logs\tests"
    $summaryFile = "$summaryDir\run-all-summary_$(Get-Date -Format 'yyyy-MM-dd_HHmmss').json"
    $results | ConvertTo-Json | Set-Content -Path $summaryFile -Encoding UTF8
    Write-Info "요약 JSON: $summaryFile"
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $overallFail++
} finally {
    if ($overallFail -ge 1) {
        Write-Host "종료 시 실패 카운트: $overallFail" -ForegroundColor Red
    }
    Stop-ScriptLog -ExitCode $overallFail
}
exit $overallFail
