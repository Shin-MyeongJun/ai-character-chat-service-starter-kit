# Chat 모듈

## 소유 데이터와 호출 경계

`messages`, `product_generations`, `chat_message_requests`, `generation_prompts`를 소유한다. 기존 테이블명은 유지한다. ORM 읽기·쓰기는 `repository.py`에만 있고, Entity 해석은 `mapper/persistence.py` 및 `mapper/prompts.py`를 거친다.

conversation의 공개 `get_owned_conversation(OwnedConversationCommand)`으로 소유권·현재 상품 버전을 확인하고, `list_conversation_characters`의 Info로 실제 참여 캐릭터를 확인한다. 별도 대화방 상태 컬럼은 없으며, 생성 시에는 기존 상품 버전 사용 가능 정책도 적용한다. Legacy 대화는 사용자 메시지 CRUD는 가능하고, 검증된 버전이 필요한 생성은 기존대로 거절한다.

chat → conversation / memory / product / billing / llm 방향으로 공개 service/types만 참조한다. conversation은 chat을 호출하지 않는다. 대화방 생성과 고정 시작 내용은 conversation이 소유한다. 신규 첫 대사는 messages에 저장하지 않는다. 상품 통계도 `app/use_cases/product_statistics.py`가 각 도메인의 사실 조회와 product의 통계 저장을 조정하므로 product → chat 역방향 의존성이 없다.

## 파일별 책임

- `service/command/messages.py`: 사용자 저장·마지막 메시지 교체·되돌리기, 내부 캐릭터 저장/교체, 인가·멱등성·충돌·메모리 무효화 조정.
- `service/query/messages.py`: 소유권을 확인한 메시지 커서 페이지 조회.
- `service/query/messages.py`의 내부 공개 `list_memory_source`는 인가된 현재 선형 이력의 정상 저장 메시지를 position 순으로 값 타입으로 제공한다. memory/use_cases는 message ORM을 직접 참조하지 않는다.
- `service/query/generation.py`의 `get_generation_state`는 최상위 use_case가 응답 저장 뒤 같은 대화의 memory 작업을 예약할 수 있도록 생성의 대화 id를 공개 Info로 제공한다.
- `service/command/generation.py`: 기존 생성 예약·완료·실패·취소·stale, 입력/결과 메시지 저장, usage 및 통계 갱신 요청. `BeginGenerationCommand`의 선택적 input_message_id/expected_revision은 마지막 사용자 메시지를 검증해 재저장하지 않는다. 미지정인 기존 호출은 종전대로 입력을 저장한다. execution은 신뢰된 최상위 호출자가 확정한 모델이다.
- `service/command/answers.py`: 최상위 오케스트레이터를 위한 요청/대화 잠금, 입력 참조 검증, metadata/lease 쓰기 및 만료 생성 조회. 새 테이블 없이 `product_generations.answer_metadata`와 `answer_lease_until`을 소유한다.
- `service/query/generation.py`: 생성 당시의 불변 사실을 통계 Info로 제공한다.
- `types.py`: 메시지/생성/답변/문맥 준비의 Command·Info·오류. `schemas/{messages,answers}.py`, `mapper/schema/{messages,answers}.py`, `router/{messages,answers}.py`: HTTP DTO·변환·실행. `dependencies.py`는 답변 runtime 연결만 담당한다.

메시지 편집과 생성 수명주기는 입력·권한·실패 조건이 달라 기능 파일로 나눴다. 밀접한 메시지/생성 저장소는 단일 repository를 유지했다. 답변의 외부 호출과 복구는 선택적 workflow에 두며 리롤·스트리밍용 빈 계층은 추가하지 않았다.

## 조회·변환 타입 계약 (2026-10-26)

- `service/query`와 `mapper` 폴더 전체를 엄격 품질 검사 범위에 포함한다. 조회 서비스는
  `AsyncSession`과 Command를 받고 공개 Info 또는 값 사전을 반환한다.
- 미리보기는 `dict[UUID, str]`, 대화 활동은 `dict[UUID, ConversationActivityInfo]`다.
  SQL Row 형태와 집계 컬럼 순서는 repository의 타입 별칭으로 표현하고 공개 반환에 노출하지 않는다.
