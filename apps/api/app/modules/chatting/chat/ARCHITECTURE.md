# Chat 모듈

## U19 a7 답변 이미지 선택·저장·복구

- `service/answer_images.py`는 생성에 고정된 runtime 이미지 카탈로그에서 답변 캐릭터와
  활성 `(lorebook_snapshot_id, lore_entry_id)`에 속한 후보를 발행 순서로 최대 24개 고른다.
  로어의 캐릭터 대상 범위도 기존 프롬프트와 동일하게 적용한다. 후보 키는 요청별로 격리한다.
- 기존 nonstream 답변 경로에 선택적인 JSON 출력 envelope를 지원한다. 서버의 출력 지시만
  system에 두고 후보 키·종류·태그·설명은 user 참조 데이터로 전달한다. 이미지/파일 UUID나
  URL은 모델에 보내지 않는다. 최종 입력 예산에서 뒤쪽 후보부터 제거하며 후보가 없으면
  기존 텍스트 요청을 그대로 실행한다. 외부 모델이 envelope를 사용하지 않으면 텍스트로 보존한다.
- 서버는 `(candidate_key, after_paragraph)`를 검증하고 잘못된 키·위치·bool을 무시한다.
  빈 줄 기준 문단 뒤 위치를 안정 정렬해 최대 3개를 적용하며 같은 이미지 반복을 보존한다.
  텍스트 블록의 연결은 원문과 정확히 같고 원문 이미지 문법/URL은 파일로 승격하지 않는다.
- 검증된 순서 있는 블록을 `answer_metadata.content_blocks`의 result_ready에 내구 저장한다.
  복구는 이 블록만 사용하며 공급자 호출·후보 선정·최신 파일 재해석을 반복하지 않는다.
  `GeneratedMessage.content_blocks`는 선택 필드이며 미지정 구형 완료 digest는 그대로 유지한다.
- `messages.content_blocks`(Alembic 0039/초기 SQL 029)는 현재 revision의 nullable JSONB다.
  메시지 저장 뒤 a5 공개 해금 서비스를 같은 세션에서 호출하며 기존 usage·크레딧 정산·기억
  예약과 한 트랜잭션으로 커밋한다. 실패·취소·stale와 terminal 재생에서는 해금하지 않는다.
  구형 행/내부 텍스트 쓰기는 NULL이고 새 nonstream 텍스트 결과는 텍스트 블록 배열이다.
- GET messages의 선택적 `content_blocks`는 a6의 공통 HTTP DTO/URL 변환을 재사용한다.
  파일은 `/conversations/{conversation_id}/messages/{message_id}/revisions/{revision}/blocks/{block_index}/content`로 읽는다.
  `service/query/image_blocks.authorize_message_image_block`이 방 소유권, 실제 생존 메시지,
  정확한 revision과 이미지 위치를 검사한 뒤 a5 snapshot 보존 참조를 반환한다.
  현재 앨범 해금·최신 버전·실행 만료는 과거 본문의 읽기 조건이 아니다.
- 파일은 발행 시 등록한 snapshot 참조로 보존한다. 생성과 메시지의 snapshot FK 및 a4의
  만료 후 참조 유지 정책을 재사용한다. 향후 발행본 물리 삭제/참조 해제를 구현할 때에는
  result_ready·보존 메시지 참조가 남은 스냅샷의 파일 pin을 해제하면 안 된다.
- 현재 이력은 단일 revision만 조회한다. 텍스트 교정은 content_blocks를 NULL로 바꾸고
  revision을 올리며 되감기는 메시지를 삭제하므로 이전 발생 URL은 404다. 해금은 유지한다.
  a8의 이력 복사/리롤/분기는 당시 `content_blocks`를 그대로 복사해야 하며 새 파일로 바꾸거나
  후보를 재선정해서는 안 된다. 조회 가능한 revision 확장은 해당 이력 엔진의 책임이다.
- a6와 담당 합의: 공통 ProductTypes 블록 값·`http/content_blocks.py`는 a6 소유로 재사용;
  a7은 메시지 블록·발생 인가와 `http/media.py`의 메시지 endpoint만 확장한다.

## U27 호환 경로 정리 (2026-11-02)

