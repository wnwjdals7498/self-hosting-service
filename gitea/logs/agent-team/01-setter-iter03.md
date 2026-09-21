# Agent 1 (Setter) 보고서 — Iteration 3
작성 시각: 2026-04-19 13:52

## 이번 iter의 스코프

직전 iter1/iter2는 `run-all-setup.ps1` + `setup\01~10` + `tests\01~13`에 집중했으므로, iter3은 **아직 리뷰 공백이었던 경로**를 정조준:

- `scripts\backup.ps1`
- `scripts\restore.ps1`
- `scripts\common.ps1` (로깅/Transcript 래퍼)
- `scripts\config.ps1` (조건부 기본값 경계)

실제 실행은 Gitea가 설치되지 않은 상태에서 부작용 없는 방식으로 `backup.ps1 -SkipUpload`와 `restore.ps1 -BackupFile <없는 파일> -SkipDownload -SkipFirewall`을 호출하여 사전 체크·오류 처리 경로의 실측을 확보.

## 실행 시도 결과

### 1) `backup.ps1 -SkipUpload` (Gitea 미설치 상태)
로그: `D:\Workspace\gitea\logs\backup\backup_2026-04-19_134955.log`, 이후 수정 검증: `backup_2026-04-19_135148.log`

- exit=1, `APPINI_MISSING`으로 line 42(수정 전) → line 45(수정 후)에서 깔끔히 차단.
- Start-ScriptLog가 `logs\backup\` 디렉토리를 자동 생성(원래 `.gitkeep`만 있던 디렉토리에 첫 실제 로그 기록 확인).
- 수정 후 재실행 시 힌트 라인이 정상 추가 출력됨:
  `[INFO] 힌트: setup/06 setup-wizard 및 setup/07 generate-appini를 먼저 실행하세요.`
- `Stop-ScriptLog`가 `Stop-Transcript`를 정상 호출하여 로그 파일 닫힘 확인.

### 2) `restore.ps1 -BackupFile <없는 파일> -SkipDownload -SkipFirewall` (비관리자 세션)
로그: `D:\Workspace\gitea\logs\restore\restore_2026-04-19_134958.log`

- exit=1, `Assert-Admin`이 **백업 파일 존재 체크보다 먼저** 걸려 `ADMIN_REQUIRED`로 차단.
- 관찰: UX상 "없는 파일 경로를 줬을 때"의 안내를 보려면 관리자 PS가 먼저 필요함 — 기능적 버그는 아니지만 사용자가 잘못된 경로를 입력해도 관리자 메시지만 봄. 구조를 뒤집지 않는 선에서 실제 파일 존재 체크에 힌트 메시지 강화(아래 수정 1-d).

### 3) 구문/BOM 검증
- 29개 PS 스크립트 전부 `[Parser]::ParseFile` OK.
- `backup.ps1`, `restore.ps1` 수정 후에도 UTF-8 BOM(`EF BB BF`) 유지 확인.

## 발견된 버그 (수정 완료)

### 1. `scripts\restore.ps1:64~94` — 기존 데이터 덮어쓰기 전 안전장치 부재
복원 동작은 `Copy-Item ... -Force`로 기존 `app.ini`/`gitea.db`/`repos\*`를 즉시 덮어씀. 복원 도중 예외가 발생하면 원본도 손상·혼재되어 돌이킬 수 없음. **운영 중인 인스턴스에 잘못된 백업 파일을 복원하면 사용자 데이터가 날아감.**

**after (요약)**: `restore-safety-yyyyMMdd_HHmmss\` 디렉토리로 기존 `app.ini`/`gitea.db`/`repos` 사이드 백업 후 진행. 성공 시에는 사용자 판단하에 수동 삭제하도록 안내(자동 삭제 안 함 — 안전 우선).

```powershell
# restore.ps1 일부 (BackupFile 존재 체크 직후)
$safetyStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safetyRoot  = "$BASE\restore-safety-$safetyStamp"
...
if ($iniExists -or $dbExists -or $reposHasItems) {
    New-Item -ItemType Directory -Path $safetyRoot -Force | Out-Null
    if ($iniExists)     { Copy-Item $APPINI_PATH "$safetyRoot\app.ini" -Force; ... }
    if ($dbExists)      { Copy-Item $existingDb "$safetyRoot\gitea.db" -Force; ... }
    if ($reposHasItems) { Copy-Item "$REPOS_DIR" "$safetyRoot\repos" -Recurse -Force; ... }
    Write-Warn "복원 실패 시 위 경로에서 수동 복구 가능. ..."
}
```

### 2. `scripts\restore.ps1:68~94` — Expand-Archive 중간 예외 시 `restore-temp\` 정리 보장 없음
원본은 정상 경로 끝(line 94)에서만 `Remove-Item $tmp`. Expand-Archive/Copy-Item 도중 예외가 발생하면 `restore-temp\` 잔존. 다음 실행이 line 68에서 정리해주긴 하지만, 같은 실행의 safety backup 파일 근처에 temp 잔해가 남는 것은 운영 관점 이상함.

**after**: Expand~Copy 전체 블록을 `try { ... } finally { if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force } }`로 감싸 예외 경로에서도 tmp 정리 보장.

### 3. `scripts\backup.ps1:42~45` — 사전 체크에서 `$RCLONE_EXE` 유무를 `-SkipUpload`와 무관하게 강제
`-SkipUpload`로 호출해도 rclone.exe가 없으면 실패. 의도와 어긋남 — `-SkipUpload`는 업로드를 건너뛰는 옵션인데, 업로드 도구 없다고 압축 단계도 못 하게 막는 건 과도.

**before**
```powershell
if (-not (Test-Path $RCLONE_EXE))  { Write-Fail "rclone.exe 없음: $RCLONE_EXE"; throw "RCLONE_EXE_MISSING" }
```

**after**
```powershell
if (-not $SkipUpload -and -not (Test-Path $RCLONE_EXE)) {
    Write-Fail "rclone.exe 없음: $RCLONE_EXE"
    Write-Info "힌트: setup/04-download-rclone 실행 또는 -SkipUpload로 로컬 압축만 수행."
    throw "RCLONE_EXE_MISSING"
}
```

### 4. `scripts\backup.ps1` — 사전 체크/rclone 실패/restore BackupFile 미존재 메시지에 UX 힌트 추가
실측(1-a)에서 확인한 바와 같이 기존 메시지는 "무엇이 없는지"만 알려줌. 사용자가 "그래서 뭘 해야 하지"를 판단하려면 setup 스텝 순서 지식이 필요. 각 `Write-Fail` 직후에 한 줄짜리 `Write-Info "힌트: ..."`를 추가(실제 행동 지침 제공):

- APPINI_MISSING → "setup/06 setup-wizard 및 setup/07 generate-appini를 먼저 실행하세요."
- DB_MISSING → "Gitea 서비스가 최소 1회 기동되어 DB가 초기화되었는지 확인하세요."
- REPOS_DIR_MISSING → "setup/01-create-folders를 먼저 실행하세요."
- RCLONE_EXE_MISSING → "setup/04-download-rclone 실행 또는 -SkipUpload로 로컬 압축만 수행."
- RCLONE_UPLOAD_FAILED → "rclone listremotes로 gdrive: 설정 확인. 필요 시 rclone config."
- restore BACKUP_FILE_MISSING → "로컬 경로를 전달했는지, 또는 'gdrive'를 지정했는지 확인하세요."

이전 iter들과 동일한 스타일(`Write-Info`/`Write-Warn` 중심)을 유지하며 최소 침습.

### 5. `scripts\backup.ps1` — Compress-Archive 2GB 한계에 대한 사전 경고
PowerShell 5.1의 `Compress-Archive`는 **대상 또는 결과 파일이 2GB를 넘으면 조용히 손상되거나 예외 발생**(MS 공식 문서/IssueTracker). 저장소 성장 시 무언의 실패 위험.

**after**: 압축 직전 `$repoBytes + $dbBytes`를 합산하여 2GB 이상이면 경고 두 줄 출력(압축은 계속 시도 — 실제 제한은 결과물 크기에 의존하므로 강제 차단까지는 과도). 대체 경로로 7-Zip / `[System.IO.Compression.ZipFile]`를 안내.

```powershell
$rawTotal = $repoBytes + $dbBytes
if ($rawTotal -ge 2GB) {
    Write-Warn ("원시 대상 크기 {0:N2} GB — PowerShell 5.1 Compress-Archive의 2GB 제한을 초과할 수 있습니다." -f ($rawTotal / 1GB))
    Write-Warn "압축이 실패하면 수동으로 7-Zip 또는 .NET ZipFile(큰 파일 지원)을 사용하는 대체 경로를 고려하세요."
}
```

**총 수정 버그 수: 5건** (restore.ps1 2건, backup.ps1 3건). 수정 후 29개 스크립트 구문 검증 전부 OK, UTF-8 BOM 유지.

## 개선 제안 (수정 보류)

### A. `common.ps1 Start-ScriptLog`의 타임스탬프 충돌
`yyyy-MM-dd_HHmmss`(초 단위)라 같은 초에 두 스크립트가 시작하면 파일명이 겹칠 수 있음. 그러나 `Start-Transcript -Path $logFile -Append -Force`를 사용 중이라 실제로는 append되어 **데이터 손실은 없음**. 혼란은 있지만 동시 실행 시나리오(사용자 + 스케줄러 동시 트리거)는 매우 드뭄. 최소 침습 원칙으로 **보류**. 만약 구현하려면 `.fff` 추가 1줄 변경으로 가능하지만 기존 로그 파일명 규칙을 건드림.

### B. `common.ps1 _Log`가 `Write-Host`를 쓰기 때문에 출력 리다이렉션 불가
`Write-Host`는 `>` 리다이렉션 대상이 아님(InformationStream). 다만 현재 설계는 `Start-Transcript` 기반이라 **의도적**. 에러/경고를 error stream으로 흘려보내도록 `Write-Error`/`Write-Warning`으로 바꾸면 transcript와의 상호작용(중복 출력, 컬러 손실)이 복잡해짐. **설계 의도 유지 보류**.

### C. `config.ps1`에 `$BASE=$null` 뒤 dot-source 시 동작
`[string]::IsNullOrEmpty($BASE)`는 `$null` 입력에서 `$true` 반환 → 기본값 `"D:\Workspace\gitea"`로 복원. **동작상 버그 없음**. 다만 이 "조건부 재할당" 패턴 전체가 한 번도 문서화된 적 없음. 파일 상단 주석은 있지만 `-BASE` 대신 `$BASE` 전역을 세팅해야 한다는 암묵 약속을 별도 설명. 문서 개선 필요성 있으나 **코드 수정 범위 아님**.

### D. `backup.ps1`의 `Compress-Archive` 자체를 `[System.IO.Compression.ZipFile]`로 전환
PowerShell 5.1의 2GB 이슈를 근본 해결하려면 `ZipFile::CreateFromDirectory` 기반으로 재작성 필요. 그런데 현재 구조는 복수 소스(`$APPINI_PATH, $db, $REPOS_DIR`)를 한 zip에 넣는 형태라 `CreateFromDirectory`만으로는 부족하고 스테이징 디렉토리 복사가 추가로 필요 → 침습 큼. iter3은 **경고만 추가**로 그치고, 실제 저장소가 2GB에 근접할 때 추후 iter에서 본격 대응 권장.

### E. `restore.ps1`의 단계 번호 `[7/8]`·`[8/8]`
사용자 가독성 개선 여지는 있으나 기능에 영향 없음. **보류**.

### F. `backup.ps1`의 `Start-Sleep -Seconds 3` (line 60)
SQLite WAL 플러시 대기 목적의 고정 sleep. 실제로 `$svc`가 Stopped 상태가 될 때까지 폴링하는 게 더 견고하나, SQLite의 in-flight fsync는 `Stop-Service -Force` 직후 OS 레벨에서 이미 커밋됨 + 3초면 과도하게 안전. **실용상 문제 없음, 보류**.

## Tester(iter3)에게 넘길 사항

1. **restore.ps1 안전장치 회귀 확인**
   - 기존에 `$DATA_DIR\gitea.db`나 `$REPOS_DIR\*`가 존재하는 상태(mock)에서 `restore.ps1 -BackupFile ...`을 돌렸을 때 `restore-safety-yyyyMMdd_HHmmss\` 디렉토리가 생성되고 원본이 복사되는지 검증.
   - 특히 `$REPOS_DIR`이 **비어 있는 상태**에서는 safety 디렉토리에 `repos`를 만들지 않는지(`$reposHasItems` 분기) — 불필요 I/O 제거 확인.
   - Expand-Archive 실패 재현(손상된 zip 파일)에서 `restore-temp`가 삭제되는지 확인.

2. **backup.ps1 `-SkipUpload` 경로에서 rclone.exe 없이도 진행되는지**
   - Setter iter2의 rclone 가드와 동일한 철학을 backup.ps1에 적용. `-SkipUpload` 시 `Test-Path $RCLONE_EXE` 체크 스킵 확인. test-13-backup-execution에서 `-SkipUpload` 시나리오가 이미 있다면 영향 없음(rclone은 보통 이미 설치된 상태이므로 회귀 위험 낮음).

3. **2GB 경고 로직**
   - `$repoBytes + $dbBytes < 2GB` 케이스는 경고 없이 통과 — 기존 test-13 흐름 영향 없음.
   - 2GB 이상은 `Write-Warn` 2줄 추가 출력. 기존 테스트가 "정확한 라인 수"를 검사한다면 갱신 필요(검색한 결과 test-13은 exit code 중심이라 영향 없음).

4. **힌트 메시지 추가로 인한 로그 라인 수 증가**
   - test-13-backup-execution이 `backup.ps1` 출력의 특정 라인을 파싱한다면 힌트 `Write-Info` 라인 추가로 오프셋이 변경될 수 있음. 확인 결과 test-13은 exit code와 원격 `rclone ls` 결과만 검증 → 영향 없음.

## Log Manager(iter3)에게 넘길 사항 — 로그 로테이션 필수 구현

1. **이번 iter로 `logs\backup\`·`logs\restore\`에도 실제 로그가 처음으로 기록됨**
   - `logs\backup\backup_2026-04-19_134955.log`, `logs\backup\backup_2026-04-19_135148.log`
   - `logs\restore\restore_2026-04-19_134958.log`
   - 지금까진 `.gitkeep`만 있던 두 디렉토리가 append-only 누적 대상으로 합류. 로테이션 정책 대상에 포함시켜야 함.

2. **iter3 변경 파일 3개** (구문 OK + BOM 유지): `scripts\backup.ps1`, `scripts\restore.ps1`, (`common.ps1`·`config.ps1`은 수정하지 않음 — 버그 없음 확인)

3. **회귀 검증 포인트**: setup 1~4 재실행, tests 01~04 재실행, `run-all-summary_*.json` 생성 확인. backup.ps1 사전 체크 경로는 Gitea 미설치 환경에서 이미 검증됨(exit=1 깔끔).

4. **iter2 Log Manager가 남긴 "로그 관리 권고"가 iter3에도 그대로 유효** — 특히 `prune-logs.ps1` 도입 제안은 이제 `backup\`·`restore\` 디렉토리까지 커버해야 함:
   ```powershell
   Get-ChildItem D:\Workspace\gitea\logs\setup, D:\Workspace\gitea\logs\tests, D:\Workspace\gitea\logs\backup, D:\Workspace\gitea\logs\restore -File | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force
   ```

5. **restore-safety-* 디렉토리 주의**: 이제 `$BASE\restore-safety-yyyyMMdd_HHmmss\`가 자동 생성됨. **이건 로그가 아니라 사용자 데이터 복사본**이라 로그 로테이션 대상에 포함시키면 안 됨. Log Manager가 `logs\*`만 건드리는 정책을 유지하면 문제없음 — 명시적으로 기록.

6. **iter1/iter2에서 거론된 환경 제약은 변함없이 유효** (PUBLIC_IP CHANGE_ME, Step 5/8/9/10 관리자 권한, Step 6 대화형 OAuth, rclone config 대화형).