- 메시지·생성 상태·원문 프롬프트는 필드를 명시해 Info로 변환한다. 페이지와 기억 원문은
  같은 메시지 mapper를 재사용하며, 추가 한 행에 따른 커서·truncated 의미를 유지한다.
  단건 mapper의 overload는 None 입력과 존재하는 입력의 반환을 구별한다.
- 프롬프트 목록 Row는 `_select_generation_summaries`의 12개 컬럼 순서와
  `GenerationPromptSummaryValues`가 대응한다. 목록에는 원문과 answer_metadata를 포함하지 않는다.
  OUTER JOIN의 원문 미기록 상태는 prompt_recorded=False와 nullable 필드로 유지한다.
- 생성 통계의 공개 list/tuple 표현은 유지하고 각 요소 타입만 명시한다. HTTP 커서 형식,
  소유권·관리자 검증, 잠금 옵션, JSON 공유/복사 정책, 기존 키워드 인자 이름은 유지한다.
- 당시 남긴 repository 쓰기와 types의 나머지 타입 부채는 아래 메시지 쓰기 단계에서
  정리했다. 생성/답변 command·workflow의 완료 범위와는 구별한다.

## HTTP 및 내부 쓰기 계약

| 메서드·경로 | 입력 | 반환 |
| --- | --- | --- |
| POST `/conversations/{conversation_id}/messages` | `request_key`, `content` | 201 MessageResponseDto |
| GET 같은 경로 | `limit` 1–100(기본 50), `cursor` | 200 MessagePageResponseDto (`items`, `next_cursor`) |
| PUT `…/messages/{message_id}` | `content`, `expected_revision` | 200 MessageResponseDto |
| DELETE `…/messages/{message_id}` | 없음 | 200 RewindMessagesResponseDto (`deleted_count`) |

소유하지 않은 대화방·해당 방에 없는 메시지는 404, 사용자 API로 캐릭터 메시지 교체는 403, 진행 중 생성/마지막 메시지 제한/수정 버전 충돌/요청 키 재사용 충돌은 409, 잘못된 내용·커서는 422다. DELETE는 대상 포함 `position >= target.position`의 실제 삭제 건수를 반환하고 재시도 시 대상이 이미 없으면 404다. 상품 버전과 전환 이력은 되돌리지 않는다.

공개 POST는 사용자 메시지만 저장한다. sender/model/character/generation/owner 필드는 입력에 없으며 extra 필드는 거절한다. `CreateCharacterMessageCommand`, `ReplaceCharacterMessageCommand`는 HTTP에 노출하지 않는 내부 신뢰 경계다. 실제 AI 출력은 `finish_generation`에서만 generated_by_ai=true 및 생성/모델 출처를 붙인다. 내부 캐릭터 교체도 새로운 생성 사실을 만들지 않는 내용 교정이다. 교체된 메시지의 생성/모델/token/emotion 출처를 지우고 generated_by_ai=false로 설정한다. 생성 비용을 다시 기록하지 않는다.

PUT은 지정한 메시지가 해당 대화의 마지막 메시지이고 예상 revision이 같을 때만 같은 ID/position을 유지하며 내용을 변경한다. 사용자/캐릭터 Command를 구분하며, 캐릭터 교정은 현재 버전의 해당 참여 캐릭터 메시지에만 허용한다.

## 순서·멱등성·트랜잭션

- 전역 DB identity `position`으로 정렬하고 `(conversation_id, position)` 유일 제약으로 인덱싱한다. 대화방 잠금 안에서 할당하므로 같은 시각·서로 다른 요청도 커밋된 대화 내 순서가 안정적이다. 생성의 입력과 여러 출력도 저장 순서를 따른다. 기존 메시지는 마이그레이션에서 `(created_at, id)`로 순번을 채운다.
- 커서 `v1:{conversation_id}:{position}` 다음을 오름차순 조회한다. 삭제된 커서 메시지가 없어도 경계는 유효하며 다른 방 커서는 거절한다. 페이지는 호출 시점의 현재 내역이다. 페이지 사이 되돌리기를 포함한 전체 스냅샷 보장은 하지 않는다.
- 저장 키는 대화방 내 유일하며 발신자·캐릭터·내용 digest와 비교한다. 같은 요청은 같은 메시지를 반환한다. 삭제 뒤 receipt의 메시지 FK만 SET NULL로 남기며, 삭제/교체된 원본의 재시도는 409로 거절해 복원하지 않는다. 생성 request_key/digest도 기존대로 보존한다.
- 모든 쓰기는 `use_case_transaction`을 시작하거나 상위 범위에 참여한다. 생성 시작과 모든 메시지 추가/교체/되돌리기는 같은 conversation row를 FOR UPDATE로 잠근다. 완료도 conversation → generation 순서다. 생성 예약 요청 키 advisory lock은 기존 멱등성 범위다.
- pending 생성이 있으면 신규 메시지 저장·새 생성·교체·되돌리기를 거절한다. 동일 요청의 멱등 조회는 허용한다. 생성 시작과 변경이 동시에 요청돼도 잠금을 먼저 획득한 트랜잭션이 완료된 상태에서 다음 요청을 검사한다.
- 예약·완료는 각각 짧은 DB 유스케이스다. 그 사이 호출자가 외부 생성을 수행하더라도 DB 트랜잭션을 유지하지 않아야 한다. chat의 AnswerOrchestrator workflow가 예약 commit 뒤 외부 호출을 수행한다.