use_cases/conversation_directory.py 호환 연결을 제거했다. HTTP 목록은 chat 공개
service/views.list_recent_conversations와 types를 직접 사용한다. HTTP cursor_created_at을
Command.cursor_activity_at으로 연결하며 DTO·기본값·인가·COUNT/페이지 쿼리는 유지한다.
LLM 실행 결정은 공개 service/command/replacement.py를 직접 호출한다.

## U27 빈 파일 정리 (2026-11-02)

0바이트 `stream.py`는 import·문자열 로딩·실행/배포 진입점 참조가 없어 제거했다.
답변 HTTP는 `router/answers.py`, 실행은 `service/workflow/answers.py`가 계속 소유한다.
스트리밍 기능이나 공개 API를 새로 구현하지 않는다. 조사·검증 범위는
[U27 작업 기록](../../../../../../docs/audits/2026-10-26-pattern-standardization/U27-WORKLOG.md)을 따른다.

## U18 영속 복구 상한·격리·수동 복구 (2026-11-02)

- 기존 프로세스별 LRU 진단 횟수를 제거하고 `product_generations`의
  answer_recovery_attempts/next_at/quarantined_at과 chat 소유의 `answer_recovery_attempts`
  감사 테이블을 사용한다. mapper는 이를 GenerationStateInfo/AnswerRecoveryAttemptInfo로
  변환하며 HTTP DTO는 변경하지 않는다. 기존 U18 아래의 프로세스 횟수 설명은 이 정책으로 대체한다.
- `service/command/answer_recovery.py`는 conversation → generation 잠금 아래 자동
  최대 5회, 30초 지수 대기(최대 900초), 격리·수동 요청 검증을 판단한다. workflow는
  시도 선점 commit 후 기존 finalizer를 호출한다. commit 불확실성·취소도 예산을 소비한다.
  invariant/internal/storage_constraint는 첫 실패에, 나머지는 상한에 격리한다.
- 동일 키 `_resume`와 supervisor가 같은 admission을 사용한다. 스캔은 격리·상한·대기
  항목을 LIMIT 전에 제외한다. metadata·과금 예약·실행 lease는 격리로 변경하지 않는다.
  종료 생성 재생은 제어 필드/감사 행도 쓰지 않는다. 늦은 실패 기록은 현재 횟수와 pending을 재검사한다.
- 공개 `AnswerOrchestrator.recover_answer(ClaimAnswerRecoveryCommand)`는 운영자/사유를
  요구해 한 번만 재시도하고 횟수·격리를 초기화하지 않는다. 대기·실행 lease는 유지한다.
  공급자를 호출하지 않고 기존 staging/중단 처리와 원자적 완료·terminal 재조회만 사용한다.
- `service/query/answer_recovery.py`는 사용자 범위의 정제된 감사 이력을 반환한다.
  `app.answer_recovery`는 읽기 전용 조회가 기본인 운영 CLI이며 `--retry`만 감사된 수동 복구를
  실행한다. 정책 판단은 command, 완료 조율은 기존 workflow에 유지해 별도 범용 retry 계층을 만들지 않았다.
- Alembic 0036/초기 SQL 026은 기존 생성 사실을 보존하고 감사/제어 기록이 있으면
  downgrade를 거절한다. 운영 절차·배포 중지·격리 조회는
  [답변 복구 운영 정책](../../../../../../references_document/reference/answer-recovery-policy.md)을 따른다.

## U17 답변 복구 조회·종료 lease (2026-11-02)

- 복구 조회는 `pending AND answer_lease_until <= now`, lease 오름차순, 최대 100건의
  기존 계약을 유지한다. NULL lease인 legacy pending과 종료 행은 제외한다. 후보 조회는
  실행권 선점이 아니며 완료 시 기존 conversation → generation 잠금/상태 재검사를 한다.
- Alembic 0035 / 초기 SQL 025 / ORM은 `answer_lease_until`의 전체 인덱스를
  `ix_generation_pending_answer_lease`로 교체한다. predicate는
  `status = 'pending' AND answer_lease_until IS NOT NULL`이다. repository의 고정 pending
  조건은 SQL 상수로 표현해 prepared statement의 generic plan에서도 predicate를
  입증할 수 있게 한다. 사용자 입력을 SQL 상수로 삽입하지 않으며 시각·LIMIT은 바인딩한다.
