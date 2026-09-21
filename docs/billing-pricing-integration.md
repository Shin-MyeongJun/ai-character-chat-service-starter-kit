# 과금 공개 계약과 후속 연결

## 이번 단계의 구현 범위

앞 단계의 불변 Command/Info와 순수 정책 어댑터·등록부에 이어,
`billing/service/pricing.py`의 가격 계산과 `billing/service/quotes.py`의 견적 저장·조회·검증을 구현했다.
이어서 `billing/service/credits.py`에 잔액 조회·예약·차감 확정·해제를 구현했다.
HTTP, 실제 결제/충전 API, 생성 흐름 연결은 미구현이다.
견적 발급은 실제 크레딧 차감을 의미하지 않는다.

독립 PostgreSQL 통합 검증과 다음 커밋의 상세 실행 순서·복구·리롤/OCP 계약은
[생성 연결 명세](billing-generation-integration.md)에 정리했다. 이 문서 아래 단계별 검증
기록은 당시의 이력이며 최신 재실행 결과는 연결 명세의 검증 기록을 따른다.

기존 구현을 확인한 결과:

- `record_usage(RecordUsageCommand) → UsageRecordedInfo`는 사용량만 기록한다.
  `cost_credit`은 전달받은 정수이며 계산된 요금이나 잔액 차감을 보장하지 않는다.
- `record_sale`/`record_refund`는 이미 확정된 결제 사실의 상품 버전별 귀속이다.
  `PaymentInfo`의 통화 금액과 가격의 크레딧 단위는 서로 다르다.
- `payments`, `usage_logs`, `product_payment_events`는 기존 billing 소유 테이블이다.
  `subscription_plans`, `user_subscriptions`의 구독 처리는 미구현이다.
- `credit_accounts`, `credit_transactions`는 기존 credit 범위로 문서화됐지만 서비스/저장소는 비어 있었다.
  이번 단계에서 billing 소유로 재사용한다. credit 모듈 코드를 수정하거나 이중 원장을 만들지 않았다.
  기존 balance와 signed amount·거래 사유·전역 키 및 과거 기록의 의미는 유지한다.
  기존 거래의 전역 `idempotency_key` UNIQUE만으로 사용자별 예약 멱등성이나
  결과 저장과 차감의 원자성이 보장되는 것은 아니다.

## 공개 값 계약

다른 모듈은 billing의 공개 `types`와 `service` 경계만 참조한다.
모든 새 값은 frozen dataclass, enum, UUID, Decimal, datetime, 기본 스칼라와 tuple로 구성된다.
ORM/Row, DB 세션, HTTP DTO, SDK 객체, 임의의 dict를 정책 입력에 넣지 않는다.

| 타입 | 책임 |
| --- | --- |
| `BillingRequestInfo` | 과금 주체, 작업 종류, 요청 키, 작업 지문, 상품 버전, 실제 실행 설정, 입력 토큰 수와 최대 출력 예산 |
| `BillingProductInfo` | 기존 상품/스냅샷 식별자. 상품 없는 작업은 request.product=None |
| `BillingExecutionInfo` | 대체 모델 선택까지 끝난 model_id/provider/model 및 reasoning_effort, 추가 가격 설정 |
| `PricingSettingInfo` | 이름과 정규화된 문자열 값. 같은 이름 중복 금지, 이름순으로 정렬해 전달 |
| `ApplyPricingPolicyCommand` | 위 요청 값과 정상가격, 해당 정책 직전 가격 |
| `PricingPolicyResultInfo` | 정책 식별자/버전, 실행 상태, 입력/출력 가격 |
| `BillingPriceInfo` | 가격표/계산 버전, 문맥 구간, 정상가격, 원가 하한, 확정 정수 가격, 표시 할인율, 순서대로 평가한 정책 결과 |
| `CreateBillingQuoteCommand` / `BillingQuoteInfo` | 견적 요청 / 견적 ID·요청·가격·상태·만료 시각 |
| `ReserveCreditCommand` | 사용자·요청 키·견적 ID와 서버가 확인한 전체 `request: BillingRequestInfo` (필수 추가) |
| `GetCreditBalanceCommand` / `CreditBalanceInfo` | 사용자 ID / 보유·예약·사용 가능 잔액 |
| `CommitCreditReservationCommand` | 사용자·요청 키·예약 ID와 저장한 결과 ID |
| `ReleaseCreditReservationCommand` | 사용자·요청 키·해제할 예약 ID |
| `CreditReservationInfo` | 예약 ID·사용자·요청 키·견적 ID·상태·예약 금액·결과 ID |

