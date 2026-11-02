# Memory 모듈

## U27 빈 파일 정리 (2026-11-02)

0바이트 `schemas.py`는 import·문자열 로딩·실행/배포 진입점 참조가 없어 제거했다.
memory는 자체 HTTP DTO/라우터 없이 공개 service/types로 호출한다. 기존 검색·요약·
작업 계약은 유지한다. 조사·검증 범위는
[U27 작업 기록](../../../../../../docs/audits/2026-10-26-pattern-standardization/U27-WORKLOG.md)을 따른다.

## 소유 데이터와 공개 경계

`MemoryRetriever`의 세션 팩토리는 `app.db.types.SessionFactory`를 사용한다. 실제 세션
수명은 기존대로 읽기 범위별 컨텍스트가 소유하고, provider 호출 전에 닫는 순서를 유지한다.

세션을 직접 받는 저장·예약 서비스와 repository는 `AsyncSession`으로 입력을 명시한다.
페이지 mapper는 repository의 `MemoryPageRow`, 검색 mapper는 `(ConversationMemory, float)`의
반복 가능한 묶음을 받아 공개 Info로 변환한다. ORM 타입은 repository/mapper에만 둔다.
`EmbeddedSummaryInfo.settings`는 `EmbeddingSettings` TypedDict로 document 목적·truncation·
출력 차원·출력 형식을 표현한다. 기존 부분 dict 입력을 표현할 수 있도록 키는 선택적이며,
현재 생성기는 네 키를 모두 기록한다. 타입 표기는 실행 시 검증이나 저장 JSON 변환을 추가하지 않는다.
memory 폴더 전체를 엄격 품질 검사 범위에 포함하므로 새 Python 파일도 같은 검사를 받는다.

`conversation_memories`와 `memory_jobs`를 소유한다. 원본 메시지는 chat이 계속
소유하며 memory에는 요약 본문, 전체 근거 위치 범위, 근거 digest, 대화
`history_revision`, 요약/임베딩 공급자·모델·프롬프트 버전과 정규화된 토큰
사용량만 저장한다. SDK 응답과 ORM 객체는 공개 경계를 넘지 않는다.

- `service/command/summarization.py`: 일반 임계치 또는 답변의 축약 목표로 배치를
  선택하고, 공개 `TextGenerationService`로 보조 요약을 만든다.
- `service/command/indexing.py`: 저장된 요약만 `document` 용도로 임베딩하고
  벡터 수·차원·유한값·0 벡터를 검증한 뒤 ready 상태로 전환한다.
- `service/command/scheduling.py`: 대화별 세대 카운터, lease, 제한된 지수 backoff,
  영구 실패를 관리한다.
- `service/command/invalidation.py`: 수정·되돌리기와 같은 파괴적 변경에서
  conversation 공개 서비스로 리비전을 올리고 기억과 작업을 같은 트랜잭션에서
  제거한다.
- `service/query/records.py`: 인가된 단건/목록/최신 요약/미인덱싱 요약 조회.
- `service/query/retrieval.py`: 권한과 호환 기억 존재를 먼저 확인하고 query
  임베딩 후 검색한다. `MemoryRetriever`는 DB 세션을 외부 호출 전에 닫는다.
- `repository.py`, `mapper/persistence.py`, `types.py`: 영속 연산, 순수 변환,
  공개 Command/Info 계약을 각각 담당한다.

서로 다른 변경 이유와 외부 의존성을 갖는 무효화·요약·인덱싱·예약을 기능
파일로 나눴다. command/query 구분은 외부 LLM 호출 여부와 무관하게 유지한다.

## 요약과 토큰 정책

기본값은 임계치 4,000, 배치 3,000, 최근 원문 1,200, 요약 출력 700 토큰이다.
짧은 대화에서는 호출을 피하고, 한 번의 장애가 큰 원문 범위를 재처리하지 않으며,
답변 직전의 말투와 세부 표현을 원문으로 유지하려는 보수적 시작값이다. 설정은
`MemoryPolicy`와 `.env.example`에서 변경할 수 있다.

토큰 판정은 누적 API 사용량이 아니라 아직 요약되지 않은 정상 저장 메시지의
`UTF-8 byte length / 4` 올림값과 role 표기 길이를 사용한다. 빠르고 공급자
독립적이지만 한국어·이모지·모델별 tokenizer와 오차가 있다. 실제 과금/한도 판단의
권위값은 공급자 응답이며, 요약 입력·출력과 임베딩 token 사용량을 기억 행에 별도
기록한다. 이 값으로 새 과금 정책을 만들지는 않는다.

