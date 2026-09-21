# Agent Team 파이프라인 결과

## Iteration 1 (2026-04-19 13:17 ~ 13:30)
1. **[Setter](01-setter.md)** — `run-all-setup.ps1`의 `$Args` 예약변수 충돌 제거 + 자식 스크립트 9개의 `$exitCode=1; return` 패턴을 `throw "<TOKEN>"` 경로로 일괄 교체.
2. **[Tester](02-tester.md)** — 동일 패턴을 테스트 스크립트 10개에서 `throw`로 통일, `run-all-tests.ps1`·각 테스트의 catch 블록에 `Write-TestSummary` 추가.
3. **[Log Manager](03-log-manager.md)** — Step 1~4 / test-01~04 재실행으로 exit 코드 전파 검증. test-03-nssm의 `nssm version` 10초 행업 1건 발견 → iter2로 이월.

## Iteration 2 (2026-04-19 13:38 ~ 13:46)
1. **[Setter iter2](01-setter-iter02.md)** — `run-all-setup.ps1`에 rclone 미설치 가드 추가, `08-register-service.ps1` NSSM AppParameters 이중따옴표 선조립, `06-run-setup-wizard.ps1` `--work-path` 인용 보강.
2. **[Tester iter2](02-tester-iter02.md)** — iter1 이월된 test-03 행업을 `VersionInfo` 기반 판정으로 교체(10504ms FAIL → 171ms PASS). Setter iter2 변경의 테스트 회귀 없음 확인.
3. **[Log Manager iter2](03-log-manager-iter02.md)** — Setup 1~4 / 5~10 / Tests 01~04 재실행, iter1 JSON과 비교해 회귀 없음·test-03 개선만 존재함을 검증. 로그 디렉토리 현황·정리 권고 정리.

## Iteration 3 (2026-04-19 13:52 ~ 14:06)
1. **[Setter iter3](01-setter-iter03.md)** — iter1/2가 다루지 않았던 `backup.ps1`·`restore.ps1`·`common.ps1`·`config.ps1`을 정밀 리뷰. **5건 버그 수정**: restore 사이드 백업 안전장치, restore temp try/finally 정리, backup `-SkipUpload`의 rclone 가드, 6종 에러 메시지 UX 힌트, Compress-Archive 2GB 사전 경고.
2. **[Tester iter3](02-tester-iter03.md)** — 신규 `test-14-backup-precheck.ps1`(12 어설션) 로 Setter iter3의 5건 수정을 정적 패턴+실측 동시 검증. PASS=12/FAIL=0. 기존 테스트 회귀 없음.
3. **[Log Manager iter3](03-log-manager-iter03.md)** — **권고 단계를 넘어 실제 로테이션 도구 구현**. `scripts\rotate-logs.ps1` 신규(`-RetentionDays`/`-MaxPerCategory`/`-DryRun`), `setup\11-register-log-rotation-schedule.ps1` 신규(매주 일요일 04:00), `common.ps1`에 `logs-rotation` 카테고리 추가. Setup 1~4 / Tests 01,02,03,04,14 재실행 모두 PASS, 회귀 없음.

## 전체 진척도

### 자동화 완료
- setup Step 1~4 (폴더/바이너리 3종 다운로드)
- `run-all-setup.ps1`·`run-all-tests.ps1` exit code 전파 신뢰
- 부분 구간 실행(`-From 5 -To 10`)의 rclone 가드 안전성
- NSSM/gitea web 공백 경로 내성
- test-01~04 안정 PASS (행업 제거)
- backup/restore 안전장치 (사이드 백업, try/finally temp 정리, SkipUpload 가드, 2GB 경고, UX 힌트 6종)
- test-14-backup-precheck 신규 (비관리자·비네트워크 환경 정적/실측 겸용)
- **로그 로테이션 도구 구현 (`rotate-logs.ps1` + 주간 스케줄러 `setup/11`)**
- 전체 PS 스크립트 32개 구문 검증 OK · 전부 UTF-8 BOM 유지

### 사용자 환경에서 할 일
1. `scripts\config.ps1`의 `$PUBLIC_IP` 실제 IP로 변경 (`CHANGE_ME` 상태).
2. 관리자 PowerShell로 `run-all-setup.ps1 -From 5 -To 5` (방화벽).
3. 포그라운드 `gitea web` + 브라우저 마법사(Step 6) → Ctrl+C.
4. `run-all-setup.ps1 -From 7 -To 10` (app.ini/서비스/복구/스케줄).
5. `bin\rclone.exe config`로 `gdrive` 리모트 OAuth 설정.
6. `run-all-tests.ps1` 필터 없이 전체 실행(+`-IncludeE2E` 선택).
7. **관리자 PowerShell로 `setup\11-register-log-rotation-schedule.ps1` 직접 실행** — 매주 일요일 04:00 로그 로테이션 스케줄 등록 (현 `run-all-setup.ps1`는 1~10 하드코딩이라 step 11은 직접 호출).

## TL;DR
세 iteration으로 Gitea 셀프 호스팅 파이프라인을 **자동화 완성 + 장기 운영 지속성**까지 끌어올렸다. **iter1**은 exit 코드 전파 결함을 setup 12파일·테스트 10파일 일괄 수리, **iter2**는 test-03 10초 행업·rclone `CommandNotFound`·공백 경로 NSSM/gitea web 인자 잘림을 해소, **iter3**은 이전 2회가 다루지 않았던 `backup.ps1`·`restore.ps1`에서 5건 버그(복원 안전장치·try/finally·SkipUpload 가드·2GB 경고·UX 힌트)를 수정하고 12개 어설션의 `test-14`를 신규 투입했으며, **이전 iter들이 "권고"로만 남겼던 로그 로테이션을 실제 구현**(`rotate-logs.ps1` + 주간 스케줄러)했다. 회귀 검증에서 어떤 iteration도 이전 결과를 퇴행시키지 않았고 각 iter의 수정이 독립적으로 검증됨. 스크립트 32개 전부 구문 OK·UTF-8 BOM 유지. 자동화 범위 내 모든 스텝이 녹색이고 남은 사용자 수동 작업(7가지)도 명시적 순서로 정리됨 — 파이프라인은 이제 운영 투입 + 장기 유지 가능 상태다.