견적 및 예약 Command/Info 모두 실행 서비스가 있다. 앞 단계의 예약 값 계약에 실행 조건을
필수 추가했으며, 아직 연결된 운영 호출자는 없다. 기존 usage/결제 귀속 계약은 변경하지 않았다.
예약 명령은 가격을 다시 받지 않는다. 신뢰할 수 있는 저장된 견적에서 가격과 작업을 읽어야 한다.
견적의 `QUOTED`/`EXPIRED`와 예약의 `RESERVED`/`COMMITTED`/`RELEASED`는
새 리소스의 상태이며 기존 generation/payment 상태를 대체하지 않는다.
견적에 예약 상태를 중복 저장하지 않고 예약의 quote_id로 연결한다.
`reserved_credit`은 최초 예약 금액으로 해제/확정 후에도 동일하다.
`result_id`는 COMMITTED에서만 존재하며 생성 결과의 외부 식별 값이다.

가격·견적 서비스에서 필수 값, UUID, sha256 작업 지문, 중복 없는 정규화 설정,
0 이상의 입력 토큰·출력 예산, 유한한 비음수 가격, 시간대가 있는 만료 시각을 검증한다.
Command만 생성했다고 인가/검증이 수행되지는 않는다.

## 정책 등록과 최종 계산 책임

공통 계약은 `PricingPolicyAdapter.apply_policy(ApplyPricingPolicyCommand)`이고
반환은 `PricingPolicyResultInfo`다. 어댑터의 `policy`는 정책 ID와 버전을 제공한다.
정책은 입력 값만으로 판단하며 다른 모듈 조회, repository/ORM, 시계/네트워크 접근을 하지 않는다.
필요한 시점·자격·버전 등은 후속 공개 값 계약을 확장하여 호출자가 전달한다.

등록은 `PricingPolicyRegistry(tuple[PricingPolicyRegistration, ...])`로 구성한다.
각 항목의 `order` 오름차순을 사용하며 같은 순서 또는 같은 policy_id의 중복은 거절한다.
순서를 명시한 항목을 추가하거나 제거하거나 order를 바꿔 새 등록부를 구성한다.
빈 구성도 허용한다. 전역 등록부를 실행 중에 변경하거나 자동으로 정책을 탐색하지 않는다.
이 구성 객체는 실행 의존성을 담는 service 계층의 조립용 객체이며 업무 Command/Info가 아니다.

기본 구성은 다음과 같다.

| order | 정책 ID | 버전 | 현재 동작 |
| --- | --- | --- | --- |
| 10 | product_author | noop-v1 | 상품 상태·작가 정책 미구현 |
| 20 | promotion | noop-v1 | 프로모션 할인 미구현 |
| 30 | unpopular_product | noop-v1 | 비인기 작품 할인 미구현 |

세 어댑터 모두 입력 가격을 소수 정밀도까지 그대로 유지한다. enabled=True이면
UNIMPLEMENTED, False이면 DISABLED를 반환한다. 이를 APPLIED나 할인율 0으로 위장하지 않는다.
장래 구현용 APPLIED와 NOT_APPLICABLE도 결과 상태로 정의했다.
정책 결과 목록에는 미구현/비활성 결과도 포함하고 APPLIED로 실제 적용 여부를 구분한다.
가짜 상품 조건·프로모션 자격·순위 데이터는 없다.

계산기의 고정 순서:

1. 인증된 사용자 요청의 유료 생성만 과금 대상으로 판단한다.
   USER_GENERATION/USER_REGENERATION/USER_CONTINUATION은 이 용도로 분류한다.
   INTERNAL_EMBEDDING/INTERNAL_SUMMARY는 별도 사용자 청구/예약을 만들지 않는다.
   enum 값만으로 유료 작업의 인가를 대신하지 않는다.
2. 실제 실행 모델·가격 설정·문맥 구간에 해당하는 고정 정상가격을 선택한다.
   입력 토큰 수/최대 출력 예산을 받되 실제 출력 토큰당 소매 요금으로 변경하지 않는다.
3. 등록 순서대로 정책을 적용하고 이전 출력 가격을 다음 입력 가격으로 전달한다.
4. 원가 보호 하한을 적용한 후 크레딧 정수 단위로 올림한다.
   이 두 단계는 계산기의 고정 로직이며 등록·제거 가능한 어댑터가 아니다.
5. 표시 할인율은 정상가격과 최종 확정가격을 비교해 계산한다.
   정상가격이 양수이면 `max(0, (정상가격 - 확정가격) / 정상가격 * 100)`이고,
   정상가격이 0이면 0이다. 어댑터 할인율을 합산하지 않는다.

정책 중간값과 정상가격/하한은 Decimal 크레딧, 확정가격은 int 크레딧이다.
가격표 구간 경계, 원가 산식과 버전, 표시 소수 자리 정책은 아래 구현 계약을 따른다.
견적은 가격표 버전·구간·계산 버전·순서 있는 정책 ID/버전/상태/금액을 함께 고정한다.
기발급 견적/예약을 현재 등록 순서나 최신 가격으로 다시 계산하지 않는다.

## 요청 키와 충돌 계약

