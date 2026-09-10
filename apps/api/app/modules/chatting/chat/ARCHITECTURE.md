# Chat 모듈

## 소유 데이터와 호출 경계

`messages`, `product_generations`, `chat_message_requests`를 소유한다. 기존 테이블명은 유지한다. ORM 읽기·쓰기는 `repository.py`에만 있고, Entity 해석은 `mapper/persistence.py`를 거친다. 타 모듈 테이블 JOIN 예외는 없다.

conversation의 공개 `get_owned_conversation(OwnedConversationCommand)`으로 소유권·현재 상품 버전을 확인하고, `list_conversation_characters`의 Info로 실제 참여 캐릭터를 확인한다. 별도 대화방 상태 컬럼은 없으며, 생성 시에는 기존 상품 버전 사용 가능 정책도 적용한다. Legacy 대화는 사용자 메시지 CRUD는 가능하고, 검증된 버전이 필요한 생성은 기존대로 거절한다.

chat → conversation / memory / product / billing / llm 방향으로 공개 service/types만 참조한다. conversation은 chat을 호출하지 않는다. 대화방 생성과 첫 캐릭터 메시지 저장은 `app/use_cases/conversations.py`에서 두 공개 Command를 같은 트랜잭션으로 조합한다. 상품 통계도 `app/use_cases/product_statistics.py`가 각 도메인의 사실 조회와 product의 통계 저장을 조정하므로 product → chat 역방향 의존성이 없다.

## 파일별 책임

- `service/command/messages.py`: 사용자 저장·마지막 메시지 교체·되돌리기, 내부 캐릭터 저장/교체, 인가·멱등성·충돌·메모리 무효화 조정.
- `service/query/messages.py`: 소유권을 확인한 메시지 커서 페이지 조회.
- `service/command/generation.py`: 기존 생성 예약·완료·실패·취소·stale, 입력/결과 메시지 저장, usage 및 통계 갱신 요청. 외부 LLM 호출은 하지 않는다.
- `service/query/generation.py`: 생성 당시의 불변 사실을 통계 Info로 제공한다.
- `types.py`: 위 기능의 Command와 Info, 커서, 업무 오류. `schemas.py`, `mapper/schema.py`, `router.py`: HTTP DTO·변환·기존 인증/세션 훅 연결.

메시지 편집과 생성 수명주기는 입력·권한·실패 조건이 달라 기능 파일로 나눴다. 밀접한 메시지/생성 저장소는 단일 repository를 유지했다. 외부 호출·프롬프트·리롤·스트리밍용 빈 계층은 추가하지 않았다.

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
- 예약·완료는 각각 짧은 DB 유스케이스다. 그 사이 호출자가 외부 생성을 수행하더라도 DB 트랜잭션을 유지하지 않아야 한다. 이번 구현에는 외부 호출이 없다.

## 연결 데이터

메모리의 단일 source_message_id로는 요약·파생 사실의 전체 의존 범위를 알 수 없어 교체/되돌리기 때 memory 공개 service가 해당 대화의 모든 기억·요약을 삭제한다. 출처가 없는 legacy 메모리도 포함한다. 다른 방 메모리는 유지한다. 임베딩·요약 재생성은 하지 않는다.

생성 status/result_digest/message_count/finished_at와 usage/payment/credit 기록은 이미 발생한 사실로 유지한다. `history_invalidated_at`은 해당 대화의 원래 생성 맥락이 변경됐음을 보수적으로 표시한다. message_count는 현재 화면의 메시지 수가 아니라 원래 성공 출력 수이며 통계도 그 의미를 유지한다. 완료 재전송은 메시지나 사용량을 다시 쓰지 않는다. messages→generation 및 usage→generation FK는 유지되고, 삭제 시 generation이 역으로 삭제되지 않는다.

version_changes는 메시지를 참조하는 컬럼이 없으며 conversation과 두 상품 snapshot을 참조한다. 이 레코드와 FK는 변경하지 않는다. 대화방 전체 삭제는 이번 범위가 아니며 기존 generation→conversation FK 정책도 유지한다.

## 미연결 범위

HTTP는 기존 `app.http.dependencies`를 사용한다. 실제 인증/세션은 여전히 503 미연결 훅이며 우회 인증을 만들지 않았다. 테스트에서 같은 훅에 소유자와 PostgreSQL 세션을 주입해 계약을 확인한다. 외부 LLM/임베딩, 프롬프트·로어 활성화, 새 답변 리롤, 스트리밍·이미지 선택은 이번 범위 밖이다.
