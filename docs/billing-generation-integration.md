# 비스트리밍 답변의 billing → credit 연결

2026-09-22 현재 구현과 검증 계약이다. 이전 문서의 “생성 연결 미구현”, HTTP 견적 API,
신규 UUID 강제 요구는 이 문서로 대체한다. billing router는 추가·등록하지 않았다.
가격 계산과 무료 우선 지갑 배분은 기존 구현을 사용한다.

## 실제 호출 구조

`app.main` → 기존 `POST /conversations/{id}/answers` → `AnswerOrchestrator.generate_answer`
→ chat/conversation/prompt/llm 공개 service/types → billing quotes/credits → credit 공개 서비스.
전체 조율은 `chat/service/workflow/answers.py`가 소유한다. chat은 생성과 메시지 저장, billing은 가격·견적·
과금 연결, credit은 지갑·예약·원장을 소유한다. 타 모듈 repository/mapper/ORM 참조는 없다.

1. 인증·CSRF·소유권 확인 후 사용자 요청 키와 대화를 잠그고 **기존 요청부터** 확인한다.
2. 신규 요청만 현재 입력, 대화/이력, 참여 캐릭터, runtime, 최종 실행 모델과 context window를
   읽는다. 짧은 준비 트랜잭션을 종료한 뒤 memory 검색 및 최종 프롬프트를 만든다.
3. 다시 요청 키·대화 잠금을 얻고 위 준비 스냅샷 및 서버 실행 설정을 비교한다. 변경됐으면
   409로 거절한다. 새 견적/생성/크레딧 예약은 남기지 않는다.
4. 같은 상위 트랜잭션에서 generation, 가격 견적, credit 예약, generation의 과금 연결과
   실행 토큰/lease를 저장한다. credit이 같은 지갑 잠금 안에서 잔액 검사와 무료/유료 배분을 한다.
5. commit이 정상 반환한 호출자만 `calling`을 짧은 트랜잭션으로 저장하고 LLM을 한 번 호출한다.
   외부 생성 및 메모리 임베딩 중에는 DB 트랜잭션·잠금을 유지하지 않는다.
6. 공급자 결과 또는 정규화한 실패 후보를 먼저 `result_ready`로 staging한다.
7. 최종 트랜잭션에서 답변·usage·기존 memory 작업 예약을 저장하고 chat의 **반환 상태**가
   succeeded일 때만 billing을 통해 예약액을 확정한다. failed/cancelled/stale이면 해제한다.

내부 메모리 검색 임베딩·요약은 사용자 청구/예약을 추가하지 않는다. 준비 실패에는 실행 가능한
견적이 없으므로 credit을 예약하지 않는다. 기존 실패 결과와 `summary_required` memory 예약
동작은 유지하며 metadata에 `unbilled_reason=preparation_failed`를 기록한다.

## 견적과 실행 입력

최종 `prompt.request_json` 한 개를 준비해 digest와 추정 토큰을 견적에 고정하고, 그 **동일한
문자열**을 LLM에 전달한다. 모델/provider/reasoning effort와 실제 `max_output_tokens`도 고정한다.
추정 방식은 `utf8-bytes-plus-32-per-message-plus-32-v1`이다:
각 메시지 content의 UTF-8 byte 수 + 메시지당 32 + 전체 32. 기존 보수적 prompt 예산을
재사용한 추정이며 모델별 정확한 tokenizer가 아니다. 큰 문맥을 보수적으로 거절할 수 있다.
공급자 실제 token usage는 별도로 기록한다.

작업 지문 `answer-operation-v1`은 정렬 JSON(SHA-256, UTF-8, ensure_ascii=False,
separators=(',', ':'))에 Command, 준비 스냅샷 digest, 최종 prompt digest, 추정 방식/입력 토큰,
출력 한도를 포함한다. 준비 스냅샷에는 대화·history_revision·참여자·runtime·model Info·현재
원문 source가 포함된다. 준비 중 원문/모델/서버 설정 변경은 예약 시 재검증한다.

가격 계산은 기존 `context-budget-cost-floor-v1`의 구간 정상가격 → 정책 순서 → 원가 하한 →
정수 올림을 유지한다. 성공 시 **견적의 예약액 전체**를 차감하며 실제 출력 token 수로 재정산하지
않는다. 무료 우선/부족분 유료 배분을 예약 때 고정하므로 도중 무료 지급에도 기존 배분은 유지된다.

## 트랜잭션과 잠금

모두 `use_case_transaction`으로 조합하며 내부 서비스는 상위 commit/rollback을 하지 않는다.
credit/billing의 내부 SAVEPOINT도 상위 트랜잭션의 일부다.

