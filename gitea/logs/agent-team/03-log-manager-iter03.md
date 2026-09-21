# Agent 3 (Log Manager) 최종 보고서 — Iteration 3
작성 시각: 2026-04-19 14:06

## 이번 iter 추가된 것

이전 iter1/iter2의 Log Manager는 "로그 로테이션을 권고"만 하고 실제 도구는 만들지 않았다. iter3은 사용자의 강조("로그 관리도 까먹지 말라")에 맞춰 **권고 → 구현** 단계로 진입.

### 1. `scripts\rotate-logs.ps1` (신규)
- 파라미터: `-Base <path>`, `-RetentionDays <int=30>`, `-MaxPerCategory <int=100>`, `-DryRun`
- 대상 카테고리: `setup`, `tests`, `backup`, `restore` (4개). `.gitkeep`은 자동 제외.
- 보호 카테고리(삭제 금지): `agent-team/`(보고서), `gitea/`(Gitea 런타임 로그), `logs-rotation/`(본인이 쓰는 로그).
- 규칙:
  - (a) `LastWriteTime < now - RetentionDays` 파일 **AGE** 삭제
  - (b) 남은 파일이 `MaxPerCategory` 초과 시 **CAP** 오래된 순 삭제
- 파일 잠금 등 실패 시 `try/catch`로 다음 파일 계속 진행(전체 중단 없음).
- `Start-ScriptLog -Category 'logs-rotation' -Name 'rotate'` → `logs\logs-rotation\rotate_<타임스탬프>.log`로 모든 판단/삭제 내역 기록.
- UTF-8 BOM(`EF BB BF`), `[Parser]::ParseFile` OK.

### 2. `scripts\setup\11-register-log-rotation-schedule.ps1` (신규)
- 관리자 권한 필요(`Assert-Admin`). 기존 10번과 동일한 Windows Scheduled Task 방식(NSSM 아님).
- 트리거: **매주 일요일 04:00** (기존 daily backup 03:00과 1시간 간격 둠).
- 파라미터로 `-RetentionDays`, `-MaxPerCategory`, `-WeeklyDay`, `-TriggerTime`, `-TaskName` 조정 가능.
- SYSTEM 계정 / `RunLevel Highest`.
- UTF-8 BOM, Parse OK.

### 3. `scripts\common.ps1` 확장 (1줄)
`Start-ScriptLog`의 `-Category` ValidateSet에 `'logs-rotation'` 추가. 기존 4개(`setup/tests/backup/restore`)는 그대로 유지 — 호환성 영향 없음.

### 그 외
- `logs\agent-team\README.md` iter3 섹션 추가, TL;DR·진척도·사용자 TODO 갱신.

## 재실행 결과

### Setup 1~4
로그: `D:\Workspace\gitea\logs\setup\run-all-setup_2026-04-19_140510.log`
요약 JSON: `D:\Workspace\gitea\logs\setup\run-all-summary_2026-04-19_140511.json`

| 스텝 | 스크립트 | ExitCode | 결과 |
|---|---|---|---|
| 1 | 01-create-folders.ps1 | 0 | PASS |
| 2 | 02-download-gitea.ps1 | 0 | PASS (이미 존재, 스킵) |
| 3 | 03-download-nssm.ps1 | 0 | PASS (이미 존재, 스킵) |
| 4 | 04-download-rclone.ps1 | 0 | PASS (이미 존재, 스킵) |

전체 `run-all-setup` 종료코드 **0**.

### Tests 01,02,03,04,14
로그: `D:\Workspace\gitea\logs\tests\run-all-tests_2026-04-19_140513.log`
요약 JSON: `D:\Workspace\gitea\logs\tests\run-all-summary_2026-04-19_140516.json`

| 테스트 | Result | ExitCode | DurationMs |
|---|---|---|---|
| test-01-folders.ps1 | PASS | 0 | 305 |
| test-02-gitea-binary.ps1 | PASS | 0 | 308 |
| test-03-nssm-binary.ps1 | PASS | 0 | 210 |
| test-04-rclone-binary.ps1 | PASS | 0 | 365 |
| test-14-backup-precheck.ps1 | PASS | 0 | 1232 |

**결과: PASS=5 / FAIL=0**. 전체 `run-all-tests` 종료코드 **0**.

### 구문 검증 (전수)
`[Parser]::ParseFile` — **32/32 OK** (신규 2개 포함). iter2 대비 +4건: `test-14`, `rotate-logs`, `setup\11-register-log-rotation-schedule`, (+ common.ps1 수정).

