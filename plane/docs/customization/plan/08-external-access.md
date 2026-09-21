# Phase 7 — 외부 접근 (Caddy 네이티브 + 공인 IP)

> **네비게이션**: [← Phase 6](07-systemd.md) · [목차](../plan.md) · [다음: Phase 8 →](09-verification.md)
>
> 연관: [../../apps/proxy/Caddyfile.ce](../../../apps/proxy/Caddyfile.ce) (원본, docker 기반) · [../security-todo.md §2·§3](../security-todo.md)

**전제 (Phase 0 Q1-보강)**:
- 도메인 없음. 공인 IP **`222.234.220.199`** 로 외부 접근.
- `site.env` 의 `PUBLIC_HOST` / `PUBLIC_SCHEME` / `PUBLIC_PORT` 가 단일 소스.
- HTTPS 는 도메인 확보 후 Cloudflare Tunnel 또는 Caddy 자동 ACME 로 전환 (본 Phase §8 미래 경로).

**목표**:
1. Caddy 네이티브를 Windows Service 로 설치.
2. path prefix 라우팅으로 SPA 3개 + API 프록시 + Live WebSocket 을 단일 80 포트에서 서빙.
3. 방화벽 80 인바운드 허용.
4. 공인 IP 직접 접근 성공 확인.

**이 Phase 에서 생성하는 파일**:
- `D:\Workspace\plane-app\ops\Caddyfile`
- Windows 서비스 `caddy` (NSSM 또는 내장 서비스 설치)
- 방화벽 규칙 `Allow Inbound tcp/80 (Plane)`

---

## 1. Caddy 네이티브 설치

```powershell
# winget (권장)
winget install --id CaddyServer.Caddy -e

# 또는 수동 다운로드
# https://caddyserver.com/download → caddy_windows_amd64.exe
# C:\Program Files\Caddy\caddy.exe 에 배치

caddy version       # v2.8+ 확인
```

---

## 2. `Caddyfile` 작성

`D:\Workspace\plane-app\ops\Caddyfile`:

```caddyfile
# Plane 네이티브 Caddy 설정 — 공인 IP 기반 HTTP
# 도메인 + HTTPS 전환은 §8 참조.

{
	# 전역 로그 위치
	log {
		output file "D:/Workspace/plane-logs/caddy/caddy.log"
		format json
	}
}

# :80 = 공인 IP 222.234.220.199 에 직접 응답
:80 {
	request_body {
		max_size 50mb    # FILE_SIZE_LIMIT 보다 여유
	}

	# API + auth + Django static + 업로드 (LocalFSStorage endpoint)
	reverse_proxy /api/*      127.0.0.1:8000
	reverse_proxy /auth/*     127.0.0.1:8000
	reverse_proxy /static/*   127.0.0.1:8000

	# Live Yjs (WebSocket upgrade)
	reverse_proxy /live/* 127.0.0.1:3100 {
		header_up Host {host}
		header_up X-Real-IP {remote}
		header_up X-Forwarded-For {remote}
	}

	# Admin SPA  (prefix /god-mode/)
	redir /god-mode /god-mode/ permanent
	handle_path /god-mode/* {
		root * "D:/Workspace/plane-app/apps/admin/build/client"
		try_files {path} /index.html
		file_server
	}

	# Space SPA  (prefix /spaces/)
	redir /spaces /spaces/ permanent
	handle_path /spaces/* {
		root * "D:/Workspace/plane-app/apps/space/build/client"
		try_files {path} /index.html
		file_server
	}

	# Web SPA  (기본 fallback)
	handle {
		root * "D:/Workspace/plane-app/apps/web/build/client"
		try_files {path} /index.html
		file_server
	}

	# 접근 로그
	log {
		output file "D:/Workspace/plane-logs/caddy/access.log" {
			roll_size 10mb
			roll_keep 10
			roll_keep_for 2160h   # 90d
		}
		format json
	}
}
```

### 2.1 경로 정합성 재확인

- Phase 5 빌드 산출물 경로와 일치: `apps/{web,admin,space}/build/client/`
- Phase 6 백엔드 리스닝: `127.0.0.1:8000`, `127.0.0.1:3100`
- Phase 4 Storage `LocalFSStorage._endpoint` 이 반환하는 `WEB_URL` 은 `http://222.234.220.199` → `/api/assets/local-{upload,download}/` 경로가 Caddy `/api/*` 를 통과

### 2.2 정적 파일 직접 서빙은?

Phase 4 `LocalFSStorage` 는 **서명 검증 필수** 이므로 `/uploads/*` 를 Caddy 가 직접 서빙하지 않는다. 모든 업로드 접근이 `/api/assets/local-download/...` 를 경유하도록 유지 — **권한 우회 방지**. [../security-todo.md §4](../security-todo.md) 참고.

---

## 3. Caddy 설정 검증

```powershell
cd D:\Workspace\plane-app\ops
caddy validate --config .\Caddyfile
# Valid configuration
```

잠시 전경(foreground) 기동하여 실측:

```powershell
caddy run --config .\Caddyfile
```

다른 창에서:

