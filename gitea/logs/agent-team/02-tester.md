# Agent 2 (Tester) 보고서
작성 시각: 2026-04-19 13:45

## Setter 인수인계 요약

Setter가 적용한 핵심 변경:

1. **`run-all-setup.ps1`의 `Invoke-Step` 파라미터 이름 변경**: `-Args` (PS 예약 자동변수 `$Args`와 충돌 → 치명 버그) → `-StepArgs`. 호출부 8곳 전부 교체. 테스트 스크립트는 이 러너를 직접 호출하지 않으므로 영향 없음.
2. **자식 setup 스크립트의 `$exitCode = 1; return` → `throw "<TOKEN>"` 통일**: try/catch/finally/exit 경로로 라우팅되어야 `exit $exitCode`가 실행되고 `$LASTEXITCODE`가 부모로 정확히 전파된다. 02/03/04/06/07/08/09/10 및 `backup.ps1`에 일괄 적용.
3. **`common.ps1`의 `Assert-Admin` / `Assert-ConfigSet`이 `exit 1` → `throw "<TOKEN>"`**: 자식 try 블록이 catch를 거치도록 하여 로그의 "종료 코드" 표기가 정확해짐. 테스트들은 Assert-* 함수를 직접 쓰지 않아 영향 없음.
4. **실패 exit 코드 신뢰성 향상**: `tests\run-all-tests.ps1:87`의 `$ec -eq 0` 판정이 이제 실제 자식 스크립트 실패와 일치.

Setter가 남긴 유일한 테스트 관련 경고: "이전엔 일부 실패 경로에서 `$ec`가 빈값이라 잘못된 PASS로 찍혔을 가능성. 테스트 로그 재검토 권장." → 이는 setup 쪽 수정으로 이미 해결되었고, 추가로 **테스트 스크립트 자체에도 같은 패턴 버그가 있음을 발견** (아래 수정 내역 참조).

## 테스트 스크립트 수정 내역

### 핵심 버그: `$fail++; return` — Setter가 고친 것과 동일한 패턴

각 테스트의 try 블록 안에서 선행조건 실패 시 `$fail++; return`을 사용. PowerShell 스크립트의 try 블록 안 `return`은 finally만 실행하고 스크립트를 종료시키며, 스크립트 말미의 `exit $fail`을 **실행하지 못함**. 결과적으로 `$LASTEXITCODE`가 0이 남아 `run-all-tests.ps1`에서 **실패를 PASS로 잘못 집계**할 수 있었음.

해결: Setter의 패턴을 그대로 따라 `throw "<TOKEN>"`로 교체. catch 블록에서 `$fail++` 하여 카운트를 1회만 증가. 요약 누락 방지를 위해 catch 블록에 `Write-TestSummary` 추가.

| 파일 | 라인 | before | after |
|---|---|---|---|
| `test-02-gitea-binary.ps1` | 26 | `else { $fail++; return }` | `else { throw "GITEA_EXE_MISSING" }` |
| `test-03-nssm-binary.ps1` | 23 | `else { $fail++; return }` | `else { throw "NSSM_EXE_MISSING" }` |
| `test-04-rclone-binary.ps1` | 23 | `else { $fail++; return }` | `else { throw "RCLONE_EXE_MISSING" }` |
| `test-06-appini.ps1` | 35 | `else { $fail++; return }` | `else { throw "APPINI_MISSING" }` |
| `test-07-service.ps1` | 27 | `else { $fail++; return }` | `else { throw "SERVICE_NOT_REGISTERED" }` |
| `test-08-recovery.ps1` | 29 | `else { $fail++; return }` | `else { throw "SERVICE_NOT_REGISTERED" }` |
| `test-11-rclone-config.ps1` | 26–28 | `Test-Result...; $fail++; return` | `Test-Result...; throw "RCLONE_EXE_MISSING"` |
| `test-11-rclone-config.ps1` | 35–39 | `else { $fail++; Write-Warn ...; return }` | `else { Write-Warn ...; throw "RCLONE_REMOTE_NOT_CONFIGURED" }` |
| `test-12-backup-schedule.ps1` | 23 | `else { $fail++; return }` | `else { throw "SCHEDULED_TASK_NOT_REGISTERED" }` |
| `test-13-backup-execution.ps1` | 41–42 | `Test-Result...; $fail++; return` | `Test-Result...; throw "BACKUP_SCRIPT_MISSING"` |

