# Billing 모듈

- 현재 구현에서 사용하는 소유 테이블: `payments`, `usage_logs`, `product_payment_events`, `billing_quotes`, `credit_accounts`, `credit_transactions`, `credit_reservations`.
- 구독용 `subscription_plans`, `user_subscriptions`는 이 도메인의 기존 미구현 데이터다. 기존 credit 모듈은 빈 서비스/저장소만 있으므로 크레딧 단계에서 기존 잔액/원장을 billing 소유로 재사용한다. credit 모듈 코드와 기존 데이터 의미는 변경하지 않았다.
- `service/command/attribution.py`: 검증된 결제의 상품 버전별 매출 배분·환불 귀속. 모든 요청은 Command, 결과는 저장된 PaymentEventInfo다. 원래 결제/매출 한도를 넘어서는 배분·환불과 멱등 키 재사용 충돌을 거절한다.
- `service/command/__init__.py`: RecordUsageCommand → UsageRecordedInfo. generation과 같은 트랜잭션 안에서 기록한다.
- `service/query.py`: 상품 통계에 BillingStatisticsInfo를 제공한다.
- `repository.py`: 자체 결제/사용량/귀속 이력 저장과 집계용 원시 조회. `mapper/persistence.py`: Entity/Row를 공개 Info로 변환한다.

상품 버전 정보는 product 공개 query에서 받고, 통계 갱신 요청은 product 공개 Command로 전달한다. 타 모듈 ORM/JOIN 예외는 없다. use_case_transaction 및 멱등 잠금으로 재시도와 동시 환불을 처리한다.

귀속 기능은 이미 확정된 결제 사실의 귀속을 기록한다. 실제 결제 승인·외부 PG 호출·구독 상태 처리는 구현하지 않는다. 크레딧 예약/차감은 아래 별도 서비스로 구현했다. 귀속과 사용량 쓰기는 서로 다른 유스케이스이므로 파일을 나눴고 공통 저장소는 규모와 응집도를 고려해 유지했다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: chat.finish_generation → billing.record_usage → repository.create_usage_log. 매출/환불은 별도로 attribution.record_sale/record_refund → 키 잠금 → 결제/원매출 잠금 → 누계 검증 → 귀속 이벤트와 통계 예약을 따라 읽는다.

금액은 currency 단위 Decimal이며 cost_credit과 다르다. refund의 occurred_at은 실제 환불 시각, attributed_at은 원매출 귀속 시각이다. 통계 facts 조회는 [start, end), 사용량 created_at과 결제 attributed_at을 각각 사용한다.

관련 테스트: `test_product_usage`, `test_product_statistics`, `test_use_case_transaction`. billing router/schemas 및 credit service/repository의 빈 파일은 HTTP 결제나 잔액 차감 구현이 아니다. 새 크레딧 공개 서비스는 billing/service/credits.py에 있다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.

## 가격 계약과 정책 확장 (2026-09-21)

- `types.py`: 기존 usage/결제 귀속 계약을 보존한다. 추가한 불변 Command/Info는
  사용자·작업·UUID 요청 키·작업 지문·상품 버전·실제 실행 모델/설정·토큰 예산과
  가격/정책 버전·견적/예약 식별자 및 상태를 표현한다. ORM/외부 모듈 의존성은 없다.
- 공개 `service/policies.py`: `PricingPolicyAdapter.apply_policy`는
  `ApplyPricingPolicyCommand → PricingPolicyResultInfo`인 순수 계약이다.
  상품/작가, 프로모션, 비인기 작품의 세 무효과 어댑터는 입력 가격을 보존하고
  UNIMPLEMENTED/DISABLED 상태를 구분한다. 외부 조회나 가짜 조건은 없다.
- `PricingPolicyRegistry`와 `PricingPolicyRegistration`은 service 계층의 구성 객체다.
  명시한 order 순으로 정렬하며 중복 order/정책 ID를 거절한다. 새 구성으로 추가·제거·
  순서 변경을 한다. `create_default_policy_registry`의 순서는 10/20/30이며 전역 변경은 없다.
  이 객체들은 업무 값 타입이 아니므로 어댑터의 Command/Info로 전달하지 않는다.
