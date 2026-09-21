# Agent 2 (Tester) 보고서 — Iteration 2
작성 시각: 2026-04-19 13:42

## Setter iter2 영향 분석

Setter iter2가 고친 3개 파일을 테스트 관점에서 각각 검토함.

| Setter iter2 변경 | 관련 가능 테스트 | 영향 여부 | 근거 |
|---|---|---|---|
| `run-all-setup.ps1` — rclone 가드(`Test-Path $RCLONE_EXE` 추가) | test-04-rclone-binary, test-11-rclone-config | **영향 없음** | 테스트는 `rclone.exe` 존재 / `listremotes`만 보고 setup 러너의 분기 로직을 타지 않음. `run-all-tests.ps1`의 forward 로직도 rclone 가드와 무관. |
| `08-register-service.ps1` — NSSM `AppParameters` 이중따옴표 보강(`$nssmArgs = 'web --custom-path "{0}\custom" --work-path "{0}"'`) | test-07-service | **영향 없음** | test-07은 `nssm get ... Application`, `nssm get ... AppDirectory` 두 키만 검증하며 `AppParameters`는 검증하지 않음. `grep AppParameters\|work-path\|custom-path scripts/tests`도 0건. 현재 `$BASE = D:\Workspace\gitea` (공백 없음)이므로 실제 값도 변동 없음. |
| `06-run-setup-wizard.ps1` — `--work-path "$BASE"` 인용 | (없음) | **영향 없음** | 마법사 전용 스크립트에 대응하는 테스트 없음. |

결론: iter2 Tester에서 **Setter 변경에 따른 테스트 보수 작업은 없음**.

## test-03 수정

### 원인
iter1 Log Manager 실측: `& $NSSM_EXE version`은 NSSM 2.24에서 stdout/stderr 모두 비운 채 약 10초 행업 → `-match 'NSSM'` 실패. 인자 없이 실행해도 본 환경에서는 stdout/stderr 길이 0(측정값: `Length: 0`). 즉 usage 메시지 출력 경로도 신뢰 불가.

반면 파일 버전 리소스(`(Get-Item $NSSM_EXE).VersionInfo`)는 안정적으로 아래 값을 돌려줌:
```
ProductName     : NSSM 64-bit
ProductVersion  : 2.24
FileVersion     : 2.24
FileDescription : The non-sucking service manager
```

### 수정 (`scripts\tests\test-03-nssm-binary.ps1:29-31`)

**before**
```powershell
$verOut = & $NSSM_EXE version 2>&1 | Out-String
$runs = $verOut -match 'NSSM'
if (Test-Result -Name "nssm version 실행 가능" -Passed $runs -Detail $verOut.Trim()) { $pass++ } else { $fail++ }
```

**after**
```powershell
# NSSM 2.24는 `nssm version`이 GUI 경로로 빠져 콘솔 출력이 비어 행업되는 이슈가 있어
# 파일 버전 리소스(ProductName/FileDescription/ProductVersion)를 기준으로 검증한다.
$vi = (Get-Item $NSSM_EXE).VersionInfo
$verTag = "$($vi.ProductName) / $($vi.FileDescription) / $($vi.ProductVersion)"
$runs = ("$($vi.ProductName) $($vi.FileDescription)") -match '(?i)NSSM|non-sucking'
if (Test-Result -Name "nssm 버전 리소스 확인" -Passed $runs -Detail $verTag) { $pass++ } else { $fail++ }
```

### 실제 실행 결과

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Workspace\gitea\scripts\tests\test-03-nssm-binary.ps1
```

```
[PASS] nssm.exe 존재                D:\Workspace\gitea\bin\nssm.exe
[PASS] 파일 크기 > 100KB            323.5 KB
[PASS] nssm 버전 리소스 확인        NSSM 64-bit / The non-sucking service manager / 2.24
결과: PASS=3  FAIL=0  TOTAL=3
종료 코드: 0
```

행업 제거(167ms 완료), 매칭 로직이 파일 버전 리소스 기반으로 견고해짐.

추가로 `run-all-tests.ps1 -Filter "01,02,03,04"` 전체도 PASS=4/FAIL=0, 전체 exit code 0으로 회귀 없음 확인 (로그: `run-all-summary_2026-04-19_134226.json`).

## 기타 테스트 수정

없음. iter2 Setter 변경 어느 것도 기존 테스트 로직에 파급 없음을 확인.

## 구문 검증

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

PASS=14 FAIL=0. test-03 파일 UTF-8 BOM 유지 확인 (`\xef\xbb\xbf`).

## Log Manager(iter2)에게 넘길 사항

1. **test-03 행업 해소**: 파일 버전 리소스 기반 검증으로 전환. 재실행 시 `test-03-nssm-binary`는 100~200ms 내 PASS로 종료. 이전 반복의 `run-all-summary_2026-04-19_132653.json`에서 `test-03: ExitCode=1, FAIL`로 남아 있던 항목이 iter2에서는 `ExitCode=0, PASS`로 뒤집힐 것. **이는 테스트 로직 개선에 따른 정상 변경**이며 Setter/Tester 수정의 exit-code 전파와는 무관.
2. **Setter iter2의 3개 변경은 테스트 집합에 아무런 회귀도 일으키지 않음**. test-07은 `AppParameters`를 보지 않으므로 NSSM 따옴표 보강 전/후 동일하게 통과(실제 실행은 관리자/서비스 등록 후에만 가능).
3. **환경 제약 변화 없음**: test-05/07/08/09/10/12/13은 여전히 사전 setup 완료가 필요(관리자, wizard, rclone config 등). iter1 Tester 보고에 나온 우선 실행 순서 그대로 유효.
4. **Filter 자릿수 주의 유지**: `-Filter "1"`은 매치 0건. 반드시 두 자리로 전달(`-Filter "01,02,03,04"`).
5. **`run-all-tests.ps1`의 forward 로직**: `$scriptContent -match "\[\w+(\[\])?\]\s*\$$k\b"` — iter2 Setter의 rclone 가드는 러너 `param()` 블록을 건드리지 않아 forward 판정에 영향 없음. 재검증 불필요.
6. **권장 재실행**: 관리자 세션에서 `-From 5 -To 10` 성공 후 `run-all-tests.ps1` 필터 없이 전체 실행. iter2 전 test-03 FAIL을 포함한 JSON과 iter2 JSON을 비교 시 test-03 PASS 전환이 유일한 차이여야 함.