### catch 블록에 `Write-TestSummary` 호출 추가

throw 경로에서도 PASS/FAIL 요약이 출력되도록 모든 `test-*.ps1`과 `run-all-tests.ps1`에 `Write-TestSummary`를 catch 블록에 추가 (`run-all-tests.ps1`은 집계 로직이 별도여서 실패 카운트만 강조 출력).

| 파일 | 변경 |
|---|---|
| `test-01-folders.ps1` ~ `test-13-backup-execution.ps1` (총 13개) | catch 블록에 `Write-TestSummary -Pass $pass -Fail $fail` 한 줄 추가 |
| `run-all-tests.ps1` | finally에 `Write-Host "종료 시 실패 카운트: $overallFail"` 추가 (catch 경로에서 사용자가 실패를 놓치지 않도록) |

before (공통 패턴):
```powershell
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
} finally {
    Stop-ScriptLog -ExitCode $fail
}
```

after:
```powershell
} catch {
    Write-Fail "예외: $($_.Exception.Message)"
    $fail++
    Write-TestSummary -Pass $pass -Fail $fail
} finally {
    Stop-ScriptLog -ExitCode $fail
}
```

### 확인만 하고 수정하지 않은 항목 (최소 침습)

- **`test-09-http-connectivity.ps1:40,54`의 `if (Test-Result ... -Passed $false ...) {} else { $fail++ }`**: `Test-Result`는 항상 `$false`를 반환하므로 결과적으로는 정확히 `$fail`만 1 증가. 의도가 이상해 보이지만 동작은 맞음 — 건드리지 않음.
- **`test-11-rclone-config.ps1:34`의 멀티라인 matching**: `"$remotes" -match "^${GDRIVE_REMOTE}:" -or "$remotes" -match "`n${GDRIVE_REMOTE}:"` — 배열을 공백으로 문자열화하므로 `\n`이 없을 수 있어 원격이 두 번째 이후 줄일 때 매칭 실패 가능성. 하지만 기존 로직이고 Setter 수정 범위 밖이며, 실제 `listremotes` 출력은 줄 단위로 이어져 `$remotes`가 string[] → 공백 join 시 `"gdrive: foo:"` 형태가 되어 `^gdrive:`는 매칭됨. Low-risk. 보류.
- **`run-all-tests.ps1:77`의 regex `\[\w+(\[\])?\]\s*\$$k\b`**: param 타입이 `[int]`, `[string]`, `[switch]`, `[int[]]` 전부 `\w+(\[\])?`에 매칭. 정상.
- **test-13의 `$forwardArgs` splatting**: `$PSBoundParameters`에서 switch 타입 포함해도 PS가 올바르게 처리. OK.
- **test-01은 조기 종료가 없음**: 폴더 배열 순회만 하므로 `return` 버그 없음. catch에만 `Write-TestSummary` 추가.
- **관리자 권한 / 외부 서비스 의존 테스트**: test-05(방화벽 read-only라 비관리자 가능), test-07~10, test-12~13은 실제 setup이 끝난 뒤에만 유효. FAIL 나도 테스트 버그가 아님.

## 구문 검증 결과

```
OK  run-all-tests.ps1
OK  test-01-folders.ps1
OK  test-02-gitea-binary.ps1
OK  test-03-nssm-binary.ps1
OK  test-04-rclone-binary.ps1
OK  test-05-firewall.ps1
OK  test-06-appini.ps1
OK  test-07-service.ps1
OK  test-08-recovery.ps1
OK  test-09-http-connectivity.ps1
OK  test-10-ssh-connectivity.ps1
OK  test-11-rclone-config.ps1
OK  test-12-backup-schedule.ps1
OK  test-13-backup-execution.ps1
```