| 경계 | 함께 저장되는 내용 | 오류 처리 |
| --- | --- | --- |
| 실행 준비 | 공개 runtime/model 준비(기존 모델 대체 이력 포함) | 세션 종료 후 외부 memory 검색 |
| 생성/과금 예약 | generation + quote + credit reservation + billing binding + answer metadata/lease | 전부 rollback. 부족하면 생성 LLM 0회 |
| calling staging | 실행권·lease 확인, phase 변경 | 불확실하면 새 세션 조회. LLM 재호출 없음 |
| 결과 staging | 실행권·lease 확인, 공급자 결과/usage/실패 후보 | 결과가 영속화됐는지 새 세션으로 확인 |
| 성공 완료 | 답변 + usage + memory 작업 + credit 확정 원장/배분 | 전부 rollback; 원래 RESERVED와 staging 유지 |
| 실패 완료/복구 | failed/cancelled/stale + usage 청구 0 + credit 해제 | 전부 rollback; 같은 키/복구 supervisor로 재시도 |

chat 잠금 → billing/credit 잠금 순서를 정상 실행과 복구에서 동일하게 사용한다.
신규/요청 재전송은 사용자 generation 요청 키 → conversation → generation → billing 요청 키
→ credit 지갑 advisory/row → 예약 순서다. 완료/복구는 conversation → generation 이후
동일 billing/credit 순서다. 완료는 뒤늦게 generation 요청 키를 획득하지 않아 역순이 없다.
기억/usage/통계 작업은 기존 완료 트랜잭션에 참여한다.

`usage.cost_credit`은 chat의 최종 status가 succeeded인 경우에만 후보 예약액을 저장한다.
billing이 반환한 확정 금액과도 비교하고 불일치하면 상위 전체를 rollback한다. 실패/취소/stale의
공급자 token 사용 사실은 남길 수 있지만 사용자 청구액은 0이다. 원장 result_id/reference_id는
저장된 generation.id이다. COMMITTED를 release로 환불하는 전이는 기존대로 거절한다.

## 멱등 키와 영속 연결

HTTP `request_key: str`(1..128자, 공백만인 값 거절) 계약을 유지한다. 문자열을 trim하거나 UUID로
강제 파싱하지 않는다. UUID 문자열도 일반 문자열과 같은 방식으로 처리한다.

```python
namespace = uuid5(NAMESPACE_URL, "chatkit:answers:billing:v1")
billing_key = uuid5(namespace, f"{user_id}:{request_key}")
```

고정 namespace + 사용자 ID + 원래 문자열로 매번 같은 UUID가 나온다. 재전송에 랜덤 UUID를
발급하지 않는다. 원래 키는 generation에, 변환 키/quote_id/reservation_id/예약액/작업 지문은
`answer_metadata.billing` version 1에 보존한다. generation metadata version은 2다.
견적의 기존 JSON snapshot이 실행·가격 조건을 보존하고 billing_credit_bindings가 credit 예약에
연결한다. 기존 JSONB/lease 컬럼을 사용하므로 새 테이블·migration·기존 데이터 재작성은 없다.

같은 사용자·키의 다른 대화/입력 ID/revision/대상 캐릭터와 변경된 원래 이력은 409다.
클라이언트에게 model/prompt/출력 한도/가격 설정 입력을 새로 받지 않는다. 기존 요청은 당시
실행 스냅샷으로 처리하며 배포 후 모델/템플릿/가격/TTL이 바뀌어도 다시 계산하지 않는다.
완료 재전송은 저장된 결과를 반환한다. pending은 실행 중이면 202, 결과 staging이 있으면
동일 키 재전송에서 최종 저장만 재시도한다. 만료된 실행은 동일 키에서 복구할 수도 있다.

## 실행권·불확실성·복구

신규 실행은 영속 `execution_token`과 `answer_lease_until`(예약 시각 + timeout + 60초)을 가진다.
chat.update_answer는 conversation/generation 잠금 아래 token·lease·불변 실행/과금 스냅샷을
확인한다. result_ready는 덮어쓸 수 없고 terminal 생성에는 staging할 수 없다.
복구 쓰기(`UpdateAnswerCommand.recover=True`)는 lease가 실제로 만료된 경우에만 허용한다.

- timeout/연결 실패/취소는 곧바로 release하지 않는다. 새 staging 세션에서 영속 상태·token·
  lease를 확인한 뒤 실패 후보를 기록하고, 또 다른 최종 트랜잭션에서 실패 확정+해제를 처리한다.
- 만료 전 calling/reserved는 예약을 유지한다. 견적 TTL은 신규 예약만 제한하며 실행 lease와 다르다.
- 만료 후 result_ready가 있으면 결과 저장+확정/해제만 재시도한다. LLM을 재호출하지 않는다.
- 만료 후 결과가 없으면 새 잠금 아래 interrupted_before_call 또는 interrupted_uncertain을
  확정하고 해제한다. 실패 확정 전에도 lease를 잃은 작업자는 늦은 결과를 staging할 수 없다.
