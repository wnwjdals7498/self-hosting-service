# ============================================
# 공통 함수 (로깅 + 테스트 헬퍼)
# ============================================

# --- 콘솔 + 로그 파일 겸용 출력 ---
function Write-Step { param([string]$Message) _Log "STEP" $Message "Cyan" }
function Write-Ok   { param([string]$Message) _Log " OK " $Message "Green" }
function Write-Fail { param([string]$Message) _Log "FAIL" $Message "Red" }
function Write-Info { param([string]$Message) _Log "INFO" $Message "Gray" }
function Write-Warn { param([string]$Message) _Log "WARN" $Message "Yellow" }

function _Log {
    param([string]$Tag, [string]$Message, [string]$Color)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    $line = "[$ts] [$Tag] $Message"
    Write-Host $line -ForegroundColor $Color
    # 파일로는 Start-Transcript가 자동 기록 (아래 Start-ScriptLog 참조)
}

function Assert-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object System.Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Fail "관리자 권한이 필요합니다. 관리자 PowerShell에서 다시 실행하세요."
        throw "ADMIN_REQUIRED"
    }
}

function Assert-ConfigSet {
    if ($PUBLIC_IP -eq "CHANGE_ME") {
        Write-Fail "config.ps1의 `$PUBLIC_IP를 먼저 설정하세요."
        throw "PUBLIC_IP_NOT_SET"
    }
}

# ============================================
# 스크립트 실행 로그 (Start-Transcript 래퍼)
# ============================================
# 사용:
#   Start-ScriptLog -Category 'setup' -Name '01-create-folders'
#   ... 실제 작업 ...
#   Stop-ScriptLog
#
# 로그 위치: $BASE\logs\{Category}\{Name}_{타임스탬프}.log
# ============================================

$script:_CURRENT_LOG = $null

function Start-ScriptLog {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('setup','tests','backup','restore','logs-rotation')]
        [string]$Category,
        [Parameter(Mandatory=$true)][string]$Name,
        [System.Collections.IDictionary]$Parameters = $null
    )

    $logDir = "$BASE\logs\$Category"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    $ts = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $logFile = "$logDir\${Name}_$ts.log"
    $script:_CURRENT_LOG = $logFile

    # Start-Transcript는 모든 콘솔 출력(Write-Host 포함)을 캡처
    try { Stop-Transcript -ErrorAction SilentlyContinue | Out-Null } catch {}
    Start-Transcript -Path $logFile -Append -Force | Out-Null

    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host " $Name" -ForegroundColor Cyan
    Write-Host " 시작 시각 : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
    Write-Host " 카테고리  : $Category" -ForegroundColor Cyan
    Write-Host " 로그 파일 : $logFile" -ForegroundColor DarkGray
    Write-Host " 호스트    : $env:COMPUTERNAME / 사용자: $env:USERNAME" -ForegroundColor DarkGray
    Write-Host " PS 버전   : $($PSVersionTable.PSVersion)" -ForegroundColor DarkGray

    # --- 호출 시 넘어온 파라미터 덤프 ---
    if ($Parameters -and $Parameters.Count -gt 0) {
        Write-Host " 호출 파라미터:" -ForegroundColor Cyan
        foreach ($k in $Parameters.Keys) {
            $v = $Parameters[$k]
            if ($v -is [switch]) { $v = if ($v.IsPresent) { 'True' } else { 'False' } }
            Write-Host "   -$k = $v" -ForegroundColor DarkGray
        }
    } else {
        Write-Host " 호출 파라미터: (없음 — 모두 config.ps1 기본값)" -ForegroundColor DarkGray
    }

    # --- 효과 설정 값 (config 병합 후) ---
    Write-Host " 효과 설정 값:" -ForegroundColor Cyan
    Write-Host "   BASE        = $BASE" -ForegroundColor DarkGray
    Write-Host "   PUBLIC_IP   = $PUBLIC_IP" -ForegroundColor DarkGray
    Write-Host "   HTTP_PORT   = $HTTP_PORT" -ForegroundColor DarkGray
    Write-Host "   SSH_PORT    = $SSH_PORT" -ForegroundColor DarkGray
    Write-Host "   SERVICE     = $SERVICE_NAME" -ForegroundColor DarkGray
    Write-Host "   GITEA_VER   = $GITEA_VERSION" -ForegroundColor DarkGray
    Write-Host "================================================================" -ForegroundColor Cyan
}

function Stop-ScriptLog {
    param([int]$ExitCode = 0)
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host " 종료 시각 : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
    Write-Host " 종료 코드 : $ExitCode" -ForegroundColor $(if ($ExitCode -eq 0) { 'Green' } else { 'Red' })
    if ($script:_CURRENT_LOG) {
        Write-Host " 로그 파일 : $($script:_CURRENT_LOG)" -ForegroundColor DarkGray
    }
    Write-Host "================================================================" -ForegroundColor Cyan
    try { Stop-Transcript | Out-Null } catch {}
    $script:_CURRENT_LOG = $null
}

# ============================================
# 테스트 헬퍼
# ============================================

function Test-Result {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][bool]$Passed,
        [string]$Detail = ""
    )
    $ts = Get-Date -Format "HH:mm:ss.fff"
    if ($Passed) {
        Write-Host "  [$ts] [PASS] $Name" -ForegroundColor Green
        if ($Detail) { Write-Host "                 $Detail" -ForegroundColor DarkGray }
    } else {
        Write-Host "  [$ts] [FAIL] $Name" -ForegroundColor Red
        if ($Detail) { Write-Host "                 $Detail" -ForegroundColor Yellow }
    }
    return $Passed
}

function Write-TestSummary {
    param([int]$Pass, [int]$Fail)
    $color = if ($Fail -eq 0) { 'Green' } else { 'Red' }
    Write-Host ""
    Write-Host "---------------------------------------------" -ForegroundColor $color
    Write-Host " 결과: PASS=$Pass  FAIL=$Fail  TOTAL=$($Pass + $Fail)" -ForegroundColor $color
    Write-Host "---------------------------------------------" -ForegroundColor $color
}