요약 prompt는 사용자 입력을 포함해 인물, 사건 순서, 약속, 부정, 미해결 사항,
확정 사실을 보존하고 추측을 금지한다. 원문은 삭제하지 않는다. 동일 범위·리비전·
prompt version은 unique constraint로 멱등 저장된다.

## 인덱싱, 검색, 선택

요약 저장(`pending`)과 검색 준비(`ready`)를 분리한다. 임베딩 실패 시 pending
요약을 먼저 재시도하므로 텍스트 생성은 반복하지 않는다. document/query 용도를
구분하며 provider, model, dimension, output dtype/dimension, truncation과 본문
digest를 기록한다. provider/model/dimension이 정확히 같은 ready 벡터만 검색하고
출처가 불명확한 legacy vector는 제외한다. 현재 컬럼은 1536차원 고정이며 대규모
기존 데이터 재임베딩은 범위 밖이다.

초기 선택 점수는 `0.65 * cosine similarity + 0.20 * importance + 0.15 * recency`다.
최근성은 30일 단위 역수 감쇠를 사용한다. 내용 정규화 digest로 중복을 제거하고
점수로 예산 안의 항목을 선택한 뒤 원문 위치·생성 시각 순으로 안정적으로 반환한다.
본문, 근거 범위/digest, 관련도·중요도·최근성·선택 점수, 모델 metadata가 공개
결과에 포함된다. 검색할 호환 기억이 없으면 query 임베딩 호출 자체를 생략한다.
공급자/DB 실패는 빈 결과로 바꾸지 않는다.

## 작업, 동시성, 무효화

`memory_jobs`는 대화당 한 행이다. 예약은 `requested_generation`을 증가시키며,
claim 시 처리 범위인 `scope_generation`을 고정한다. 실행 중 새 예약은 running을
유지하고, 완료할 때 requested가 scope보다 크면 다시 pending이 되어 유실되지
않는다. `FOR UPDATE SKIP LOCKED`, 만료 lease, 대화별 unique PK로 다중 워커와
재시작을 처리한다. worker는 공정한 오래된 순서로 한 대화씩 claim하고 로컬
동시성을 제한한다. 기본 5회, 5초 시작/최대 300초 지수 backoff이며 정규화 오류의
`retryable` 값으로 영구 오류를 구별한다.

`app/modules/chatting/chat/service/workflow/memory.py`와 `MemoryRetriever`는 외부 호출 전에 읽기 세션을 닫는다. U05 이후 workflow는 배치 원문 조회와 결과 저장에서 짧게 conversation row를
잠근다. 저장 직전 `history_revision`과 모든 source message id/position/revision/
content digest를 다시 확인한다. 단순 append는 리비전을 바꾸지 않아 기존 결과를
허용한다. 수정·되돌리기는 리비전을 올리고 기억/작업을 삭제한다. 대화 삭제는 두
소유 테이블의 CASCADE FK로 늦게 끝난 작업의 재생성을 막으며, 최종 저장의 소유권·
리비전 검사도 실패한다. 로그에는 대화 id와 정규화된 오류 종류만 남기고 원문과
비밀 키는 남기지 않는다.

## 인가 JOIN 예외

비스트리밍 prompt 경로는 `SearchMemoriesCommand.conservative_token_budget=True`로 JSON 문자열의 UTF-8 byte 길이(+구분자 여유)를 선택 예산에 사용한다. 기본 호출의 기존 /4 추정은 유지한다. 미요약 원문 임계치는 계속 요약 정책의 원문 추정이며 API usage나 최종 prompt 예산과 혼동하지 않는다. `estimate_rendered_memory_tokens`는 pending summary fallback에도 같은 단위를 제공한다.

## U01 답변 예산에 따른 축약 목표 (2026-10-30)

`estimate_message_tokens`는 일반 원문의 role 포함 UTF-8 /4 추정과 최종 프롬프트의
보수적 UTF-8 바이트+32 계산을 제공한다. 답변 준비와 `plan_context_compaction`은
같은 단위로 가용 이력 예산을 비교한다. 일반 백그라운드 임계치·배치·최근 원문
정책의 기존 /4 의미는 유지한다.