```powershell
# 로컬 루프백
curl.exe -sI http://127.0.0.1/
curl.exe -sI http://127.0.0.1/god-mode/
curl.exe -sI http://127.0.0.1/api/users/me/
```

Ctrl+C 로 종료.

---

## 4. Caddy Windows Service 등록

Caddy 2.x 는 자체 서비스 인스톨 명령이 없으므로 NSSM 사용.

```powershell
$svc = "caddy"
$caddy = (Get-Command caddy).Source
$cfg = "D:\Workspace\plane-app\ops\Caddyfile"
$logs = "D:\Workspace\plane-logs\caddy"
New-Item -ItemType Directory -Path $logs -Force | Out-Null

nssm install $svc $caddy "run --config `"$cfg`" --adapter caddyfile"
nssm set $svc AppDirectory "D:\Workspace\plane-app\ops"

# plane 계정으로 실행 (Phase 6 Set-NssmCommon 재사용)
nssm set $svc ObjectName ".\plane" "<plane-password>"
nssm set $svc Start SERVICE_AUTO_START
nssm set $svc AppExit Default Restart
nssm set $svc AppRestartDelay 5000
nssm set $svc AppStdout  "$logs\stdout.log"
nssm set $svc AppStderr  "$logs\stderr.log"
nssm set $svc AppStdoutCreationDisposition 4
nssm set $svc AppStderrCreationDisposition 4
nssm set $svc AppRotateFiles 1
nssm set $svc AppRotateOnline 1
nssm set $svc AppRotateSeconds 86400
nssm set $svc AppRotateBytes 10485760

# 의존성: Plane API 가 먼저 기동
nssm set $svc DependOnService "plane-api"

nssm start $svc
Get-Service caddy    # Running
```

---

## 5. 방화벽 인바운드 허용

Phase 0 §8.1 에서 80 포트를 차단하지 않았지만 혹시 모를 차단 규칙 대비 명시적 허용:

```powershell
New-NetFirewallRule -DisplayName "Allow Inbound tcp/80 (Plane Caddy)" `
  -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow -Profile Any
```

아웃바운드는 기본 허용.

### 5.1 공유기 포트 포워딩 — **해당 없음 (현 환경)**

현 환경은 공유기 없이 **공인 IP `222.234.220.199` 를 호스트가 직접 물림**. 포트 포워딩 불필요. Windows 방화벽 인바운드 규칙만으로 80 이 외부에 직접 노출된다.

```powershell
# 호스트 IP 확인 (참고)
Get-NetIPAddress -AddressFamily IPv4 | Where-Object InterfaceAlias -like "Ethernet*" | Select IPAddress
# → 222.234.220.199 로 직접 표기되면 NAT 없이 공인 IP 직결
```

> NAT 방패가 없어 Windows 방화벽이 **유일한 경계**. Phase 0 P0-18 의 내부 포트 6종 Block + §5 의 80 Allow 외에 여는 포트가 없도록 정기 감사. IPBan 등 brute force 방어는 [../security-todo.md §2](../security-todo.md).

---

## 6. 외부 접근 실측

```powershell
# 호스트 자체에서
curl.exe -sI http://222.234.220.199/
# HTTP/1.1 200 OK

# 다른 네트워크(휴대폰 LTE 등) 에서
# 브라우저로 http://222.234.220.199/ 접속
# → Plane 로그인 화면 렌더
# → /god-mode/ 접근 → admin SPA
# → /spaces/ → space SPA
# → /live/ WebSocket 업그레이드 (개발자 도구 → Network → WS 프레임 흐름 확인)
```

---

## 6a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P7-1 | Caddy 네이티브 설치 (winget) | — | §1 | `caddy.exe` |
| P7-2 | `ops/Caddyfile` 작성 (path prefix 라우팅 + SPA fallback) | P5-4 | §2 | Caddyfile |
| P7-3 | `caddy validate` | P7-2 | §3 | Valid configuration |
| P7-4 | `caddy run` 수동 기동 smoke (4 경로 응답) | P7-3, P6-2 | §3 | 루프백 응답 |
| P7-5 | NSSM `caddy` Windows Service 등록 | P7-3 | §4 | Running |
| P7-6 | 방화벽 80 인바운드 허용 | P7-5 | §5 | New-NetFirewallRule |
| P7-7 | 공유기 포트 포워딩 — **해당 없음 (공인 IP 직접 물림)** | P7-6 | §5.1 | 스킵 |
| P7-8 | 외부 네트워크에서 `http://222.234.220.199/` 접근 실측 | P7-7 | §6 | 로그인 화면 렌더 |

---

## 6b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P7-1 | `caddy version` | v2.8+ |
| P7-3 | `caddy validate --config ops\Caddyfile` | `Valid configuration` |
| P7-4 | `curl -sI http://127.0.0.1/` · `/god-mode/` · `/spaces/` · `/api/users/me/` | 200/301/401 (500 아님) |
| P7-5 | `Get-Service caddy` | Running · Automatic |
| P7-6 | `Get-NetFirewallRule -DisplayName "Allow Inbound tcp/80 (Plane Caddy)"` | 1건 Action=Allow |
| P7-8 | 외부 브라우저 `http://222.234.220.199/` | Plane 로그인 화면 |
| P7-8 | DevTools → Network → WS `/live/` 프레임 | 양방향 송수신 |