- 호출자는 사용자 작업 시작 시 UUID를 **한 번** 생성한다.
- 통신 재전송과 동일 작업 재시도에는 같은 키를 사용한다. 의도적인 새 작업에는 새 키를 사용한다.
- billing은 누락된 키를 생성하지 않는다. 신규 값 타입은 UUID이며 기본값도 없다.
- 기존 chat/HTTP의 문자열 request_key, 기존 billing의 문자열 event_key 계약은 변경하지 않았다.
  새 UUID 흐름을 도입할 때 호출 경계에서 문자열 표현을 전달/변환하는 방법과
  기존 비-UUID 문자열의 호환 경로를 별도 작업으로 정해야 한다.
  이번 변경으로 기존 문자열 입력을 UUID로 강제하거나 자동 변환하지 않는다.
- 멱등 스코프는 `(user_id, request_key)`다. 같은 스코프의 다른 작업은 충돌이다.
  operation_kind, operation_fingerprint, 상품/스냅샷, 실제 모델/모든 가격 설정,
  input_tokens/max_output_tokens 전체를 비교해야 한다.
- operation_fingerprint는 조율 계층이 정규화한 사용자 입력·대상 대화/버전·작업 옵션 등의
  논리적 작업 정보를 SHA-256으로 계산한 `sha256:<64 hex>` 값이다.
  같은 토큰 수의 다른 프롬프트도 구분하고, 지문 정규화는 버전을 정해 유지한다.
  전송 시각 등 재전송마다 바뀌는 메타데이터는 제외한다. billing은 원문을 조회하지 않는다.
- 최초 확정한 작업 스냅샷을 재전송에도 사용한다. 모델 대체/문맥 변경으로 작업 정보가 달라지면
  기존 키를 몰래 재사용하지 않는다. 호출자가 충돌을 처리하고 새 사용자 작업 여부를 결정한다.
- 같은 내용의 예약/확정/해제 재호출은 기존 결과를 반환한다.
  같은 키의 다른 견적, 다른 예약, 확정 시 다른 result_id는 충돌이다.
  해제된 예약의 확정 및 확정된 예약의 해제도 충돌이며 해제를 환불로 취급하지 않는다.
- 견적과 예약/확정/해제 모두 충돌 검증·동시성 잠금·고유 제약·저장 결과 재사용을 구현했다.
  견적 만료는 신규 예약에만 적용하며, 기존 예약/완료 요청 재전송은 같은 조건의 저장 결과를 반환한다.

## 다른 모듈이 제공할 정보와 연결 지점

이번 작업에서 아래 모듈은 수정하지 않았다. 후속 조율 계층은 공개 service 결과를 받아
billing의 공개 값으로 변환하며 어댑터 안에서 다른 모듈을 조회하지 않는다.

| 제공 주체 | 필요한 공개 정보와 연결 위치 |
| --- | --- |
| identity / 호출 진입점 | 인증된 사용자 ID, 유료 생성 요청의 권한. 견적 전에 검증 |
| product | 상품/스냅샷 ID, 장래 상품 상태·작가 설정·정책 버전. 상품 정책 입력 구성 시 연결 |
| llm | 대체 선택 후의 실제 model_id/provider/model/reasoning_effort, 가격 영향 설정. 견적 전에 확정 |
| chat / conversation / prompt 조율 | 논리적 작업 지문, 문맥 버전, 최종 입력 토큰 수, 최대 출력 예산, 결과 ID. 견적/확정 시 전달 |
| 장래 프로모션 소유 모듈 | 판정된 적용 자격·유효 기간·할인 규칙 및 버전. 프로모션 정책 입력으로 연결 |
| 장래 인기도 통계 소유 모듈 | 인기도 판단 정보·집계 기준 시각·판정 버전. 비인기 정책 입력으로 연결 |
| 장래 충전/환불 조율 | billing 소유 기존 계정/원장을 통해 같은 계정 잠금·불변식을 준수하는 공개 계약 설계. 이번에는 API 미구현 |

프로모션/통계의 위 내용은 필요한 계약 목록이며 해당 모듈이나 DB를 새로 만들라는 뜻이 아니다.
원가/가격표는 서버 소유의 명시적인 `BillingPricingConfiguration`으로 공급한다.
운영 설정의 로딩·승인·가격표 버전 발행 및 실제 앱 주입은 후속 조립 작업에서 연결해야 한다.

## 가격표와 견적의 구현 계약

`BillingPricingConfiguration(price_book=..., policies=..., quote_ttl_seconds=...)`은
서비스 실행 의존성이다. HTTP 입력으로 직접 받지 않는다. 전역 기본값·운영 시드·샘플 운영
가격표는 없다. 예제 금액은 `tests/test_billing_prices.py`의 fixture에만 존재한다.
`price_book=None`이면 신규 계산/발급은 `BillingPricingError`로 실패한다.
기존 견적 조회와 동일 요청 재전송은 새 가격표가 없어도 최초 저장값을 반환한다.