- `repository.finish_generation`은 succeeded/failed/cancelled/stale의 상태·완료 시각과
  함께 lease를 NULL로 만든다. 외부 트랜잭션 실패 시 pending lease도 함께 복원된다.
  lease는 실행권 만료이며 종료 이력이 아니다. metadata/실행 token/result digest/finished_at/
  usage·과금 사실과 terminal 재생의 무쓰기 계약은 유지한다. 기존 종료 행은 일괄
  재작성하지 않고 부분 인덱스에서 제외한다.
- 새 공개 인터페이스나 계층은 추가하지 않았다. 인덱스 교체는 API/worker를 중지한
  migration 절차로 적용하며 운영 DB에 자동 적용하지 않는다. 합성 10만 행의 분포별
  custom/generic EXPLAIN과 회귀 검증은
  [U17-WORKLOG.md](../../../../../../docs/audits/2026-10-26-pattern-standardization/U17-WORKLOG.md)를 따른다.

## U18 답변 오류 분류·복구 진단 (2026-10-30)

- 최초 세션 열기·기존 요청 조회·문맥 조회·읽기 트랜잭션 종료도 `preparation_read`로
  진단한다. SQLAlchemy 오류는 AnswerStorageError로 번역해 기존 503/동일 키 재시도
  응답을 사용한다. 이 경계에서 새 생성·과금 예약·공급자 호출은 없으므로
  storage_uncertain=False다. SQLAlchemy의 LookupError 하위 타입도 저장소 오류로
  먼저 분류한다. 기존 ValueError/LookupError/MessageConflictError의 입력·인가·설정
  계약과 CancelledError 전파는 유지하며 나머지 내부 오류는 안전한 RuntimeError로
  전달한다. diagnostic_id는 최초 조회 전에 생성하고 이후 준비·예약까지 공유한다.
- `service/workflow/answers.py`는 예약 전 문맥 준비에서 예상한 예산·모델·공급자·timeout
  실패만 기존 unbilled 실패 receipt로 저장한다. 예상 밖 내부 오류는 안전한 RuntimeError로
  전파하고 SQLAlchemy 오류는 기존 AnswerStorageError로 번역한다. 이 시점에는 생성·과금
  예약·텍스트 호출이 없으므로 request_key를 소진하지 않는다. 텍스트 호출 이후의 실패는
  기존 실패/uncertain 기록과 같은 키 재생 계약을 유지한다.
- 결과 검증은 내부 전용 예외의 code로 분류한다. 일반 ValueError/TypeError의 메시지가
  `invalid_usage` 등과 같아도 검증 오류로 오인하지 않는다. 기존 HTTP 오류 코드·DTO와
  provider 결과의 검증 기준은 유지한다.
- `AnswerStateError`는 기존 AnswerStorageError의 하위 타입으로 billing binding/금액 등
  완료 불변 조건 위반을 식별한다. HTTP는 기존 503/storage_pending_recovery 및
  retry_same_key=True를 유지한다. 이 신호가 공급자 재호출을 허용하지 않는다.
- 예약·calling staging·결과 staging·완료·취소 정리·복구 조회를 구분해 진단한다.
  `service/util/answer_diagnostics.py`는 타입 기반 오류 분류와 정제한 코드 위치만 만든다.
  메시지/SQL/매개변수/원문/locals/source/절대 경로/실행 token/request_key는 출력하지 않는다.
  원인 체인은 최대 4개 타입, app 내부 stack_frames는 최대 24개 위치다. 이 보조 책임은
  workflow 실행 순서와 분리하며 DB 접근이나 복구 정책을 소유하지 않는다.
- 로그의 `failure_class`는 internal/invariant/storage_constraint/storage_unavailable/
  storage_error/storage_uncertain/provider_retryable/provider_permanent/domain/timeout/
  invalid_result를 구별한다. OperationalError라는 타입만으로 일시 장애를 단정하지 않는다.
  `storage_uncertain`은 commit 확인 여부이며 failure_class와 독립이다. 공급자의 retryable
  분류도 자동 재호출 허가가 아니다.
