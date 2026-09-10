# Billing 모듈

- 현재 구현에서 사용하는 소유 테이블: `payments`, `usage_logs`, `product_payment_events`.
- 구독용 `subscription_plans`, `user_subscriptions`는 이 도메인의 기존 미구현 데이터다. `credit_accounts`, `credit_transactions`는 별도 credit 모듈 범위이며 여기서 접근하지 않는다.
- `service/command/attribution.py`: 검증된 결제의 상품 버전별 매출 배분·환불 귀속. 모든 요청은 Command, 결과는 저장된 PaymentEventInfo다. 원래 결제/매출 한도를 넘어서는 배분·환불과 멱등 키 재사용 충돌을 거절한다.
- `service/command/__init__.py`: RecordUsageCommand → UsageRecordedInfo. generation과 같은 트랜잭션 안에서 기록한다.
- `service/query.py`: 상품 통계에 BillingStatisticsInfo를 제공한다.
- `repository.py`: 자체 결제/사용량/귀속 이력 저장과 집계용 원시 조회. `mapper/persistence.py`: Entity/Row를 공개 Info로 변환한다.

상품 버전 정보는 product 공개 query에서 받고, 통계 갱신 요청은 product 공개 Command로 전달한다. 타 모듈 ORM/JOIN 예외는 없다. use_case_transaction 및 멱등 잠금으로 재시도와 동시 환불을 처리한다.

이 기능은 이미 확정된 결제 사실의 귀속을 기록한다. 실제 결제 승인·외부 PG 호출·잔액 차감·구독 상태 처리는 구현하지 않는다. 귀속과 사용량 쓰기는 서로 다른 유스케이스이므로 파일을 나눴고 공통 저장소는 규모와 응집도를 고려해 유지했다.
