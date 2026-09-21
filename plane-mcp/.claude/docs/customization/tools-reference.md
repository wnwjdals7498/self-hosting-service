# Plane MCP Server — Tools Reference

> Fork-custom 7 tool (`tools/files.py` × 3 + `tools/admin.py` × 4). Header-PAT factory(`/mcp/http/api-key/mcp`) 에만 노출되며 upstream 55+ tool 은 공식 plane-mcp-server README 참조.
>
> - **Generated**: 2026-04-24 (commit `6fae501` — `plane-mcp-v2-deploy` 완료 시점)
> - **선행 프로젝트**: `plane-mcp-v2-bootstrap` (bootstrap 산출물) → `plane-mcp-v2-deploy` (실배포 + 이 문서)
> - 엔트리: `http://<PUBLIC_HOST>/mcp/http/api-key/mcp` (Caddy 80 경유) 또는 `http://127.0.0.1:8211/http/api-key/mcp` (호스트 내부 직접)

---

## 공통 규약

| 항목 | 값 |
|---|---|
| Transport | HTTP MCP, JSON-RPC 2.0 |
| Method | `POST` only |
| Auth header (필수) | `Authorization: Bearer <PAT>` — FastMCP TokenVerifier 규약 |
| Workspace 헤더 (필수) | `x-workspace-slug: <slug>` |
| Content type | `application/json` |
| Accept | `application/json, text/event-stream` — SSE 이벤트로 응답 |
| PAT 발급 | Plane Web UI → 프로필 아이콘 → **Settings** → **Profile** 카테고리의 **API Tokens** (🔑) → "Add API token". Workspace Settings 가 아닌 **Profile Settings** 에 있음 |

### 응답 포맷 (성공)

```
event: message
data: {"jsonrpc":"2.0","id":<N>,"result":{"content":[{"type":"text","text":"<JSON-as-string>"}],"structuredContent":{<파싱된 dict>},"isError":false}}
```

### 응답 포맷 (실패)

```
event: message
data: {"jsonrpc":"2.0","id":<N>,"result":{"content":[{"type":"text","text":"<에러 문구>"}],"isError":true}}
```

### 공통 에러 문구

| 문구 | 뜻 |
|------|----|
| `authentication required` | PAT 헤더 부재/형식 오류. fastmcp middleware 도달 전 — 401 JSON |
| `requires instance admin` | admin tool 에 non-admin PAT 으로 호출. admin_guard 가 Plane `/api/v1/users/me/` 에서 `is_instance_admin` 체크 |
| `authentication failed: token invalid` | PAT 가 Plane 에서 401. 만료/삭제된 토큰 |
| `admin check failed: <status>` | Plane 5xx (또는 4xx non-401). 인가 판정 보류 → 안전 거부 |
| `plane api error: <status> <message>` | 실 tool 호출 중 Plane 이 4xx/5xx 반환 |

---

## Files Tools (Fork)

### `upload_file`

**Scope**: 일반 user (admin 불필요), 대상 issue 에 대한 project-member 권한 보유.
**대상**: 이슈 첨부 파일 (`ISSUE_ATTACHMENT`). 다른 entity_type (`WORKSPACE_LOGO` / `USER_AVATAR` 등) 은 **미지원** — `todo.md` #7.

| Args | Type | 제약 |
|---|---|---|
| `workspace_slug` | string | 워크스페이스 slug |
| `project_id` | UUID | 프로젝트 UUID |
| `entity_id` | UUID | 이슈 UUID |
| `name` | string | 파일명 |
| `mime` | string | `image/jpeg` / `image/jpg` / `image/png` / `image/webp` / `image/gif` — **이미지 전용** |
| `content_base64` | string | base64. decoded size ≤ 5MB |

**Returns** `UploadFileResult`:
```json
{"asset_id": "<uuid>", "name": "<str>", "mime": "<str>", "size": <int>, "warning": "<optional>"}
```
`warning` 은 size > 2MB 시 `"consider Plane UI for files > 2MB"`.

**Errors**: `unsupported mime` / `file too large` / `invalid base64` / `plane api error: ...` / `upload failed: <status>` / `plane patch failed: <status>`.

**Flow**: 3-step — Plane POST → multipart presigned POST → Plane PATCH (`is_uploaded=True`).

