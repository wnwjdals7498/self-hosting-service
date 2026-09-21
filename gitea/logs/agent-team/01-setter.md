# Agent 1 (Setter) 보고서
작성 시각: 2026-04-19 13:17

## 실행 요약
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Workspace\gitea\scripts\run-all-setup.ps1` 를 `-From N -To N` 로 1부터 10까지 단계별로 실행 시도.
- 첫 실행(Step 1)에서 마스터 러너가 즉시 터지는 치명 버그 1건 발견 → 수정.
- Step 1, 2, 3(재시도), 4 실행 성공 확인 (관리자/네트워크/서비스 불필요 구간).
- Step 5(방화벽), 7(app.ini 생성) 시도로 하위 자식 스크립트의 `exit`/`$LASTEXITCODE` 전파 버그 발견 → 수정.
- 각 스크립트 정적 리뷰로 추가 `return` 패턴 버그 일괄 수정.
- 사용한 도구: Bash(powershell.exe 호출), Read, Edit, Grep.

## 발견된 스크립트 버그 (수정 완료)

### 1. `scripts\run-all-setup.ps1:69-97` — `$Args` 예약 변수 충돌 (치명)
`Invoke-Step` 함수 param 이름 `$Args`는 PowerShell 자동 변수(함수에 넘어온 언바운드 args 배열)와 충돌. `[hashtable]$Args = @{}` 타입 변환에서 `"System.Object[]" -> "System.Collections.Hashtable" 변환 불가` 에러로 즉사.

**before**
```powershell
function Invoke-Step {
    param(
        [int]$Num,
        [string]$ScriptName,
        [hashtable]$Args = @{}
    )
    ...
    if ($Args.Count -gt 0) { ... }
    & "$setup\$ScriptName" @Args
    ...
    $script:results += [PSCustomObject]@{
        Step = $Num; ...; Result = if ($ec -eq 0) { 'PASS' } else { 'FAIL' }; ...
    }
}
Invoke-Step -Num 1 -ScriptName '01-...' -Args $a1
```

**after**
```powershell
function Invoke-Step {
    param(
        [int]$Num,
        [string]$ScriptName,
        [hashtable]$StepArgs = @{}
    )
    ...
    if ($StepArgs.Count -gt 0) { ... }
    & "$setup\$ScriptName" @StepArgs
    ...
    $resultText = if ($ec -eq 0) { 'PASS' } else { 'FAIL' }
    $script:results += [PSCustomObject]@{
        Step = $Num; ...; Result = $resultText; ...
    }
}
Invoke-Step -Num 1 -ScriptName '01-...' -StepArgs $a1
```

(호출부 8곳 전부 `-Args` → `-StepArgs` 로 교체. PS 5.1에서 hashtable 리터럴 안에 `if`식 삽입은 줄내 세미콜론 구분 시 파서가 혼란스러워하는 경우가 있어 한 줄 위로 추출.)

### 2. 자식 스크립트의 `$exitCode = 1; return` 패턴 — exit 미실행 (실패 exit 코드 미전파)
PowerShell 스크립트에서 try 블록 안 `return` 을 하면 finally만 실행되고 스크립트가 종료됨. 스크립트 맨 끝의 `exit $exitCode` 가 실행되지 않아, 부모(run-all-setup.ps1)의 `$LASTEXITCODE` 가 null/빈값이 됨. 결과적으로 요약표에 `ExitCode=` 공란이 찍히고 판정 로직이 어긋남.

실측: `-From 7 -To 7` 에서 app.ini 없음으로 실패 시 `ExitCode=` (빈값) 로 표시됨.

**수정한 파일/라인** (`$exitCode = 1; return` → `throw "…"` 으로 교체, try/catch/finally/exit 경로로 재라우팅):

- `scripts\setup\02-download-gitea.ps1:31` — `throw "BIN_DIR_MISSING"`
- `scripts\setup\03-download-nssm.ps1:31,61` — `throw "BIN_DIR_MISSING" / "NSSM_EXE_NOT_FOUND_IN_ZIP"`
- `scripts\setup\04-download-rclone.ps1:28,53` — `throw "BIN_DIR_MISSING" / "RCLONE_EXE_NOT_FOUND_IN_ZIP"`
- `scripts\setup\06-run-setup-wizard.ps1:31` — `throw "GITEA_EXE_MISSING"`
- `scripts\setup\07-generate-appini.ps1:45,71` — `throw "APPINI_MISSING" / "SECRET_OR_TOKEN_MISSING"`
- `scripts\setup\08-register-service.ps1:33,34,35` — `throw "NSSM_EXE_MISSING" / "GITEA_EXE_MISSING" / "APPINI_MISSING"`
- `scripts\setup\09-configure-recovery.ps1:32,46` — `throw "SERVICE_NOT_REGISTERED" / "SC_FAILURE_CMD_FAILED"`
- `scripts\setup\10-register-backup-schedule.ps1:34` — `throw "BACKUP_SCRIPT_MISSING"`
- `scripts\backup.ps1:42~45,92` — 동일 패턴 교체

**예시 (07-generate-appini.ps1:43-45)**

before
```powershell
if (-not (Test-Path $APPINI_PATH)) {
    Write-Fail "app.ini가 없습니다. 먼저 setup/06-run-setup-wizard.ps1로 설정 마법사를 완료하세요."
    $exitCode = 1; return
}
```

after
```powershell
if (-not (Test-Path $APPINI_PATH)) {
    Write-Fail "app.ini가 없습니다. 먼저 setup/06-run-setup-wizard.ps1로 설정 마법사를 완료하세요."
    throw "APPINI_MISSING"
}
```

재실행 후 요약표에 `ExitCode=1` 로 정상 표기 확인.

### 3. `scripts\common.ps1:20-34` — `Assert-Admin` / `Assert-ConfigSet` 의 `exit 1` (로그 오염)
`exit 1` 을 호출하면 자식 스크립트의 try/finally가 정상 동작은 하지만 catch가 작동하지 않아 `$exitCode` 가 0인 채로 `Stop-ScriptLog` 가 호출됨. 로그 파일에는 `종료 코드 : 0` 으로 잘못 기록됨. 부모는 native exit code 1을 받지만 자식 로그가 혼란스러움.

**before**
```powershell
function Assert-Admin { ...; exit 1 }
function Assert-ConfigSet { ...; exit 1 }
```

**after**
```powershell
function Assert-Admin { ...; throw "ADMIN_REQUIRED" }
function Assert-ConfigSet { ...; throw "PUBLIC_IP_NOT_SET" }
```

이후 05 수동 재현: 자식 로그가 `종료 코드 : 1` 로 올바르게 기록됨.

## 환경 제약 (수정 안 한 것)

- **Step 3 (nssm.cc 503)** — 최초 시도 시 HTTP 503 Service Unavailable. 재시도 시 성공. nssm.cc 쪽 일시적 문제이며 스크립트 버그 아님. 재시도 로직 추가는 과설계라 패스.
- **Step 5 (방화벽)** — 관리자 권한 필요. 현 세션은 비관리자. `Assert-Admin` 이 의도대로 차단 (수정 후 exit 코드도 깔끔).
- **Step 6 (설정 마법사)** — 포그라운드 gitea web + 브라우저 상호작용 필요. 자동화 불가.
- **Step 7 (app.ini 생성)** — Step 6 산출물(`$BASE\custom\conf\app.ini`) 필요. Step 6 건너뛴 상태에서 `throw "APPINI_MISSING"` 정상 동작.
- **Step 8 (서비스 등록)** — 관리자 + Step 7 결과 필요.
- **Step 9 (복구 정책)** — 관리자 + Step 8 결과 필요.
- **Step 10 (스케줄 태스크)** — 관리자 필요.
- **rclone config** — 브라우저 OAuth 필요.

추가 정적 주의사항 (수정 대상 아님, 참고):

- `08-register-service.ps1:60` NSSM install 인자 문자열에 `$BASE` 가 공백 포함된 경로면 gitea.exe가 `--custom-path` 값을 오해할 수 있음. 현재 `D:\Workspace\gitea` 는 공백 없어 무문제.
- `run-all-setup.ps1:188-189` — `$RCLONE_EXE listremotes` 호출. 10단계가 범위 안일 때만 실행되므로 rclone 미설치 시 같은 범위 내에서만 에러. 실제로 Step 4가 먼저 수행되는 전제라 정상.

## Tester Agent에게 넘길 사항

1. **Invoke-Step 파라미터 이름 변경** — `run-all-setup.ps1` 의 `-Args` 가 `-StepArgs` 로 변경됨. 테스트가 이 함수를 직접 쓰지 않으면 무관.
2. **실패 자식 스크립트의 exit 코드 전파가 이제 믿을 수 있음** — `tests\run-all-tests.ps1:87` 의 `Result = if ($ec -eq 0) ...` 가 실제로 의미를 가짐. 이전엔 일부 실패 경로에서 `$ec` 가 빈값이라 잘못된 PASS로 찍혔을 가능성 있음. 테스트 로그 재검토 권장.
3. **Assert-Admin/Assert-ConfigSet 이 `throw` 로 변경** — 테스트 스크립트가 이 함수들을 직접 호출해 early-exit 를 기대했다면, 이제는 `try { } catch { }` 로 받아야 함. (현재 test-*.ps1 파일들은 Assert-* 미사용으로 보여 영향 없을 것.)
4. **스크립트가 오류 시 `throw` 로 끝나는 게 정상 경로가 됨** — 테스트에서 `-ContinueOnError` 필요 여부 재확인.
5. `sc.exe failure` 출력/`app.ini` 내용 검증 테스트는 Step 6-7-8 선행 필요. 본 세션에서 6-10은 실행되지 않았음.

## 다음 단계 권고 (Log Manager / 재실행 시)

1. **nssm.cc 503 재현 여부** — 배포/재설치 시 간헐적으로 터질 수 있음. Log Manager는 Step 3 실패를 항상 "스크립트 버그" 가 아니라 먼저 nssm.cc 쪽 503 로그인지 분리해서 판단할 것. `Invoke-WebRequest -MaximumRetryCount` 가 PS 5.1에 없어 자동 재시도 불가 — 운영자가 수동 재실행 안내.
2. **로그 파일명 타임스탬프 충돌** — `Start-ScriptLog` 에서 `yyyy-MM-dd_HHmmss` 사용. 같은 초에 두 번 실행하면 `-Append` 로 합쳐짐. 의도된 동작이나 Log Manager 파싱 시 헷갈릴 수 있음.
3. **한글 로그 인코딩** — 본 세션 bash 터미널 출력에서 한글 깨짐 확인됨 (CP949 ↔ UTF-8 이슈). 로그 파일 자체는 Start-Transcript 기본 인코딩이므로, Log Manager가 `Get-Content -Encoding Default` 로 읽어야 할 수 있음. 또는 로그 열람을 PowerShell 콘솔 (UTF-8) 에서 하면 정상.
4. **`run-all-summary_*.json`** — 마스터 러너가 매 실행마다 생성. Log Manager는 최신 것 1개만 의미 있음 (또는 병합 필요).
5. **재실행 안전성** — 01~04는 멱등, 05~10은 `-Force` 없이도 대부분 idempotent (이미 존재하면 건너뜀). 10(스케줄)만 `Unregister + Register` 로 항상 덮어씀.
