# ============================================
# 로그 로테이션 / 정리 스크립트
#   - $BASE\logs\{setup, tests, backup, restore}\*.log 만 대상
#   - agent-team/, gitea/ 폴더는 정책상 보호 (건드리지 않음)
# ============================================
# 옵션:
#   -Base <path>              : 기본 디렉토리 (기본 config.ps1 값)
#   -RetentionDays <int>      : 보존일수 (기본 30)
#   -MaxPerCategory <int>     : 카테고리별 최대 파일 수 (기본 100)
#   -DryRun                   : 실제 삭제하지 않고 대상만 출력
# ============================================
param(
    [string]$Base,
    [int]$RetentionDays = 30,
    [int]$MaxPerCategory = 100,
    [switch]$DryRun
)

if ($Base) { $BASE = $Base }

. "$PSScriptRoot\config.ps1"
. "$PSScriptRoot\common.ps1"

Start-ScriptLog -Category 'logs-rotation' -Name 'rotate' -Parameters $PSBoundParameters

$exitCode = 0
$started = Get-Date

# 대상 카테고리(삭제 허용). agent-team, gitea, logs-rotation 은 의도적으로 제외.
$targetCategories = @('setup','tests','backup','restore')

# 통계 누적
$totalExamined = 0
$totalDeletedByAge = 0
$totalDeletedByCount = 0
$totalBytesFreed = 0L
$totalErrors = 0

try {
    Write-Step "로그 로테이션 시작 — $($started.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Info "BASE            = $BASE"
    Write-Info "RetentionDays   = $RetentionDays"
    Write-Info "MaxPerCategory  = $MaxPerCategory"
    Write-Info "DryRun          = $($DryRun.IsPresent)"
    Write-Info "대상 카테고리   = $($targetCategories -join ', ')"
    Write-Info "보호 카테고리   = agent-team, gitea, logs-rotation"

    $cutoff = (Get-Date).AddDays(-1 * [Math]::Abs($RetentionDays))
    Write-Info "보존 기준일시   = $($cutoff.ToString('yyyy-MM-dd HH:mm:ss')) 이전은 삭제 대상"

    foreach ($cat in $targetCategories) {
        $dir = Join-Path $BASE "logs\$cat"
        if (-not (Test-Path $dir)) {
            Write-Warn "[$cat] 디렉토리 없음 — 건너뜀: $dir"
            continue
        }

        Write-Step "[$cat] 스캔 — $dir"

        # .log 및 .json(run-all-summary_*.json) 포함. .gitkeep 은 제외.
        $files = @(Get-ChildItem -Path $dir -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne '.gitkeep' })

        $examined = $files.Count
        $totalExamined += $examined
        Write-Info "[$cat] 파일 수 = $examined"

        if ($examined -eq 0) {
            Write-Info "[$cat] 정리 대상 없음"
            continue
        }

        # (a) 보존일수 초과 파일
        $ageVictims = @($files | Where-Object { $_.LastWriteTime -lt $cutoff })
        Write-Info "[$cat] 나이 기준 삭제 후보 = $($ageVictims.Count)"

        foreach ($f in $ageVictims) {
            $ageDays = [int]((Get-Date) - $f.LastWriteTime).TotalDays
            if ($DryRun) {
                Write-Info "[DRY] [AGE $ageDays d] 삭제 예정: $($f.FullName) ($([Math]::Round($f.Length/1KB,2)) KB)"
                $totalDeletedByAge++
                $totalBytesFreed += $f.Length
            } else {
                try {
                    $size = $f.Length
                    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop
                    Write-Ok "[AGE $ageDays d] 삭제: $($f.Name) ($([Math]::Round($size/1KB,2)) KB)"
                    $totalDeletedByAge++
                    $totalBytesFreed += $size
                } catch {
                    Write-Warn "[AGE] 삭제 실패(계속 진행): $($f.FullName) — $($_.Exception.Message)"
                    $totalErrors++
                }
            }
        }

        # (b) 남은 파일 중 MaxPerCategory 초과분 — 오래된 순 삭제
        #     DryRun일 때도 "이미 삭제된 것으로 가정"하고 남은 목록에서 평가.
        $survivors = @($files | Where-Object { $_.LastWriteTime -ge $cutoff })
        if ($survivors.Count -gt $MaxPerCategory) {
            $overflow = $survivors.Count - $MaxPerCategory
            Write-Info "[$cat] 개수 기준 추가 삭제 후보 = $overflow (잔존 $($survivors.Count) > 상한 $MaxPerCategory)"
            $byOldest = $survivors | Sort-Object LastWriteTime | Select-Object -First $overflow
            foreach ($f in $byOldest) {
                if ($DryRun) {
                    Write-Info "[DRY] [CAP] 삭제 예정: $($f.FullName) ($([Math]::Round($f.Length/1KB,2)) KB)"
                    $totalDeletedByCount++
                    $totalBytesFreed += $f.Length
                } else {
                    try {
                        $size = $f.Length
                        Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop
                        Write-Ok "[CAP] 삭제: $($f.Name) ($([Math]::Round($size/1KB,2)) KB)"
                        $totalDeletedByCount++
                        $totalBytesFreed += $size
                    } catch {
                        Write-Warn "[CAP] 삭제 실패(계속 진행): $($f.FullName) — $($_.Exception.Message)"
                        $totalErrors++
                    }
                }
            }
        } else {
            Write-Info "[$cat] 개수 상한 이내 ($($survivors.Count) <= $MaxPerCategory) — 추가 삭제 없음"
        }
    }

    # --- 요약 ---
    $elapsed = (Get-Date) - $started
    Write-Step "로테이션 요약"
    Write-Info "검사 파일 수      = $totalExamined"
    Write-Info "나이 기준 삭제    = $totalDeletedByAge"
    Write-Info "개수 기준 삭제    = $totalDeletedByCount"
    Write-Info "총 삭제           = $($totalDeletedByAge + $totalDeletedByCount)"
    Write-Info "회수 용량 (대략)  = $([Math]::Round($totalBytesFreed/1KB,2)) KB"
    Write-Info "삭제 실패         = $totalErrors"
    Write-Info "소요              = $($elapsed.TotalSeconds.ToString('F2')) s"
    if ($DryRun) {
        Write-Warn "DryRun 모드 — 실제 파일은 삭제되지 않았습니다."
    }
    Write-Ok "로테이션 완료"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