## 연결 데이터

교체/되돌리기 때 memory 공개 service가 `history_revision`을 증가시키고 해당 대화의 모든 기억·요약·예약을 삭제한다. 출처가 없는 legacy 메모리도 포함하고 다른 방은 유지한다. 실행 중 작업은 결과 저장의 revision/range 검증에서 거절된다. 단순 후속 메시지 append는 revision을 바꾸지 않는다. 성공 응답과 기억 예약의 원자적 조립은 `service/workflow/answers.py`의 `finish_generation_and_schedule_memory`가 담당한다.

생성 status/result_digest/message_count/finished_at와 usage/payment/credit 기록은 이미 발생한 사실로 유지한다. `history_invalidated_at`은 해당 대화의 원래 생성 맥락이 변경됐음을 보수적으로 표시한다. message_count는 현재 화면의 메시지 수가 아니라 원래 성공 출력 수이며 통계도 그 의미를 유지한다. 완료 재전송은 메시지나 사용량을 다시 쓰지 않는다. messages→generation 및 usage→generation FK는 유지되고, 삭제 시 generation이 역으로 삭제되지 않는다.

version_changes는 메시지를 참조하는 컬럼이 없으며 conversation과 두 상품 snapshot을 참조한다. 이 레코드와 FK는 변경하지 않는다. 대화방 전체 삭제는 이번 범위가 아니며 기존 generation→conversation FK 정책도 유지한다.

## 미연결 범위

HTTP는 기존 `app.http.dependencies`를 사용한다. `app.main`은 DB 세션을 실제 session factory에, 기본 owner 훅을 identity의 쿠키·CSRF·사용자/세션 검증에 연결한다. `create_app(authenticate=...)`는 기존 명시적 주입 계약으로만 유지하며 기본 실행에 필요하지 않다. 개별 라우터만 조립하고 의존성을 연결하지 않으면 기존 503 훅이 적용된다. 비스트리밍 답변은 `app.http.answers` → `app.modules.chatting.chat.service.workflow.answers`에서 조율한다. chat 자체는 외부 호출을 하지 않는다. 스트리밍·리롤 UI·이미지는 제외한다.

답변 키는 사용자 전체 범위이며 입력 ID/revision/대상 캐릭터를 비교한다. pending 재전송은 202, 성공 재전송은 저장된 metadata 답변, 이력 변경 후 재전송은 409다. 결과 staging 후 최상위 AnswerOrchestrator가 기존 finish·usage·memory 예약과 billing 확정/해제를 원자적으로 수행한다. lease 만료 복구는 저장된 결과만 재사용하며 호출 결과가 없으면 failed/cancelled 사실과 불확실성을 보존한다. 상세 오류와 원문은 로그에 출력하지 않는다. 기존 legacy pending(lease 없음)은 이번 복구 대상이 아니다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: `router.py` → `service/command/messages.py` 또는 `generation.py` → `repository.py` → `mapper/persistence.py` → `types.py`. answers 전용 입력 검증은 `service/command/answers.py`와 최상위 오케스트레이터를 함께 본다.

`get_owned_conversation`은 소유권과 값을 확인하는 조회다. 버전 사용 가능 여부는 생성 경로가 product 공개 서비스로 추가 확인한다. repository만 직접 호출한다고 같은 인가·멱등성·상태 검사를 보장하지 않는다. 대조 테스트는 `test_chat_messages`, `test_chat_http`, `test_product_usage`, `test_nonstream_answers`다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.

