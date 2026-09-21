# ============================================
# [07] app.ini 생성 (경량화 설정 적용)
# ============================================
# 설정 마법사에서 생성된 app.ini 위에서:
#   - [security].{SECRET_KEY, INTERNAL_TOKEN, INSTALL_LOCK, PASSWORD_HASH_ALGO} 보존
#   - [oauth2].JWT_SECRET 보존
#   - 나머지는 경량화 설정으로 덮어쓰기
# ============================================
# 옵션:
#   -Base <path>
#   -PublicIp <str>
#   -HttpPort <int>
#   -SshPort <int>
#   -AppName <str>      : 기본 "My Projects"
#   -LogLevel <str>     : 기본 "warn"
# ============================================
param(
    [string]$Base,
    [string]$PublicIp,
    [int]$HttpPort,
    [int]$SshPort,
    [string]$AppName,
    [string]$LogLevel
)

if ($Base)     { $BASE       = $Base }
if ($PublicIp) { $PUBLIC_IP  = $PublicIp }
if ($HttpPort) { $HTTP_PORT  = $HttpPort }
if ($SshPort)  { $SSH_PORT   = $SshPort }
if ($AppName)  { $APP_NAME   = $AppName }
if ($LogLevel) { $LOG_LEVEL  = $LogLevel }

. "$PSScriptRoot\..\config.ps1"
. "$PSScriptRoot\..\common.ps1"

Start-ScriptLog -Category 'setup' -Name '07-generate-appini' -Parameters $PSBoundParameters

$exitCode = 0
try {
    Assert-ConfigSet
    Write-Step "app.ini 생성 (PublicIp=$PUBLIC_IP, HTTP=$HTTP_PORT, SSH=$SSH_PORT)"

    if (-not (Test-Path $APPINI_PATH)) {
        Write-Fail "app.ini가 없습니다. 먼저 setup/06-run-setup-wizard.ps1로 설정 마법사를 완료하세요."
        throw "APPINI_MISSING"
    }

    # --- 기존 비밀 값 파싱 ---
    Write-Info "기존 app.ini에서 비밀 값 추출 중..."
    $existing = @{}
    $section = ""
    foreach ($line in Get-Content $APPINI_PATH) {
        if ($line -match '^\s*\[(.+?)\]') { $section = $matches[1].ToLower(); continue }
        if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+?)\s*$') {
            $k = $matches[1]; $v = $matches[2]
            $existing["$section.$k"] = $v
        }
    }

    $installLock   = $existing['security.INSTALL_LOCK']
    $secretKey     = $existing['security.SECRET_KEY']
    $internalToken = $existing['security.INTERNAL_TOKEN']
    $pwAlgo        = $existing['security.PASSWORD_HASH_ALGO']
    $jwtSecret     = $existing['oauth2.JWT_SECRET']

    if (-not $installLock)   { $installLock = 'true' }
    if (-not $pwAlgo)        { $pwAlgo = 'pbkdf2_hi' }

    # INTERNAL_TOKEN은 필수
    if (-not $internalToken) {
        Write-Fail "INTERNAL_TOKEN 없음. 설정 마법사를 제대로 완료했는지 확인하세요."
        throw "INTERNAL_TOKEN_MISSING"
    }

    # SECRET_KEY는 Gitea 1.20+ 에선 선택적. 없으면 gitea generate secret 로 생성.
    if (-not $secretKey) {
        Write-Warn "SECRET_KEY 없음 — Gitea 1.20+ 마법사는 생성하지 않음. gitea.exe로 생성 시도..."
        if (Test-Path $GITEA_EXE) {
            try {
                $generated = (& $GITEA_EXE generate secret SECRET_KEY 2>&1 | Out-String).Trim()
                if ($generated -and $generated -notmatch '(?i)error|usage|unknown' -and $generated.Length -ge 32) {
                    $secretKey = $generated
                    Write-Ok "SECRET_KEY 생성 완료 ($($secretKey.Length)자)"
                } else {
                    Write-Warn "gitea generate secret 결과가 예상과 다름: $generated"
                    $secretKey = ""
                }
            } catch {
                Write-Warn "gitea generate secret 실행 실패: $($_.Exception.Message)"
                $secretKey = ""
            }
        }
    }

    $secretKeyLen = if ($secretKey) { $secretKey.Length } else { 0 }
    Write-Ok "보존/생성 값: INSTALL_LOCK=$installLock, SECRET_KEY=***($secretKeyLen 자), INTERNAL_TOKEN=***($($internalToken.Length)자)"
    if ($jwtSecret) { Write-Ok "JWT_SECRET=***($($jwtSecret.Length)자)" } else { Write-Warn "JWT_SECRET 없음 — oauth2 섹션 비움" }

    # --- 기존 파일 백업 ---
    $backup = "$APPINI_PATH.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item $APPINI_PATH $backup -Force
    Write-Info "기존 파일 백업: $backup"

    # --- 새 app.ini 작성 ---
    $jwtLine        = if ($jwtSecret) { "JWT_SECRET = $jwtSecret" } else { "" }
    $secretKeyLine  = if ($secretKey) { "SECRET_KEY         = $secretKey" } else { "" }

    $ini = @"
