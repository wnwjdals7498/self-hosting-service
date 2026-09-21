# Plane MCP local fork

셀프 호스팅 Plane 인스턴스를 AI 도구와 연결하기 위해 유지하는 Python·FastMCP 기반 작업 복사본입니다. 일반적인 설치·transport·환경 변수 설명은 [보존한 upstream README](./README.upstream.md)를 확인하세요.

## 로컬 포크에서 추가한 범위

- Header PAT 기반 HTTP transport를 사용하는 로컬 운영 흐름
- 이미지 첨부 파일 업로드·다운로드·조회 도구
- 인스턴스 관리자 전용 정보 조회, 상태 확인, 백업 실행 도구
- Windows 호스트의 IPBan 로그 조회 지원

추가 도구는 header-PAT HTTP factory에서만 등록됩니다. `stdio`와 OAuth 흐름은 upstream과의 호환성을 우선합니다.

## 실행과 검증

Python 3.10 이상과 `uv`를 사용합니다.

```bash
uv pip install -e ".[dev]"
python -m plane_mcp stdio
pytest
ruff check plane_mcp/
```

stdio 모드에서는 `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`가 필요합니다. 실제 키는 `.env.test.local` 같은 로컬 전용 파일에만 두고 커밋하지 않습니다.

## 알려진 제한

현재 로컬 Plane 포크에서 workspace·project page API는 `plane-sdk` 호출 시 404가 발생하는 것으로 기록되어 있습니다. 이 경로는 원인을 확인해 수정하기 전까지 사용할 수 없는 기능으로 취급합니다.

## 라이선스

[MIT License](./LICENSE)