공개 `PlanContextCompactionCommand`는 미요약 원문, 정책, 가용 예산, 보수적 단위
여부를 받는다. `plan_context_compaction`은 최근 원문 보호 범위를 먼저 계산하고,
가용 예산에 맞추는 데 필요한 오래된 연속 접두 구간의 끝 position을 반환한다.
보호 원문이 들어가는 한 기억 예산도 확보하며, 공간이 더 작으면 보호 원문을
유지하는 범위에서 확보한다. 메시지 중간 절단이나 원문 삭제는 하지 않는다.
보호 원문만으로도 예산을 넘으면 `ContextCompactionUnavailableError`를 내며
`summary_required=False`다. 답변은 기존 `fixed_context_exceeded` 비재시도 계약을 쓴다.

`ContextBudgetExceededError.summary_through_position` → 답변 metadata →
`ScheduleMemoryWorkCommand.summary_through_position` → `memory_jobs` → claim의
`MemoryWorkInfo` → `PlanSummarizationCommand` 순서로 목표를 전달한다. 새 필드는
모두 선택적이며 기본 None이다. 목표가 남으면 일반 4,000 임계치 미만이어도
기존 크기의 배치를 생성하고, 남은 목표가 있으면 `more_work=True`로 다시 예약한다.
목표가 보호 범위와 충돌하면 조용한 완료 대신 비재시도 실패로 기록한다.

큐는 여러 목표의 최댓값을 보존한다. 일반 예약/더 작은 목표/실패 재시도는 목표를
지우지 않는다. 실행 중 새 예약은 기존 세대와 동일하게 다음 claim으로 남고,
목표는 후속 배치·새 세대가 모두 끝날 때만 해제한다. U03 claim 토큰·저장 잠금·
revision/digest 검증 및 U29 전체 처리 기한은 그대로 적용한다.

스키마는 Alembic `0032`와 초기 SQL `022_memory_summary_target.sql`로 추가한다.
기존 작업은 NULL 목표로 보존한다. 구 API/worker를 중지하고 migration 후 함께
새 버전으로 실행해야 목표 전달·소비 계약이 성립한다. 실행 중 또는 미완료 목표가
있는 상태의 downgrade는 거절한다. 앱 DB 자동 migration은 하지 않는다.

`test_context_compaction`은 실제 PG 큐·요약 저장·pgvector 색인/검색·답변 재시도를
검증하며 외부 텍스트/임베딩 공급자만 대역이다. ASCII·한글·작은 문맥의 여러 배치·
큰 고정 문맥, 불가능 상태, 목표 병합/재claim/오래된 완료를 다룬다.
`test_memory_compaction_migrations`와 `test_product_migrations`는 migration/초기 SQL
경로와 기존 행 보존을 검증한다.

`conversation_memories.conversation_id → conversations.id` JOIN은 결과에
conversation 컬럼을 포함하지 않고 `conversations.user_id`로 범위를 제한하는
용도로만 사용한다. 기억 존재를 확인해 불필요한 외부 호출을 막는 bool 조회도 같은
인가 가드다. 타 모듈 repository/mapper를 직접 호출하지 않는다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: `chat/service/workflow/memory.py` → scheduling/summarization/indexing → query/retrieval → repository → `app.memory_worker`. `test_hypha_memory`는 원문 변경·중복 예약·재시도 흐름, `test_memory_query`는 인가·모델/차원 조건과 선택 예산을 확인한다.

`search_memories(session, ...)` 호환 경로는 호출자가 준 세션을 닫지 않는다. 외부 I/O 전에 세션을 닫는 구현은 `MemoryRetriever`와 상위 기억 처리 유스케이스다. 요약 배치의 첫 메시지는 큰 메시지 하나라도 선택될 수 있어 batch_tokens가 절대 입력 상한은 아니다.

lease는 만료 후 다시 claim할 수 있고 현재 worker에는 주기 갱신이 없다. U29에서 작업 시도별 전체 처리 기한을 추가했으며 아래 계약을 따른다. U03 이후 완료/실패와 결과 저장은 worker·scope뿐 아니라 개별 claim 토큰도 확인한다. 저장 출처의 UNIQUE와 외부 호출 중복 여부를 구분한다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.