- `PriceBookInfo`: 가격/원가/환산 설정 버전, 원가 통화, 통화 1단위당 크레딧,
  안전 계수, `ModelPriceInfo` tuple. 각 모델 항목은 실제 execution 전체와 정확히 일치해야 한다.
  동일 model_id라도 reasoning_effort/추가 설정별로 명시적인 가격 항목을 제공한다.
- `ContextPriceTierInfo`: `[min_context_tokens, max_context_tokens_exclusive)`.
  문맥 토큰은 **서버가 확보한 최종 입력 토큰 + 최대 출력 토큰 예산**이다.
  경계에서 다음 구간이 적용된다. 같은 실행의 중복 구간 ID, 겹치는 구간,
  역전·빈 구간과 중복 실행 항목은 구성 시 거절한다. 구간 공백/범위 초과는 요청 시 실패한다.
- 각 토큰 수는 0..2^31-1 정수, 금액/단가/환산율은 유한한 비음수 Decimal로
  1e18 미만, 소수 12자리 이하다. float는 거절한다. 환산율은 양수, 안전 계수는 1 이상이다.
  정책 출력에도 같은 금액 범위를 적용하고 최종 크레딧은 signed bigint 범위로 제한한다.
  이는 저장·계산의 기술적 범위이며 운영 요금을 결정하지 않는다.
- 명시적으로 0으로 설정한 정상가격은 허용하지만 원가 하한은 여전히 적용한다.
  미설정/잘못된 구성/지원하지 않는 실행 조건을 0으로 대체하지 않는다.
- 원가 하한은 `(입력 토큰 × 입력 단가 + 최대 출력 토큰 × 출력 단가)
  × 통화당 크레딧 × 안전 계수`다. 단가는 해당 원가 통화의 **토큰 1개당** 금액이다.
  외부 요금표가 백만 토큰 단위이면 서버 구성 공급자가 정확히 환산해야 한다.
  모델별 추가 고정 비용/별도 추론 비용 등이 있는 경우 현재 산식으로 공급 가능한지 검토하고
  부족하면 후속 계산 버전과 값 계약을 확장한다. 추정 할인이나 임의 환율은 사용하지 않는다.
- Decimal precision 160의 독립 context에서 계산한다. 정책 뒤
  `ceil(max(정책 적용 가격, 원가 하한))`을 최종 int 크레딧으로 확정한다.
  무효과 정책만 있으면 정책 가격은 정상가격을 유지하되, 하한/소수 정상가격 올림은 적용된다.
- 할인율은 확정 int 크레딧 기준으로 계산 후 소수 둘째 자리 ROUND_HALF_UP한다.
  정상가격 0 또는 확정가격 ≥ 정상가격이면 0이다. `cost_floor_exceeds_normal`로
  원가 하한이 정상가격을 초과한 상황을 별도로 보존한다.
- 정책 결과의 ID/버전·입력 금액·상태를 검증한다. APPLIED만 가격을 바꿀 수 있고
  APPLIED에는 적용 근거 `reason`이 필수다. 기존 비적용 결과의 빈 reason에는 상태 설명을
  채운다. 저장 목록 순서가 실제 적용 순서이며 제거된 정책은 새 견적에만 반영된다.

공개 호출 경계:

| 서비스 | 반환/계약 |
| --- | --- |
| `pricing.calculate_billing_price(CalculateBillingPriceCommand, configuration=...)` | 저장 없는 `BillingPriceInfo` 계산 |
| `quotes.create_billing_quote(session, CreateBillingQuoteCommand, configuration=...)` | `BillingQuoteInfo` 생성/재사용, 최상위 transaction 또는 기존 use_case_transaction 참여 |
| `quotes.get_billing_quote(session, GetBillingQuoteCommand)` | 소유 사용자·전체 실행 일치 검증 후 QUOTED/EXPIRED 조회, 최신 가격표 불필요 |
| `quotes.validate_billing_quote(session, GetBillingQuoteCommand)` | 같은 검증 후 EXPIRED는 `BillingQuoteExpiredError`. 예약 서비스는 재전송 구분을 위해 get 결과에서 신규 요청에만 만료 적용 |

조회 Command는 quote_id와 **서버가 확인한 전체 BillingRequestInfo**를 받는다.
다른 사용자/미존재는 `BillingQuoteNotFoundError`, 요청 키·작업 종류·작업 지문·상품/버전·
모델/설정·토큰 예산 불일치는 `BillingQuoteConflictError`다. 같은 사용자/요청 키의
생성 재호출도 전체 조건이 달라지면 충돌한다. request_key는 자동 생성하지 않는다.

발급 TTL은 서버 설정으로 1..86400초다. 잠금과 계산 후 timezone-aware 시계로 발급 시각을
정하고 `now >= expires_at`에 만료된다. 재전송은 만료를 연장하지 않으며 이미 만료된 견적도
동일 ID/가격의 EXPIRED 결과를 반환한다. 새 견적이 필요한 경우 호출자는 사용자의 새 작업
여부를 결정하고 새 키를 공급한다. 예약 유스케이스는 기존 예약을 먼저 조회하며,
기존 예약의 정확한 재전송은 견적이 현재 만료됐더라도 반환한다.

