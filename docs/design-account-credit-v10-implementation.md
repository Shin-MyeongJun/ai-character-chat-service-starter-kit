# Figma v10 웹 구현 및 검증

작업일: 2026-10-20 (Asia/Seoul)

화면과 기존 서비스에 대한 코드 연결을 구현했다. **외부 결제·크레딧 구매·실서비스 인증/결제 운영을 완료했다는 의미는 아니다.** 실제 구매·과금·배포는 수행하지 않았다.

## 조사 결과와 구현 경로

| 화면 | 조사 시 상태 | 구현 경로와 데이터 |
| --- | --- | --- |
| 마이페이지 | 없음 | `/account`: 실제 `/auth/me`, 잔액, 소유 대화·작품 조회, 부분 실패 구분 |
| 계정 설정 | 가입·인증·비밀번호 복구만 있음 | `/account/settings`: 실제 계정 정보, 테마, 로그아웃, 기존 비밀번호 복구 경로 |
| 내 작품 관리 | 스튜디오의 로컬 보관함만 있음 | `/account/works`: 서버 작품과 브라우저 초안을 분리, 공유 작품 카드·검색·데스크톱 작업실 메뉴 |
| 크레딧 지갑 | 잔액 API만 HTTP로 공개 | `/account/wallet`: 실제 잔액과 새 원장 조회 경계, 기간·사용/획득 필터·이전 내역 조회 |
| 구매 내역·상세 | 주문 도메인/결제사 계약 없음 | `/account/purchases`, `/account/purchases/{orderId}`: 준비 중 안내, 허위 구매 기록 없음 |
| 충전·상품 요약 | 상품·판매 정책·PG 계약 없음 | `/account/topup`, `/account/checkout`: 준비 중 및 Disabled |
| 결제 결과·재확인 | 외부 승인/충전 상태 계약 없음 | `/account/purchases/{orderId}/result`, `/recheck`: 실제 상태를 확정하지 않음. 개발 경로에서 상태별 화면 검증 |
| 대화·대화 설정 | 실제 메시지/답변 API 연결 있음 | `/chats/{id}`: v10 레이아웃, 설정/삭제 안내/크레딧 부족 모달, 지갑·마이페이지 복귀 |
| 제작 화면 | 로컬 작품·캐릭터·로어·장면 편집, 서버 저장·발행 있음 | `/studio`: 기존 기능 유지, 공유 작품 카드, 통합 테마, 계정 진입, 모바일 헤더 보완 |
| 작품별 편집 | 공통 작업실만 열림 | `/studio?work={browserWorkId}`, `/studio?product={serverProductId}` |

루트와 `apps/web/AGENTS.md`, v10 인계 문서·감사 JSON, 설치된 Next.js 16.3.3의 로컬 라우팅/레이아웃/개발 Origin 문서를 확인했다. 백엔드 변경 전에 모듈 아키텍처·명명 규칙과 credit의 `ARCHITECTURE.md`를 읽었다. 루트 `contracts/`에는 사용 가능한 계약 파일이 없어 실제 HTTP 등록 목록·Pydantic DTO·공개 service/types·기존 OpenAPI 고정 계약 검사를 기준으로 삼았다.

기존 서비스 조사에서 credit 원장/커서 조회를 발견하여 단순 목업으로 대체하지 않고 HTTP 경계를 추가했다. 반면 billing은 답변 가격·예약·사용량을 다루며 PG 주문/승인/영수증 서비스는 제공하지 않는다. account_reporting도 통계 모듈이며 프로필·주문 관리를 소유하지 않는다.

## 추가한 실제 API

`GET /account/credits/transactions`

- 기존 cookie 인증의 owner dependency를 사용한다. 사용자가 입력한 다른 계정 ID는 받지 않는다.
- 기존 `credit.service.query.list_credit_transactions`를 직접 호출한다. 통화는 `CREDIT`으로 고정한다.
- `limit` 1~100(기본 50), 시간대가 포함된 `start`/`end`, `cursor_created_at`/`cursor_id` 쌍을 지원한다.
- 결과: `items[{id, operation, amount, free_amount, paid_amount, created_at}]`, 다음 커서의 시각·ID.
- 원장 signed amount·무료/유료 배분만 표시하고 내부 namespace, reason, request_key, reference_id, 사용자 ID는 노출하지 않는다.
- 쓰기·지갑 준비·지급·commit을 하지 않는다. 조회 오류를 빈 성공이나 잔액 0으로 바꾸지 않는다.
- 원장은 결제 주문이나 현금 영수증이 아니다. 작품명으로 해석할 공개 계약이 없으므로 실제 화면에는 크레딧 사용/획득으로 표시한다.
- 기간은 서버 조회에 적용한다. 사용/획득 구분은 불러온 페이지에 적용하며, 이전 내역 더 보기와 적용 범위를 화면에서 안내한다.

