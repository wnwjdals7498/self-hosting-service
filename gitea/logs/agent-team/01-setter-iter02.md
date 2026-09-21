# Agent 1 (Setter) 보고서 — Iteration 2
작성 시각: 2026-04-19 13:40

## iter1 이후 변경점 (내가 한 것)

iter1 Log Manager가 넘긴 "남은 이슈 + 권고"와 `Step 5~10` 실행 결과를 바탕으로:

1. **run-all-setup.ps1**의 대화형 rclone 안내 블록에서 `$RCLONE_EXE` 존재 체크 추가(구간 실행 시 Step 4를 거치지 않아도 안전하게 동작).
2. **08-register-service.ps1**의 NSSM install 인자를 공백 포함 `$BASE` 경로에도 안전하도록 내부 이중따옴표로 보강.
3. **06-run-setup-wizard.ps1**의 `gitea web ... --work-path $BASE`에서 `$BASE` 인자 누락된 따옴표 추가.

모든 수정 후 전체 PowerShell 스크립트 28개 구문 검증: 전부 OK. 수정 3파일 모두 UTF-8 BOM 유지 확인.

실행 측면: `-From 5 -To 10 -ContinueOnError`로 한 번 전 구간 시도 → Step 5/8/9/10은 `ADMIN_REQUIRED`, Step 7은 `PUBLIC_IP_NOT_SET`, Step 6은 대화형 스킵, Step 10의 rclone 가드도 신규 로직으로 정상 통과. 5건 전부 exit=1로 깔끔히 전파됨을 `run-all-summary_2026-04-19_133303.json`에서 확인.

## 스텝별 결과 (5~10)

로그: `D:\Workspace\gitea\logs\setup\run-all-setup_2026-04-19_133301.log`, 요약 JSON: `run-all-summary_2026-04-19_133303.json`

| 스텝 | 종료코드 | 분류 | 조치 |
|------|---------|------|------|
| 5 | 1 | env (ADMIN_REQUIRED) | Assert-Admin이 정상 차단. 수정 불필요 |
| 6 | — | env (대화형 y/N = 건너뜀) | `Invoke-Step` 미호출이라 요약 JSON에 안 실림. 설계 의도대로 |
| 7 | 1 | env (PUBLIC_IP_NOT_SET — CHANGE_ME) | Assert-ConfigSet 정상 차단. 이후 재시도 `-PublicIp 203.0.113.5`로도 APPINI_MISSING(=06 선행 필요)로 정상 |
| 8 | 1 | env (ADMIN_REQUIRED) | 코드 버그 아님. 단, NSSM 인자 공백 안전성 신규 버그 1건 발견 → 수정(아래) |
| 9 | 1 | env (ADMIN_REQUIRED) | 정상 차단 |
| 10 | 1 | env (ADMIN_REQUIRED) | 정상 차단. rclone 가드 로직 정비 |

전체 exit code 전파 경로는 iter1이 이미 닫아둔 대로 신뢰할 수 있음.

## 발견된 신규 코드 버그 (수정 완료)

### 1. `scripts\run-all-setup.ps1:186-200` — rclone 미설치 상태에서 대화형 안내가 CommandNotFound 예외 유발
`-From 5 -To 10` 등 Step 4가 빠진 구간 실행 시 `& $RCLONE_EXE listremotes`가 존재하지 않는 실행 파일을 호출하여 상위 try/catch가 "중단"으로 마무리될 수 있음. iter1 Log Manager의 "권고 사항"과 환경 제약 목록에서 `rclone config`는 대화형이라 어차피 스킵 대상.

**before**
```powershell
if (10 -ge $From -and 10 -le $To -and -not $SkipRclonePrompt) {
    # rclone 원격이 이미 설정되었는지 확인
    $remotes = & $RCLONE_EXE listremotes 2>&1
    $configured = "$remotes" -match "^${GDRIVE_REMOTE}:" -or "$remotes" -match "`n${GDRIVE_REMOTE}:"
