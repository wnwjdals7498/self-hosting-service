# Self-hosting Service

셀프 호스팅 운영에 사용하는 세 구성 요소를 한 저장소에서 관리합니다. 각 서비스는 독립적으로 실행하며, 해당 디렉터리의 안내를 따릅니다.

| 경로 | 용도 |
| --- | --- |
| [`gitea`](./gitea) | Windows Server용 Gitea 설치·백업 자동화 |
| [`plane`](./plane) | 로컬 Plane 포크 및 셀프 호스팅 구성 |
| [`plane-mcp`](./plane-mcp) | Plane 인스턴스용 MCP 서버 |

## 시작

각 구성 요소의 `README.md`와 기존 배포 문서를 확인한 뒤 필요한 서비스만 설정합니다. 세 서비스의 런타임 설정, API 키, 데이터베이스, 업로드 자산 및 백업 파일은 커밋하지 않습니다.

## 라이선스

구성 요소별 라이선스가 적용됩니다. Plane은 `plane/LICENSE.txt`의 AGPL-3.0, Plane MCP는 `plane-mcp/LICENSE`의 MIT 라이선스를 따릅니다. Gitea 자동화 스크립트의 사용 조건은 `gitea/README.md`를 확인하세요.