;; ============================================
;; 자동 생성됨 — setup/07-generate-appini.ps1
;; 생성 시각: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
;; ============================================
APP_NAME = $APP_NAME
RUN_MODE = prod

[server]
DOMAIN           = $PUBLIC_IP
HTTP_PORT        = $HTTP_PORT
ROOT_URL         = http://${PUBLIC_IP}:$HTTP_PORT/
SSH_PORT         = $SSH_PORT
START_SSH_SERVER = true
SSH_LISTEN_HOST  = 0.0.0.0
SSH_LISTEN_PORT  = $SSH_PORT
DISABLE_SSH      = false
LFS_START_SERVER = false
OFFLINE_MODE     = true

[security]
INSTALL_LOCK       = $installLock
$secretKeyLine
INTERNAL_TOKEN     = $internalToken
PASSWORD_HASH_ALGO = $pwAlgo

[oauth2]
$jwtLine

[service]
DISABLE_REGISTRATION = true
REQUIRE_SIGNIN_VIEW  = true
ENABLE_NOTIFY_MAIL   = false
ENABLE_CAPTCHA       = false

[packages]
ENABLED = false

[mirror]
ENABLED = false

[actions]
ENABLED = false

[federation]
ENABLED = false

[mailer]
ENABLED = false

[api]
ENABLE_SWAGGER = false

[database]
DB_TYPE = sqlite3
PATH    = $DATA_DIR\gitea.db

[repository]
ROOT                    = $REPOS_DIR
DEFAULT_BRANCH          = main
ENABLE_PUSH_CREATE_USER = true
DISABLED_REPO_UNITS     = repo.wiki, repo.ext_wiki, repo.ext_issues
DEFAULT_REPO_UNITS      = repo.code, repo.issues, repo.pulls, repo.projects

[log]
MODE      = file
LEVEL     = $LOG_LEVEL
ROOT_PATH = $LOG_DIR

[cache]
ADAPTER  = memory
INTERVAL = 60

[session]
PROVIDER = file
"@

    Set-Content -Path $APPINI_PATH -Value $ini -Encoding UTF8
    Write-Ok "app.ini 생성 완료: $APPINI_PATH"
    Write-Info "파일 크기: $([math]::Round((Get-Item $APPINI_PATH).Length / 1KB, 2)) KB"
    Write-Info "총 라인 수: $((Get-Content $APPINI_PATH).Count)"
} catch {
    Write-Fail "오류: $($_.Exception.Message)"
    Write-Fail $_.ScriptStackTrace
    $exitCode = 1
} finally {
    Stop-ScriptLog -ExitCode $exitCode
}
exit $exitCode