- 가격 정책은 기존 DB 쓰기인 usage/attribution과 다른 책임이므로 독립 service 파일로
  분리했다. 단일 types 파일은 기존 import 계약과 관련 값들의 탐색성을 유지한다.
- 계약 단계 이후 가격·견적 단계에서 `billing_quotes`를 추가했다. 이후 크레딧 단계에서는
  기존 잔액/원장을 billing 소유로 재사용했다. 새로운 타 모듈 ORM/JOIN 예외는 없다.

사용자 요청의 유료 생성만 과금하고 내부 임베딩/요약은 별도 청구하지 않는다.
계산기는 모델·문맥 구간별 고정 정상가격 → 순서 있는 정책 → 원가 보호 하한 →
크레딧 단위 올림을 적용한다. 하한과 올림은 어댑터로 등록하지 않는다.
표시 할인율은 정상가격과 최종가격을 비교한다.

가격 계산 본체와 견적 생성·조회·예약 전 검증 서비스를 구현했다.
예약/차감/해제와 잔액 조회도 공개 서비스로 구현했다. HTTP 및 실제 생성 연결은 미구현이다.
요청 키는 호출자가 작업 시작 시 UUID를 한 번 만들고 재전송에 재사용한다.
누락 시 자동 생성하지 않으며 기존 API의 문자열 키 계약은 변경하지 않았다.
견적 저장 서비스는 같은 사용자·요청 키의 다른 작업 정보를 충돌로 거절한다.

생성 전에 예약하고 실패하면 해제한다. 차감 확정과 결과 저장은 최상위 조율 계층이
동일 트랜잭션으로 묶어야 하며 내부 서비스가 임의로 종료하지 않는다.
상태 전이·멱등성·필요한 외부 공개 정보·아직 구현하지 않은 연결 사항은
[후속 연결 문서](../../../../../../docs/billing-pricing-integration.md)에 기록했다.
관련 검증: `test_billing_pricing_contracts.py` (정책 구성/무효과 동작/의존성 경계).

## 가격 계산과 불변 견적

- `service/pricing.py`: 공개 `calculate_billing_price(CalculateBillingPriceCommand)` →
  `BillingPriceInfo`. 서버 구성 의존성 `BillingPricingConfiguration`을 명시적으로 받는다.
  운영 가격/기본 가격표는 없고 미설정 시 실패한다. 실행 설정 전체에 일치하는 가격표에서
  입력+최대 출력 토큰 합계의 `[min, max)` 구간을 선택한다. 구간 공백은 허용하지만
  해당 요청은 실패하며 중복·겹침은 구성 시 거절한다.
- `service/quotes.py`: 공개 `create_billing_quote(CreateBillingQuoteCommand)`,
  `get_billing_quote(GetBillingQuoteCommand)`, `validate_billing_quote(GetBillingQuoteCommand)` →
  `BillingQuoteInfo`. 조회는 만료 상태를 반환하고 검증은 만료를 오류로 거절한다.
  사용자는 인증된 서버 호출자가 공급한다. enum 값으로 유료 실행 인가를 대체하지 않는다.
- 생성은 `use_case_transaction`을 사용하고 `(user_id, request_key)` advisory lock과 UNIQUE로
  재전송을 직렬화한다. 같은 작업은 최초 견적/만료를 재사용하고 전체 요청 불일치는 거절한다.
  조회는 사용자 ID로 스코핑하고 모든 실행 조건을 비교한다. 조회에는 현재 가격 구성이 필요 없다.
  단독 생성은 이 관리자가 트랜잭션을 소유한다. 상위 조합도 `use_case_transaction`을 사용해야
  참여하며 임의 `session.begin()`/AUTOBEGIN을 채택하지 않는다. 크레딧 쓰기의 명시적
  `session.begin()` 허용과 구분한다.
- `repository.py`에 견적 insert/select만 추가했다. `mapper/quotes.py`는 버전 1 JSONB 스냅샷의
  Decimal 문자열·UUID·불변 tuple을 변환한다. Row 판단은 mapper 이후 Info에서만 수행한다.
  견적 UPDATE/DELETE 공개 경로는 없으며 만료 상태를 DB에 덮어쓰지 않는다.
  기존 스냅샷 관례처럼 DB 관리자 직접 SQL UPDATE까지 막는 트리거는 설치하지 않는다.
