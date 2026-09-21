# Billing/Credit 최종 계약과 기존 데이터 전환 보류

2026-09-22. 현재 원본 구현의 기준 문서다. 과거 “설계만”, “단일 잔액만”, “무료/유료 다음 단계”
범위와 미적용 단일 잔액 복구 패치는 이 구현으로 대체했다. 최초 자료는 작업 시작 복구 사본에 보존했다.

## 구현 범위와 책임

billing은 기존 가격표·정책·견적·실행 조건·만료를 검증하고, 현재 v1 상품의 소비 재화 CREDIT과
확정 수량을 선택하여 credit 공개 service/types로 전달한다. quote와 reservation 연결은
billing_credit_bindings가 소유한다. 기존 네 공개 credit 어댑터 함수와 Command/Info/오류 계약,
사용량·매출/환불 귀속·통계 계약을 유지한다. free/paid 합계는 같은 CREDIT 안에서만 계산한다.

credit은 재화별 free/paid 지갑·지급·예약·확정·해제·원장·조회 책임을 갖는다.
[credit ARCHITECTURE](../apps/api/app/modules/commerce/credit/ARCHITECTURE.md)에 정확한
공개 함수·Command/Info·멱등 키·잠금·수량·오류 계약을 기록했다.
[billing ARCHITECTURE](../apps/api/app/modules/commerce/billing/ARCHITECTURE.md)는 기존 가격과
신규 호출 경계를 함께 설명한다. 타 모듈의 저장 계층 직접 참조나 chat → credit 호출은 없다.

기존 v1 견적은 CREDIT을 뜻한다. v1 의미를 미래 설정 변경으로 다른 재화로 바꾸면 안 된다.
새 재화를 billing 상품 가격에 도입하려면 견적의 불변 재화 스냅샷과 새 버전 공개 계약을 별도로
추가해야 한다. 현재 credit의 재화 구조·격리는 여러 재화를 지원하지만 billing v1은 CREDIT만 선택한다.

## 스키마 경로

0023은 작업 시작 시 staged/unstaged 내용이 다른 신규 파일이었다. Git commit 이력에는 없으며
운영 적용 여부를 조회하지 않았다. 현재 실제 0023의 코드/SQL 값과 014 바이트를 유지하고 후속 0024를 추가했다.
0023은 기존 긴 SQL 문자열의 Python 표기만 Ruff에 맞게 나누었으며 최초 사본과 AST 전체가 같다.
운영 DB를 조회하거나 revision을 추정하여 stamp하지 않았다. 이미 적용한 revision 재작성은 없다.

0024/015는 신규 wallet/balance/entry, 거래의 operation·currency·namespace·UUID key,
예약의 currency·free/paid·allocation_status를 추가한다. 서비스·타입·mapper·ORM과 함께 맞췄다.
legacy 글로벌 키는 부분 UNIQUE 인덱스로 보존하고 신규 키는 사용자/재화/업무로 스코핑한다.
기존 account와 거래·예약의 금액/ID/참조/키/상태/시각은 그대로 보존한다.

Alembic은 한 PostgreSQL 트랜잭션에서 DDL을 수행한다. 초기 015도 BEGIN/COMMIT으로 원자적이다.
이전 실패는 모든 신규 DDL을 rollback한다. 0024 downgrade는 지갑이나 분류된 거래/예약이 있으면
첫 DROP 전에 거절한다. 이력이 없는 경우에만 0023으로 되돌릴 수 있다. 0023의 원래 이력 가드도 유지한다.
초기 SQL은 빈 DB 설치 경로이고 기존 DB에는 Alembic만 사용한다. create_all은 migration 대체가 아니다.

## 확정된 기존 데이터 정책

**분류 근거 없음: 분류 승인 전 기존 데이터 전환·활성화 보류.** 추가 승인을 질문하지 않는다.
기존 잔액 전체를 임의 FREE/PAID로 분류하지 않는다. purchase/refund/subscription_grant라는
사유 이름만으로는 보너스·구독 유무상 구성과 과거 소비 배분을 복원할 수 없다.

