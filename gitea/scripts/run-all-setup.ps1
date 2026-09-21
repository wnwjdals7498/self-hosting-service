# ============================================
# 전체 셋업 마스터 러너
# ============================================
# 순서대로 setup/01~10을 실행하는 통합 스크립트.
# 대화형 단계(06 gitea 마법사, rclone config)는 사용자가 수동으로 완료한 뒤
# 이어서 나머지를 자동 진행합니다.
#
# 사용법:
#   # 전체 자동 실행 (대화형 단계는 프롬프트로 일시정지)
#   .\run-all-setup.ps1 -PublicIp 1.2.3.4
#
#   # 구간 실행 — 이미 마법사를 완료한 경우
#   .\run-all-setup.ps1 -PublicIp 1.2.3.4 -SkipWizard -SkipRclonePrompt
#
#   # 특정 단계만 실행 (1~10 번호)
#   .\run-all-setup.ps1 -From 7 -To 10
#
#   # 강제 재설치
#   .\run-all-setup.ps1 -PublicIp 1.2.3.4 -Force
# ============================================
param(
    # --- 환경 ---
    [string]$Base,
    [string]$PublicIp,
    [int]$HttpPort,
    [int]$SshPort,

    # --- 버전 ---
    [string]$GiteaVersion,
    [string]$NssmVersion,

    # --- 서비스 / 스케줄 ---
    [string]$ServiceName,
    [string]$DisplayName = "Gitea Self-Hosted",
    [int]$RestartDelay,
    [int]$ResetPeriod,
    [string]$TaskName,
    [string]$TriggerTime,
    [string]$TaskUser = "SYSTEM",

    # --- app.ini ---
    [string]$AppName,
    [string]$LogLevel,

    # --- 방화벽 ---
    [string]$HttpRuleName = "Gitea HTTP",
    [string]$SshRuleName  = "Gitea SSH",

    # --- 진행 제어 ---
    [int]$From = 1,
    [int]$To   = 10,
    [switch]$SkipWizard,
    [switch]$SkipRclonePrompt,
    [switch]$ContinueOnError,
    [switch]$Force
)

if ($Base) { $BASE = $Base }

. "$PSScriptRoot\config.ps1"
. "$PSScriptRoot\common.ps1"

Start-ScriptLog -Category 'setup' -Name 'run-all-setup' -Parameters $PSBoundParameters

$setup = "$PSScriptRoot\setup"
$results = @()
$overallFail = 0

function Invoke-Step {
    param(
        [int]$Num,
        [string]$ScriptName,
        [hashtable]$StepArgs = @{}
    )
    if ($Num -lt $From -or $Num -gt $To) {
        Write-Info "[$Num] 건너뜀 (-From $From -To $To 범위 밖)"
        return
    }

    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Magenta
    Write-Host " [$Num/10] $ScriptName" -ForegroundColor Magenta
    if ($StepArgs.Count -gt 0) {
        $argStr = ($StepArgs.GetEnumerator() | ForEach-Object { "-$($_.Key) $($_.Value)" }) -join ' '
        Write-Host " 전달 파라미터: $argStr" -ForegroundColor DarkGray
    }
    Write-Host "================================================================" -ForegroundColor Magenta

    $started = Get-Date
    & "$setup\$ScriptName" @StepArgs
    $ec = $LASTEXITCODE
    $dur = [int]((Get-Date) - $started).TotalSeconds

    $resultText = if ($ec -eq 0) { 'PASS' } else { 'FAIL' }
    $script:results += [PSCustomObject]@{
        Step = $Num; Script = $ScriptName; ExitCode = $ec; Result = $resultText; DurationSec = $dur
    }

    if ($ec -ne 0) {
        $script:overallFail++
        Write-Fail "[$Num] 실패 (exit=$ec)"
        if (-not $ContinueOnError) {
            throw "Step $Num ($ScriptName) 실패. -ContinueOnError 로 무시 가능."
        }
    } else {
        Write-Ok "[$Num] 완료 (${dur}초)"
    }
}

