# Plane local fork

셀프 호스팅 Plane 환경을 점검하고 로컬 요구사항을 실험하기 위한 작업 복사본입니다. 원본 Plane 프로젝트의 제품 설명, 설치 방법, 기여 안내는 [보존한 upstream README](./README.upstream.md)를 확인하세요.

## 이 저장소의 목적

- 로컬·셀프 호스팅 환경에서 Plane을 구동하고 연동 동작을 확인
- 프로젝트 자산 엔드포인트가 `X-Api-Key` 인증 헤더를 받아들이도록 확장
- upstream 코드와의 차이를 최소화하면서 필요한 변경을 분리

## 개발 환경

이 저장소는 pnpm workspace와 Turbo 기반 모노레포입니다. 전체 개발·빌드·검증 명령은 upstream 문서와 [`CONTRIBUTING.md`](./CONTRIBUTING.md)를 따릅니다.

```bash
pnpm dev
pnpm check
```

## 주의

로컬 `.env` 파일, 데이터베이스, 업로드 자산, API 키는 저장소에 넣지 않습니다. 운영 배포는 upstream의 공식 셀프 호스팅 문서를 기준으로 별도 검토해야 합니다.

## 라이선스

원본 Plane 프로젝트와 동일하게 [AGPL-3.0](./LICENSE.txt)을 따릅니다.