## 생성 과금 연결과 실행권 (2026-09-22)

전체 생성 조율은 chat/service/workflow/answers.py가 소유한다. chat은 credit을 직접 호출하지 않으며,
생성 당시 `answer_metadata` version 2에 실행 token, 준비/prompt digest, 토큰 산정 버전과
입력/출력 예산, billing 요청 UUID·견적·예약 ID·예약액을 보존한다. 기존 JSONB를 사용해
신규 migration이나 기존 행 재작성은 없다. 상세 구조는 [생성 연결 문서](../../../../../../docs/billing-generation-integration.md)를 따른다.

`UpdateAnswerCommand`에 선택적 execution_token/recover(default False)를 추가했다.
신규 token이 있는 생성의 후속 staging은 저장된 token과 유효 lease가 필요하고,
recover=True는 만료된 lease에서만 허용한다. 실행/과금 스냅샷 변경, 이미 저장된 result_ready
덮어쓰기, terminal 상태의 늦은 staging을 거절한다. 기존 token 없는 metadata 계약은 보존한다.

finish_generation은 후보 outcome을 실제 succeeded/stale로 판단한 뒤 usage.cost_credit을 정한다.
실제 succeeded만 전달된 예약액을 기록하며 failed/cancelled/stale에는 0을 기록한다.
그 반환 상태를 받은 상위 orchestrator가 billing 공개 서비스를 통해 확정/해제하므로
답변·usage·memory·차감이 함께 rollback된다. 과거 연결 없는 생성은 청구 0으로 복구하며
기존 완료 기록/원장을 임의 수정하거나 소급 차감하지 않는다.


## 답변 workflow (2026-09-27)

세션 생성 의존성은 `app.db.types.SessionFactory`로 표현한다. 기억 workflow의 내부
읽기/저장/색인/완료 함수도 공개 Info를 입력·반환 타입으로 명시하며 기존 tuple 결과를
유지한다. `AnswerOrchestrator.sessions` 속성과 생성자의 호출 방식은 호환을 위해 유지한다.
2026-10-26 타입 정리는 요약 임계치·작업 lease·재시도·잠금 정책을 변경하지 않는다.

- `service/workflow/answers.py`: 준비 재검증 → 생성·견적·credit 예약 확정 → LLM → result_ready staging → 메시지·usage·기억 예약·과금 확정/해제. 정상 완료와 lease 복구는 동일 `_finalize`와 완료 규칙을 사용한다. 불확실한 공급자 호출을 다시 실행하지 않는다.
- `service/workflow/answer_preparation.py`: 공개 conversation/memory 서비스와 chat 원문 조회로 문맥을 수집하고 고정 예산과 미요약 원문을 확보한다. 초과 원문을 조용히 잘라내지 않는다.
- `service/workflow/memory.py`: `ProcessMemoryWorkCommand`로 받은 작업의 pending 색인 재개·요약·임베딩·저장 전 원문/revision 재검증·실패 기록. 요약 정책·검색·임베딩·저장·작업 전이는 memory 소유다.
- `mapper/prompt.py`: MessageInfo → prompt 자체 PromptMessageInfo 순수 변환. prompt는 chat 타입/서비스를 참조하지 않는다.
- command/query는 workflow를 호출하지 않는다. workflow는 구체적인 chat command/query 파일을 호출하며 repository를 직접 사용하지 않는다. `main`/`memory_worker`는 의존성과 반복 실행만 조립한다.

답변의 요청 키·실행권·lease·staging·stale/cancelled·가격·사용량·기억 예약 계약은 기존 과금 구현 그대로다. 답변 HTTP 경로와 상태 코드를 유지하고, 응답 DTO에 선택적 `price_credit`를 추가해 기록된 예약 견적 금액을 보여준다. 별도 answer 모듈이나 기존 use_cases 재노출은 없다.

## 최종 답변 프롬프트 기록 (2026-10-21)

- `service/command/prompts.py`의 `save_generation_prompt(SaveGenerationPromptCommand)`는
  conversation → generation 잠금, 실행 token·digest·provider·출력 예산·예약/lease 검증 후
  UTF-8 원문의 SHA-256과 원문을 저장한다. 같은 원문의 재호출은 기존 시각을 유지하고,
  다른 원문/실행 설정은 거절하며 UPDATE 경로를 제공하지 않는다.