저장은 `billing_quotes`에 요청/가격 JSONB 스냅샷과 사용자·키·발급/만료 시각을 insert한다.
JSON schema version은 1, 금액은 문자열, 최종 크레딧은 정수다. 정상가격·구간 경계·모든 원가
수치·정책 순서/버전/상태/근거/중간 가격·계산 버전 `context-budget-cost-floor-v1`을 보존한다.
저장값을 읽을 때 실행 모델이나 가격표를 다시 조회하지 않는다. frozen Info/tuple로 반환하며
공개 UPDATE/DELETE 경로는 없다. 만료 상태는 조회 결과에서만 계산한다. DB 관리자 직접
UPDATE를 막는 트리거는 기존 스냅샷 관례에 맞춰 추가하지 않았다.

기존 `usage_logs`는 실행 후 사용량, `payments`/귀속 이벤트는 확정 결제 사실이고,
`credit_transactions`는 확정된 잔액 증감 원장이므로 실행 전 견적 저장소로 재사용하지 않는다.
새 테이블의 `(user_id, request_key)` UNIQUE와 공통 advisory lock으로 동시 발급을 직렬화한다.
사용자는 RESTRICT FK로 참조하고 상품·모델은 당시 값으로 보존한다. 사용자 삭제/견적 보존
정책은 향후 계정 정리와 연결할 때 결정해야 한다. Alembic `0021`은 초기 SQL
`012_billing_quotes.sql`을 재사용하며 견적이 남아 있으면 downgrade를 거절한다.

## 후속 연결에서 필요한 작업

- 서버가 인증·유료 작업 권한, 실제 모델/설정, 정규화 작업 지문, 최종 입력 토큰과 최대 출력
  예산을 확정한 뒤 공개 서비스에 전달한다. 현재 서비스는 이 정보를 외부 모듈에서 조회하거나
  인증하지 않는다. 테스트 때문에 identity/다른 모듈 정책을 변경하지 않는다.
- 운영 가격표·원가·환산율·안전 계수·TTL을 승인하고 버전을 부여하여 조립 계층에서 주입한다.
  같은 버전의 의미를 바꾸지 말고 새 버전을 발행한다. 기존 견적에는 영향을 주지 않는다.
- 조율 계층은 실제 실행 조건을 확정해 `ReserveCreditCommand.request`로 전달한다.
  billing은 저장된 견적과 전체 조건을 비교하고 final_price_credit만 사용한다.
  견적 발급 뒤 모델 대체/문맥 변경이 생기면 이전 예약으로 다른 실행을 시작하지 않는다.
- 구현된 billing 크레딧 공개 서비스를 통해 결과 저장과 차감 확정을 아래와 같이 조율한다.
  생성 결과·usage 기록의 cost_credit 연결, 실패 해제와 복구, HTTP 오류 매핑 및
  앱 조립은 이 단계에서 수정하지 않았다. 실제 상품/프로모션/인기도 조회와 새 관련 DB도 없다.

## 결과 저장과 차감의 트랜잭션

후속 구현은 실행 전에 예약을 영속화해 가용 크레딧을 확보한다. 외부 LLM 호출 중에는
DB 트랜잭션을 열린 채 유지하지 않는다. 정상 완료 시 최상위 조율 유스케이스가
**결과 저장과 예약 차감 확정을 동일 DB 세션·동일 트랜잭션**으로 묶는다.
billing/credit 내부 서비스는 진행 중인 트랜잭션에 참여하고 임의로 commit/rollback하지 않는다.
둘 중 하나가 실패하면 결과와 차감을 모두 rollback한다. 결과 ID만 전달하는 것 자체가
원자성을 보장하지 않으므로 조율 계층에서 이 경계를 실제로 구현하고 통합 검증해야 한다.

생성 실패·취소를 확정할 때는 실패 상태 저장과 예약 해제를 같은 트랜잭션으로 처리한다.
결과 저장 실패로 rollback되면 기존 영속 예약은 RESERVED로 남는다. 복구 가능한 staging
결과가 있으면 예약을 유지하며 저장+확정을 재시도한다. 복구 불가능한 실패를 확정할 때만
별도 복구 트랜잭션에서 실패 상태 저장+해제를 수행하고, 해제 실패/중단도 같은 키로 복구한다.
기존 stale/failed generation의 usage 기록을 성공한 유료 결과로 해석하지 않는다.
스트리밍 중단·stale 결과·취소·견적 만료·예약 정리의 처리와 동시 확정/해제 충돌은
생성 연결 단계에서 명시적으로 검증한다. DB 밖의 LLM 호출까지 원자적이라고 가정하지 않는다.

## 검증

