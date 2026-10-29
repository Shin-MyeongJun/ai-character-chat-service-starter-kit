# Conversation 모듈

- 소유 테이블: `conversations`, `conversation_characters`, `conversation_version_changes`. 메시지와 `product_generations`는 chat 소유이며 이 모듈에서 읽거나 쓰지 않는다. `conversations.history_revision`은 기존 원문 변경 세대이며 단순 후속 append에는 증가하지 않는다.
- `service/query.py`: `get_owned_conversation(OwnedConversationCommand)`은 소유 방의 ConversationInfo를 반환하며 lock=true이면 FOR UPDATE를 획득한다. `list_conversation_characters`는 같은 소유권 조건의 실제 참여 캐릭터 Info를 반환한다. 통계 조회는 방 생성/버전 전환 사실만 제공한다.
- `service/command/__init__.py`: `start_conversation(StartConversationCommand)`은 방·최초/현재 상품 버전·시작 옵션·참여자를 같은 트랜잭션으로 저장한다. chat 호출이나 첫 대사 메시지 저장은 없다.
- `service/views.py`: 인가된 최초 snapshot의 opening_message/start_set과 현재 버전의 실제 참여자·primary ID를 조합한다.
- `service/command/versions.py`: 순방향 버전 전환, 동의 정책, 대상 구성 검증. 메시지·기억·생성 이력을 수정하지 않는다.
- `service/command/context.py`: `prepare_runtime_context(PrepareRuntimeContextCommand)`. 기존 모델 대체 계획을 저장할 수 있는 쓰기 유스케이스이며 ConversationRuntimeView를 반환한다. 로어 활성화는 lorebook 공개 서비스에 고정 스냅샷과 `activation_text`를 전달한다.
- `service/command/history.py`: `advance_history_revision(AdvanceHistoryRevisionCommand)`은 소유 대화를 잠그고 파괴적 chat 변경 세대를 증가시킨다. memory 무효화가 같은 최상위 트랜잭션에서 호출한다.
- `repository.py`: 자체 테이블만 조회/저장. `mapper/persistence.py`: 자체 Entity와 공개 snapshot/runtime 결과의 순수 변환.
- `router.py`, `mapper/schema.py`: 시작·버전 전환·업데이트 조회의 기존 HTTP 경로, DTO 이름, 필드, 상태 코드를 유지한다. 시작 라우터는 conversation command에 직접 연결한다.

## 계약과 분리 이유

대화방과 상품 버전은 conversation, 메시지 저장과 생성 수명주기는 chat 책임이다. conversation → chat 역방향 호출은 없다. chat이 공개 서비스로 소유권·현재 버전·참여 캐릭터를 검증한다. 생성과 기본 CRUD가 공통 대화방 잠금을 획득하도록 공개 lock 계약을 유지했다. 타 모듈 JOIN 예외는 없다.

최상위 조립 결과는 기존 ConversationStartedInfo, 전환 결과는 VersionSwitchedInfo이며 changed=false는 이미 해당 버전인 멱등 성공이다. 버전 변경은 pending 생성을 취소하지 않고 기존 완료 stale 처리와 연결된다. 메시지 되돌리기는 현재 버전·initial_snapshot_id·전환 이력을 바꾸지 않는다. version_changes는 메시지 FK가 없으며 방과 두 snapshot의 기존 참조를 유지한다. Legacy 대화의 검증되지 않은 버전 매핑은 계속 거절한다.

생성 Command/Info/mapper/repository 및 호출부는 chat으로 이동했다. 생성 통계와 방 통계의 조합은 최상위 `app/use_cases/product_statistics.py`로 이동해 product에서 chat을 역으로 호출하지 않는다. 관련 없는 기존 product pending-update View → conversation query 의존성은 유지한다.

런타임 `lorebooks[].entries`는 후보가 아닌 자동 활성화가 끝난 항목 목록이다. enabled 일반 항목 중 always와 `activation_text`에 매칭된 keyword만 포함한다. 텍스트는 호출자가 명시적으로 구성하며 메시지 이력을 암묵적으로 조회하지 않는다. 생략 시 빈 문자열로 처리하여 always만 포함한다. start_set은 별도 start 필드로 제공하며 semantic/manual 활성화, 토큰 예산 적용, 실제 프롬프트 구성은 범위 밖이다. 원본 로어북 조회로 스냅샷을 대체하지 않는다.

시작·버전 전환 schema mapper는 인증 사용자와 경로 ID를 받아 최종 Command를 생성한다. 업데이트 응답 변환도 같은 mapper 클래스에서 처리한다. ConversationInfo.product_id는 DB와 동일하게 필수이며 레거시 여부는 product_snapshot_id의 None 여부로 판단한다.