- 복구 실패/해제 오류는 실패 상태와 해제를 함께 rollback한다. lease가 이미 만료되어 있어
  이전 작업자가 결과를 덮어쓰는 것도 거절한다. 다음 supervisor 또는 같은 키가 재시도한다.
- 예약 commit 응답 유실은 새 세션으로 원래 요청을 확인하고 pending/완료를 반환한다.
  저장된 RESERVED를 새 실행 허가로 해석하지 않는다. durable calling 응답 유실 시에도 재호출하지
  않는다. 결과/최종 commit 응답 유실은 영속 result_ready/terminal을 조회하여 완료/재사용한다.
- DB가 계속 불가하면 503 `storage_pending_recovery`와 같은 키 재전송 지시를 반환한다.
  `recover_answers` supervisor는 기존대로 15초 간격이며 만료 생성의 저장/실패 확정만 수행한다.

DB와 공급자 사이의 exactly-once 분산 트랜잭션을 주장하지 않는다. 호출 성공 여부를 복구할 수 없는
중단은 사용자 청구 0의 불확실 실패로 끝낼 수 있고, 그 호출에 대한 공급자 비용이 발생할 수 있다.

## 과거 데이터

과금 연결 없는 기존 generation은 재견적하거나 소급 차감하지 않는다. identity가 있는 기존
완료 결과는 재사용하고 기존 result_ready/lease 복구는 청구 0으로 완료한다. 기존 lease 없는
pending은 자동 복구하지 않는다. identity 없는 과거 키는 새 요청으로 재사용하지 않고 충돌한다.
신규 version 2의 과금 연결 누락은 명시적 준비 실패 외에는 저장 복구 오류로 차단한다.

credit의 기존 분류 승인 보류 정책을 유지한다. legacy account/거래/예약이 있는 사용자는 새 지갑이
있어도 기존 guard가 예약을 차단한다. 무료/유료 임의 분류·과거 원장 수정·운영 충전은 없다.
[분류 계약](credit-billing-refactor-plan.md)을 따른다.

## 앱 설정과 HTTP

`BILLING_PRICING_CONFIG_PATH`에 UTF-8 JSON 파일 경로를 지정한다. 앱 lifespan이 공개
`billing.service.configuration.load_billing_pricing_configuration()`으로 읽고 AnswerOrchestrator의
`pricing` 실행 의존성에 주입한다. 애플리케이션 직접 조립 시 기존 BillingPricingConfiguration도
주입할 수 있다. 기본 정책 순서는 기존 product_author/promotion/unpopular_product noop-v1이다.

JSON의 필수 구조:

| 위치 | 필드와 자료형 |
| --- | --- |
| root | quote_ttl_seconds: 정수 1..86400, price_book: object |
| price_book | version, currency: 문자열; credits_per_currency_unit, safety_factor: Decimal 문자열; models: 배열 |
| models 항목 | execution: object; input_cost_per_token, output_cost_per_token: Decimal 문자열; tiers: 배열 |
| execution | model_id: 실제 서버 모델 UUID 문자열; provider, model, reasoning_effort: 실제 실행 문자열; pricing_settings: 선택적 name/value 배열(기본 빈 배열) |
| tiers 항목 | tier_id: 문자열; min_context_tokens, max_context_tokens_exclusive: 정수; normal_price_credit: Decimal 문자열 |

원가는 토큰 1개당 단위다. 서버가 선택할 모델·reasoning effort별 승인 가격표와 문맥 구간,
원가 통화·환산율·안전 계수를 공급해야 한다. 금액의 JSON float/bool은 거절한다. 승인된 값을
제공하지 않았으므로 운영 가격 파일/시드는 만들지 않았다. 기존 `CREDIT_COST_PER_1K_TOKENS`는
버전 가격표·원가·환산율을 표현하지 못하는 미사용 변수이며 이를 임의 변환하지 않는다.

경로 미설정은 앱의 인증·조회·복구를 살려두되 **신규 답변을 503으로 거절**한다. 설정 경로가 있지만
파일/구성이 잘못되면 앱 시작을 실패시킨다. 미지원 실행/구간도 가격 오류이며 무료 실행으로
대체하지 않는다. 승인된 지갑 준비/지급 경로가 있어야 사용자 생성이 가능하다. 이번 작업은 충전
기능을 만들거나 계정에 자동 지급하지 않는다. tests의 지급은 UUID 테스트 스키마 전용 fixture다.