2026-09-27: 기억 실행 조율은 chat workflow로 이전했다. memory는 chat을 호출하지 않으며 정책·검색·SummaryGenerator/MemoryIndexer·기억 저장·작업 상태를 계속 소유한다. MemoryModelConfig는 memory/types에 둔다. 신규 고정 첫 대사는 메시지가 아니므로 요약 원문에 포함되지 않는다. 시작 문맥은 conversation → chat → prompt가 별도로 전달한다. legacy 메시지/기억의 기존 의미는 보존한다.

## worker 실행 타입 (2026-10-28)

app.memory_worker의 process는 MemoryWorkInfo→None이며 active는 Task[None] 집합이다.
기존 concurrency 제한·건별 오류 기록 후 계속 처리·once의 drain·취소 대기 후 text/
embedding/engine 순서 종료를 유지한다. 새 lease 갱신·재시도·초기화 복구는 없다.
test_runtime_entrypoint_contracts는 작업/DB/공급자 대역으로 once의 여러 작업 처리,
건별 실패 후 다음 작업 처리와 실행 루프 종료 시 자원 정리를 확인한다. 실제 lease/
DB 경쟁 조건·공급자 초기화 중 실패·실제 외부 호출은 이 검증에 포함하지 않는다.

## U29 작업 전체 처리 기한 (2026-10-30)

chat의 공개 ProcessMemoryWorkCommand는 기존 세 위치 인자를 유지하면서 선택적
timeout_seconds=240.0을 추가한다. workflow는 유한한 양수인지 실행 전에 검사하고
하나의 단조 시계 deadline을 pending 색인·원문 조회·새 요약·저장·임베딩·완료 전체에
공유한다. 단계별/SDK 재시도마다 예산을 초기화하지 않는다. 기한 초과는 공개
MemoryWorkDeadlineExceededError(TimeoutError)로 구분해 기존 실패 큐에 기록한다.
기한 초과/실제 요청 timeout은 기본 최대 5회·5~300초 backoff를 사용하고 SDK 내부/
파싱 오류는 비재시도다. pending 요약 재사용·세대 보존·revision/출처 재검사는 유지한다.

worker는 MEMORY_WORK_TIMEOUT_SECONDS(기본 240)와 MEMORY_WORK_LEASE_SECONDS
(기본 300)를 자원 초기화 전에 검증한다. timeout은 lease보다 짧아야 하고 lease는
기존 1~3600초다. lease를 240초 이하로 설정했다면 timeout도 함께 줄여야 한다.
이 제한은 workflow 진입부터 한 시도에 적용되며 claim DB 대기·큐 대기·모든 재시도에
걸친 누적 SLA는 아니다. SDK별 요청 timeout과 별개이며 lease 갱신은 추가하지 않는다.

취소는 같은 태스크에 전달하고 DB 컨텍스트/공급자 정리 후 별도 실패 기록을 기다린다.
shutdown의 CancelledError는 기존대로 전파하며 실패/재시도 기록을 만들지 않는다.
기한이 지난 공급자 반환값은 다음 저장 전에 다시 검사한다. 동기 파싱·취소를 무시하는
외부 코드·DB rollback/commit·실패 기록까지 벽시계로 강제 중단하는 보장은 없다.
cleanup이 lease를 넘거나 claim이 지연되면 실행 중복이 가능하다. U03에서 아래의 claim별
실행 토큰 검증을 추가했지만 전체 기한이나 토큰만으로 정확히 한 번 외부 호출을 보장하지 않는다.

test_memory_deadlines는 전체 공유 예산·취소 정리/실패 기록 순서·늦은 결과 거절·
외부 취소·기존 성공·실제 SQLite UPDATE의 backoff/최대 횟수/새 세대 보존과 worker
환경 설정 전달을 확인한다. PostgreSQL 실제 잠금·경합과 live 공급자 검증은 별도다.

## U03 claim별 소유권과 결과 저장 (2026-10-30)

`scheduling.claim_memory_work`가 매 획득 시 UUID `claim_token`을 생성한다. repository는
작업 행을 잠그고 세대·시도 횟수와 함께 저장하며 mapper는 토큰을 `MemoryWorkInfo`에
전달한다. worker id, scope, attempt가 같은 재시도·작업 행 재생성도 새 토큰으로 구별한다.
기존 다섯 위치 인자는 유지하되 `MemoryWorkInfo` 생성에는 `claim_token` 키워드가 필수다.
`SaveSummaryCommand`/`SaveEmbeddingCommand`에도 해당 `work`가 필수이며 토큰 없는
호환 저장 경로는 없다. HTTP/저장된 요약·벡터/원문 API는 바뀌지 않는다.