대화 생성·버전 전환·런타임 준비는 변경 이유가 달라 기능 파일로 나눴다. 런타임 준비는 쓰기 부수효과가 있으므로 command에 유지하고 순수 View 조립은 persistence mapper에 둔다. 공개 재노출은 `service/__init__.py`에서 명시한다. `app.main`은 실제 DB 세션과 기본 쿠키 인증을 연결하고 인증 검증기를 선택적으로 주입받는다. 503은 개별 라우터의 미연결 훅에 해당하며 기본 앱은 실제 identity 검증을 수행한다. 외부 답변 생성은 `app/modules/chatting/chat/service/workflow/answers.py`가 담당하며 conversation 자체는 공급자를 호출하지 않는다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: `router.py` → `service/command/__init__.py` → `command/versions.py` → `command/context.py` → repository/mapper. `product_snapshot_id`는 현재 버전, `initial_snapshot_id/start_set_id`는 시작 당시 값이다.

runtime은 최초 snapshot의 시작 옵션을 조회한다. 현재 버전에서 최초 ID를 찾던 문제(F01)를 해결했으며 test_conversation_opening이 전환 후 runtime과 최초 만료 버전의 시작 내용 조회를 검증한다. 대조 테스트: `test_conversation_runtime`, `test_product_integration`, `test_product_usage`.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.


## 고정 시작 내용과 기존 데이터 호환 (2026-09-27)

- `opening_message`는 상품이 제공하는 고정 첫 대사이고 `start_set`은 사용자가 선택한 시작 장면/옵션이다. 서로 대체하지 않는다. 기존 단일 옵션 자동 선택·복수 옵션 명시 선택 계약을 유지한다.
- GET `/conversations/{id}/start` → `ConversationStartResponseDto`: `initial_snapshot_id`, `opening_mode`, `opening_message`, `start {title, content}`, `participants`, `primary_product_character_id`. 소유권 미확인 시 404다. 가짜 메시지 ID가 없고 POST `/conversations`의 기존 응답은 그대로다.
- `opening_mode=legacy_messages`는 migration 이전 대화 및 구형 작성자의 기본값이다. 기존 messages를 변경하지 않고 opening_message는 null로 응답하여 중복 표시/삽입을 막는다. 원문 문자열이나 생성 시각으로 첫 메시지를 추정하지 않는다. 검증된 snapshot이 없는 legacy는 start와 primary도 null일 수 있다.
- 신규 서비스 생성은 명시적으로 `opening_mode=snapshot`을 저장한다. 첫 대사는 messages에 없고 수정/되돌리기/리롤 ID도 없다. 고정 첫 대사는 최초 snapshot에서 읽으며 현재 버전 전환·최초 버전의 만료가 시작 이력을 바꾸지 않는다.
- runtime은 현재 캐릭터/모델/로어와 최초 start/첫 대사를 조합한다. settings에서 현재 opening_message를 제거하여 최초 첫 대사와 충돌하지 않는다. 고정 첫 대사는 요약 범위에서 제외하고 매 답변의 고정 프롬프트 예산에 포함한다. legacy 이력/기억은 기존 의미로 보존한다.
- Alembic `0025`와 초기 SQL `016_conversation_opening.sql`을 적용한다. snapshot 대화가 있으면 downgrade를 거절한다. 구형 API writer를 중지하고 migration → 새 API/클라이언트 순서로 배포한다. 서버 default는 legacy를 보수적으로 판정하기 위해 유지한다.

현재 클라이언트는 `.local_test/static/app.js`와 `apps/web`이다. 고정 내용을 별도 aside로 표시하고 답변 대상은 시작 조회의 primary_product_character_id로 정한다.

소유 대화 목록 `GET /conversations/mine`은 사용자 ID로 제한하고 생성 시각·ID 내림차순 커서를 사용한다. 대화 제목은 생성 당시 상품 스냅샷의 고정 제목이다. 마지막 메시지 문구는 상위 use case가 chat 공개 서비스를 통해 결합한다. 이미지 정보는 현재 계약에 없다.

## 저장소·조회·mapper 타입 정리 (2026-10-28)

repository.py, service/query.py, mapper/persistence.py와 types.py를 엄격 검사에 추가했다.
세션·UUID·시각·Command·Entity/목록/None 반환을 명시한다. 단건 조회와 이력 갱신의
scalar, 잠긴 조회의 FOR UPDATE/populate_existing, 생성·전환의 flush/참여자 교체 순서는
유지한다. 커서 인자 쌍·COUNT의 non-null·상위에서 잠근 전환 대상 존재는 assertion으로
표현한다. 공개 service의 미소유/미존재 LookupError와 커서 검증 정책은 유지한다.

대화 Info 변환은 필드를 명시한다. 원본 character ID, character snapshot ID, 상품 참여
슬롯 ID를 구별하고 Command는 키워드로 구성한다. 목록은 기존 limit+1과 생성 시각/ID
내림차순, 참여자는 role_order/ID 오름차순이다. 전체 개수는 페이지 커서와 독립적이다.
통계 raw 결과는 repository의 ConversationStatisticsRows로 표현하고 mapper에서 값 tuple
목록으로 바꾼다. 생성은 최초 snapshot, 전환은 도착 snapshot별로 세며 [start,end)와
상품 범위를 유지한다. 최초 snapshot IS NOT NULL 조건도 유지한다.