PASS=14 FAIL=0

UTF-8 BOM: 14개 파일 전원 BOM 유지 확인.

## Log Manager에게 넘길 사항

### 재실행 시 기대되는 동작

1. **실패 테스트의 exit code가 이제 신뢰 가능**. `run-all-summary_*.json`의 `ExitCode` 컬럼이 비거나 0으로 잘못 찍히는 경우가 제거되었다. 이전 JSON과 교차 비교하면 "이전엔 PASS였는데 이번엔 FAIL"인 항목이 나올 수 있으며, 이는 **실제 FAIL이 과거에 PASS로 오인된 것**이다 (회귀 아님).
2. throw 경로를 거친 테스트도 콘솔과 로그에 `Write-TestSummary`로 PASS/FAIL 숫자가 찍힌다.

### 우선 실행 순서 권고

setup이 아직 미완료이므로 (Setter 세션에서 Step 5~10 미실행), 테스트는 다음 순서로 분리해 실행:

1. **무조건 실행 (전제 조건 없음)**: test-01 (폴더), test-02 (gitea.exe), test-03 (nssm.exe), test-04 (rclone.exe)  
   → `powershell.exe -NoProfile -ExecutionPolicy Bypass -File run-all-tests.ps1 -Filter "01,02,03,04"`
2. **방화벽/서비스/설정 실행 후**: test-05, test-06, test-07, test-08, test-09, test-10
3. **rclone 설정 후**: test-11
4. **스케줄 등록 후**: test-12
5. **E2E (실제 백업)**: test-13은 `-IncludeE2E` 플래그로만 실행됨. Google Drive 업로드 발생 주의.

### 주의할 점

1. **외부 네트워크 테스트** (`test-09`, `test-10`)는 `PUBLIC_IP = CHANGE_ME` 상태에서는 외부 IP 루프를 건너뜀. `-PublicIp` 또는 `-SkipExternal`로 명시 필요.
2. **관리자 권한이 필요한 테스트**는 없음 — 읽기 전용 조회(`Get-NetFirewallRule`, `Get-Service`, `sc.exe qfailure`, `Get-ScheduledTask`)는 비관리자에서도 동작.
3. **test-11의 rclone 원격 매칭 regex**는 공백 문자열화 경계 케이스에서 살짝 약하나 실사용에 문제 없음. 이후 누군가 건드릴 일이 있다면 `($remotes -split '\r?\n') -match "^${GDRIVE_REMOTE}:$"` 형태가 더 안전.
4. **test-13 (E2E)**은 실제 `backup.ps1`을 실행하므로 Gitea 서비스 일시 중지 + GDrive 업로드 발생. CI에서는 `-SkipUpload` 필수.
5. **`run-all-tests.ps1`의 Filter 파라미터**는 `-Filter "01"`로 test-01뿐 아니라 test-10/11/12/13도 잡을 수 있는지 주의 필요. 실제 로직은 `test-$n-` 패턴이므로 `test-1-`는 없고 `test-10-`, `test-11-` 등만 존재 → `-Filter "1"`은 매칭 0개가 될 것. 사용자에게 2자리 전달을 안내.
6. **로그 파일명 `yyyy-MM-dd_HHmmss`**: Setter 보고와 동일. 동일 초에 두 번 돌리면 `-Append`로 합쳐지므로 Log Manager가 최신 파일을 구별할 때 유의.
7. **콘솔 인코딩**: bash에서 `powershell.exe`를 호출할 때 CP949↔UTF-8 한글 깨짐 발생 가능. 로그 파일 자체는 Transcript 기본 인코딩이며 Windows PowerShell 콘솔에서 직접 보는 것이 안전.