`test_billing_pricing_contracts.py`는 등록 추가·제거·재정렬·빈 구성·중복 거절,
세 정책의 소수/0 가격 보존과 미구현/비활성 구분, 필수 요청 키, 불변 값,
공개 시그니처와 types/정책의 외부 모듈·ORM import 경계를 검증한다.
DB 없이 실행 가능하며 운영 인증이나 기존 정책을 완화하지 않는다.

저장소 루트 PowerShell에서 실행:

```powershell
$env:PYTHONPATH = 'apps/api'
.venv/Scripts/python.exe -m pytest apps/api/tests/test_billing_pricing_contracts.py -q
```

2026-09-21 앞 단계(정책/값 계약) 검증 결과:

- 신규 정책/계약 테스트: 18 passed.
- 위 테스트와 기존 product_usage/product_statistics/use_case_transaction을 함께 실행:
  19 passed, 10 skipped. TEST_DATABASE_URL이 없어 기존 PostgreSQL 통합 검사 10개는
  실행하지 못했다. DB 기반 원자성/멱등성 검증이 통과했다고 해석하지 않는다.
- 변경 Python 파일 3개의 Ruff E/F/I 및 format 검사 통과.
- billing types/policies의 mypy 검사 통과 (`--follow-imports=silent`).
- `git diff --check` 통과.

2026-09-21 가격 계산·견적 단계 검증 결과:

- 신규 가격/견적/마이그레이션 검사와 기존 정책 계약, product_usage,
  product_statistics, use_case_transaction, product_migrations: **66 passed, 14 skipped**.
- 구간 경계/출력 예산/구간 공백, 미설정·잘못된 가격표, 실행 설정 미지원,
  정책 실행 순서/무효과/잘못된 반환, 원가 하한/올림/실효 할인율을 검증했다.
- 저장소 대역과 실제 JSON mapper로 불변 스냅샷 왕복, 설정 변경/가격표 제거 후 재전송,
  만료 직전/경계, 전체 실행 조건 충돌 및 다른 사용자 접근 거절을 검증했다.
- 새 PostgreSQL 검사 3개는 저장/동시 발급 재시도, 외부 트랜잭션 rollback,
  충돌 시 기존 견적 보존을 다룬다. TEST_DATABASE_URL 미설정 및 Docker daemon 부재로
  이 3개와 기존 DB 검사 11개는 실행하지 못했다. 대역 테스트를 DB 동시성 검증으로
  해석하지 않는다. 실제 DDL 동등성도 test_product_migrations 실행이 남아 있다.
- Alembic `0020:head --sql` 생성과 초기 SQL 일치, 견적 테이블 외 변경/가격 시드 부재,
  데이터 보존 downgrade 가드를 오프라인 검사했다. 실제 DB에 migration을 적용하지 않았다.
- 변경 Python 파일의 Ruff E/F/I·format 및 billing 구현 7개 파일 mypy 검사 통과.
- 기존 미커밋 변경을 보존했으며 실제 git commit/push는 하지 않았다.

재실행 명령(테스트 전용 PostgreSQL 사용 시 TEST_DATABASE_URL 설정):

```powershell
$env:PYTHONPATH = 'apps/api'
.venv/Scripts/python.exe -m pytest apps/api/tests/test_billing_pricing_contracts.py apps/api/tests/test_billing_prices.py apps/api/tests/test_billing_quotes.py apps/api/tests/test_billing_quote_migrations.py apps/api/tests/test_product_usage.py apps/api/tests/test_product_statistics.py apps/api/tests/test_use_case_transaction.py apps/api/tests/test_product_migrations.py -q
```


## 크레딧 서비스 구현 계약

공개 진입점은 `app.modules.commerce.billing.service.credits`다.

| 서비스 | 요청 | 결과 |
| --- | --- | --- |
| get_credit_balance | GetCreditBalanceCommand(user_id) | CreditBalanceInfo: balance_credit / reserved_credit / available_credit |
| reserve_credit | ReserveCreditCommand(user_id, request_key, quote_id, request) | 최초 또는 기존 CreditReservationInfo |
| commit_credit_reservation | CommitCreditReservationCommand(user_id, request_key, reservation_id, result_id) | COMMITTED CreditReservationInfo |
| release_credit_reservation | ReleaseCreditReservationCommand(user_id, request_key, reservation_id) | RELEASED CreditReservationInfo |

모든 쓰기는 호출자가 연 트랜잭션에만 참여한다. 인증된 서버 호출자가 실제 실행 조건을
확정하여 공급해야 하며 사용자가 제출한 request/가격/인가 주장 자체를 신뢰해서는 안 된다.
reserve의 사용자·키와 request 안의 사용자·키도 동일해야 한다. 견적 ID만 받는 앞 단계 계약은
실행 조건 검증에 부족하므로 request를 필수 추가했다. 기존 usage/attribution 계약은 보존했다.