- 준비·예약 전 로그는 임의 diagnostic_id, 생성 이후는 generation_id로 연결한다.
  같은 키 재전송과 background 복구는 동일 완료·재조회 경계를 사용한다. 완료 예외 뒤
  새 세션의 terminal 상태만 성공 증거로 삼고, 재조회도 실패하면 두 오류를 따로 기록하고
  최초 예외 cause를 보존한다. staging·예약액은 임의로 해제하거나 덮어쓰지 않는다.
- 복구 attempt_count는 orchestrator 인스턴스의 최근 1,024개 생성에 한정한 진단값이다.
  재시작·인스턴스 교체·LRU 퇴출 시 초기화되며 전역/영속 횟수가 아니다. terminal 확인 시
  제거한다. 개별 복구 실패는 다른 생성 복구를 막지 않고 CancelledError는 전파한다.
  재시도 상한·backoff·격리·예약 해제의 새 정책은 도입하지 않았다. 미확정 commit의
  운영 처리 계약과 함께 별도로 설계해야 한다.

## 소유 데이터와 호출 경계

`messages`, `product_generations`, `chat_message_requests`, `generation_prompts`, `chat_history_versions`를 소유한다. 기존 테이블명은 유지한다. ORM 읽기·쓰기는 `repository.py`에만 있고, Entity 해석은 `mapper/persistence.py` 및 `mapper/prompts.py`를 거친다.

conversation의 공개 `get_owned_conversation(OwnedConversationCommand)`으로 소유권·현재 상품 버전을 확인하고, `list_conversation_characters`의 Info로 실제 참여 캐릭터를 확인한다. 별도 대화방 상태 컬럼은 없으며, 생성 시에는 기존 상품 버전 사용 가능 정책도 적용한다. Legacy 대화는 사용자 메시지 CRUD는 가능하고, 검증된 버전이 필요한 생성은 기존대로 거절한다.

chat → conversation / memory / product / billing / llm 방향으로 공개 service/types만 참조한다. conversation은 chat을 호출하지 않는다. 대화방 생성과 고정 시작 내용은 conversation이 소유한다. 신규 첫 대사는 messages에 저장하지 않는다. 상품 통계도 `app/use_cases/product_statistics.py`가 각 도메인의 사실 조회와 product의 통계 저장을 조정하므로 product → chat 역방향 의존성이 없다.

## 파일별 책임

`service/workflow/memory.py`의 ProcessMemoryWorkCommand는 기존 work/policy/models
위치 인자를 보존하고 timeout_seconds=240.0을 선택적으로 받는다. U29의 단일 단조 시계
기한은 pending 색인부터 요약·저장·완료까지 공유한다. 취소/DB 정리를 기다린 뒤
MemoryWorkDeadlineExceededError를 재시도 가능한 실패로 기록하며 shutdown 취소는
그대로 전파한다. 늦게 반환된 공급자 결과는 저장 전에 기한을 재검사한다. worker의
timeout<lease 설정과 정리 지연·U03의 남은 실행 소유권 한계는 memory/ARCHITECTURE.md의
「U29 작업 전체 처리 기한」을 따른다. 모듈 의존 방향·소유 테이블은 바꾸지 않는다.

- `service/command/messages.py`: 사용자 저장·마지막 메시지 교체·되돌리기, 내부 캐릭터 저장/교체, 인가·멱등성·충돌·메모리 무효화 조정.
- `service/query/messages.py`: 소유권을 확인한 메시지 커서 페이지 조회.
- `service/views.py`: 소유자 활동순 대화 페이지. 명시된 읽기 projection으로 페이지를 가져오고 conversation 공개 COUNT를 조합해 View를 반환한다.
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