- `db/models/billing_quote.py`, Alembic `0021`, 초기 SQL `012_billing_quotes.sql`이 같은 테이블을
  정의한다. 사용자는 RESTRICT FK, 상품/모델은 발급 당시 값 스냅샷이며 외부 조회/JOIN이 없다.
  기존 usage/결제 테이블은 실행 전 요청·가격·만료 계약이 없어 재사용하지 않았다.
- 가격 계산, 견적 생명주기, 스냅샷 변환은 변경 이유가 달라 분리했다. 밀접한 견적
  생성/조회/사용 검증은 하나의 기능 파일에 유지하고, 기존 repository/types import는 보존했다.

원가 하한 = `(입력 토큰 × 입력 토큰당 원가 + 최대 출력 예산 × 출력 토큰당 원가)
× 통화당 크레딧 환산율 × 안전 계수`다. 단가/환산율/계수는 가격표 설정이며 계산 버전과
함께 견적에 보존한다. 하한 적용과 올림은 계산 함수에 고정된다. 최종 할인율은 소수 둘째 자리
ROUND_HALF_UP이며 정상가격 이상은 0이다. 정상가격 초과 하한은 별도 flag로 식별한다.

상세 수치 범위·만료·트랜잭션·후속 연결은 [설계 문서](../../../../../../docs/billing-pricing-integration.md),
검증은 `test_billing_prices.py`, `test_billing_quotes.py`, `test_billing_quote_migrations.py`를 참조한다.


## 크레딧 예약과 확정 (2026-09-21)

- `service/credits.py`: `get_credit_balance(GetCreditBalanceCommand) → CreditBalanceInfo`,
  `reserve_credit(ReserveCreditCommand)`, `commit_credit_reservation(CommitCreditReservationCommand)`,
  `release_credit_reservation(ReleaseCreditReservationCommand) → CreditReservationInfo`.
  실행 의존성인 AsyncSession은 별도 인자다. 모든 업무 판단은 mapper가 변환한 Info로 한다.
- `mapper/credits.py`: 계정/예약 Entity를 불변 Info로 순수 변환한다.
  `repository.py`: 계정 잠금/증감, 예약 조회/저장/상태 갱신, 기존 원장의 확정 차감을 담당한다.
  밀접한 저장 경로는 기존 repository에 추가해 import 경로를 보존했다. 가격/견적과 다른
  상태 전이 책임인 크레딧 서비스 및 mapper는 별도 기능 파일로 나눴다.
- 기존 `credit_accounts.balance`는 보유 잔액 그대로다. 추가한 `reserved_credit`은 활성 예약의
  합계이며 `0 <= reserved_credit <= balance`; 사용 가능 잔액은 두 값의 차이다.
  계정 미존재는 오류이며 자동 생성/충전하지 않는다. 조회는 한 SQL 문장의 일관된 값이다.
- `credit_reservations`: 사용자·요청 키 UNIQUE, quote_id UNIQUE, 확정 원장 transaction_id
  UNIQUE/FK, 상태별 result_id/transaction_id/finalized_at CHECK로 재전송 기록을 보존한다.
  최초 예약액은 최종 상태에서도 유지한다. 예약/해제는 이 테이블에 기록하며 잔액 증감 원장에
  가짜 출금/환불을 쓰지 않는다. 확정만 기존 `credit_transactions`에 음수 `chat_usage` 한 건을
  추가한다. reference_id는 호출자가 저장한 result_id이며 0 가격도 금액 0의 확정 기록을 남긴다.
  기존 usage/귀속 기능을 호출하거나 그 의미를 변경하지 않는다.
- 잠금 순서: 계정 `FOR UPDATE` → 해당 사용자·키의 예약 `FOR UPDATE` → 불변 견적 조회 →
  계정 갱신 → 확정 원장 insert(확정만) → 예약 insert/update. 계정 잠금은 첫 예약 행이 없을 때도
  사용자별 모든 변경을 직렬화한다. 견적 UPDATE/DELETE 공개 경로는 없고 UNIQUE/FK도 보호한다.
  동일 트랜잭션에서 여러 사용자 계정을 다룰 장래 호출자는 user_id 오름차순으로 잠근다.