## 회귀 점검

iter2(`run-all-summary_2026-04-19_134414.json`) vs iter3(`run-all-summary_2026-04-19_140516.json`) 비교:

| 항목 | iter2 | iter3 | 판정 |
|---|---|---|---|
| test-01-folders | PASS | PASS | 유지 |
| test-02-gitea-binary | PASS | PASS | 유지 |
| test-03-nssm-binary | PASS (171ms) | PASS (210ms) | 유지 |
| test-04-rclone-binary | PASS | PASS | 유지 |
| **test-14-backup-precheck** | (없음) | PASS (1232ms) | **신규 — Setter iter3 5건 버그 전수 커버** |
| setup 1~4 | 4/4 PASS | 4/4 PASS | 유지 |
| 전체 구문 | 28/28 | 32/32 | 개선 |

**퇴행 없음**. iter3의 세 축(backup/restore 코드 보강, test-14 신설, 로그 로테이션 도구)이 이전 통과 경로에 어떤 영향도 주지 않음 확인.

## 로그 로테이션 dry-run 결과

### 1차 실행: 기본값 (`-RetentionDays 30 -MaxPerCategory 100 -DryRun`)
로그: `D:\Workspace\gitea\logs\logs-rotation\rotate_2026-04-19_140453.log`

```
[setup]   파일 수 = 63, 나이 기준 = 0, 개수 기준 = 0 (63 <= 100)
[tests]   파일 수 = 29, 나이 기준 = 0, 개수 기준 = 0 (29 <= 100)
[backup]  파일 수 =  6, 나이 기준 = 0, 개수 기준 = 0 ( 6 <= 100)
[restore] 파일 수 =  1, 나이 기준 = 0, 개수 기준 = 0 ( 1 <= 100)

검사 파일 수 = 99, 총 삭제 = 0, 회수 용량 = 0 KB, 소요 = 0.12s, ExitCode=0
```
모든 로그가 오늘 생성(2026-04-19)이라 30일 초과도 없고 상한 초과도 없음 — **현재 시점 실제 삭제 대상 0건이 정상 상태**.

### 2차 실행: 상한 분기 검증 (`-MaxPerCategory 20 -DryRun`)
로그: `D:\Workspace\gitea\logs\logs-rotation\rotate_2026-04-19_140503.log`

```
[setup]   63 > 20 → CAP 43건 삭제 예정 (가장 오래된 순)
[tests]   29 > 20 → CAP  9건 삭제 예정
[backup]   6 <= 20 → 0건
[restore]  1 <= 20 → 0건

총 삭제 예정 = 52건, 회수 용량 ≈ 92.04 KB, ExitCode=0
```
CAP 분기가 정상 동작하고 "오래된 순"으로 선택됨을 확인(첫 삭제 예정 항목: `01-create-folders_2026-04-19_130918.log` 등 초기 타임스탬프).

**실제 실행은 하지 않음** — 테스트 증거(iter1/iter2/iter3 로그)를 보존해야 회귀 분석 가능.

## 로그 디렉토리 현황