HTTP는 기존 `app.http.dependencies`를 사용한다. `app.main`은 DB 세션을 실제 session factory에, 기본 owner 훅을 identity의 쿠키·CSRF·사용자/세션 검증에 연결한다. `create_app(authenticate=...)`는 기존 명시적 주입 계약으로만 유지하며 기본 실행에 필요하지 않다. 개별 라우터만 조립하고 의존성을 연결하지 않으면 기존 503 훅이 적용된다. 비스트리밍 답변은 `app.http.answers` → `app.modules.chatting.chat.service.workflow.answers`에서 조율한다. chat 자체는 외부 호출을 하지 않는다. 스트리밍·리롤 UI는 제외한다. 답변 이미지는 위 U19 a7 경계에서 제공한다.

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
- U01: 원문 초과 시 memory의 공개 `plan_context_compaction`으로 필요한 접두 구간
  끝 position을 계산하고 오류에 포함한다. workflow는 실패 metadata의
  `summary_through_position`을 완료와 같은 트랜잭션에서 기억 작업에 전달한다.
  최근 보호 원문이 예산을 넘거나 원문 검사 한도를 넘으면 무진행 요약 예약 대신
  기존 `fixed_context_exceeded` 비재시도 결과를 반환한다. 같은 입력 재시도는
  저장된 사용자 메시지 ID/revision을 재사용하고 새 답변 요청 키를 사용한다.
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
`list_conversation_previews`와 `list_conversation_activity`의 기존 Conversation JOIN은 `Conversation.user_id` 소유권 스코핑에만 쓰며 대화 컬럼은 반환하지 않는다. 최근 대화 목록의 현재 경로는 아래 U11 절의 제한된 읽기 projection이다. HTTP 목록은 chat 공개 views/types를 직접 참조한다.


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


## U11 최근 대화의 제한적 DB 읽기 projection (2026-10-29)

아키텍처 규칙 C.2에 따라 repository.list_recent_conversations에만 conversation 소유
conversations의 id/user_id/product_id/title/created_at 읽기를 허용한다. 자기 messages와
상관 하위 조회로 조합하고 user_id 조건을 커서/정렬/LIMIT 전부터 적용한다. 해당 소유
metadata 전체를 서비스로 가져오지 않는다. 타 모듈 repository/mapper 호출·쓰기·행 잠금·
소유권 이전은 추가하지 않는다. 기존 인가용 JOIN 예외는 별도로 유지한다.

활동은 마지막 생존 메시지의 created_at DESC/position DESC로 고르고, 메시지가 없을 때만
대화 created_at으로 대체한다. 메시지가 대화 생성보다 오래됐더라도 GREATEST로 바꾸지
않으며 빈 content도 실제 메시지다. 활동 시각/대화 UUID DESC, 엄격한 이전 커서 조건과
limit+1을 DB에서 적용한 뒤 해당 페이지의 미리보기를 같은 SQL 안에서 읽는다.
RecentConversationValues/Row의 6컬럼 순서는 id/product_id/title/created_at/last_message/
last_activity_at이며 persistence mapper가 공개 RecentConversationsPageView로 변환한다.

service/views.list_recent_conversations는 ListRecentConversationsCommand의 limit와
활동 커서 쌍/시간대를 검사한다. 정확한 전체 개수는 conversation 공개 COUNT로 읽고
repository 페이지와 조합한다. 빈 결과에도 COUNT는 커서와 독립적이다. 전체 SQL 호출은
COUNT+페이지 2회이고 목록 반환은 최대 limit+1이다. DB는 소유 대화의 활동 평가·정렬과
정확한 COUNT 작업을 계속 수행한다. O(limit) 또는 인덱스만으로 고정 시간이라는 보장은
없으며 실제 PostgreSQL 실행 계획/처리량은 측정하지 않았다. 기존 메시지
(conversation_id, created_at) 인덱스를 유지하고 migration은 추가하지 않았다.

COUNT와 페이지는 READ COMMITTED에서 서로 다른 시점일 수 있다. 페이지 자체의 활동/
미리보기는 한 SQL로 읽고 여러 요청을 고정 snapshot으로 만들지 않는다. 대화의 새 활동은
이전 커서 앞으로 이동할 수 있고 새로고침으로 순회를 다시 시작한다. 삭제된 커서 행의
존재는 요구하지 않는다. HTTP cursor_created_at 이름은 계속 활동 시각을 담는다.

View 정의는 chat types가 소유하며 HTTP가 직접 참조한다.
last_activity_at=None/total=0 기본값과 DTO 필드/경로/오류는 같다. conversation의 metadata 목록 API와 쓰기·생성 잠금은 그대로다.