**cURL example**:
```bash
curl -sS -X POST http://127.0.0.1/mcp/http/api-key/mcp \
  -H "Authorization: Bearer <PAT>" \
  -H "x-workspace-slug: develop" \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"upload_file","arguments":{"workspace_slug":"develop","project_id":"<pid>","entity_id":"<issue-uuid>","name":"screenshot.png","mime":"image/png","content_base64":"iVBORw0KGgo..."}}}'
```

### `download_file`

**Scope**: 일반 user, 해당 project 접근 권한.

| Args | Type |
|---|---|
| `workspace_slug` | string |
| `project_id` | UUID |
| `asset_id` | UUID |
| `include_content_base64` | bool (default `false`) |

**Returns** `DownloadFileResult`:
```json
{"asset_id": "<uuid>", "presigned_url": "http://.../api/assets/local-download/<key>?sig=...", "content_base64": "<optional>", "warning": "<optional>"}
```
`include_content_base64=true` + size ≤ 5MB 면 `content_base64` 채움; 이상이면 URL-only + warning.

**Errors**: `plane api error: ...` / `download failed: <status>` / `plane api error: missing presigned URL in redirect location`.

**Flow**: Plane GET (project-scoped) → 302 Location 헤더가 presigned URL → 옵션으로 URL 콘텐츠 fetch.

### `list_file_assets`

**상태**: **Not implemented** — Plane `/api/assets/v2/` 가 list-by-entity 를 지원하지 않음. 호출 시:

```
NotImplementedError: Plane fork's /api/assets/v2/ does not expose a list-by-entity endpoint — see .claude/docs/customization/todo.md #7
```

tool surface 는 유지되어 있어 향후 확장 가능.

---

## Admin Tools (Fork, `@require_instance_admin`)

전 admin tool 은 **InstanceAdmin 테이블에 user 가 존재해야 실행**. 판정 캐시 60s.

### `get_instance_info`

**Args**: 없음.
**Returns** `InstanceInfo`:
```json
{"instance_id":"<uuid>","version":"<str>","workspace_count":<int|null>,"user_count":<int|null>,"is_setup_done":<bool|null>,"captured_at":"2026-04-24T..."}
```
Plane `/api/instances/` 응답을 래핑. 포크에서 해당 path 가 없거나 404 면 필드 전부 `null` + `captured_at` 만 채운 degrade 반환.

### `list_workspace_health`

| Args | Type | Default |
|---|---|---|
| `limit` | int (1..50) | 20 |

**Returns** `ListWorkspaceHealthResult`:
```json
{"workspaces":[{"workspace_id":"<uuid>","slug":"develop","name":"Develop","member_count":<int|null>,"project_count":<int|null>,"issue_count":null,"last_activity_at":"<iso|null>"}],"total":<int>}
```
Plane `/api/workspaces/` iterate → workspace 별 members/projects count. 부분 실패(403/404) 는 silent skip + WARN 로그. `issue_count` 는 현 구현에서 항상 `null` (N+1 회피, `todo.md` #4 이후).

### `get_recent_ipban_events`

| Args | Type | Default |
|---|---|---|
| `limit` | int (1..1000) | 50 |

**Returns** `GetRecentIpbanEventsResult`:
```json
{"events":[{"timestamp":"...","level":"WARN","type":"Banning","ip":"1.2.3.4","user_name":"alice","count":6,"raw":"..."}],"warning":null}
```
`host/ipban_reader.tail_events` wrapper. 로그 부재·권한 거부 시 `warning` 필드로 전달 (2xx).

### `trigger_backup_now`

**Args**: 없음.
**Returns**:
```json
{"task_name":"PlaneBackup","started_at":"2026-04-24T...","pid":null}
```
Plane 포크 `POST /api/instances/admin/backup/` → `Start-ScheduledTask -TaskName PlaneBackup` subprocess. `pid` 는 Start-ScheduledTask 가 즉시 반환이라 항상 `null`.

**주의**: plane-mcp NSSM 서비스 계정(`.\plane`) 이 Task Scheduler 의 `PlaneBackup` 실행 권한을 가져야 함. 없으면 `plane api error: 500 Failed to start PlaneBackup task: Start-ScheduledTask : 액세스가 거부되었습니다` 반환 (`todo.md` #8 에서 처리 예정).

---

## Claude Desktop 설정 예시 (부록)

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "plane": {
      "transport": {
        "type": "streamable-http",
        "url": "http://222.234.220.199/mcp/http/api-key/mcp",
        "headers": {
          "Authorization": "Bearer <YOUR_PAT>",
          "x-workspace-slug": "develop"
        }
      }
    }
  }
}
```