---

## 6c. 요구사항 검증 체크리스트

- [ ] **단일 도메인/IP 라우팅** — Caddy 가 80 포트 단일 수신, path prefix 로 web/admin/space/live/api 분기
- [ ] **SPA fallback** — `try_files {path} /index.html` 로 client-side routing 복구
- [ ] **WebSocket proxy** — `/live/*` 업그레이드 헤더 전달
- [ ] **정적 업로드 직접 서빙 차단** — `/uploads/*` Caddy 직접 서빙 금지 (서명 경로 `/api/assets/local-download/` 만)
- [ ] **로그 분리** — Caddy access/error 로그가 `plane-logs/caddy/` 에 저장
- [ ] **외부 접근 실측** — 공인 IP 로 외부 네트워크에서 로그인 화면 렌더 성공
- [ ] **HTTPS 이월** — HTTPS 는 도메인 확보 후 §8 경로로 전환 (현재 HTTP only)
- [ ] **방화벽 원칙** — 내부 서비스 포트(8000/3000/3001/3002/3100) 는 Phase 0 P0-18 의 Block 유지, 80 만 외부 노출

---

## 7. 체크포인트

```powershell
# 서비스
Get-Service caddy      # Running
Test-Path "D:\Workspace\plane-app\ops\Caddyfile"

# 로그
Test-Path "D:\Workspace\plane-logs\caddy\access.log"

# 루프백 응답
@("/", "/god-mode/", "/spaces/", "/api/users/me/") | ForEach-Object {
  $code = (Invoke-WebRequest -Uri "http://127.0.0.1$_" -UseBasicParsing -MaximumRedirection 0 -ErrorAction SilentlyContinue).StatusCode
  "$_  → $code"
}

# 방화벽
Get-NetFirewallRule -DisplayName "Allow Inbound tcp/80 (Plane Caddy)"
```

- [ ] Caddyfile validate 통과
- [ ] caddy 서비스 Running + Automatic
- [ ] 루프백 경로 4개 모두 200/301/302 응답 (500 없음)
- [ ] 방화벽 80 인바운드 허용 규칙 존재
- [ ] 공유기 포트 포워딩 — 해당 없음 (공인 IP 직접 물림)
- [ ] 외부 네트워크에서 공인 IP 접속 시 Plane 로그인 화면 렌더
- [ ] `/live/*` WebSocket 프레임 양방향 확인

---

## 8. 도메인 + HTTPS 전환 경로 (미래)

도메인 확보 시:

### 8.1 Caddy 자동 ACME (가장 간단)

`Caddyfile` 을:
```caddyfile
plane.example.com {
	# §2 와 동일한 내용, :80 → 도메인 블록
	...
}
```

Caddy 가 자동으로 Let's Encrypt 발급. 443 포트 허용 + 공유기 포트 포워딩만 추가.

```powershell
New-NetFirewallRule -DisplayName "Allow Inbound tcp/443 (Plane Caddy)" `
  -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow -Profile Any
```

`site.env`:
```ini
PUBLIC_HOST=plane.example.com
PUBLIC_SCHEME=https
PUBLIC_PORT=
```

→ `render-envs.ps1` 재실행 → `pnpm turbo build` 재빌드 (VITE_* 재주입) → `Restart-Service caddy plane-api plane-live`.

### 8.2 Cloudflare Tunnel (도메인이 Cloudflare DNS 에 있을 때)

Phase 0 §7.4 에서 `cloudflared` 는 이미 설치됨.

```powershell
cloudflared tunnel login
cloudflared tunnel create plane
```

`~/.cloudflared/config.yml`:
```yaml
tunnel: <tunnel-id>
credentials-file: C:/Users/plane-admin/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: plane.example.com
    service: http://127.0.0.1:80
  - service: http_status:404
```

```powershell
cloudflared tunnel route dns plane plane.example.com
cloudflared service install
```

Caddy 는 내부 80 포트로만 응답하고 공인 포트 80 을 닫을 수 있음 — Tunnel 이 Cloudflare Edge 에서 HTTPS 처리 + 80/443 원본 노출 불필요.

---

## 9. 이월 / 후속

- **HTTPS 전환** — §8.1 또는 §8.2 (도메인 획득 후, [../security-todo.md §2](../security-todo.md))
- **Cloudflare Access** — `/god-mode/` 에 이메일 SSO 게이트 → [../security-todo.md §3](../security-todo.md)
- **Rate limiting** — Caddy 모듈 `caddy-ratelimit` 도입 (anon throttle 은 Django 수준에서도 가능)
- **CSP/HSTS 헤더** — 도메인 + HTTPS 전환 이후 Caddy `header` 지시어로 추가

---

> **네비게이션**: [← Phase 6](07-systemd.md) · [목차](../plan.md) · [다음: Phase 8 →](09-verification.md)