test_read_composition_contracts의 17건은 실제 SQLite SELECT/COUNT의 소유권/시각·UUID
동률/빈 대화/생존 메시지·position/삭제/시간 fallback/미리보기·HTTP DTO/잘못된 커서를
확인한다. 소유 대화 353개와 limit 1/7/100에서 반환 limit+1과 SQL 2회를 검증한다.
SQLite 반환 시각의 tzinfo만 UTC로 복구하며 정렬/커서/페이지는 테스트 대역이 수행하지
않는다. PostgreSQL SQL도 컴파일하지만 실제 격리·플래너/인덱스 성능 검증은 아니다.


## U12 메시지 증분 동기화 체크포인트 (2026-10-29)

기존 GET messages의 items/next_cursor와 v1:conversation_id:position 형식·입력 검증은
유지하고 선택적 history_revision/sync_cursor를 추가했다. 두 필드는 기본 None이라
기존 MessagePageInfo 생성/메타데이터 없는 대역과 이전 클라이언트를 지원한다.
query는 기존 공개 소유권 조회의 ConversationInfo.history_revision을 mapper에 전달한다.
Entity/Row를 서비스에서 해석하거나 별도 SQL·잠금·쓰기·migration을 추가하지 않았다.

next_cursor는 다음 페이지가 있을 때만 존재한다. sync_cursor는 반환한 마지막 메시지
위치이며 마지막 페이지에도 존재하고, 추가 메시지가 없는 증분 페이지는 입력 커서를
그대로 돌려준다. lookahead 한 행의 위치를 체크포인트로 쓰지 않는다. 최초 빈 이력은
None이다. 필드가 없는 이전 서버에서는 프런트가 전체 조회로 돌아간다.

기존 원문 history_revision은 수정/되돌리기 때 증가하고 일반 append에는 증가하지 않는다.
프런트는 같은 revision이면 체크포인트 이후를 ID로 병합하고, 변경이 보이면 전체 이력을
새로 읽어 교체한다. 원문 revision 조회와 메시지 SQL은 기존처럼 별도 READ COMMITTED
읽기다. 둘 사이의 동시 변경이나 이후 변경까지 고정하는 snapshot 보장은 없다. 다음
동기화에서 변경을 감지할 수 있으며 페이지 사이 revision 불일치는 프런트가 한 번만
전체 재조회한 뒤 계속 바뀌면 오류로 멈춘다. 주기적 실시간 push/polling은 추가하지 않았다.

새 test_message_sync_contracts의 8건은 소유권 거절, 최초/증분의 빈·마지막·lookahead
페이지 6조합, nullable 기본값과 schema 왕복을 확인한다. 기존 router 테스트는 실제
ASGI 응답에 두 필드가 반영되는지 확인한다. OpenAPI 고정 계약 검사는 두 선택 필드만
추가로 허용하고 기존 필드·required·나머지 계약은 그대로 비교한다. SQL 락/격리의
실제 PostgreSQL 통합 검증은 이번 오프라인 실행에서 하지 않았다.


## U13 완료 잠금 범위와 상태 전이 결과 재사용 (2026-10-29)

command/generation의 모듈 내부 _locked_generation은 사용자 범위 생성 조회로 대화 ID를
확인하고 conversation→generation 순으로 잠근 뒤 최신 Info를 제공한다. 트랜잭션 범위에
한정된 _LockedGeneration은 AsyncSession/해당 transaction/ConversationInfo/
GenerationStateInfo만 보유하며 Entity를 밖으로 반환하지 않는다. 문맥을 벗어나거나
transaction이 달라지면 내부 쓰기를 거절한다. ORM은 기존 repository/mapper에서만 쓴다.

public finish_generation과 workflow의 finish_generation_and_schedule_memory는 여전히
독립 진입점의 조회/인가/잠금·결과 digest 검증을 수행하고 기존 GenerationInfo를 반환한다.
AnswerOrchestrator._finalize만 이미 획득한 같은 내부 범위를 재사용한다. 범용 검증 생략
옵션·타 모듈에 넘길 잠금/ORM 객체·공개 types/API 변경은 추가하지 않았다.

_finish_locked_generation은 현재 잠긴 상태로 pending 여부·같은 결과 재전송·버전/만료/
출력 참여자 조건을 판단하고 기존 메시지/사용량/통계 쓰기를 수행한다. repository 완료의
반환 Entity를 즉시 Info로 변환해 _GenerationCompletion(state, transitioned)을 반환한다.
transitioned=True이면서 성공일 때만 memory 공개 서비스를 호출한다. 중복 성공 완료는
원문·사용량·메모리 세대를 다시 쓰지 않는다. final response도 이 상태에서 조립하므로
완료 뒤 get_generation_state를 다시 호출하지 않는다.

