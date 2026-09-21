# CLAUDE.md

이 파일은 본 저장소에서 작업하는 Claude Code (claude.ai/code) 에 지침을 제공한다.

> 프로젝트 전용 지침. 범용 원칙은 `~/.claude/CLAUDE.md` 참조.
> 문서화 구조 가이드 원본: `claude_참고.md` (repo root).

---

## 0. Document maintenance policy

**이 CLAUDE.md는 정적 문서가 아니다.** 작업으로 인해 아래 항목이 변경되면 본 문서도 같은 작업 안에서 함께 갱신한다.

### 갱신 프로토콜
1. 작업 중 본 문서와 어긋나는 사실 발견 시 즉시 사용자에게 보고 후 수정 여부 확인.
2. 새 의존성·환경 변수·외부 시스템·tool 모듈·auth provider·transport 모드 도입 시 해당 섹션에 반영안 제시 후 승인.
3. 기존 기술이 제거·치환되면 관련 섹션에서 제거. "참고용으로 남기기" 금지.
4. 모든 변경은 사용자 승인 후에만. 자발적 "개선" 금지.
5. 섹션 번호가 이동하면 본문 상호 참조도 함께 갱신.

### 자주 간과되는 갱신 대상
- `plane_mcp/tools/` 모듈 추가·삭제·이름 변경 → Architecture > Tools 의 모듈 수·카운트 (현재 "19 tool modules / 55+ tools").
- `plane_mcp/__main__.py` transport 인자 추가·삭제 → Entry Point & Transport Modes 설명.
- `plane_mcp/auth/` 파일 추가·인증 방식 변경 → Authentication 섹션 + Architectural constraints.
- 환경 변수 추가·의미 변경 → Key Environment Variables 표.
- `.claude/docs/customization/spec.md` 결정사항이 실제 코드에 반영되는 순간: spec 의 해당 항목 상태 + 본 문서의 Architectural constraints.
- `.claude/code-map/INDEX.md` · `.claude/coding-rules.md` · `.claude/db-info/` (생성되는 시점부터).

### 코드 탐색·수정 진입 순서 (모든 코드 작업 공통)
1. `.claude/coding-rules.md` — 규칙 숙지 (세션 중 1회). *미생성이면 본 문서의 Architectural constraints + Tool pattern 만 참조.*
2. `.claude/code-map/INDEX.md` — 대상 파일·플로우 상세 맵 조회. *미생성이면 `plane_mcp/tools/` 디렉토리 목록 + `.claude/docs/customization/spec.md` §4 컴포넌트 표 로 대체.*
3. 해당 상세 맵 Read — 의존(→)·피의존(←) 양방향으로 영향 범위 예측.
4. 실코드 Read — 맵은 stale 가능. 마지막 검증은 실파일.
5. 수정.
6. 수정 직후 같은 작업 안에서 영향받은 code-map·규칙·CLAUDE.md·spec 을 사용자 승인 후 갱신.

### 참조 문서 현황

| 문서 | 경로 | 상태 |
|---|---|---|
| Fork 커스터마이즈 스펙 (브레인스토밍 확정) | `.claude/docs/customization/spec.md` | ✅ 존재 (design 확정, 구현 진행 중 — `plane-mcp-v2-bootstrap` 프로젝트) |
| Follow-up todo (spec.md 범위 밖 항목) | `.claude/docs/customization/todo.md` | ✅ 존재 (2026-04-24 생성, 6 항목 — `plane-mcp-v2-deploy` 프로젝트로 처리 중) |
| Upstream sync 이력 | `.claude/docs/customization/upstream-sync.md` | ✅ 존재 (2026-04-24 초기 entry, 다음 예정 2026-05-31) |
| Fork 신규 tool 사용자 문서 | `.claude/docs/customization/tools-reference.md` | ✅ 존재 (2026-04-24, 7 tool) |
| 운영 배포 로그 | `.claude/docs/customization/deployment.md` | ✅ 존재 (2026-04-24 Session 1 = `plane-mcp-v2-deploy`) |
| 운영 검증 체크리스트 (Smoke + Regression) | `.claude/docs/customization/test-scenarios.md` | ✅ 존재 (2026-04-25, 8 smoke + 21 regression) |
| 시나리오 설계 spec | `.claude/docs/customization/test-scenarios-design.md` | ✅ 존재 (2026-04-25) |
| 시나리오 구현 plan | `.claude/docs/customization/test-scenarios-plan.md` | ✅ 존재 (2026-04-25, 11 task) |
| 문서화 구조 가이드 (참고용) | `claude_참고.md` | ✅ 존재 |
| 코드 맵 인덱스 | `.claude/code-map/INDEX.md` | ❌ 미정비 |
| 코드 규약 | `.claude/coding-rules.md` | ❌ 미정비 |
| DB 참조 | `.claude/db-info/` | ❌ 해당 없음 (Plane REST API 호출만, 자체 DB 없음) |

