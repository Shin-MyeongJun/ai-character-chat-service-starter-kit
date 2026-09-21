# 최상위 유스케이스 조립

도메인 모듈을 역방향으로 호출하게 만들지 않고 여러 모듈의 공개 service/types만 조합한다. 자체 테이블·repository·HTTP DTO는 없다. router와 배치 조립 코드가 진입하고, 도메인 service는 이 계층을 호출하지 않는다.

- `answers.AnswerOrchestrator.generate_answer(GenerateAnswerCommand)`: 기존 사용자 메시지 ID와 한 참여 캐릭터를 받아 비스트리밍 답변 하나를 생성한다. 짧은 예약 트랜잭션에서 모델/runtime/template을 확정하고 세션 종료 후 memory 검색·프롬프트·LLM 호출을 수행한다. 공급자 결과를 먼저 staging하고 기존 finish + usage + memory 예약을 원자적으로 완료한다. `recover_answers`는 lease 만료 결과 저장만 재개하거나 불확실 실패로 종료한다. SDK/상위 자동 재호출은 없다.
- 프롬프트 규칙과 구조는 chatting/prompt 공개 service/types에 분리한다. HTTP DTO는 app/http/contracts/answers.py, 표현 변환은 app/http/answer_mapper.py가 소유한다.
- `answer_preparation`은 선택적으로 확정 runtime, current_message_id 및 실제 렌더링된 기본 예산을 받는다. 오케스트레이터의 최종 메시지 예산은 UTF-8 byte 기반 보수 추정이며 runtime JSON 크기만으로 요청을 허용하지 않는다. 미요약 원문 초과는 실패 상태를 먼저 확정하고 memory를 예약하여 pending 교착 없이 새 요청 키로 재시도할 수 있다.
- `memory.finish_generation_and_schedule_memory`는 conversation lock 후 pending→succeeded 전이를 한 번만 예약한다. 완료 재전송 때 memory 세대는 증가하지 않는다.

`app.main:create_app`은 DB와 공급자 클라이언트의 수명, 15초 주기 복구 supervisor를 조립한다. 기본 인증은 identity의 실제 쿠키·CSRF·사용자/세션 검증에 연결된다. 실제 credit 가격 계산은 별도 배포 선행 조건이다. 현재 기록은 기존 usage 계약의 token과 cost_credit=0이며 실제 잔액 차감을 구현한 것으로 간주하지 않는다. `test_first_answer_integration.py`는 기본 앱 lifespan과 PostgreSQL에서 가입→이메일 인증→로그인→공개 콘텐츠 API→첫 답변을 검증한다. 외부 메일 전송/LLM·임베딩 호출만 테스트 경계에서 대체한다.

- `conversations.start_conversation(StartConversationCommand)`: conversation의 방/상품 버전/참여 캐릭터 생성과 chat의 첫 캐릭터 메시지 저장을 동일 use_case_transaction으로 처리한다. 기존 ConversationStartedInfo 및 POST /conversations 계약을 유지한다.
- `product_statistics.rebuild_day(RebuildDayCommand)`: conversation의 방/버전 전환 사실, chat의 생성 사실, billing의 사용량/매출 사실을 받아 product 공개 통계 저장 Command에 전달한다.
- `product_statistics.process_pending(ProcessPendingCommand)`: 날짜 작업 잠금·재집계·완료를 한 트랜잭션으로 처리한다. 실패하면 큐가 보존된다. 최근 날짜 재요청은 product 자체 기능을 명시적으로 재노출한다.
- `memory.finish_generation_and_schedule_memory`: chat 성공 응답 저장과 memory 세대 예약을 같은 `use_case_transaction`으로 묶는다. 실패/취소/stale 생성은 예약하지 않는다.
- `memory.process_memory_work`: conversation revision과 chat source Info를 읽고 memory의 요약 정책·공개 LLM 서비스를 조합한다. 읽기 세션을 닫은 뒤 외부 API를 호출하고, 새 트랜잭션에서 conversation lock과 원문 범위를 재검증해 저장한다. pending 요약 인덱싱을 항상 새 요약보다 먼저 처리한다.
- `answer_preparation.prepare_answer_context`: 기존 conversation runtime View, chat 원문 Info, memory 검색 결과를 전체 prompt 예산 안에서 조립한다. 미요약 구간은 절대 자르지 않으며 들어가지 않으면 `ContextBudgetExceededError(summary_required=True)`를 반환한다. 인덱싱 대기 요약은 검색 없이 본문 fallback으로 포함할 수 있고 검색 오류는 전파한다.

대화 시작, 통계 집계, 기억 처리, 답변 문맥 조립은 변경 이유가 달라 별도 파일이다. `app.memory_worker`는 `python -m app.memory_worker`(일회 실행은 `--once`)로 실행하며 DATABASE_URL과 `.env.example`의 MEMORY/VOYAGE 설정을 사용한다. product.statistics_job은 기존 통계 배포 진입점이다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽기는 `answers.generate_answer` → `answer_preparation.prepare_answer_context` → `memory.finish_generation_and_schedule_memory` 순서로 시작한다. 예약/외부 호출/staging/완료는 서로 다른 실패 경계다. DB 완료 트랜잭션의 원자성을 공급자 호출까지 확장해서 해석하지 않는다. `recover_answers`의 반환 건수는 성공 답변 수가 아니라 복구 대상으로 처리한 건수다.

답변 예산은 최종 렌더링 추정, 요약 임계치는 미요약 원문 추정이다. 입력 변경 시 재검증, summary_required 시 실패 확정과 작업 예약, staging 실패 시 lease 복구를 각각 따라 읽는다. `test_nonstream_answers`와 `test_answer_prompt`는 이 구간의 DB/mock 경계를 보여준다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../references_document/backend_review/README.md)에 모았다.