계정이 없으면 CreditAccountNotFoundError, 가용 잔액이 부족하면 InsufficientCreditError다.
예약 키/예약 ID/견적 재사용/최종 상태/result_id 충돌은 CreditReservationConflictError,
사용자·키에 예약이 없으면 CreditReservationNotFoundError다. 견적 소유권·실행 조건·만료
오류는 기존 BillingQuoteNotFoundError / BillingQuoteConflictError / BillingQuoteExpiredError다.
HTTP 상태로 변환하는 작업은 후속 라우팅 계약에 남긴다.

기존 balance는 보유 크레딧을 유지한다. reserved_credit은 활성 예약 합계,
available_credit은 balance - reserved_credit이다. 예약 조회와 계정 조회의 reserved_credit은
서로 다른 의미다: 예약 Info는 최초 예약 금액을 최종 상태에서도 보존하고, 계정 Info는 현재
활성 예약 합계를 반환한다. 계정 조회는 자동 계정 생성이나 충전을 하지 않는다.

| 전이 | 보유 balance | 계정 reserved_credit | 기록 |
| --- | --- | --- | --- |
| 신규 예약 A | 유지 | +A | RESERVED 예약 생성 |
| RESERVED → COMMITTED | -A | -A | 예약에 result_id/원장 ID/확정 시각, 기존 원장 amount=-A 한 건 |
| RESERVED → RELEASED | 유지 | -A | 예약에 해제 상태/시각, 차감·환불 원장 없음 |
| 같은 예약/확정/해제 재전송 | 유지 | 유지 | 기존 예약/최종 상태 반환 |
| COMMITTED → RELEASED 또는 RELEASED → COMMITTED | 변경 없음 | 변경 없음 | 충돌 오류 |

A는 저장된 견적의 final_price_credit이다. 최신 가격표/실제 출력 토큰으로 재계산하지 않는다.
0 가격도 예약 상태와 0 금액 확정 원장을 기록하여 멱등성을 유지한다. 임베딩/요약은 견적의
유료 사용자 작업 검증에서 거절되므로 별도 청구 경로가 없다. 확정 원장의 기존 사유는
chat_usage, reference_id는 결과 ID, 전역 키는 `billing:credit-settlement:{user_id}:{request_key}`다.
기존 문자열 원장 키와 과거 amount/사유/참조는 재작성하지 않는다. 두 번째 잔액 원장은 없다.

잠금 순서는 **계정 FOR UPDATE → 사용자·키 예약 FOR UPDATE → 불변 견적 조회 →
계정 갱신 → 원장 insert(확정만) → 예약 insert/update**다. 미존재 예약도 먼저 계정을 잠그므로
같은 사용자·키 중복 및 다른 키의 초과 예약을 함께 막는다. 조회는 DB에서 다시 읽도록
populate_existing을 적용하여 세션에 남은 이전 값으로 판단하지 않는다. 견적은 공개 수정
경로가 없으며 quote_id UNIQUE는 완료/해제 후에도 재사용을 차단한다. 멱등 기록을 삭제하지 않는다.
상위 트랜잭션이 여러 사용자 계정을 변경할 때는 user_id 정렬 순서로 잠금을 획득해야 한다.

서비스의 SAVEPOINT는 외부 commit이 아니다. 계정/원장/예약 쓰기 중 오류가 나면 이번 호출의
부분 변경을 되돌리고 오류를 전달한다. 상위 호출자가 오류를 잡더라도 부분 차감은 남지 않는다.
결과 저장을 포함한 유스케이스는 실패를 삼키지 말고 외부 트랜잭션 전체를 rollback해야 한다.
SQLAlchemy begin_nested는 진입 시 호출자의 pending ORM 변경을 먼저 flush하므로, 결과의
flush 오류도 최상위 유스케이스에서 처리한다. 임의 AUTOBEGIN을 서비스가 채택하거나 종료하지 않는다.
READ COMMITTED 기준으로 검증했으며 더 강한 격리 수준의 직렬화 실패/교착은 외부에서
같은 요청 키로 전체 트랜잭션을 재시도한다.

후속 조율 예시(현재 생성 코드에 연결되지 않은 계약 설명):

```python
async with use_case_transaction(session):
    reservation = await BillingCreditService.reserve_credit(session, reserve_command)
# 위 외부 트랜잭션이 성공한 뒤 LLM 실행. DB 잠금을 유지하지 않는다.
# 기존 RESERVED 재전송은 LLM 재실행 허가가 아니다. 생성 요청 소유권/상태를 확인한다.
# COMMITTED이면 저장 결과를 재사용, RELEASED이면 같은 키로 다시 실행하지 않는다.

async with use_case_transaction(session):
    result = await ResultService.store_result(session, result_command)
    settled = await BillingCreditService.commit_credit_reservation(
        session,
        BillingTypes.CommitCreditReservationCommand(
            user_id=user_id, request_key=request_key,
            reservation_id=reservation.id, result_id=result.id,
        ),
    )
# ResultService는 예시 이름이며 새 외부 모듈 구현이나 실제 연결을 의미하지 않는다.
```