- `service/workflow/answers.py`는 최종 prompt 확정 및 준비 재검증 후 생성·견적·크레딧
  예약·answer metadata·프롬프트 저장을 **같은 트랜잭션**에 조립한다. commit 성공 반환 후에만
  calling staging과 LLM 호출로 간다. 저장 실패는 예약 전체 rollback이며 외부 호출은 없다.
  commit 응답 유실 시 기존 요청을 조회/복구하며 불확실한 외부 호출을 새로 실행하지 않는다.
- 현재 하나의 생성 ID는 하나의 실행권/외부 호출이다. SDK 내부 재시도나 lease 복구용
  추가 프롬프트/시도 행은 만들지 않는다. 복구는 원문을 재구성하거나 덮어쓰지 않는다.
- 원문은 공급자 어댑터 변환 **전** `prompt.request_json`의 전체 문자열이며 TEXT로 보존한다.
  JSONB 재직렬화나 원본별 사후 재조립을 하지 않는다. system/reference_data, 캐릭터·로어·기억,
  역할별 이력·현재 입력을 포함한 최종 구조를 유지한다. SDK 전송 HTTP 본문 기록이 아니다.
- `generation_prompts.generation_id` PK/FK가 생성당 한 행을 보장한다. FK는 CASCADE로
  의도적인 부모 생성 삭제 시 고아를 남기지 않는다. 메시지 편집/되돌리기는 기존대로
  generation을 삭제하지 않으므로 기록이 남는다. 기존 generation→conversation/user/product
  및 usage/payment FK는 바꾸지 않는다. 기존 대화방 전체 삭제 제약도 그대로다.
- 저장 시각·형식 버전(1)·digest·provider·max_output_tokens를 저장한다.
  model_id/model_name/reasoning_effort는 생성의 기존 불변 필드를 사용한다. 따라서 현재
  models/providers 카탈로그를 JOIN하여 과거 실행 설정을 추정하지 않는다. reasoning_effort=none은
  LLM Command에서 None으로 전달되는 기존 계약이다. 공급자 키/헤더/SDK 설정은 읽거나 저장하지 않는다.
- `service/query/prompts.py`의 공개 `list_generation_prompts(ListGenerationPromptsCommand)`와
  `get_generation_prompt(GetGenerationPromptCommand)`는 identity로 활성 admin을 재검증한다.
  Row를 공개하지 않고 `GenerationPromptPageInfo`/`GenerationPromptDetailInfo`를 반환한다.
  operations_reporting은 이 service/types만 이용한다. 일반 사용자·작가용 조회 API는 없다.
- 목록 SQL은 원문/answer_metadata를 SELECT하지 않는다. 상세에서만 원문을 반환하며,
  과거 미기록은 prompt=None, 생성 미존재는 LookupError다. 미기록 이유나 전송 성공은 추정하지 않는다.
  저장 사실은 전송/응답 성공의 증거가 아니며 실패·호출 전 중단 기록도 보존한다.
- Alembic 0030 / 초기 SQL 020 / GenerationPrompt ORM을 함께 관리한다. backfill은 없으며
  행이 있는 상태의 downgrade는 손실 방지를 위해 거절한다. DBA 직접 UPDATE를 막는
  트리거는 없고 애플리케이션 쓰기 경계가 불변성을 보장한다.
- 애플리케이션 로그/오류에 원문을 출력하지 않는다. 기본 API 엔진은 hide_parameters=True로
  SQL 오류의 바인드 값도 숨긴다. answer_metadata와 일반 답변 DTO에는 원문을 추가하지 않는다.

파일은 기존 메시지/생성 저장소를 유지하고, 민감 원문 저장·조회 Command/Query와 순수 mapper만
기능별 파일로 분리했다. prompt 모듈은 순수 구성 책임을 유지하며 기억 요약·임베딩 기록은 제외한다.
작가용 부분 조회는 공개 범위/지침 비노출 정책을 별도 설계할 후속 과제이며 이번 구현에 포함하지 않는다.

API/검증 범위는 [프롬프트 조회 계약](../../../../../../docs/generation-prompts.md)을 따른다.

