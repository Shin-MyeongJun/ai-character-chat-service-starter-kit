# 관리자 웹 Figma 디자인 기록

2026-10-22. 애플리케이션 및 백엔드 구현에 앞서는 디자인 작업이다.

> 같은 날짜의 후속 프런트 구현은 `apps/admin_web`에 완료했다. 아래는 디자인 제작 시점의 기록이다. 현재 결정·차이·제약은 [구현 결과](admin-web-implementation-plan.md), [실행 문서](../apps/admin_web/README.md), [검증 기록](admin-web-validation.md)을 따른다. Figma와 Studio 원본은 구현 과정에서 변경하지 않았다.

## 파일과 진행 상태

- 관리자 전용: [Studio Admin · 관리자 조회 v1](https://www.figma.com/design/yVzKbeu9mNhbXrZhGBkuqO).
- Studio 원본: [작품 개요 Light / 4:193](https://www.figma.com/design/GABZWkKaaUnGsXMpMz3mNu?node-id=4-193). 읽기 전용으로 조사하고 스크린샷을 확인했다. 원본을 수정하지 않았다.
- [프로토타입 시작](https://www.figma.com/proto/yVzKbeu9mNhbXrZhGBkuqO?node-id=5-175&page-id=0%3A1&starting-point-node-id=5%3A175&scaling=scale-down&content-scaling=fixed).
- 완료: 편집 가능한 화면 16개, 공통 컴포넌트 6세트·29변형, 변수 컬렉션 2개와 글자 스타일 6개, 개발 인계 프레임. 전체 화면을 이미지로 대체하지 않았다.
- API 할당량 소진 후 반복 호출을 중단하고 computer-use로 같은 파일에서 이어갔다. 사용자의 명시적 승인 아래 Scripter에서 생성·보완 스크립트를 실행한 뒤, 브라우저 Figma UI에서 컴포넌트와 프로토타입을 수정·검수했다. 기존 관리자 노드와 Studio 원본을 보존했다.
- 제작 자료: `tmp/admin-figma-20261022/build-admin-design.js`, `polish-admin-design.js`, 실제 노드 검수 `figma-state.json`. 최종 Figma에는 이후 UI 보완도 포함되므로 생성 스크립트만으로 최종 상태를 판단하지 않는다.
- 미리보기: [주요 화면](assets/admin-web-design/overview.png), [전체 16개 화면](assets/admin-web-design/all-screens.png), [공통 요소](assets/admin-web-design/components.png).

## 실제 확인한 근거

| 근거 | 확인 내용 |
| --- | --- |
| `apps/web/components/studio/studio.module.css` | Light/Dark 의미 색상, Noto Sans KR, 72px 상단 바, 260px 탐색기, 버튼·입력·선택·오류 스타일 |
| `apps/web/components/studio/creator-studio.tsx` | 브랜드, 현재 문맥, 상단 행동, 작업실 및 선택된 탐색 항목 구조 |
| `apps/web/components/studio/studio-controls.tsx` | 공통 입력·버튼 구성 |
| `apps/web/components/user-theme.tsx` | 초기 light, 이후 저장된 사용자 설정 또는 OS 설정 적용. 명세의 기본 테마는 Light이나 실제 구현은 시스템 설정도 따름 |
| `apps/web/app/globals.css` | 로컬 Noto Sans KR 폰트 등록 |
| `docs/figma-creator-studio-brief.md` | 화이트 우선, 중성색·낮은 그림자·명확한 타이포, 편집 가능한 컴포넌트 지향 |
| `docs/creator-studio-implementation.md` | Studio 구현 구성과 시각적 기준 |
| Studio `4:193` | 1440×1040, 흰 본문·옅은 사이드바·짙은 버튼·절제된 경계선. 실제 텍스트의 Noto Sans KR Regular/Medium/Bold 확인 |
| `docs/generation-prompts.md` 및 `apps/api/app/modules/reporting/operations_reporting/schemas.py` | 조회 필터, 상태, 반환 필드, 상세 원문 계약 |
| `apps/api/app/modules/chatting/prompt/service.py` | `chat_message_format`와 `messages`의 role/content 구조. 참조 자료는 user 메시지의 JSON 문자열 |
| `apps/api/app/modules/reporting/operations_reporting/ARCHITECTURE.md` | 조회 책임, 인가, no-store, 미기록·미존재 구분 |

## 계승할 토큰과 관리자 조정

| 의미 | Studio Light 값 | 관리자 적용 |
| --- | --- | --- |
| canvas / surface | `#FFFFFF` | 본문·입력·표 |
| sidebar | `#F7F7F8` | 왼쪽 탐색·보조 영역 |
| hover | `#F1F1F3` | 행·중립 버튼 hover |
| border | `#E5E5E8` | 1px 경계·행 구분 |
| text / secondary | `#202024` / `#65656F` | 본문·보조 정보 |
| action / on-action | `#252529` / `#FFFFFF` | 검색·로그인 |
| selection | `#EEEEF1` | 현재 메뉴·선택 |
| positive / danger | `#3B6550` / `#9D493E` | 상태 문구. 색상 외 라벨 병기 |
| radius | 8px / 12px | 입력·버튼 / 정보 카드 |
| typography | Noto Sans KR | 제목 24/34·섹션 18/28·본문 14/22·보조 12/20 |
| spacing | 4·8·12·16·24·32px | 기본 간격 체계 |

표는 긴 UUID를 앞·뒤 구간으로 축약하고 상세에서 전체 문자열을 보여준다. 모델명은 고정 너비 안에서 최대 2줄로 감싸며 행 높이를 유지한다. 아이콘만으로 상세 진입을 표시하지 않고 ‘상세 보기’를 사용한다. 관리자에 필요한 조정은 224px 탐색기, 밀도 높은 64px 표 행, 두 줄 식별자와 모델 표시다. 원문은 장식 없이 넉넉한 줄 간격으로 읽는다.

## 화면과 상태 명세

| 화면 | 기본 내용 | 구분할 상태 |
| --- | --- | --- |
| 관리자 로그인 | 이메일·비밀번호·로그인. 가입/소셜 로그인 없음 | 기본·입력 중·로그인 중·자격 증명 오류·요청 실패 |
| 생성 프롬프트 목록 | 날짜·대화 ID·생성 상태·검색·초기화·표·페이지 | 데이터·로딩·검색 결과 없음·조회 오류·422 입력 오류 |
| 생성 프롬프트 상세 | 복귀·메타데이터·생성 상태·원문 기록·역할별/원본 전환·복사 | 역할별·원본 문자열·복사 완료·원문 미기록·로딩·조회 오류·404 |
| 접근 권한 없음 | 관리자 전용 안내·로그아웃 후 로그인 | 인증된 비관리자/권한 회수. 관리자 데이터 노출 없음 |

로그인에서 목록, ‘상세 보기’에서 상세, ‘목록으로’에서 동일 검색 조건의 목록으로 돌아간다. 로그아웃은 로그인으로 이동한다. 페이지 내 콘텐츠·통계·결제의 미구현 메뉴는 표시하지 않는다. 로딩은 데이터 개수 0건이나 이전 결과를 새 결과처럼 표시하지 않는다. 오류에서는 결과 개수를 미확정으로 표시한다.

## 목록과 API 대응

- `date_from` / `date_to`: 필수 날짜, 서울 기준 양 끝 포함, 최대 731일. 화면의 기본 기간은 2026-10-16~2026-10-22(최근 7일 가상 예시).
- `conversation_id`: 선택 UUID. 생성 ID·모델명·사용자명·원문 검색은 현재 계약에 없으므로 입력을 추가하지 않는다.
- `status`: 전체(미전달), 대기(pending), 성공(succeeded), 실패(failed), 취소(cancelled), 만료(stale). ‘만료’ 한국어 표현은 구현 시 도메인 의미를 확인한다.
- `page` / `page_size`: 기본 1/50, 크기 제안 20·50·100. 필터·크기 변경 시 첫 페이지. 최신 생성 시각/ID 내림차순 고정, 정렬 UI 없음.
- 열: 생성 ID, 대화 ID, 당시 모델, reasoning effort, 생성 상태, 생성 시각(서울), 원문 기록, 상세 보기.
- 결과 개수는 `total`, 현재 범위는 page/page_size/items로 계산한다. 목록 응답에는 원문·digest가 없다.
- 1280px에서도 8개 데이터 열과 상세 진입점을 보존한다. 열 최소 너비를 침범하면 표 자체만 가로 스크롤하며 페이지 전체 넘침은 피한다. 긴 모델명을 잘라 숨기기보다 두 줄 표시한다.
- 목록 복귀 시 URL query와 스크롤을 복원한다. count와 페이지는 동시 변경 중 서로 달라질 수 있으므로 고정 스냅샷이라고 표현하지 않는다.

## 상세와 원문 의미

- 생성 정보는 generation_id, conversation_id, model_id/model_name, reasoning_effort, status, created_at, finished_at, history_invalidated_at, provider를 사용한다. nullable 시각은 ‘—’로 표시한다.
- 기록 정보는 prompt_created_at, prompt.created_at, format_version, max_output_tokens, digest를 사용한다. 생성 시각과 기록 시각을 혼동하지 않는다.
- `prompt_recorded=true`는 ‘원문 저장됨’이다. 실패 생성에서도 원문이 있을 수 있다. ‘공급자 전송 성공’이라는 문구·아이콘을 만들지 않는다.
- 보조 문구: ‘저장된 원문은 공급자 어댑터 변환 전의 JSON입니다. 원문 저장 여부는 공급자 전송 또는 생성 성공을 뜻하지 않습니다.’
- 역할별 보기는 request_json을 파싱해 messages 순서와 role을 보존한다. system/user/assistant 라벨과 한국어 보조 이름을 함께 표시한다. 참조 JSON을 별도 역할로 바꾸지 않는다.
- ‘원본 JSON 문자열’은 응답에서 이스케이프를 해제한 request_json을 재직렬화하지 않고 표시한다. 줄바꿈 on/off는 화면 표시만 바꾼다. 원문 복사는 이 문자열 전체를 대상으로 하며 복사 완료는 실제 clipboard 성공 후에만 나타낸다.
- 긴 본문은 세로 스크롤, wrap off는 가로 스크롤을 제공한다. 파싱 실패·알 수 없는 버전은 원본 문자열 보기를 제공하고 내용을 소실하지 않는다.
- `200 + prompt=null`은 ‘기록된 프롬프트 원문이 없습니다.’ 미기록 이유·전송 여부를 추정하지 않는다. 복사 버튼은 비활성으로 표시한다.
- 404는 ‘생성 기록을 찾을 수 없습니다.’로 원문 미기록과 구분한다. 403은 접근 권한 없음, 미인증/세션 만료는 로그인, 422는 필터 오류, 5xx/네트워크는 재시도 안내다.
- 가상 관리자 `운영 관리자 / admin@example.test`, 가상 UUID와 판타지 대화를 사용한다. 운영 원문·개인정보는 넣지 않는다.

## 후속 구현 전 결정할 사항

1. `/admin/session`은 기존 계획의 제안이며 현재 조회 API와 별개다. 기존 인증의 사용자 정보만으로 관리자 여부를 확정하지 말고 서버 검증 계약·표시할 최소 관리자 정보를 확정한다.
2. 날짜 필터 기본 기간, stale의 한국어 명칭, page_size 선택값과 UUID 축약/전체 확인 방식.
3. 역할별 파싱의 버전·대용량 처리, 원본 wrap 기본값, 복사 실패 피드백과 복사 범위.
4. 시스템 테마를 따를지 관리자 Light 고정으로 시작할지. 이번 디자인 기준은 Studio 명세의 Light다.
5. no-store, 원문을 브라우저 저장소·분석·오류 로그에 남기지 않는 처리, 세션 만료와 필터 복귀 정책.
6. 원문 조회 감사 기록의 주체·대상·시각·보존 정책. 원문 자체를 감사 로그에 복제하지 않는다.

## 후속 운영 기능 제안 — 이번 내비게이션에 미노출

아래는 일반적인 운영 수요를 바탕으로 한 제품 제안이다. 현재 API가 모두 제공된다는 뜻은 아니다. 목록/상세 조회를 먼저 정의하고 변경 작업은 별도 권한·검증·감사와 함께 추가한다.

| 우선 | 영역 | 먼저 제공할 조회 | 관리 기능 후보 / 선행 결정 |
| --- | --- | --- | --- |
| P1 | 작품·콘텐츠 | 작품/캐릭터/로어북 목록·상세, 소유자, 공개/발행 상태, 신고 연계 | 공개 제한·복구·태그 관리. 기존 전역 조회의 미연결 관리자 인가와 검색 계약부터 확인 |
| P1 | 사용자 | ID 기준 계정·활성 상태·가입/최근 활동, 소유 작품 및 지원 이력 | 정지/해제·관리자 역할 부여는 강한 권한·사유·재인증·감사 필요. 노출 개인정보 최소화 |
| P1 | 결제 내역 | 주문·결제·환불·실패 상태, 금액·통화·시각, 사용자/거래 식별자 | 결제와 크레딧을 분리. 카드 원문 미노출. 환불은 PG·부분환불·중복 방지 계약 이후 별도 설계 |
| P1 | 크레딧 원장 | 충전·차감·예약·해제·조정 이력과 관련 생성/결제 | 잔액 직접 수정 대신 사유가 있는 원장 조정, 승인·중복 방지 정책 |
| P1 | 신고·검토 | 신고 목록·상세·대상·처리 상태 | 담당 배정·조치·이의 제기·사유/증거 보존·역할 분리 |
| P2 | 생성 운영 | 실패·대기·취소·stale 조회와 생성/대화/비용 연계 | 실제 전송 근거가 없는 상태 추정 금지. 재실행/환급은 별도 계약과 실행권 검토 |
| P2 | 감사·권한 | 관리자 로그인/민감 조회/변경 이력, 관리자 계정·권한 | 역할별 허용 범위·MFA·세션 회수·보관 기간 |
| P2 | 운영 통계 | 생성량·실패율·비용·확정 매출·사용 크레딧·활성 지표 | 기록/확정·통화·집계 지연·미수집을 구분. 기존 reporting 서비스의 HTTP 계약 필요 |
| P2 | 모델·가격 | 당시 모델 설정과 현행 모델/가격표, 적용 기간 | 가격 변경의 효력 시각·이력·검토 절차. 과거 생성 메타데이터 보존 |
| P3 | 고객지원·공지 | 문의·처리 이력, 공지 초안·게시 이력 | 담당자·알림 발송·공지 예약·템플릿 권한 |

## 검수 기록

완료: 저장소·Studio Figma 원본 조사, 전용 파일 제작, 조회 계약 매핑, 계획 우선순위 갱신, 실제 화면·컴포넌트·프로토타입 검수.

- 화면: 로그인·로그인 오류, 목록 데이터 1440/1280·로딩·빈 결과·오류, 상세 역할별 1440/1280·원본 wrap on/off·복사 완료·미기록·오류·404, 접근 권한 없음. 총 16개이며 인계 프레임은 별도다.
- 컴포넌트: Button 10·Input 4·Badge 7·Navigation 2·Table row 3·Prompt message 3변형. 기본·hover·focus·disabled·loading 등 필요한 상태와 의미 색상을 정리했다. 로딩 버튼의 문구는 ‘처리 중…’이다.
- 구조 검수: 실제 Figma 노드의 Noto Sans KR, Auto Layout, 변수 바인딩을 확인했다. 보완 스크립트의 검수 결과 16개 화면에서 루트 밖 넘침 0개, 이미지 노드 0개였다. 긴 본문/표의 내부 스크롤과 의도적인 clip은 별도다.
- 시각 검수: 모든 화면을 실제 PNG로 확인하고 로그인 문구 겹침, 과도한 메타데이터 높이, 역할 카드 간격, 목록의 50행 내부 스크롤, JSON 줄바꿈 전환을 수정했다. 최종 PNG 16개와 공통 요소 갤러리를 재확인했다. 미기록 샘플의 모델·effort·시각을 목록과 맞췄다.
- 프로토타입 실동작: 로그인 → 목록 → 상세 → 목록 복귀, 로그아웃, 검색 → 로딩 → 목록, 원본 전환, wrap on/off, 복사 완료, 미기록 행 진입을 확인했다. 1280 목록/상세의 복귀 대상도 1280 목록으로 연결했다.
- 프로토타입은 입력·조회·클립보드 성공을 설명하는 디자인 시뮬레이션이다. 실제 로그인·API 호출·원문 복사는 후속 구현 범위다. 복사 성공 표시는 실제 clipboard 성공 후에만 구현한다.
- 애플리케이션 및 백엔드 코드는 구현하지 않았다. 상태별 HTTP 대응과 구현 결정은 위 명세 및 Figma 인계 프레임을 따른다.