추가 후속 연결 항목:

- 생성 요청의 실행권·중복 실행 방지와 예약 ID 연결, 결과 저장·usage 기록·확정의 단일 트랜잭션.
  billing은 result_id의 외부 저장 여부를 조회하지 않는다. 결과 ID 전달만으로 저장 성공이 증명되지 않는다.
- LLM 실패/취소 확정 시 실패 상태와 해제를 같은 트랜잭션으로 저장한다. 결과 저장 rollback
  뒤에는 staging 결과의 복구 가능성을 확인하여 저장+확정 재시도 또는 실패 저장+해제를 선택한다.
  타임아웃으로 결과 저장 성공 여부가 불명확하면 먼저 생성/예약 상태를 확인한다.
- 오래된 RESERVED 복구: 생성이 아직 실행 중인지, 결과가 이미 저장됐는지 확인하는 공개 계약과
  복구 조율이 필요하다. 단순 견적 TTL 경과만으로 해제하는 워커는 구현하지 않았다.
- 장래 충전/환불/관리자 조정도 같은 계정 잠금과 balance >= reserved_credit 불변식을 준수하고
  기존 원장을 사용해야 한다. 현재 credit 빈 모듈에서 병렬 잔액 쓰기 경로를 만들지 않는다.
- RESTRICT FK로 예약/견적/확정 원장이 보존되므로 identity의 계정 삭제·보존 정책을 별도 설계한다.
  이번 작업에서 다른 모듈이나 운영 인증 정책은 변경하지 않았다.

마이그레이션 `0022`/초기 SQL `013_billing_credits.sql`은 기존 계정에 예약액 기본값 0 및
CHECK를 추가하고 credit_reservations만 새로 만든다. 기존 잔액/원장 행은 변경하지 않는다.
예약 기록 또는 비영 예약 잔액이 있으면 downgrade를 거절한다. 초기 크레딧은 테스트 fixture만
공급하며 운영 가격/충전 시드, 실결제 API는 추가하지 않았다.


2026-09-21 크레딧 관리 단계 최종 검증:

- 일회용 `pgvector/pgvector:pg17` PostgreSQL 컨테이너의 전용 `billing_test` DB 및
  테스트마다 UUID로 분리한 스키마를 사용했다. 운영 DB나 기존 데이터에는 접근하지 않았다.
- 신규 크레딧/마이그레이션 검사 17개 및 앞 단계 가격·견적, 기존 usage/통계/트랜잭션/
  스키마 검사를 합쳐 **97 passed, 0 skipped**.
- 별도 세션 6개의 동시 예약에서 잔액 20/견적 10 기준 정확히 2건 성공·4건 잔액 부족,
  예약/확정/해제 각각 5중 재전송, 확정-해제 경합의 단일 최종 전이를 확인했다.
- 신규/기존 예약의 실행 조건 불일치, 키/견적/예약/결과 ID 충돌, 다른 사용자 접근,
  최초 예약의 만료 거절과 만료 뒤 RESERVED/COMMITTED/RELEASED 재전송을 확인했다.
  실제 계정 잠금 대기를 관찰한 뒤 만료 시각을 넘겨, 잠금 획득 후 만료 검사도 검증했다.
- 예약·확정·해제 후 외부 rollback 및 잔액/원장 쓰기 뒤 오류를 주입한 SAVEPOINT rollback에서
  잔액·활성 예약 합계·확정 원장의 일관성을 확인했다.
- 초기 SQL/전체 Alembic/ORM의 실제 PostgreSQL 스키마 비교 통과. 추가로 0022 online
  upgrade/downgrade, 기존 잔액·원장 행 보존, 모델 CHECK 동등성, 해제 이력 보존 가드를 검증했다.
- 이번 변경 Python 파일의 Ruff E/F/I·format, 크레딧 서비스/mapper/repository/types/모델 5개
  파일의 mypy (`--follow-imports=silent`) 통과. 기존 미커밋 변경은 보존했으며 commit/push하지 않았다.
- 테스트 컨테이너는 검증 후 제거한다. 테스트 자료는 fixture이며 실결제/충전/생성 연결 검증을
  했다는 의미가 아니다.

재실행(테스트 전용 PostgreSQL과 vector 확장 사용, DB 이름에 test 포함):

```powershell
$env:PYTHONPATH = 'apps/api'
$env:TEST_DATABASE_URL = '<전용 테스트 DB의 postgresql+asyncpg URL>'
.venv/Scripts/python.exe -m pytest apps/api/tests/test_billing_credits.py apps/api/tests/test_billing_credit_migrations.py apps/api/tests/test_billing_pricing_contracts.py apps/api/tests/test_billing_prices.py apps/api/tests/test_billing_quotes.py apps/api/tests/test_billing_quote_migrations.py apps/api/tests/test_product_usage.py apps/api/tests/test_product_statistics.py apps/api/tests/test_use_case_transaction.py apps/api/tests/test_product_migrations.py -q
```