새 대화의 고정 첫 대사는 conversation 시작 조회에서 받고 prompt의 고정 assistant 문맥으로 전달한다. 메시지 목록이나 요약 원문에는 들어가지 않는다. legacy_messages 대화의 기존 첫 메시지는 이력으로 보존하며 snapshot 첫 대사를 추가하지 않는다. 기존 이력 요약 의미를 소급 변경하거나 기존 기억을 일괄 재작성하지 않는다.
`list_conversation_previews`는 소유 대화 목록 페이지에 대해 마지막 메시지 문구만 조회한다. chat repository의 Conversation JOIN은 `Conversation.user_id` 소유권 스코핑에만 쓰며 대화 컬럼은 반환하지 않는다. 상위 `use_cases/conversation_directory.py`가 두 모듈의 공개 결과를 조합한다.


## 본인 reporting 사실 조회 (2026-10-15)

get_account_generation_statistics(GetAccountGenerationStatisticsCommand)는 identity의
최신 활성 사용자 확인 후 자기 소유 ProductGeneration을 user_id 및 created_at [start,end)로
SQL 스코핑해 현재 상태별 건수를 제공한다. 최대 731일 timezone-aware 범위이며
pending도 포함한다. 기존 작품 통계의 finished_at 완료 코호트와 기간 기준이 다르다.
repository/mapper/types에 최소 연산을 추가했고 메시지·metadata·다른 사용자·모델 내부
정보는 반환하지 않는다. 읽기 중 autoflush를 금지하며 생성 쓰기나 회복은 수행하지 않는다.

## 메시지 쓰기·공유 저장소 타입 정리 (2026-10-28)

repository.py, service/command/messages.py와 types.py 전체를 엄격 검사에 추가했다.
세션·UUID·시각·입력 Command·Entity/목록/None 반환을 명시했다. get_message는 삭제된
receipt의 message_id=None도 기존대로 조회할 수 있고, service가 재생성 대신 충돌로
판단한다. scalar SQL·populate_existing·잠금·flush 순서와 명시적 generation prompt 저장
필드는 유지한다. 삭제 건수만 DML의 CursorResult 계약을 근거로 cast해 rowcount를 읽는다.
생성 완료는 상위의 존재 확인/잠금 전제를 assertion으로 표현한다.

메시지 내부 helper의 사용자/캐릭터 Command와 bool 분기를 overload·Literal로 연결하고
캐릭터 분기 입력은 타입 assertion으로 명시한다. receipt_entity/message_entity/last_entity/
replaced_entity를 구별한다. 기존 content/request/revision 검증·digest 직렬화, 정확한
재전송의 pending 검사 이전 반환, 삭제/교체 후 요청 키 충돌, 마지막 메시지와 버전/참여자
검증, memory→generation history 무효화→쓰기/되돌리기 순서는 유지한다.

답변 metadata는 개방형 재귀 JSON 별칭으로 표현한다. 저장 v1/v2 및 확장 키·중첩 참조를
보존하며 새로운 실행 시 JSON 검증·보정·깊은 복사를 추가하지 않는다. AnswerConfig의
기존 __post_init__은 반환 None만 명시했다. 이 값 타입의 구체화가 생성/답변 command와
workflow 전체의 엄격 검사 완료를 뜻하지는 않는다.

test_chat_message_contracts의 24건은 서비스 대역/실제 AsyncSession으로 사용자/캐릭터
저장·재전송·영수증 충돌·편집 거절·기억 무효화 실패·되돌리기·인가/입력 거절을 확인한다.
SQL 검사는 SQLite 최소 테이블에서 재조회, 출처 초기화, 포함 삭제와 receipt SET NULL,
기존 입력 참조에 따른 생성 입력 저장 여부, metadata/lease/원문 보존을 확인한다.
메시지 position은 테스트용 증가 함수로 대체하며 PostgreSQL Identity 자체를 검증하지 않는다.
선택한 receipt FK와 메시지 position UNIQUE만 복제했고 나머지 FK/CHECK·DB 잠금/경합·
실제 memory/billing 원자성과 외부 모델 호출은 미검증이다.

## 생성·답변·프롬프트 저장 command 타입 정리 (2026-10-28)

service/command 전체 5파일을 엄격 검사에 편입했다. generation.py의 digest 입력/반환을
GenerationResult/str로, generation·answers·prompts의 세션을 AsyncSession으로 명시했다.
generation_entity는 mapper에 전달하는 저장 결과이며 업무 판단은 기존 Info로 수행한다.
재귀 AnswerMetadata를 비교·저장하는 command는 기존 v1/v2 및 확장 키를 그대로 소비한다.
새로운 JSON 정규화/복사나 기본값 정책은 추가하지 않았다.