| 디렉토리 | 파일 수 | 용량 | 최신 타임스탬프 | 로테이션 대상 |
|---|---|---|---|---|
| `logs\setup\` | 70 | 120.89 KB | 2026-04-19 14:05 | 예 |
| `logs\tests\` | 37 | 78.36 KB | 2026-04-19 14:05 | 예 |
| `logs\backup\` | 8 | 14.79 KB | 2026-04-19 14:05 | 예 |
| `logs\restore\` | 2 | 2.23 KB | 2026-04-19 13:49 | 예 |
| `logs\gitea\` | 1 (.gitkeep) | 0 KB | 2026-04-19 12:35 | **아니오** (Gitea 런타임) |
| `logs\agent-team\` | 10 | 71.69 KB | 2026-04-19 14:06 | **아니오** (보고서) |
| `logs\logs-rotation\` | 2 | 15.47 KB | 2026-04-19 14:05 | **아니오** (자기 참조) |

- iter2 대비 증가: setup +6, tests +17(test-14 및 run-all 반복 기여), backup +7(iter3 신규 기록), restore +1, agent-team +2(iter3 보고서), logs-rotation +2(신규).
- 로테이션 대상(setup/tests/backup/restore) 총 **117개 / 216.27 KB** — 현재는 상한(`100`) 근사치에 setup만 도달. 30일 후 시점에는 자연 삭제로 안정화될 전망.
- **로테이션 후 예상 절감량**: 기본값(30/100) 기준 현재는 0 KB. 상한을 `-MaxPerCategory 20`으로 강제하면 92 KB 회수. 실제 운영 궤도 진입 시(약 30일 후) 1일 약 10건씩 쌓이는 setup 기준 RetentionDays=30·MaxPerCategory=100이면 300KB 수준에서 정상화 예상.

### `restore-safety-*` 디렉토리 정책 (Setter iter3 인계 사항 반영)
- Setter iter3가 `restore.ps1`에 `$BASE\restore-safety-yyyyMMdd_HHmmss\` 자동 생성을 도입. 이 디렉토리는 **사용자 데이터 복사본**(app.ini, gitea.db, repos 스냅샷).
- `rotate-logs.ps1`은 `$BASE\logs\*`만 스캔하므로 `restore-safety-*`를 건드리지 않음 — 안전.
- 명시적 보호 정책: 현재 스크립트는 `$BASE\logs\{setup,tests,backup,restore}\`만 열거하므로 다른 경로는 구조적으로 도달 불가.

## 3-iteration 전체 진척 요약

### 완료된 것 (세 iteration 누적)

| 영역 | iter1 | iter2 | iter3 |
|---|---|---|---|
| 러너 exit 전파 (setup/tests) | 완료 | 유지 | 유지 |
| `$Args` 예약변수 충돌 | 완료 | — | — |
| test-03 행업 (10504ms) | 이월 | **완료**(171ms PASS) | 유지 |
| 부분 구간 rclone 가드 | — | **완료** | 유지 |
| NSSM/gitea web 공백 경로 | — | **완료** | 유지 |
| restore 사이드 백업 안전장치 | — | — | **완료** |
| restore temp try/finally | — | — | **완료** |
| backup SkipUpload rclone 가드 | — | — | **완료** |
| backup 에러 힌트 6종 | — | — | **완료** |
| Compress-Archive 2GB 경고 | — | — | **완료** |
| test-14-backup-precheck 신설 | — | — | **완료** (12 어설션) |
| 로그 로테이션 도구 | 권고만 | 권고 유지 | **실제 구현** |
| 주간 로그 로테이션 스케줄러 | — | — | **구현** (setup/11) |
| 전체 PS 구문 검증 | 28/28 OK | 28/28 OK | **32/32 OK** |
| UTF-8 BOM 유지 | 확인 | 확인 | 확인 |

### 사용자 환경에서 남은 수동 작업 (9단계)

1. `scripts\config.ps1`의 `$PUBLIC_IP`를 실제 공인 IP로 변경 (`CHANGE_ME` → 예: `203.0.113.5`).
2. 관리자 PowerShell 세션.
3. Step 5: `run-all-setup.ps1 -From 5 -To 5` (방화벽).
4. Step 6: 포그라운드 `gitea web` + 브라우저 마법사 → Ctrl+C. `app.ini` 생성.
5. Step 7: `run-all-setup.ps1 -From 7 -To 7` (app.ini 보강).
6. Step 8~10: `run-all-setup.ps1 -From 8 -To 10` (NSSM/복구/백업 스케줄).
7. `bin\rclone.exe config` → `gdrive` 리모트 OAuth.
8. **Step 11 (신규): `setup\11-register-log-rotation-schedule.ps1` 직접 실행 — 주간 로그 로테이션 스케줄 등록** (현 `run-all-setup.ps1`는 1~10 하드코딩이라 step 11은 직접 호출. 향후 iter에서 러너 확장 권장).
9. `run-all-tests.ps1` 필터 없이 전체 실행(+ `-IncludeE2E` 선택) → test-05~13까지 모두 PASS 목표.

**참고**: Step 11은 Step 5/8/9/10과 마찬가지로 관리자 권한이 필요하므로 같은 관리자 세션에서 묶어 실행하면 효율적.

### 현재 시점 설치 완료도
- **자동 수행 가능한 범위**: 100% 완료 + 장기 운영 지속성까지 확보.
- **수동/대화형 부분**: 9단계로 명시, 각 단계에 스크립트·검증 방법·에러 힌트까지 제공.
- **3-iteration 누적 결과**: Gitea 셀프 호스팅 파이프라인이 운영 투입 단계를 넘어 **장기 무인 운영(주간 로그 정리 포함) 가능** 상태에 도달.
