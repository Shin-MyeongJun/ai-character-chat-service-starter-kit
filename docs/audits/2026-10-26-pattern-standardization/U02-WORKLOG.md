# U02 작업 기록 — 계정 전환 중 추가 페이지 응답 혼입

작성일: 2026-10-30 (Asia/Seoul)

상태: **구현·오프라인 검증 완료.** 브라우저 E2E는 실행하지 않았다.

## 문제와 수정

기존 `useConversationDirectory`의 첫 조회는 effect 내부의 active/sequence를
검사했지만 `loadMore`는 이를 공유하지 않았다. A의 추가 페이지가 진행 중일 때
B로 전환하면 A의 늦은 응답이 B의 목록·커서를 덮거나 오류·로딩 상태를 바꿀 수 있었다.

- 첫 조회와 더 보기가 하나의 ref에 있는 active/sequence/busy/cursor를 공유한다.
  인증 변경, 인증 storage 이벤트와 storage 초기화, focus 재조회에서 세대를 증가시키고
  목록·커서를 초기화한다. effect cleanup에서도 세대를 증가시켜 이전 작업을 무효화한다.
- 첫 조회와 더 보기의 성공·실패·finally에서 현재 세대와 수명을 검사한다.
  이전 요청의 finally가 새 요청의 로딩과 busy 잠금을 해제하지 않는다.
  getMe 이후에도 검사하여 이미 무효가 된 인증 확인에서 목록 요청을 시작하지 않는다.
- busy는 렌더를 기다리지 않고 설정하여 같은 렌더에서 연속 호출해도 추가 요청이
  중복되지 않는다. 커서도 ref에서 읽어 오래된 callback이 이전 계정/이전 페이지의
  커서를 재사용하지 않는다. hasMore는 화면 상태로 유지한다.
- 정상 페이지의 ID 중복 제거·순서, 다음 커서 진행, 현재 요청 실패의 오류 표시와
  동일 커서 재시도, 로그아웃 시 브라우저 시연 대화 표시는 유지한다.

기존 hook 안에서 수명을 관리한다. 이 동작만을 위한 새 계층·공통 API 클라이언트 변경은
필요하지 않으므로 파일을 분리하지 않았다. 백엔드·HTTP DTO·서버 페이지 정렬은 변경하지
않았다. 공통 REPORT와 기존 작업 트리의 다른 변경은 유지했다.

## 검증

새 테스트는 실제 TSX를 TypeScript로 변환해 hook을 실행하고 최소 useState/useRef/useEffect
대역과 제어된 Promise로 완료 순서를 지정한다. React 렌더러나 실제 브라우저의 검증을
대체하지 않는다. 구현 문법 검색 대신 반환 목록·오류·로딩·hasMore, API 호출과 전달 커서,
무효화된 작업의 상태 갱신 유무를 확인한다.

22건은 이전 계정 추가 페이지의 지연 성공/실패가 새 첫 조회 전·후·새 추가 조회 중에
완료되는 경우, focus/storage 갱신, 로그아웃, unmount와 listener 정리, 같은 렌더의 중복
호출, 연속 페이지·ID 중복 제거, 오류 재시도, 오래된 첫 페이지/인증 응답, Strict Mode의
effect cleanup/setup 재실행 모형, 로컬 이벤트와 무관한 storage 이벤트를 포함한다.

대조 실행에서는 `git show HEAD:apps/web/components/recent-conversations.tsx`로 읽은
수정 전 소스를 테스트 프로세스 안에서만 대신 로드했다. 선택한
`old account additional-page success is ignored after new first page` 회귀가
**1 failed / 0 passed / 0 cancelled**로 실패해 이전 응답의 상태 갱신을 확인했다.
작업 파일을 수정 전 상태로 되돌리지는 않았다.

| 검사 | 결과 |
|---|---|
| `node --test apps/web/tests/recent-conversations.test.cjs` | 22 passed / 0 failed / 0 skipped |
| `node --test apps/web/tests/*.test.cjs` | 72 passed / 0 failed / 0 skipped |
| `pnpm web:typecheck` | 통과 |
| `pnpm web:build` | production build 통과 |
| `.venv/Scripts/python.exe tools/check_backend_quality.py` | 기준선 0개, Ruff 393파일, mypy 372소스, 검사 테스트 13 passed |
| 변경 파일 diff 공백 검사 | 통과 |

첫 품질 검사에서는 기본 sandbox 임시 폴더를 만들 수 없어 pytest 2건이 setup 오류였다
(11 passed). `PYTEST_ADDOPTS`에 작업 공간의 고유 `tmp/u02-quality-<UUID>` 경로를
forward slash로 지정한 뒤 전체 품질 검사를 다시 실행해 통과했다. 검사 코드·설정·기준선을
변경하지 않았다. Next 빌드가 생성한 next-env.d.ts 경로 변경은 빌드 전 내용으로 복원했다.

## 변경 파일

- `apps/web/components/recent-conversations.tsx`: 공유 요청 수명·세대·직렬화·커서.
- `apps/web/tests/recent-conversations.test.cjs`: 제어된 응답 순서 회귀 22건.
- `apps/web/README.md`: 대화 목록 응답 수명과 테스트 명령.
- 이 작업 기록.

네트워크 요청 자체를 중단하는 변경은 없으며 완료된 오래된 응답의 적용을 차단한다.
실제 브라우저·쿠키 세션·다중 탭 통합 검증, 전체 API 업무 테스트는 이번 범위에 포함하지
않았다. commit/push는 하지 않았다.