HTTP contracts와 순수 schema mapper를 별도 파일로 두었다. 기존 `/account/credits`와 나머지 API 계약은 변경하지 않았으며 기존 OpenAPI 기준 비교를 통과했다. credit 아키텍처 문서에 공개 경계를 기록했다.

## 공통 화면과 디자인 기준

Figma 원본은 읽기만 했다. `figma-design-to-code`와 `figma-use` 지침으로 03의 마이페이지·설정·지갑·작품·구매 목록/상세·결제 진입/처리/실패/재확인·모바일 대화, 01의 작업실을 읽고 실제 디자인 스크린샷을 확보했다. 02의 컴포넌트 목록과 사용 정의 및 두 변수 컬렉션을 확인했다. 활성 71개 프레임은 화면/테마/상태 변형으로 통합하고, 보관 프레임은 기준에서 제외했다. 추가 조회 중 Starter MCP 한도에 도달하여 미확보 변형의 개별 스크린샷 추가 조회는 수행하지 못했다.

확인한 역할 값은 같은 CSS 역할 이름으로 통합했다.

| 역할 | Light | Dark |
| --- | --- | --- |
| canvas | #FFFFFF | #1C1C1E |
| sidebar | #F7F7F8 | #222225 |
| surface | #FFFFFF | #27272A |
| hover | #F1F1F3 | #303034 |
| border | #E5E5E8 | #3D3D42 |
| text | #202024 | #F4F4F5 |
| muted/secondary | #65656F | #B2B2BB |
| action | #252529 | #F0F0F2 |
| onAction | #FFFFFF | #202024 |
| selection | #EEEEF1 | #35353B |
| positive | #3B6550 | #BCD9C8 |
| danger | #9D493E | #E6B6AC |

Noto Sans KR 가변 폰트와 OFL 라이선스를 로컬로 포함했다. 본문 14/22, 캡션 12/20, 섹션 18/28, 큰 제목 32/44, 버튼 40px·8px 라운드, 24/40px 간격을 기준으로 했다. 데스크톱 계정 화면은 760px 본문·360px 보조 영역으로 구성하고 모바일은 단일 열과 콘텐츠 높이로 전환한다. 작품 관리는 작업실 메뉴와 3→2→1열 카드로 바뀐다. 화면 배경 스크린샷이나 전체 절대 좌표 복제는 사용하지 않았다.

기존 StudioButton/StudioField/StudioDialog를 재사용하고 상태 행·카드·선택 그룹·링크 버튼·공유 WorkTile을 조합했다. 네이티브 dialog로 포커스 제한·Escape를 지원하고, 닫은 뒤 호출 버튼으로 포커스를 되돌린다. 테마는 계정·대화·스튜디오·발견 화면에서 같은 환경 설정을 사용하며 이전 스튜디오 테마 값도 읽는다.

## 실제 기능과 개발 시연의 경계

`/dev/design-v10`는 **개발 모드 전용**이다. 같은 AccountApp에 분리된 fixture를 주입하고 실제 계정·지갑 API를 호출하지 않는다. 상단에 시연임을 명시한다. 프로덕션 실행에서 해당 경로가 404임을 확인했다.

개발 경로 예:

- `/dev/design-v10/settings`, `/works`, `/wallet`, `/purchases`, `/topup`, `/checkout`, `/chat`
- `/dev/design-v10/purchases/MC-20261019-001/result`: 처리 중
- `/dev/design-v10/purchases/MC-20261018-014/result`: 성공 예시
- `/dev/design-v10/purchases/MC-20261017-008`: 실패 예시
- `/dev/design-v10/purchases/MC-20261017-008/recheck`: 미확정 예시
- 지갑·작품·구매 경로에 `?state=empty`, `?state=loading`, `?state=error`
- `/dev/design-v10/chat?state=credit`: 크레딧 부족 모달

주문번호·상품 수량·금액·시각을 하나의 Order로 보존한다. 재확인은 미확정 상태를 유지하고, 클릭·리디렉션·대기 시간으로 성공/지급을 만들지 않는다. 성공 예시를 보아도 잔액은 증가하지 않는다. 로그인 화면으로 이동하는 링크는 실제 인증을 수행하지 않는다.

미연동 항목은 프로필 수정·탈퇴·대화 삭제·크레딧 구매·PG 결제·주문 조회·영수증·환불/판매 정책이다. 실제 사용자 화면에 Figma 내부 주석을 복사하지 않고 준비 중 안내로 바꿨다. 닉네임·프로필은 실제 계약이 없으므로 읽기 전용이며, 저장·삭제·구매 버튼은 Disabled다.

서버 작품 링크는 해당 product ID의 스튜디오 초안을 읽는다. 기존 작품에 studio-draft 문서가 없으면 지원하지 않는다는 안내를 표시한다. 브라우저에서 수정한 사본은 링크 진입만으로 덮어쓰지 않으며, 기존 서버 충돌 비교 기준도 보존한다. 발행·결제·로그인을 브라우저 검증 과정에서 실행하지 않았다.