runtime의 캐릭터 JSON·로어 항목·설정과 통계 tuple 요소를 공개 값 타입으로 구체화했다.
RuntimeStart.title과 ConversationRuntimeView.start는 실제 nullable 입력/반환을 표현한다.
빈 제목/장면을 합성하거나 HTTP 스키마를 바꾸지 않는다. 최초 장면의 scene opening,
명시적 빈 문자열/None과 legacy 첫 대사 없음, 기존 default 키 조회의 KeyError를 유지한다.
상품 JSON의 TypedDict→개방형 JSON 및 발행 scene 옵션 구조에만 근거를 남긴 cast 2곳을
둔다. 런타임의 최상위 settings 사전 생성, 중첩 JSON/캐릭터 data/활성 entry의 기존 참조
공유도 유지하며 추가 깊은 복사나 실행 시 버전 검증을 도입하지 않는다.

test_conversation_query_contracts의 17건은 최소 SQLite 테이블의 소유자 범위·커서·개수,
조회 캐시 갱신·참여자 순서/nullable ID, 생성/원문 세대/전환 보존, 통계 시간 경계와
순수 mapper의 슬롯/JSON/시작 값 계약을 확인한다. FK/UNIQUE를 복제하지 않은 테스트이며
실제 PostgreSQL 잠금·동시성 보장은 검증하지 않는다. 당시 남긴 쓰기/시작/runtime service와
prompt 소비부 진단의 후속 결과는 아래에 기록한다. HTTP는 후속 엄격 검사 범위다.

## 쓰기·views 및 프롬프트 소비부 타입 정리 (2026-10-28)

service/ 디렉터리 전체를 엄격 검사에 포함했다. 시작·버전 전환·원문 세대·runtime 준비와
시작 내용/수동 로어 views의 AsyncSession을 명시한다. 같은 모듈의 버전 전환은 구체적
query 진입점을 참조하고, 상품 snapshot·통계 갱신 Command는 키워드로 구성한다.
character_commands/start_option/lorebook/snapshot_id/known_entry_ids로 역할을 구별한다.
시작 ID의 membership 검사 뒤 UUID non-null 가정은 assertion으로 표현한다.

기존 시작 옵션 자동/명시 선택과 primary 요구, 상품 잠금, 버전 전환의 대화 잠금·동일 버전
멱등 성공·순방향/노트/동의 검증은 유지한다. 원문 세대 변경은 소유 대화 잠금 안에서
실행한다. 각 트랜잭션·가용성/모델 선택/활성화/수동 ID 검증/최초 시작 조회의 순서도 같다.
runtime의 lock 인자나 최초 만료 snapshot 조회 정책을 새로 바꾸지 않았다.

test_conversation_command_contracts의 26건은 시작 성공/거절, 전환 멱등·동의·구성 검증과
저장/통계 호출, 원문 세대 잠금, 최초 시작/현재 primary 및 실제 참여자 구별, legacy 수동
목록과 pinned manual 항목, 스냅샷별 수동 ID 선택과 실패 후 세션 트랜잭션 종료를 확인한다.
서비스·저장소는 대역이며 실제 AsyncSession으로 상위 트랜잭션 범위를 실행한다. DB 잠금·
교차 도메인 쓰기 원자성·경합까지 검증한 것은 아니다. 프롬프트 쪽 내부 입력 전제와
직렬화 보존 검증은 prompt/ARCHITECTURE.md를 따른다.

## HTTP·모듈 전체 엄격 검사 완료 (2026-10-28)

router의 시작·전환·업데이트·시작 내용 반환을 기존 ResponseDto로 명시했다. manual-lore는
기존 dict[str, tuple[ManualLoreInfo,...]]를 반환하고 response_model=None으로 raw 응답
처리를 유지한다. DTO 이름·경로·필드·상태 코드·인증 훅은 보존한다. 단독 conversation
router의 OpenAPI는 전후 동일하다(5경로·12스키마). schema mapper는 포맷만 정리했고
schemas의 필드/검증은 변경하지 않았다.

필수 검사 범위를 conversation 디렉터리 전체로 묶었다. 전체 15 source files의 mypy가
통과하고 conversation의 시그니처 기준선은 0개다. 다른 디렉터리의 DB 모델·최상위 use case·
공유 HTTP 조립 코드까지 모두 완료했다는 뜻은 아니다.

test_conversation_http의 12건은 신뢰된 owner/session·경로/본문 ID, 201 시작·멱등 전환,
업데이트의 만료/노트, snapshot/legacy 시작 내용·nullable 참여자, manual raw 응답,
404/422 변환·미연결 의존성의 서비스 미호출·본문 user_id 거절을 확인한다. 시작 객체의
title=None은 기존 HTTP 모델이 여전히 거절하며 현재 errors 경계에서 422가 됨을 확인했다.
nullable 제목 정책은 별도 결함 검토 대상이며 이 단계에서 문자열을 합성하거나 DTO를
완화하지 않았다. 서비스 대역을 사용한 HTTP 계약 검사이며 실제 인가/DB 검증은 아니다.