현재 차단 위치는 credit/service/command.py의 `_reject_legacy_credit`다. credit_accounts 행,
operation=legacy 거래, currency NULL 예약 중 하나라도 있는 사용자는 prepare/grant/balance 및
모든 예약 쓰기가 차단된다. 명시적 지갑 생성이나 다른 재화 선택도 이를 우회하지 못한다.
조회 서비스의 currency_code=None은 미분류 원장/예약 이력만 반환하고 잔액을 만들지 않는다.
신규 사용자 경로는 완성되어 빈 DB와 합성 신규 데이터로 정상 사용할 수 있다.

## 승인 이후 전환에 필요한 입력과 검증

승인 전환 도구/활성화 writer는 이번 구현에 포함하지 않는다. 승인 데이터 없이 실행할 수 있는
우회 API도 제공하지 않는다. 이후 전환 변경은 기존 자료를 덮어쓰는 UPDATE나 재지급으로 만들지 않고,
별도의 승인 manifest와 opening balance provenance를 보존해야 한다.

필요한 manifest 입력:

1. 승인 ID·승인자·승인 시각·근거 위치·대상 재화·기준 시각과 당시 DB revision.
2. 대상 사용자별 기존 account 원본(ID, balance, reserved_credit, updated_at)과 거래/예약 ID 집합 및 digest.
3. 사용자별 FREE/PAID opening 보유량과 분류 근거. 각 값은 bool 제외 bigint 비음수,
   합계는 기존 balance와 정확히 일치해야 한다.
4. 진행 중 예약별 FREE/PAID 배분과 근거. 각 합계는 기존 reserved_credit와 일치하고,
   bucket별 활성 예약 합계는 승인된 보유량 이하이며 account의 reserved_credit 합계와도 같아야 한다.
5. 기존 잔액과 원장 누계 차이의 승인된 설명. 원장을 지우거나 과거 지급을 다시 기록해 맞추지 않는다.
6. 과거 확정/해제 이력의 분류 가능한 범위와 증거. 근거가 없는 거래·배분은 계속 미분류로 보존한다.

승인 writer는 구버전 writer 중단과 동일 잠금 아래 digest/원본/대상 집합을 재검증한다.
중복 사용자·누락/중복 예약·범위 초과·다른 사용자나 재화·불일치 합계·기준 이후 데이터 변경을
전부 거절한다. manifest와 신규 opening 잔액·활성 예약 배분을 한 트랜잭션으로 저장하고,
원본 account/원장/예약의 ID·금액·키·상태·시각을 보존하는 별도 provenance 구조가 필요하다.

현재 guard를 제거하거나 account를 지워 활성화하면 안 된다. 승인 manifest를 검증한 사용자만
활성화하도록 guard를 확장하는 후속 migration/service 변경과 이관 전후 대사·롤백 테스트가 필수다.
합성 분류 입력은 그 후속 전환 도구를 검증하는 fixture일 뿐 운영 승인으로 간주하지 않는다.
이번 검증은 실제 과거 DDL·합성 미분류 데이터를 보존하고 신규 경로가 이를 차단함을 검증한다.

## 범위 밖

실제 chat/answers 생성 연결, payment/현금 결제·환불, HTTP API, UI, 관리자 화면,
billing_chat 분리, 재화 만료·교환·송금·확정 소비 환급은 구현하지 않았다.
PAID 지급은 결제 사실을 검증한 것으로 취급하지 않고 usage/매출을 자동 생성하지 않는다.
[생성 연결 문서](billing-generation-integration.md)는 후속 chat 조율 작업의 기준이다.

최종 원본 실행 결과와 재실행 명령은 [완료 보고](credit-billing-separation-handoff.md)에 기록한다.