| 기존 answers HTTP 경계 | 응답 |
| --- | --- |
| InsufficientCreditError | 402 / insufficient_credit |
| 지갑 없음 또는 legacy 분류 차단 | 409 / credit_account_unavailable |
| 가격 구성 없음/미지원 | 503 / billing_not_configured |
| 견적·예약 충돌/신규 견적 만료 | 409 / billing_conflict |
| 불확실 저장 | 503 / storage_pending_recovery, retry_same_key=true |

기존 인증·소유권·CSRF·요청/답변 DTO와 pending 202/Retry-After 계약을 유지한다.
견적 HTTP API, billing router, 프런트엔드, 스트리밍, 새 리롤/OCP, 결제/충전/환불/구독,
실제 프로모션·통계 확장은 범위 밖이다.

## 검증과 재실행

`test_answer_billing_integration.py`는 실제 PostgreSQL에서 답변 오케스트레이터·공개 billing/credit을
조합한다. 성공/부족/공급자 실패/timeout/동시 키/서로 다른 대화의 잔액 경쟁/준비 변경/확정 및
해제 실패/staging 복구/실행권 상실/늦은 완료/stale/TTL 및 가격 변경/commit 응답 유실/
과거 생성과 legacy credit 차단/무료·유료 배분을 검사하고 LLM 호출 횟수를 확인한다.
`test_nonstream_answers.py`의 같은 키 다른 입력·memory 저장 rollback·인증/실패 회귀도 실행한다.
`test_first_answer_integration.py`는 기본 앱의 실제 설정 파일 로딩·쿠키 인증·첫 답변을 통과하며,
SDK LLM/메일/임베딩만 결정적인 대역을 사용한다. 운영 지급이나 공급자 실호출 검증은 아니다.

```powershell
$env:PYTHONPATH = 'apps/api'
$env:TEST_DATABASE_URL = '<test가 이름에 포함된 전용 PostgreSQL asyncpg URL>'
$env:TEST_AUTH_DATABASE_URL = $env:TEST_DATABASE_URL
.venv/Scripts/python.exe -m pytest apps/api/tests -q -rs --basetemp=tmp/answer-billing-regression
```

2026-09-22, 최종 작업 폴더의 Windows/Python 3.12.14에서 실행했다.
이 작업 전용 `pgvector/pgvector:pg17` 컨테이너의 `answer_billing_test` DB와 테스트마다
분리한 UUID 스키마를 사용했다. 운영 DB/잔액에는 접근하거나 지급하지 않았다.

| 검사 | 결과 |
| --- | --- |
| 과금 연결 + 설정/HTTP + 비스트리밍 + 기본 앱 첫 답변 + usage + 아키텍처 관련 회귀 | **83 passed, 0 failed, 0 skipped**, 50.65초 |
| 전체 `apps/api/tests` | **647 passed, 0 failed, 4 skipped**, 159.67초 |
| DB/마이그레이션 검사 skip | **0** |
| 변경 Python 13개 Ruff E/F/I 및 format --check | 통과 |
| answers 오케스트레이터, billing configuration, chat answers/generation, HTTP answers mypy | 5개 소스 통과 (`--follow-imports=silent`) |
| git diff HEAD --check | 통과 |

새 실제 과금 답변 통합은 25개, 가격 설정/HTTP 오류는 7개다. 전체 회귀에는 기존 무료/유료
지갑·가격·견적·멱등성·마이그레이션 보존/차단·인증/CSRF·메모리 검사가 포함된다.
마지막 Python 변경은 Ruff의 줄바꿈 형식 정리뿐이며 실행 동작 변경은 없다.

실행하지 않은 4개는 실 S3 2개(RUN_ASSET_STORAGE_S3_INTEGRATION 미설정),
실 Mailpit SMTP 1개(TEST_MAILPIT_HTTP_URL 미설정), 실 Voyage 1개(VOYAGE_API_KEY 미설정)다.
외부 서비스 opt-in을 켜거나 실제 공급자 키를 사용하지 않았다. 실제 OpenAI/Anthropic 호출,
운영 SMTP/HTTPS 프록시, 운영 배포/가격 승인/legacy 분류 이관은 검증하지 않았다.
전체 app mypy 성공을 주장하지 않으며 이번에는 위 변경 경계만 타입 검사했다.

완료 후에도 운영 적용에는 승인된 가격 JSON, 실제 실행 모델 설정, 이미 승인된 사용자 지갑
준비/지급 경로가 필요하다. legacy 분류 승인 보류는 유지한다. 실결제·충전/환불·구독·UI 및
새 리롤/OCP/스트리밍은 별도 작업이며 이번 구현의 누락된 생성 연결 작업은 아니다.
Git commit/push와 운영 migration은 실행하지 않았다.