## 실행한 검사

| 검사 | 결과 |
| --- | --- |
| `pnpm web:typecheck` | 통과 |
| `pnpm web:build` | 최종 프로덕션 빌드 통과 |
| `node --test apps/web/tests/*.test.cjs` | 34 passed |
| 새 원장 경계·아키텍처·credit 서비스/지갑·기존 actor 검사 | 22 passed, 71 skipped |
| 변경 Python 파일 Ruff 검사 | 통과 |
| 프로덕션 `next start -p 3002` | 개발 시연 경로 404 확인, 검증 후 종료 |

백엔드 실행 명령(저장소 루트):

```powershell
Set-Location apps/api
../../.venv/Scripts/python.exe -m pytest tests/test_account_credit_history.py tests/test_architecture_contracts.py tests/test_credit_services.py tests/test_credit_wallets.py tests/test_content_actor_routes.py -q -p no:cacheprovider
```

owner 고정·CREDIT 고정·커서/기간 검증·민감 메타데이터 제외·인증 거절 시 서비스 미호출·저장소 실패 전파를 검증했다. PostgreSQL 테스트 71개는 `TEST_DATABASE_URL` 미설정으로 제외됐다. 테스트 클라이언트에는 공개 조회 서비스를 대체한 단위 테스트가 포함되므로 실 DB 검증 완료로 해석하면 안 된다.

## 실제 브라우저 검증

Codex 브라우저 자동화로 로컬 Next 서버를 실행·조작했다. 127.0.0.1 개발 자원이 Next의 Origin 보호에 막히는 문제를 설치된 로컬 문서에 따라 localhost/127.0.0.1 허용 목록으로 해결했다.

- 1440×1040, 390×844에서 Light/Dark를 디자인 스크린샷과 비교했다. 개발 시연 배너는 원본에 없는 구분 표시다.
- 계정 주요 경로를 320/390/768/1440px에서 검사했다. 확인한 화면과 작품별 스튜디오에서 가로 넘침이 없었다.
- 마이페이지 → 설정 → 탈퇴 안내 → 취소/Escape → 마이페이지.
- 지갑 → 주문 목록 → 실패 주문 → 재확인. MC-20261017-008·5,000원·5,000크레딧 보존 및 미확정 유지.
- 완료 주문 상세·성공 상태 및 영수증 Disabled, 상품 요약·처리 중 상태를 확인했다.
- 대화 → 설정 → 삭제 안내 → 취소 → Dark 전환 → 닫기. 설정이 닫히고 대화가 유지됨을 확인했다.
- Tab 포커스가 모달 내부에 머물고 Escape 후 호출 버튼에 복귀함을 확인했다.
- 긴 시연 메시지 전송·줄바꿈·세로 스크롤·하단 전송 버튼 접근, Dark 크레딧 부족 모달을 확인했다.
- 지갑·작품·구매의 빈/로딩/오류 상태와 재조회 복구, 빈 구매 요약 0건을 확인했다.
- 실제 계정 경로에서 백엔드 접속 실패가 가짜 계정/0원으로 바뀌지 않고 오류로 표시됨을 확인했다.
- 로그인 링크 → 실제 폼 → 브라우저 뒤로 가기, 기존 `/chats/demo-archive?from=account` 설정 → 마이페이지 복귀를 확인했다.
- 기존 브라우저 초안을 수정하지 않고 `/account/works` → `/studio?work=migrated-work`로 열어 동일 작품 제목을 확인했다.

스크린샷과 DOM 측정 결과는 [verification-v10](verification-v10/)에 보관했다.

## 실행과 남은 연동

```powershell
pnpm web:dev
```

- 실제 계정: `http://127.0.0.1:3000/account`
- 화면 확인용: `http://127.0.0.1:3000/dev/design-v10`
- 제작: `http://127.0.0.1:3000/studio`

실제 데이터 조회에는 기존 API(기본 127.0.0.1:8000), DB/마이그레이션과 인증·메일 환경이 필요하다. 설정은 `apps/web/README.md`와 루트 실행 문서를 따른다. 이번 브라우저 세션에는 동작하는 API/테스트 DB가 없어 로그인 사용자와 실 DB 원장의 종단간 확인은 남아 있다. API 경계·권한·타입·오류 처리는 위 테스트로 확인했다.

외부 결제사·서버 검증·실제 판매 상품/환불 정책·주문 영속화·지급 멱등성 계약이 마련된 뒤 주문/결제를 연결해야 한다. 기존 스튜디오의 이미지 업로드·후속 버전 발행 지원 범위도 이번 작업에서 확대하지 않았다. 사용자 브랜치의 기존 변경·Figma 백업은 보존했다.