---

## 프로젝트 개요

Plane MCP Server — Plane 의 프로젝트 관리 API 를 MCP tool 로 노출하는 Python 기반 Model Context Protocol 서버. FastMCP 위에 공식 `plane-sdk` 를 얹어 구현. 세 가지 transport 모드 지원: stdio (로컬), HTTP (OAuth 또는 header 인증), SSE (legacy).

## 주요 명령어

```bash
# 의존성 설치 (uv 사용)
uv pip install -e ".[dev]"

# 로컬 서버 실행 (stdio 모드)
PLANE_API_KEY=... PLANE_WORKSPACE_SLUG=... python -m plane_mcp stdio

# HTTP 서버 실행
python -m plane_mcp http

# 전체 테스트 실행
pytest

# 단일 테스트 실행
pytest tests/test_integration.py::test_full_integration -v

# 환경변수 파일 로드해서 테스트 실행
export $(cat .env.test.local | xargs) && pytest tests/ -v

# 코드 포맷 (line length 120)
ruff format plane_mcp/

# 린트 (rules E, F, I, UP, B / line length 120)
ruff check plane_mcp/
```

## 아키텍처

### 진입점 및 Transport 모드

`plane_mcp/__main__.py` 는 positional 인자(`stdio`, `http`, `sse`) 를 파싱해 해당 서버를 기동한다:
- **stdio**: `PLANE_API_KEY` + `PLANE_WORKSPACE_SLUG` env var 필요. 로컬 실행.
- **http**: 포트 8211 에서 두 auth 엔드포인트 노출 — OAuth (`/oauth/mcp`) 와 header 기반 PAT (`/http/api-key/mcp`).
- **sse**: Legacy OAuth 전용 SSE transport.

### Server 팩토리 (`server.py`)

세 팩토리 함수(`get_oauth_mcp`, `get_header_mcp`, `get_stdio_mcp`) 가 각각 `FastMCP` 인스턴스를 생성하고 upstream tool 들을 `register_tools()` 로 등록한 뒤 해당 auth provider 를 설정한다. OAuth/HTTP 모드는 토큰 저장에 Redis 사용 (미가용 시 in-memory fallback).

추가로 `get_header_mcp()` 만 `register_tools()` **뒤에** `register_fork_tools()` 를 호출해 fork-only 7 tool (files 3 + admin 4) 을 등록한다 (`## fork-custom` 주석 표식). OAuth/stdio factory 는 upstream 과 동일 tool 세트를 유지해 upstream cherry-pick 시 diff 를 최소화한다 (`spec.md` §7.5).

### 클라이언트 컨텍스트 (`client.py`)

`get_plane_client_context()` 는 `PlaneClientContext(client, workspace_slug)` namedtuple 을 반환한다. credential 은 MCP 요청 컨텍스트(OAuth 토큰 또는 header API key) 또는 환경 변수(stdio 모드) 에서 해결한다. server-to-server 호출에는 `PLANE_INTERNAL_BASE_URL` 를 우선 사용.

### 인증 (`auth/`)

- `PlaneOAuthProvider` — Plane API 로 토큰 검증을 포함하는 완전한 OAuth flow.
- `PlaneHeaderAuthProvider` — `x-api-key` 와 `x-workspace-slug` header 를 사용하는 단순 header 기반 인증.
- `require_instance_admin` — tool 레벨 admin 가드 decorator (`auth/admin_guard.py`, fork-custom). `get_access_token()` 으로 PAT 를 얻어 Plane `/api/v1/users/me/` 에 호출, `is_instance_admin=True` 만 통과. 판정 결과는 `key_value.aio` RedisStore (미가용 시 MemoryStore fallback) 에 `mcp:admin:sha256(token)[:16]` 키로 60s TTL 캐시. sync/async underlying tool 양쪽 지원 (async wrapper 로 변환).

### Tools (`tools/`)

