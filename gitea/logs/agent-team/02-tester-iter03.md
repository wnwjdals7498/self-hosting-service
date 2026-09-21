# Agent 2 (Tester) 보고서 — Iteration 3
작성 시각: 2026-04-19 13:59

## Setter iter3 영향 매핑

Setter iter3가 수정한 5건 버그에 대한 검증 전략. 모두 `test-14-backup-precheck.ps1`(신규) 하나로 커버.

| # | Setter iter3 수정 | 파일 | 검증 방식 | 결과 |
|---|---|---|---|---|
| 1 | restore.ps1 사이드 백업 안전장치 | `restore.ps1:71-93` | test-14 정적 패턴(`restore-safety-` + `Copy-Item`) | PASS |
| 2 | restore.ps1 try/finally로 `restore-temp` 정리 | `restore.ps1:97-126` | test-14 라인 인덱스(`Expand-Archive` → `finally` → `Remove-Item $tmp`) | PASS (expand=97 finally=121 remove=123) |
| 3 | backup.ps1 SkipUpload rclone 가드 | `backup.ps1:57` | test-14 정적 패턴(`-not $SkipUpload -and -not (Test-Path $RCLONE_EXE)`) | PASS |
| 4 | backup.ps1 에러 힌트 6종 | `backup.ps1:44,49,54,59,121` + `restore.ps1:66` | test-14 정적 패턴 6건(`힌트:.*setup-wizard`, `DB.*초기화`, `create-folders`, `download-rclone\|SkipUpload`, `listremotes\|rclone config`, `gdrive\|로컬 경로`) | PASS (6/6) |
| 5 | backup.ps1 Compress-Archive 2GB 경고 | `backup.ps1:63-72` | test-14 정적 패턴(`2GB` + `rawTotal` + `Compress-Archive`) | PASS |

**추가 실측 검증**: test-14는 Gitea 미설치 환경에서 `backup.ps1 -SkipUpload`를 실제로 실행(부작용 없음 — app.ini 없으므로 즉시 차단). exit=1, 출력에 `APPINI_MISSING` 존재, `힌트: setup/06 setup-wizard...` 라인 실제 출력까지 3건 PASS — 버그 #4의 **힌트가 런타임에 실제로 찍히는지**까지 end-to-end로 확인됨.

**5건 모두 테스트 커버됨.**

## 테스트 수정/추가

### 신규: `D:\Workspace\gitea\scripts\tests\test-14-backup-precheck.ps1`

- 총 12개 어설션 (정적 9 + 실측 3), UTF-8 BOM(`EF BB BF`) 유지.
- 관리자/네트워크 불필요 — `run-all-tests.ps1`의 기본 필터(비-E2E)에도 자연스럽게 포함됨.
- `-Base`, `-SkipLive` 파라미터. `-Base`는 run-all-tests.ps1 forward 로직과 호환(`param()` 블록 정규식 매치).
- 실측 단계는 app.ini 존재 시 자동 스킵(Gitea 정상 설치 환경에서도 무해).

**실행 결과** (`D:\Workspace\gitea\logs\tests\test-14-backup-precheck_2026-04-19_135828.log`):
```
결과: PASS=12  FAIL=0  TOTAL=12
종료 코드: 0
```

### 기존 테스트 수정

없음. 기존 test-13(E2E)은 Setter iter3의 힌트 추가/2GB 경고 추가에도 영향 없음(exit code만 검증). test-13을 Gitea 미설치 환경에서 `-SkipUpload`로 돌려본 결과:
- backup.ps1 단계: exit=1, 출력에 새 힌트 라인(`힌트: setup/06 setup-wizard...`) 정상 출력 확인 — iter3 수정이 test-13 경로를 통해 실제로 찍힘.
- test-13 자체는 "정상 종료 예상" 전제이므로 PASS=0/FAIL=2로 종료(기대대로). **기능 회귀 아님 — 환경 전제 미충족**.

## 회귀 재실행 결과 (01~04)

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Workspace\gitea\scripts\tests\run-all-tests.ps1 -Filter "01,02,03,04"
```

| Test                      | Result | ExitCode | DurationMs |
|---------------------------|--------|----------|------------|
| test-01-folders.ps1       | PASS   | 0        | 307        |
| test-02-gitea-binary.ps1  | PASS   | 0        | 310        |
| test-03-nssm-binary.ps1   | PASS   | 0        | 167        |
| test-04-rclone-binary.ps1 | PASS   | 0        | 374        |

**결과: PASS=4  FAIL=0**. 요약 JSON: `D:\Workspace\gitea\logs\tests\run-all-summary_2026-04-19_135840.json`.

## 구문 검증

`[Parser]::ParseFile` 전수 OK, 15/15:

```
OK  run-all-tests.ps1
OK  test-01-folders.ps1 ~ test-13-backup-execution.ps1
OK  test-14-backup-precheck.ps1   ← 신규
```

test-14 BOM 확인: `EF-BB-BF`.

## Log Manager(iter3)에게 넘길 사항

1. **신규 로그 소스**: `D:\Workspace\gitea\logs\tests\test-14-backup-precheck_*.log`가 새로 축적되기 시작. 기존 `logs\tests\*` 로테이션 정책에 자동 포함되므로 추가 조치 불요.

2. **신규 로그 부산물 없음**: test-14의 실측 단계는 `Start-Process`로 backup.ps1을 별도 프로세스로 호출하며 stdout/stderr을 `New-TemporaryFile`로 리다이렉트 후 즉시 `Remove-Item`. `$env:TEMP`에 잔해 남지 않음. backup.ps1 자체가 작성하는 `logs\backup\backup_*.log`만 남음(기존 iter3 Setter가 이미 만들어놓은 디렉토리).

3. **회귀 재검증 포인트**: `run-all-tests.ps1`을 필터 없이 돌리면 test-14까지 자동 실행됨(E2E인 test-13만 기본 제외). PASS=5 (01,02,03,04,14) / FAIL=0 / 나머지 11,12는 관리자/태스크 선행 필요 상태. test-14는 관리자 불필요하므로 비관리자 세션 헬스체크용으로 권장.

4. **run-all-summary JSON 구조 변화**: 엔트리 수가 13 → 14로 증가. 기존 Log Manager 파이프라인이 "13개 고정"을 가정하고 있다면 유연화 필요. Setter iter3 보고서의 `run-all-summary_*.json` 참조 부분과도 정합.

5. **test-14 자체 동작 특이사항**: app.ini 존재 시(정상 Gitea 설치 환경) 실측 3건은 스킵되어 PASS=9/FAIL=0으로 종료. PASS 카운트 범위: 9(설치 환경) ~ 12(빈 환경). 회귀 알람을 "PASS=12 기대"로 하드코딩하면 안 됨.

6. **Setter iter3의 restore-safety-* 디렉토리 정책**: Setter 보고서 5번 항목과 동일 — `$BASE\restore-safety-yyyyMMdd_HHmmss\`는 **사용자 데이터 복사본**. 로그 로테이션 대상 아님. test-14는 restore.ps1을 실행하지 않으므로 이 디렉토리를 생성하지 않음(검증은 소스 패턴 정적 매칭만).
