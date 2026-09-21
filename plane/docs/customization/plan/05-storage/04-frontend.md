# Phase 4.4 — 프론트엔드 타입 정리 (선택)

> **네비게이션**: [← 4.3 bgtasks](03-bgtasks.md) · [Phase 4 목차](../05-storage.md)

**목표**: `packages/types/src/file.ts` 의 `TFileSignedURLResponse.upload_data.fields` 타입이 AWS 고정 필드명(`x-amz-*`, `policy`) 으로 선언되어 있어 로컬 어댑터 필드 변경 시 타입 에러 가능. 어댑터가 필드명을 동일하게 유지하면 **이 서브는 스킵 가능**.

---

## 1. 현 타입 선언 (Phase 4 시작 시점)

`packages/types/src/file.ts`:

```typescript
export type TFileSignedURLResponse = {
  asset_id: string;
  asset_url: string;
  upload_data: {
    url: string;
    fields: {
      "Content-Type": string;
      key: string;
      "x-amz-algorithm": string;
      "x-amz-credential": string;
      "x-amz-date": string;
      policy: string;
      "x-amz-signature": string;
    };
  };
};
```

어댑터(4.1) 가 같은 필드명을 그대로 재사용 → 타입 변경 불필요. **기본 경로는 수정 없음**.

---

## 2. 수정이 필요해지는 경우

아래 결정이 생기면 타입 완화가 필요해진다.

- 로컬 어댑터가 새로운 필드(예: `x-plane-one-time-token`) 를 추가
- AWS 고정 필드(`x-amz-credential`) 를 제거해서 응답 크기 감소
- v2 API 가 두 스토리지 백엔드에서 다른 형상의 `fields` 를 반환하도록 확장

---

## 3. 완화 패턴

### 3.1 `fields: Record<string, string>` 로 일반화

```typescript
export type TFileSignedURLResponse = {
  asset_id: string;
  asset_url: string;
  upload_data: {
    url: string;
    fields: Record<string, string>;
  };
};
```

영향 분석:

```powershell
Select-String -Path D:\Workspace\plane-app\packages -Recurse `
  -Pattern "upload_data\.fields\." -Include *.ts
```

현재 `packages/services/src/file/helper.ts:60` 에서 `Object.entries(...)` 로 순회만 하고 개별 키 접근은 없음 → Record 변경이 안전.

### 3.2 `FormData.append` 순서

S3 는 `file` 필드가 **가장 마지막** 에 오는 것을 요구. `generateFileUploadPayload` 현재 구현:

```typescript
Object.entries(signedURLResponse.upload_data.fields).forEach(([key, value]) => formData.append(key, value));
formData.append("file", file);
```

→ Record 로 바꿔도 동작 동일. 로컬 어댑터도 `file` 을 마지막에 받으므로 순서 요구사항 유지.

---

## 4. 수정 절차 (필요 시)

```powershell
cd D:\Workspace\plane-app
# 1. 타입 수정
# packages/types/src/file.ts 를 §3.1 대로 편집

# 2. 타입 체크 (모노레포 전체)
pnpm check:types

# 3. 린트
pnpm check:lint
```

빌드 산출물 재생성은 Phase 5 에서.

---

## 4a. 작업 단위 분해 (WBS)

| WBS | 작업 | 선행 | 본문 | 산출물 |
|---|---|---|---|---|
| P4.4-1 | 4.1 어댑터의 `fields` 키 목록 확인 | P4.1-1 | §2 | 비교 |
| P4.4-2 | 동일 유지 → **스킵** / 변경 시 `file.ts` `fields: Record<string,string>` 완화 | P4.4-1 | §3 | (선택) |
| P4.4-3 | `pnpm check:types` + 빌드 dry-run | P4.4-2 | §4 | 타입 에러 0 |

---

## 4b. 단위별 테스트

| WBS | 검증 명령 | 기대 |
|---|---|---|
| P4.4-1 | 4.1 smoke 의 `r["fields"]` 키 vs `file.ts:fields` 키 비교 | 전부 포함 |
| P4.4-2 | (완화 시) `Select-String file.ts -Pattern "Record<string, string>"` | 1건 |
| P4.4-3 | `cd plane-app && pnpm check:types` | 0 error |

---

## 4c. 요구사항 검증 체크리스트

- [ ] **기본 경로는 스킵** — 4.1 이 `x-amz-*` 유지 시 본 서브 무변경
- [ ] **변경 시 안전성** — helper.ts 의 `Object.entries(fields).forEach` 가 Record 변경과 호환
- [ ] **FormData 순서 유지** — `file` 이 마지막에 append (S3·LocalFS 공통 규칙)
- [ ] **MCP (Python) 영향 0** — TypeScript 타입은 Python MCP 와 독립

---

## 5. 체크포인트

- [ ] Phase 4.1 어댑터가 `x-amz-*` 필드명 **그대로** 사용 중이라면 — **본 서브 스킵**, `packages/types` 수정 0
- [ ] 어댑터 필드명이 변경되었다면 — §3.1 적용 + `pnpm check:types` 통과 + helper.ts 순회 코드 회귀 없음
- [ ] `pnpm turbo run build --dry --filter=web` 으로 빌드 계획에 타입 에러 없음 확인

---

## 6. 후속

- **Storybook / 유닛 테스트** — `packages/types` 는 테스트가 없음 (구조 타입만). 타입 변경 시 `packages/services` 의 helper 테스트가 있으면 회귀 확인. 없으면 타입체크로 대체.
- **MCP 서버 (Python)** — Python 타입 힌트는 TypeScript 와 독립. 영향 없음.

---

> **네비게이션**: [← 4.3 bgtasks](03-bgtasks.md) · [Phase 4 목차](../05-storage.md)