완료/실패 UPDATE는 conversation·owner·running·worker·scope·nonnull token을 확인한다.
불일치는 기존처럼 무변경이고 정상 전이만 토큰을 비운다. 새 요청 세대·more_work·시도
횟수·제한된 backoff는 유지한다. lease 만료는 재claim 자격을 뜻하며, 새 claim에 대체되기
전까지 기존 토큰은 유효하다. 만료 즉시 쓰기를 금지하거나 lease를 갱신하는 정책은 아니다.

요약/임베딩 저장 service는 결과의 conversation/owner와 work를 비교하고 동일한 조건의
작업 행을 `FOR UPDATE`로 잠근다. 불일치는 `StaleMemoryWorkError`다. 이 잠금은 실제 쓰기와
상위 commit/rollback까지 유지하므로 검사 후 재claim이 끼어들 수 없다. workflow의 잠금
순서는 conversation → memory_jobs → conversation_memories다. 기존 원문 revision/범위
digest·벡터 내용 digest 검사를 유지한다. claim/완료/실패는 작업 행만 잠그므로 역순으로
conversation을 기다리지 않는다. 공급자 호출 중에는 세션이나 이 잠금을 보유하지 않는다.

기존 기능 파일의 책임을 유지하며 별도 범용 lease 계층은 만들지 않았다. 소유권 조건은
repository의 `_claim_identity`로 한정해 저장 잠금과 상태 UPDATE가 동일 조건을 쓴다.
U29의 deadline은 이제 시각과 `asyncio.Timeout.expired()`를 함께 확인한다. 타이머가 시계
정밀도 안에서 일찍 실행되고 공급자가 취소를 삼켜도 저장을 허용하지 않는다.

Alembic `0031_memory_claim_token`과 초기 설치 `021_memory_claim_token.sql`은 nullable UUID
컬럼을 추가한다. 기존 큐 행·요약·시각을 변경하지 않는다. 기존 running 행은 만료 후 새
claim에서 토큰을 얻는다. 배포 때 구 worker를 먼저 중지해야 하며 구/신 worker 혼용은
지원하지 않는다. downgrade는 running 행이 있으면 거절한다. 앱 DB에는 적용하지 않았다.

`test_memory_claim_fencing`은 실제 PostgreSQL의 동일 worker 재claim, 늦은 요약/임베딩,
행 재생성, 잠금 대기 후 조건 재평가, SKIP LOCKED, 저장 commit/rollback, 원문 무효화와
재시도를 검증한다. `test_memory_claim_migrations`는 fixture 소유 스키마에서 upgrade,
기존 행 보존, downgrade 거절/성공과 초기 SQL의 컬럼 일치를 확인한다. 공급자는 대역이며
실제 외부 API 호출 횟수·운영 처리량·장애 시 commit 응답 유실은 이 검증에 포함하지 않는다.

## U05 제한된 원문으로 계획하기 (2026-10-30)

공개 계획 함수와 MemoryPolicy의 토큰 단위는 유지한다. chat workflow는 답변의
가용 예산을 넘는 최신 suffix까지만 읽어 plan_context_compaction에 전달한다.
앞쪽의 생략된 메시지는 반환 position 이전의 연속 prefix 요약 목표에 포함된다.
보호 suffix가 가용 예산보다 크면 기존 비재시도 오류를 그대로 낸다.

worker의 plan_summarization 입력은 임계치/배치보다 충분히 긴 첫 prefix와 실제
보호 suffix의 합집합이다. prefix만으로 한 배치가 확보되어 선택된 source_messages는
항상 연속이다. 읽지 않은 중간 구간은 chat workflow의 more_work로 다음 claim에
남는다. 따라서 전체 미요약 이력이 10,000개를 넘어도 배치를 계속 처리한다.
요약 완료를 위해 필요한 전체 원문은 결국 각 배치에서 읽지만 매 배치마다 잔여 이력
전체를 수집하지 않는다. 저장 시 선택 구간의 원문 재검증, claim fencing 및 같은 전체
deadline은 유지한다. 새 memory 공개 Command/DB 컬럼은 추가하지 않았다.