- RESERVED → COMMITTED 또는 RELEASED만 허용한다. 동일 확정/해제 재전송은 금액 이동 없이
  기존 결과를 반환하고 서로 다른 최종 상태로의 전이는 충돌이다. 확정 result_id 변경도 충돌이다.
  예약 재전송은 견적·전체 실행 조건을 비교하고 최초 예약/최종 상태를 그대로 반환한다.
  신규 예약만 잠금 획득 이후 시각으로 견적 만료를 거절한다. 해제된 견적도 재사용할 수 없다.
- 쓰기는 호출자가 명시적으로 연 `session.begin()` 또는 `use_case_transaction`이 필수다.
  서비스 단독 호출 및 조회로 발생한 AUTOBEGIN은 거절한다. 서비스는 내부 SAVEPOINT로 작업
  실패의 부분 반영을 막되 외부 트랜잭션을 commit/rollback하지 않는다. SAVEPOINT 성공 뒤에도
  계정 잠금과 원장/잔액 변경은 외부 commit까지 유지된다. 결과 저장과 확정을 함께 rollback하는
  책임은 조율 계층에 있다. PostgreSQL READ COMMITTED에서 검증했으며 더 강한 격리 수준의
  serialization failure나 deadlock은 호출자가 전체 트랜잭션을 같은 키로 재시도한다.
- `db/models/billing_credit.py`, Alembic `0022`, 초기 SQL `013_billing_credits.sql`이 예약을
  정의한다. 기존 계정에는 reserved_credit=0만 추가하고 잔액/원장 과거 행은 재작성하지 않는다.
  예약 이력이 있으면 downgrade를 거절한다. 사용자/견적/확정 원장 삭제는 FK가 제한한다.
- TTL 자동 해제 워커는 없다. 오래된 RESERVED도 실행 중일 수 있어 생성 상태를 확인한 복구는
  후속 연결이다. 인증·실행 조건 확정, 실제 생성, 결과 저장/usage와의 원자적 확정, HTTP,
  충전/환불, 사용자 삭제/보존 정책은 [후속 연결 문서](../../../../../../docs/billing-pricing-integration.md)를 따른다.

검증: `test_billing_credits.py`, `test_billing_credit_migrations.py` 및 기존 과금/usage/스키마 검증.

## 독립 통합 검증과 연결 경계 (2026-09-21)

- `test_billing_lifecycle_integration.py`: 실제 PostgreSQL READ COMMITTED에서 공개
  견적/크레딧 서비스의 연속 호출을 검증한다. 만료 뒤 완료/해제 재전송, 정책 변경 전후
  불변 견적과 예약액 확정, 동일 상위 트랜잭션의 견적→예약→확정/해제 전체 rollback,
  rollback 뒤 같은 키의 정상 재시도를 독립 세션에서 확인한다.
- 기존 크레딧 테스트의 동시 예약/잔액 부족, 중복 확정/해제, 다른 사용자/실행 조건 거절,
  이미 영속화된 예약의 상위 확정/해제 rollback과 함께 실행한다. 합성 result_id만 전달하며
  실제 chat 결과 저장의 원자성 또는 생성 흐름 연결을 검증한 것으로 해석하지 않는다.
- 정책 테스트의 합성 할인은 운영 어댑터가 아니다. 상품/작가·프로모션·비인기 정책은 여전히
  무효과이며 운영 가격 구성/충전/실제 생성 연결은 없다. 기존 usage는 청구 확정이 아니다.
- 외부 연결은 기존 생성 확인 → 신규 요청만 만료 검사 → 생성/크레딧 예약의 원자적 저장 →
  트랜잭션 밖 LLM → 실제 성공 결과 저장/확정 또는 실패 상태 저장/해제 순서다.
  현재 answers의 프롬프트 준비 위치, `cost_credit=0`, chat의 stale 전환과 usage 처리,
  staging/lease 복구를 함께 조정해야 한다. 이번에는 외부 코드를 수정하지 않았다.
- [다음 생성 연결 계약](../../../../../../docs/billing-generation-integration.md)에 입력 구성,
  요청 키 보존, 잠금/트랜잭션 순서, 결과 저장 실패/불확실 호출 복구, 리롤/OCP와 정책 데이터,
  실제 검증 기록을 둔다. 기존 설계 이력과 후속 실행 명세의 변경 이유가 달라 문서를 분리했다.