```

**after**
```powershell
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
```

### 2. `scripts\setup\08-register-service.ps1:60` — NSSM AppParameters가 공백 포함 경로에서 파싱 오류 가능
`& $NSSM_EXE install $SERVICE_NAME $GITEA_EXE "web --custom-path $BASE\custom --work-path $BASE"` — `$BASE`에 공백 있으면 Gitea CreateProcess 단에서 `--custom-path`/`--work-path` 값이 잘림. 현재 `D:\Workspace\gitea`에 공백 없어 운이 좋았을 뿐.

**before**
```powershell
& $NSSM_EXE install $SERVICE_NAME $GITEA_EXE "web --custom-path $BASE\custom --work-path $BASE"
```

**after**
```powershell
# NSSM AppParameters는 Gitea에 그대로 커맨드라인으로 전달되므로
# $BASE에 공백이 있어도 안전하도록 각 경로 인자를 이중따옴표로 감싼다.
$nssmArgs = 'web --custom-path "{0}\custom" --work-path "{0}"' -f $BASE
& $NSSM_EXE install $SERVICE_NAME $GITEA_EXE $nssmArgs
```

### 3. `scripts\setup\06-run-setup-wizard.ps1:51` — gitea web `--work-path` 인자 인용 누락
`& $GITEA_EXE web --custom-path "$BASE\custom" --work-path $BASE` 의 `--work-path`만 따옴표 누락. 공백 경로에서 인자 분리됨.

**before**
```powershell
& $GITEA_EXE web --custom-path "$BASE\custom" --work-path $BASE
```

**after**
```powershell
& $GITEA_EXE web --custom-path "$BASE\custom" --work-path "$BASE"
```

## 검토했으나 수정 불필요/보류로 남긴 항목

- **`09-configure-recovery.ps1:41` sc.exe 인자**: `& sc.exe failure $SERVICE_NAME reset= $RESET_PERIOD_SEC actions= $actions` — PowerShell `&`가 공백 포함 `$SERVICE_NAME`을 자동 따옴표 처리. 재현 불가, OK.
- **`10-register-backup-schedule.ps1:52` `-At "3:00AM"`**: ko-KR 환경에서도 [datetime]::Parse 성공 실측(`04/19/2026 03:00:00`). PowerShell이 InvariantCulture로 폴백. 실용상 OK, 최소 침습 유지.
- **`07-generate-appini.ps1:52-57` 기존 app.ini 파싱 regex**: `^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+?)\s*$`. 주석(`;`)은 `[A-Z_]` 시작이 아니라 매칭 안 됨. 멀티라인 값도 Gitea 기본 app.ini에 없음. OK.
- **`$PSBoundParameters` 시점**: `Start-ScriptLog -Parameters $PSBoundParameters`는 param 블록 이후 dot-source 뒤에 호출. 항상 hashtable 성질을 가지므로 OK.
- **`run-all-setup.ps1` Step 6의 JSON 누락**: 대화형에서 N 응답 시 `Invoke-Step` 미호출이라 `$results`에 없음. Log Manager가 "Step 6은 대화형 스킵이면 JSON에 안 실림"을 인지해주면 됨.

## 환경 제약 (남겨둔 것)

iter1에서 이미 알려진 것 + iter2 실측:

1. **Step 5 (방화벽)** — `Assert-Admin` 차단. 비관리자 세션에서는 어떤 수정으로도 통과 못함.
2. **Step 6 (setup wizard)** — 포그라운드 `gitea web` + 브라우저 OAuth 마법사. 자동화 불가.
3. **Step 7 (app.ini)** — Step 6 산출물 + 유효한 `$PUBLIC_IP` 둘 다 필요.
4. **Step 8 (서비스 등록)** — 관리자 + Step 7 산출물.
5. **Step 9 (복구 정책)** — 관리자 + Step 8 산출물.
6. **Step 10 (스케줄 태스크)** — 관리자 필요.
7. **rclone config** — OAuth 브라우저 필요. iter2에서 `$RCLONE_EXE` 부재 케이스 안전장치 추가함.

## Tester(iter2)에게 넘길 사항

1. **test-03-nssm-binary.ps1 행업(iter1 Log Manager 발견)**: `nssm.exe version` 10초 행업 → stdout 비어 `-match 'NSSM'` 실패. iter1 보고에서 이미 패턴 수정 범위 밖이라 보류됨. iter2 Tester가 다음 중 하나로 교체 권장:
   - `$verOut = & $NSSM_EXE 2>&1 | Out-String` (인자 없음)
   - `(Get-Item $NSSM_EXE).VersionInfo.FileVersion`
   추천은 후자(파일 리소스 기반으로 안정적).
2. **iter2에서 `08-register-service.ps1`의 NSSM 호출 변경**: 이제 `$nssmArgs` 로컬 변수로 AppParameters 문자열을 선조립 후 전달. test-07-service에서 AppParameters 값 검증(`nssm get Gitea AppParameters`)이 있다면 공백 포함 경로 시나리오에서도 내부 따옴표가 그대로 보존되는지 확인 필요(현재 BASE엔 공백 없어 기존 테스트는 변함없이 통과해야 함).
3. **`run-all-setup.ps1`의 rclone 가드 추가**: rclone 미설치 시 `Write-Warn`만 출력하고 스킵. test에서 `-From 5 -To 10`류 부분 구간 실행 시나리오가 없다면 영향 없음.
4. **`run-all-summary_*.json`에서 Step 6 누락**: 대화형 스킵 시 `Invoke-Step`이 호출 안 되어 JSON에 해당 행 없음. Log Manager가 요약을 집계할 때 오해하지 않도록 안내.

## Log Manager(iter2)에게 참고

- iter2 실행 로그: `D:\Workspace\gitea\logs\setup\run-all-setup_2026-04-19_133301.log`, `run-all-summary_2026-04-19_133303.json` (5/7/8/9/10 FAIL, exit 전파 검증 완료).
- 추가 구간 실행 로그: `run-all-setup_2026-04-19_133659.log`(-From 7, PUBLIC_IP 주입 시 APPINI_MISSING), `run-all-setup_2026-04-19_133747.log`(-From 10, rclone 가드 정상 동작).
- iter2에서 고친 파일 3개: `run-all-setup.ps1`, `setup\06-run-setup-wizard.ps1`, `setup\08-register-service.ps1`. 모두 구문 OK + UTF-8 BOM 유지.
- 실운영 관리자 세션에서 5~10을 처음 돌릴 때, 08의 NSSM AppParameters가 내부따옴표 포함 문자열로 저장되는지 `nssm get Gitea AppParameters`로 한 번 확인 권장. 값은 `web --custom-path "D:\Workspace\gitea\custom" --work-path "D:\Workspace\gitea"` 형태여야 함.
- 남은 공지 사항(로그 인코딩, 타임스탬프 충돌, PUBLIC_IP CHANGE_ME)은 iter1 Log Manager가 남긴 그대로 유효.