answer metadata의 public update_answer도 동일 내부 잠금 범위를 얻고 token/lease/
immutable snapshot/result_ready 조건을 기존처럼 검증한다. _finalize의 만료 lease 복구는
이미 잠긴 Info로 _update_locked_answer를 실행하고 내부 run의 metadata/lease를 갱신한다.
최종 저장 결과는 repository에서 변환한 최신 state다. 실패를 내부에서 잡더라도 바깥이
rollback-only가 되도록 기존 use_case_transaction의 중첩 범위를 유지한다.

동일 SQLite 검증기에서 정상 result_ready 성공 완료의 자기 계층 generation SELECT는
8→2회, conversation FOR UPDATE 요청은 3→1회였다. 변경 전 b3c7af1의 두 완료 파일은
별도 프로세스 메모리에서만 실행해 확인했고 작업 파일은 덮어쓰지 않았다. 실제 SQL
이벤트로 generation SELECT 수를 세고, SQLite가 무시하는 FOR UPDATE는 PostgreSQL
컴파일 문장으로 요청 수를 확인했다. repository.finish_generation의 session.get은 잠금
scope가 유지하는 ORM identity map을 사용해 추가 SELECT를 하지 않는 것도 포함한다.
참여자 조회의 별도 소유권 검사와 billing/memory/product 내부 SQL은 유지하며 이 비교에
합산하지 않는다. 전체 HTTP SQL 수·운영 지연/처리량 측정이라는 뜻은 아니다.

test_generation_completion_contracts의 30건은 정상/재전송·digest 충돌, 상태/버전/만료,
사용량/통계/메모리/정산/금액 불일치의 rollback와 result_ready 복구, 준비/호출 중 만료
lease, live/legacy lease 보류, 소유권·입력 검증, scope 수명/잡힌 오류의 rollback-only,
실행 token/lease/immutable metadata와 과금 누락/요약 복구를 확인한다. 실제 AsyncSession
트랜잭션 event를 별도 SQLite Session의 commit/rollback에 연결하고 자체 SQL/ORM을
실행한다. 타 도메인은 같은 session의 검증용 효과 테이블로 대체했다. PostgreSQL의
실제 행 잠금·격리·결제/기억 구현의 영속 원자성을 증명하지 않는다. 기존 DB opt-in
실패 복구 테스트의 failpoint도 실제 호출되는 내부 완료 경계로 옮겨 의도를 유지했다.

## U03 기억 workflow의 claim 전달 (2026-10-30)

`service/workflow/memory.py`는 claim에서 받은 `MemoryWorkInfo`를 요약·임베딩 저장
Command에 필수로 전달한다. 소유권 판단과 작업 행 잠금은 memory 공개 service의
책임이다. workflow는 기존처럼 공급자 I/O 전 세션을 닫고, 결과 저장 트랜잭션에서
conversation을 먼저 잠근 뒤 원문 revision/근거를 검사한다. memory의 작업 행 잠금은
결과 저장·commit까지 유지되어 재claim과 직렬화된다. 상위 트랜잭션이나 공급자 호출을
repository로 옮기지 않았다. 실패 기록도 같은 work의 토큰을 사용하므로 오래된 실행이
새 claim을 실패시키지 못한다. lease 재획득 전에 발생한 외부 호출 중복은 막지 않는다.

U29의 같은 전체 예산을 유지하며 각 단계에서 시각뿐 아니라 `asyncio.Timeout`의 만료
상태도 확인한다. Windows 타이머 정밀도 안의 조기 취소를 공급자가 삼킨 경우에도 늦은
결과를 저장하지 않는다. 메모리 큐·마이그레이션·PG 검증 계약은 memory/ARCHITECTURE.md와
U03-WORKLOG.md에 기록한다.

## U05 답변 이력의 범위 조회와 변경 검증 (2026-10-30)