try {
    Write-Step "전체 셋업 실행 ($From → $To)"

    # ---- 파라미터 매핑 helper ----
    $a1 = @{}
    if ($Base) { $a1.Base = $Base }

    $a2 = @{} + $a1
    if ($GiteaVersion) { $a2.Version = $GiteaVersion }
    if ($Force)        { $a2.Force = $true }

    $a3 = @{} + $a1
    if ($NssmVersion) { $a3.Version = $NssmVersion }
    if ($Force)       { $a3.Force = $true }

    $a4 = @{} + $a1
    if ($Force) { $a4.Force = $true }

    $a5 = @{}
    if ($HttpPort)     { $a5.HttpPort     = $HttpPort }
    if ($SshPort)      { $a5.SshPort      = $SshPort }
    if ($HttpRuleName) { $a5.HttpRuleName = $HttpRuleName }
    if ($SshRuleName)  { $a5.SshRuleName  = $SshRuleName }

    $a6 = @{} + $a1
    if ($HttpPort) { $a6.HttpPort = $HttpPort }
    if ($Force)    { $a6.Force = $true }

    $a7 = @{} + $a1
    if ($PublicIp) { $a7.PublicIp = $PublicIp }
    if ($HttpPort) { $a7.HttpPort = $HttpPort }
    if ($SshPort)  { $a7.SshPort  = $SshPort }
    if ($AppName)  { $a7.AppName  = $AppName }
    if ($LogLevel) { $a7.LogLevel = $LogLevel }

    $a8 = @{} + $a1
    if ($ServiceName)  { $a8.ServiceName  = $ServiceName }
    if ($DisplayName)  { $a8.DisplayName  = $DisplayName }
    if ($RestartDelay) { $a8.RestartDelay = $RestartDelay }
    if ($Force)        { $a8.Force = $true }

    $a9 = @{}
    if ($ServiceName)  { $a9.ServiceName  = $ServiceName }
    if ($RestartDelay) { $a9.RestartDelay = $RestartDelay }
    if ($ResetPeriod)  { $a9.ResetPeriod  = $ResetPeriod }

    $a10 = @{} + $a1
    if ($TaskName)    { $a10.TaskName    = $TaskName }
    if ($TriggerTime) { $a10.TriggerTime = $TriggerTime }
    if ($TaskUser)    { $a10.User        = $TaskUser }

    # ============ Phase 1: 자동 (01~05) ============
    Invoke-Step -Num 1  -ScriptName '01-create-folders.ps1'      -StepArgs $a1
    Invoke-Step -Num 2  -ScriptName '02-download-gitea.ps1'      -StepArgs $a2
    Invoke-Step -Num 3  -ScriptName '03-download-nssm.ps1'       -StepArgs $a3
    Invoke-Step -Num 4  -ScriptName '04-download-rclone.ps1'     -StepArgs $a4
    Invoke-Step -Num 5  -ScriptName '05-firewall-rules.ps1'      -StepArgs $a5

    # ============ Phase 2: 대화형 06 (Gitea 마법사) ============
    if (6 -ge $From -and 6 -le $To -and -not $SkipWizard) {
        Write-Host ""
        Write-Host "================================================================" -ForegroundColor Yellow
        Write-Host " [6/10] Gitea 설정 마법사 — 대화형 단계" -ForegroundColor Yellow
        Write-Host "================================================================" -ForegroundColor Yellow
        Write-Warn "▶ 다음 프로세스가 포그라운드로 실행되며 브라우저에서 설정 완료 후 Ctrl+C로 종료해야 합니다."
        Write-Warn "▶ 이미 app.ini가 있으면 -SkipWizard 로 건너뛸 수 있습니다."
        $answer = Read-Host "계속 진행하시겠습니까? (y/N)"
        if ($answer -eq 'y') {
            Invoke-Step -Num 6 -ScriptName '06-run-setup-wizard.ps1' -StepArgs $a6
        } else {
            Write-Warn "[6] 사용자 중단 — 뒷단계 중 일부가 실패할 수 있습니다."
        }
    } elseif ($SkipWizard) {
        Write-Info "[6] -SkipWizard — 마법사 건너뜀"
    }

    # ============ 대화형: rclone config 안내 ============
    if (10 -ge $From -and 10 -le $To -and -not $SkipRclonePrompt) {
        # rclone.exe 자체가 없으면 건너뜀 (Step 4 미실행 시)
        if (-not (Test-Path $RCLONE_EXE)) {
            Write-Warn "rclone.exe 없음: $RCLONE_EXE (Step 4 미완료) — rclone 설정 안내 건너뜀"
            $configured = $true
        } else {
            # rclone 원격이 이미 설정되었는지 확인
            $remotes = & $RCLONE_EXE listremotes 2>&1
            $configured = "$remotes" -match "^${GDRIVE_REMOTE}:" -or "$remotes" -match "`n${GDRIVE_REMOTE}:"
        }

        if (-not $configured) {
            Write-Host ""
            Write-Host "================================================================" -ForegroundColor Yellow
            Write-Host " rclone Google Drive 연결 — 대화형 단계" -ForegroundColor Yellow
            Write-Host "================================================================" -ForegroundColor Yellow
            Write-Warn "원격 '$GDRIVE_REMOTE'가 설정되지 않음."
            Write-Warn "지금 '$RCLONE_EXE config' 를 실행하거나 (-SkipRclonePrompt로 건너뛰고 나중에 수동 설정)"
            $answer = Read-Host "지금 설정하시겠습니까? (y/N)"
            if ($answer -eq 'y') {
                & $RCLONE_EXE config
            } else {
                Write-Warn "rclone 설정 건너뜀 — backup.ps1 실행 시 업로드 실패합니다."
            }
        } else {
            Write-Ok "rclone 원격 '$GDRIVE_REMOTE' 이미 설정됨"
        }
    }

    # ============ Phase 3: 자동 (07~10) ============
    Invoke-Step -Num 7  -ScriptName '07-generate-appini.ps1'         -StepArgs $a7
    Invoke-Step -Num 8  -ScriptName '08-register-service.ps1'        -StepArgs $a8
    Invoke-Step -Num 9  -ScriptName '09-configure-recovery.ps1'      -StepArgs $a9
    Invoke-Step -Num 10 -ScriptName '10-register-backup-schedule.ps1' -StepArgs $a10

    # ============ 최종 요약 ============
    Write-Host ""
    Write-Host "==================== 전체 실행 요약 ====================" -ForegroundColor Cyan
    $results | Format-Table -AutoSize | Out-String | Write-Host
    Write-Host "========================================================" -ForegroundColor Cyan

    if ($overallFail -eq 0) {
        Write-Ok "모든 단계 완료! → http://localhost:$HTTP_PORT"
    } else {
        Write-Fail "$overallFail 개 단계 실패"
    }

    # JSON 요약 저장
    $summaryFile = "$BASE\logs\setup\run-all-summary_$(Get-Date -Format 'yyyy-MM-dd_HHmmss').json"
    $results | ConvertTo-Json | Set-Content -Path $summaryFile -Encoding UTF8
    Write-Info "요약 JSON: $summaryFile"
} catch {
    Write-Fail "중단: $($_.Exception.Message)"
    $overallFail++
} finally {
    Stop-ScriptLog -ExitCode $overallFail
}
exit $overallFail