- **Upstream tools** — Plane 도메인별(projects, work_items, cycles, modules 등) 20 개 모듈, 총 55+ 개 tool. 각 모듈은 `register_*_tools(mcp: FastMCP)` 함수를 export 하며 `tools/__init__.py:register_tools()` 에서 호출된다. 3 factory 모두에 등록 (OAuth / header-PAT / stdio).
- **Fork-custom tools** (`tools/files.py`, `tools/admin.py`, fork-custom) — header-PAT factory 에만 등록. `tools/__init__.py:register_fork_tools()` 가 한 곳에서 묶어 호출 (N5 진행 후 wiring 완료).
  - `tools/files.py` — `upload_file` / `download_file` / `list_file_assets` 3 tool. plane-sdk 가 `/api/assets/v2/` 를 미지원하므로 raw `httpx.AsyncClient` 사용 (`## fork-custom` 주석 표식). **엔티티 타입 제약**: `ISSUE_ATTACHMENT` 만 완전 지원. Plane v2 엔드포인트가 workspace/project scoped 이므로 `workspace_slug` + `project_id` + `entity_id`(issue UUID) 가 필수. Upload 은 3-step (Plane POST → multipart presigned POST → PATCH `is_uploaded=True`). Image MIME 만 허용 (`image/jpeg|jpg|png|webp|gif`). `list_file_assets` 는 Plane 이 list-by-entity 미지원 → `NotImplementedError` stub (`.claude/docs/customization/todo.md` #7 참조).
  - `tools/admin.py` — `get_instance_info` / `list_workspace_health` / `get_recent_ipban_events` / `trigger_backup_now` 4 tool. 전부 `@require_instance_admin` 적용. `trigger_backup_now` 는 Plane 포크 `POST /api/instances/admin/backup/` (`AdminBackupView`) 를 호출해 호스트의 `PlaneBackup` Task 를 트리거 — `{task_name, started_at, pid}` 반환.

**Upstream tool 패턴 (sync, plane-sdk):**
```python
def register_*_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def tool_name(param: str, optional_param: str | None = None) -> SomePlaneModel:
        """Docstring with Args and Returns sections."""
        client, workspace_slug = get_plane_client_context()
        return client.endpoint.operation(workspace_slug=workspace_slug, ...)
```

**Fork tool 패턴 (async, raw httpx):**
```python
def register_*_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def tool_name(...) -> SomePydanticResult:
        token = _require_token()  # or @require_instance_admin
        async with httpx.AsyncClient(timeout=30) as client:
            ...
```

Upstream tool 은 `plane-sdk` 의 Pydantic 모델을 반환하고 sync. Fork tool 은 자체 Pydantic 모델 반환 + async (decorator 가 async 이므로 필수). 양쪽 모두 Python 3.10+ union 문법(`str | None`) 사용.

### 호스트 통합 (`host/`, fork-custom)

- `host/paths.py` — 호스트 파일시스템 경로 resolve. 현재 `get_ipban_log_path()` 1개 (`PLANE_MCP_IPBAN_LOG` env).
- `host/ipban_reader.py` — IPBan `stdout.log` tail + parse. 포맷 `YYYY-MM-DD HH:MM:SS.ffff|LEVEL|IPBan|<msg>` (pipe-delimited). Banning / Un-banning / LoginFailure 3 타입 추출. 파일 부재·권한거부 는 예외 없이 `warning` 필드로 전달 (`{events:[], warning:...}`).
- Windows-only (`spec.md` §4.1). Linux fallback 없음.

### 테스트

`tests/test_integration.py` 의 통합 테스트는 `FastMCP.Client` 와 `StreamableHttpTransport` 를 사용한다. 실제 Plane 인스턴스 대상으로 실행 — `.env.test` 로 설정(실값은 `.env.test.local` 에 복사).

Fork 단위 테스트 (`test_admin_guard.py`, `test_host_paths.py`, `test_ipban_reader.py`, `test_files.py`, `test_admin.py`, `test_server_wiring.py`) 는 mock only (실 Plane 호출 0회, `httpx.MockTransport` + `key_value.aio.stores.memory.MemoryStore` 사용). async 테스트는 `pytest-asyncio` 필요 (`dev` extras).

## 주요 환경 변수

| 변수 | 필요 조건 | 용도 |
|---|---|---|
| `PLANE_API_KEY` | stdio | 인증용 API key |
| `PLANE_WORKSPACE_SLUG` | stdio | 대상 workspace |
| `PLANE_BASE_URL` | 전 모드 (default: https://api.plane.so) | Plane API URL |
| `PLANE_INTERNAL_BASE_URL` | http/sse (선택) | server-to-server 호출용 내부 URL |
| `REDIS_HOST` / `REDIS_PORT` | http/sse (선택) | 토큰 저장 + admin_guard 캐시 (미가용 시 in-memory fallback) |
| `REDIS_DB` | http/sse (선택, default 0) | DB 선택. 운영은 plane-api(0/1) 과 분리해 `2` 권장 |
| `REDIS_PASSWORD` | http/sse (선택) | Redis 인증 |
| `PLANE_OAUTH_PROVIDER_*` | http/sse OAuth | OAuth client credential 과 base URL |

Fork 커스터마이즈 env (NSSM `plane-mcp` 서비스에 `AppEnvironmentExtra` 로 주입 — `ops/register-plane-mcp.ps1`, `spec.md` §3.4):

| Variable | 참조 경로 | 용도 |
|---|---|---|
| `PLANE_MCP_HTTP_HOST` / `PLANE_MCP_HTTP_PORT` | `__main__.py` http mode | loopback `127.0.0.1:8211` 고정 (spec §3.3). env 우선, default `0.0.0.0:8211` |
| `PLANE_MCP_IPBAN_LOG` | `plane_mcp/host/paths.py:get_ipban_log_path` | `D:\Workspace\plane-logs\ipban\stdout.log` 경로 — admin tool `get_recent_ipban_events` 가 참조 |

HTTP mode 는 `PLANE_OAUTH_PROVIDER_CLIENT_ID` 가 **있을 때만** OAuth/SSE 엔드포인트를 mount 한다. 없으면 `/http/api-key/mcp` (header-PAT) 만 노출 — spec §2 "팀 공유, Header PAT 주 사용" 배포 형태에서 기본.

---

## Architectural constraints

건드릴 때 사용자 승인 필요한 영역. 본 레포는 `makeplane/plane-mcp-server` **fork** (초기 import HEAD `ca456fe` = upstream `24565ab` 시점) 이며 자체 decision 들이 `.claude/docs/customization/spec.md` 에 고정되어 있다.

- **Fork / upstream 경계**
  - 월 1회 수동 `git fetch upstream` + 선택적 cherry-pick 정책 (`spec.md` §7.5). 정기 rebase 안 함.
  - upstream 과 겹치는 파일(`plane_mcp/__main__.py`, `server.py`, `client.py`, 기본 tool 20 종)을 커스터마이즈할 때는 spec 의 §4 컴포넌트 표에서 해당 파일의 "유형" (upstream 유지 / 수정 / 신규) 확인 후 진행.
  - 우리 신규 블록에는 `## fork-custom` 주석 표식 권장 — upstream refactor 수동 재적용 시 식별용.

- **Transport 계약**
  - `stdio` / `http` / `sse` 세 진입점은 `server.py` 팩토리 3종(`get_oauth_mcp` / `get_header_mcp` / `get_stdio_mcp`) 으로 고정.
  - 네 번째 모드 추가·기존 모드 제거는 구조 변경이므로 spec 업데이트 + 별건 논의 필요.
  - 운영 배포는 **HTTP 단일** + Header PAT 주 사용 (`spec.md` §2, §3.2).

- **Tool 서명 규약**
  - `@mcp.tool()` + `get_plane_client_context()` + `plane-sdk` 호출 + Pydantic 모델 반환 패턴 고정 (Project Overview > Tool pattern 참조).
  - 반환형을 dict/JSON 직파싱으로 바꾸지 않는다. upstream 싱크 리스크.
  - 신규 tool 은 반드시 spec §4.1 표에 등재 (신규 파일은 `tools/files.py`, `tools/admin.py` 등 지정된 슬롯).

- **Auth provider 경계**
  - `PlaneOAuthProvider` · `PlaneHeaderAuthProvider` 2개 고정. 신규 auth provider 는 spec 에 등록된 것만.
  - `require_instance_admin` decorator (`auth/admin_guard.py`) 는 provider 가 아닌 **tool 레벨 추가 인가 체크**. admin 전용 tool 에만 적용. 판정 소스는 Plane `is_instance_admin` 단독 (로컬 whitelist 병행 금지).
  - Header PAT 는 query/body 전달 금지 (`spec.md` §7.1).

- **환경 변수 표 동기화**
  - Key Environment Variables + 추가 env 표에 없는 env var 도입 시 표에 함께 추가. `ops/site.env` ↔ NSSM `AppEnvironmentExtra` ↔ 본 표 3곳이 어긋나면 실 런타임 소스(NSSM) 기준으로 정렬.

- **Non-goals (`spec.md` §12)**
  - 응답 필드 축약 refactor, Plane 포크 upstream rebase, 외부 오프사이트 백업 연동 등은 범위 밖. 제안 전 spec §12 재확인.
