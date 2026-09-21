# Upstream Sync Log

> 월 1회 `git fetch upstream` 결과와 수행한 cherry-pick 을 누적 기록한다.
> 정책: `spec.md` §7.5 (월 1회 수동, bug-fix / 새 tool / 우리 신규 파일 비충돌 만 pick, 구조 refactor 는 수동 재적용).
> upstream: <https://github.com/makeplane/plane-mcp-server> / local baseline: `ca456fe` = upstream `24565ab`.

---

## 2026-04-24 — 초기 fetch

| Upstream HEAD | Local base | Action | Summary |
|---------------|-----------|--------|---------|
| `b4e949d` (bump version, 2026-04-22) | `ca456fe` (fork baseline) | review-only | upstream 의 baseline `24565ab` 이후 신규 커밋 **2개** 모두 version bump. fork 의 `pyproject.toml` 과 `plane-sdk` 핀을 지금 따라갈 이유 없음 — 우리 bootstrap 세션에서 `fastmcp==2.14.4` / `plane-sdk==0.2.8` 로 검증 완료. 다음 sync 주기(2026-05 말) 에 누적분과 함께 재검토. |

### 신규 커밋 목록 (master..upstream/main)

| Hash | Subject | 판정 |
|------|---------|------|
| `b4e949d` | bump version | skip (본 fork 의 버전 체계 독립) |
| `9b4b4de` | bump sdk version | skip (plane-sdk 핀은 우리 bootstrap 완료 기준) |

### 참고 — upstream 에 존재하는 다른 branch

`git ls-remote --heads upstream` 에 49 개 ref. `main` 이외 branch 들은 feature/chore 작업 분기 (예: `chore-add_filters_wi_search`, `chore-bump_version`) — 본 정책은 **오직 `main`** 기준.

---

## 다음 예정

- **2026-05-31 (월 1회)**: `git fetch upstream` + `master..upstream/main` 비교 + 위 포맷으로 entry 추가