- `chat_history_versions`는 chat 소유의 대화별 BIGINT 변경 번호다. PostgreSQL의
  messages INSERT/UPDATE/DELETE 트리거가 같은 트랜잭션에서 증가시킨다. 내용 외
  metadata, FK SET NULL, 대화 이동의 양쪽, TRUNCATE도 반영한다. rollback은 번호도
  되돌린다. 신규 빈 대화에는 행이 없어 0으로 읽으며, migration은 기존 대화를 0으로
  초기화한다. conversation.history_revision의 수정/되돌리기 전용 의미는 유지한다.
- 최초 준비와 예약 직전 재검증은 conversation 잠금 아래에서 전체 conversation,
  participants, runtime, model, 현재 MessageInfo와 history version을 함께 digest한다.
  runtime에는 선택된 lore, 스냅샷 내용, 실행 설정, 시작 문맥이 계속 포함된다. 원문
  전체의 직렬화만 DB 변경 번호로 대체한다. 번호는 현재 입력 밖의 오래된 원문 변경도
  감지하며, 같은 내용으로 되돌리는 변경이나 사용하지 않는 metadata 변경도 보수적으로
  충돌시킨다. 기존 영속 답변의 재생·lease 복구에서는 준비 digest를 다시 계산하지 않는다.
- `get_history_version(GetHistoryVersionCommand)`는 소유권을 확인한 변경 번호 Info다.
  `list_recent_messages(ListRecentMessagesCommand)`는 소유자 범위의 최근 최대 100개를
  position 오름차순으로 반환한다. lore v1 scan_depth의 최대 100과 legacy 현재 입력
  전용 규칙을 유지한다. SQL은 공용 범위 함수의 lookahead를 포함해 최대 101행이다.
- `read_message_window(ReadMessageWindowCommand)`는 128개씩 position 커서로 읽고
  토큰 예산을 처음 넘는 메시지까지 보존한다. 결과는 항상 오름차순 MessageWindowInfo,
  has_more는 선택 방향의 나머지 원문 존재다. 예산·최소 개수·범위·인가를 검사하며,
  ORM 해석은 mapper에서 한다. 새 범위 조회는 기존 (conversation_id, position) 인덱스를
  사용한다. 기존 list_memory_source의 10,000개 계약과 외부 메시지 페이지 API는 유지한다.
- 답변 문맥은 짧은 conversation 잠금 안에서 기대 history version, 최신 요약과 토큰
  예산에 따른 suffix를 읽는다. 미요약 원문이 모두 들어가면 그대로 쓰고, 넘으면 suffix의
  넘친 메시지를 근거로 U01 목표를 계산한다. 그 position 이전의 생략된 원문도 연속
  요약 목표에 포함되므로 조용히 버리지 않는다. 요약 이전 원문도 최대 가용 예산까지의
  suffix만 읽는다. 검색 질의는 기존 최근 6개를 유지하도록 최소 7개(현재 입력 포함)를
  확보한다. 현재 입력은 기존대로 고정 prompt에 한 번만 포함한다. 기억 검색/임베딩 전
  세션을 닫고, 예약 직전 전체 준비 조건을 다시 검증한다.
- memory workflow는 미요약 prefix를 max(임계치, 배치)+최근 원문 예산까지 읽고,
  잘렸을 때만 실제 최근 보호 suffix를 추가한다. prefix가 배치보다 길어 선택한 요약
  근거에는 중간 생략 구간이 들어가지 않는다. 생략된 원문은 more_work로 후속 claim에
  남기고, 저장 직전에는 선택한 정확한 범위를 다시 읽어 revision/원문 digest를 검사한다.
  원문 읽기도 짧은 conversation 잠금 아래 수행하며 공급자 호출 전에 해제한다.
  U03 claim token, U29 전체 기한, 요약 저장·색인·과금 트랜잭션 계약은 유지한다.
- 파일 분리는 기존 repository/mapper/query/workflow 책임을 유지했다. 별도 범용 캐시나
  검증 생략 옵션은 없다. 새 DB 모델은 변경 번호/트리거의 독립된 저장 책임을 표현한다.
  Alembic 0033 / 초기 SQL 023이 필요하며 API·worker를 중지하고 migration 후 함께
  시작한다. DB에 자동 적용하지 않는다. 현재 구현·검증 근거는
  [U05 작업 기록](../../../../../../docs/audits/2026-10-26-pattern-standardization/U05-WORKLOG.md)에 있다.
