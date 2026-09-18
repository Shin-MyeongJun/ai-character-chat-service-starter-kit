# Memory 모듈

## 소유 데이터와 공개 경계

`conversation_memories`와 `memory_jobs`를 소유한다. 원본 메시지는 chat이 계속
소유하며 memory에는 요약 본문, 전체 근거 위치 범위, 근거 digest, 대화
`history_revision`, 요약/임베딩 공급자·모델·프롬프트 버전과 정규화된 토큰
사용량만 저장한다. SDK 응답과 ORM 객체는 공개 경계를 넘지 않는다.

- `service/command/summarization.py`: 미요약 원문의 추정 토큰으로 실행 여부와
  고정 배치를 선택하고, 공개 `TextGenerationService`로 보조 요약을 만든다.
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

`app/use_cases/memory.py`와 `MemoryRetriever`는 외부 호출 전에 읽기 세션을 닫고, 결과 저장 시에만 conversation row를
잠근다. 저장 직전 `history_revision`과 모든 source message id/position/revision/
content digest를 다시 확인한다. 단순 append는 리비전을 바꾸지 않아 기존 결과를
허용한다. 수정·되돌리기는 리비전을 올리고 기억/작업을 삭제한다. 대화 삭제는 두
소유 테이블의 CASCADE FK로 늦게 끝난 작업의 재생성을 막으며, 최종 저장의 소유권·
리비전 검사도 실패한다. 로그에는 대화 id와 정규화된 오류 종류만 남기고 원문과
비밀 키는 남기지 않는다.

## 인가 JOIN 예외

비스트리밍 prompt 경로는 `SearchMemoriesCommand.conservative_token_budget=True`로 JSON 문자열의 UTF-8 byte 길이(+구분자 여유)를 선택 예산에 사용한다. 기본 호출의 기존 /4 추정은 유지한다. 미요약 원문 임계치는 계속 요약 정책의 원문 추정이며 API usage나 최종 prompt 예산과 혼동하지 않는다. `estimate_rendered_memory_tokens`는 pending summary fallback에도 같은 단위를 제공한다.

`conversation_memories.conversation_id → conversations.id` JOIN은 결과에
conversation 컬럼을 포함하지 않고 `conversations.user_id`로 범위를 제한하는
용도로만 사용한다. 기억 존재를 확인해 불필요한 외부 호출을 막는 bool 조회도 같은
인가 가드다. 타 모듈 repository/mapper를 직접 호출하지 않는다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: `use_cases/memory.py` → scheduling/summarization/indexing → query/retrieval → repository → `app.memory_worker`. `test_hypha_memory`는 원문 변경·중복 예약·재시도 흐름, `test_memory_query`는 인가·모델/차원 조건과 선택 예산을 확인한다.

`search_memories(session, ...)` 호환 경로는 호출자가 준 세션을 닫지 않는다. 외부 I/O 전에 세션을 닫는 구현은 `MemoryRetriever`와 상위 기억 처리 유스케이스다. 요약 배치의 첫 메시지는 큰 메시지 하나라도 선택될 수 있어 batch_tokens가 절대 입력 상한은 아니다.

lease는 만료 후 다시 claim할 수 있고 현재 worker에는 주기 갱신이 없다. 완료/실패는 worker와 scope를 확인한다. 저장 출처의 UNIQUE와 외부 호출 중복 여부를 구분한다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.