save_generation_prompt는 최초 소유 생성 확인 후 conversation 잠금 아래의 generation
재조회가 존재한다는 기존 전제를 assertion으로 표현한다. 이 전제가 깨진 비정상 경로는
기존 None 속성 접근의 AttributeError 대신 AssertionError가 된다. 정상·충돌·재전송의
계약은 같다. 저장된 동일 프롬프트의 선행 반환, 실행권·예약·lease 검증 순서를 유지하며
새 not-found 정책이나 동시성 안전성을 추가한 것으로 보지 않는다.

생성의 request-key digest·잠금 순서·기존 입력 참조, terminal 결과 digest 재전송,
stale의 출력/청구 크레딧 제외와 usage 기록, 메시지→usage→생성 완료→통계 예약의
상위 트랜잭션을 유지한다. 답변의 소유 token·live/recovery lease·불변 실행 스냅샷과
result_ready의 전체 metadata 일치 검사도 같다. Any/cast/ignore를 추가하지 않았다.

기존 prompt command/workflow·answer prompt·message SQL 계약과 생성/과금/답변,
billing persistence·moderation을 함께 재실행해 108 passed, 63 skipped를 확인했다.
TEST_DATABASE_URL을 제거했으며 실제 PostgreSQL 잠금·동시성·원자성 검증을 대체하지
않는다. workflow/answers.py와 chat HTTP router의 엄격 타입 편입은 후속 범위다.

## 답변 workflow 타입 정리 (2026-10-28)

service/workflow 전체 4파일을 엄격 검사에 편입했다. answers.py의 준비 결과는 기존
5요소 tuple을 유지하는 타입 별칭으로 표현했다. 세션·UUID·예외·metadata·lease와
준비/재개/staging/확정/복구의 반환을 명시했으며 self.sessions 호환 이름은 유지한다.
digest는 기존 JSON 정렬/기본 str 변환을, usage는 bool 제외·저장 범위·알 수 없는 값의
0 처리와 원본 TokenUsageInfo의 None 구분을 그대로 유지한다.

내부 _StoredIdentity/_StoredBilling/_StoredAnswer는 workflow의 기존 v1/v2 작성 필드 중
소비하는 필드만 표현하는 TypedDict 읽기 뷰다. 저장 JSON은 계속 개방형 AnswerMetadata다.
staging token, 복구 token, 완료 결과, 응답 변환의 네 cast는 이 workflow의 기존 작성
규칙을 근거로 한다. 런타임 검증·변환·기본값 추가가 아니며 누락 키/손상 타입의 기존
오류나 참조 공유·확장 필드를 보정하지 않는다. 손상 JSON 정책은 별도 후속 과제다.

요청 identity의 manual_entry_ids는 기존대로 값이 있을 때만 문자열 정렬 목록으로
기록한다. 실행 token은 같은 생성 문자열을 지역 변수로 보관해 prompt 저장에 전달한다.
준비 전 기존 요청 확인, 예약 재검증, quote/generation/credit/prompt의 commit 후 외부
호출, calling/result_ready staging, 불확실 호출 재실행 금지와 lease 복구를 유지한다.
완료 시 성공/실패/stale에 따른 예약 확정/해제, 금액 일치 검사, memory 예약도 같다.

기존 prompt workflow/command·answer prompt·nonstream·과금·가격/HTTP·생성 관련 회귀는
41 passed, 57 skipped다. 실제 PostgreSQL 트랜잭션/잠금·동시성·공급자 호출의 검증은
아니며 테스트 대역을 사용하는 오프라인 흐름과 구분한다. Any/ignore/기준선 예외는
추가하지 않았다. chat HTTP router의 통합 판정은 해당 병렬 작업의 후속 범위다.

## HTTP 병렬 결과 통합 (2026-10-28)

주 대화가 router를 포함한 모듈 전체를 직접 Ruff format/check·mypy로 확인하고 공용
엄격 검사 범위를 chat 디렉터리로 통합했다. dependencies.get_answer_orchestrator는
main이 설정한 앱 상태의 동적 값을 AnswerOrchestrator로 연결한다. cast는 조립 시
할당 계약을 표현하며 None의 기존 503과 주입된 실행/테스트 대역을 유지한다.
새 isinstance 제한·구성 기본값·인증 연결을 추가하지 않았다.
