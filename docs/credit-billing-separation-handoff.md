# Billing/Credit 구현 완료 보고

2026-09-22. **최종 원본 작업 폴더의 신규 지갑·무료/유료·지급·조회 구현을 완료했다.**
단일 잔액 분리만 검증했던 과거 인계는 이 문서로 대체한다. 별도 사본/패치의 테스트 결과를
이번 원본 결과로 사용하지 않았다. 운영 데이터 분류·활성화는 아래 결정대로 계속 보류한다.

## 복구와 작업 기준

작업 시작에 staged 16개, unstaged 23개(양쪽 중복 포함), untracked 0개를 구분했다.
복구 경로: `C:/Users/smj/AppData/Local/Temp/chat-kit-credit-backup-20260921-222226`.
`staged.patch`, `unstaged.patch`는 binary diff이며 `status.txt`와 당시 실제 파일 사본도 저장했다.
이 사본에는 미적용 단일 잔액 복구 패치 원문도 있다. 현재 `.patch` 파일은 적용 금지 안내로 대체했다.

실제 작업 파일을 기준으로 순차 구현했고 서브에이전트/별도 작업에 수정을 맡기지 않았다.
원본/복구 사본을 대조했고 무관한 코드나 기존 데이터에 대한 복원·삭제는 하지 않았다.
최종 working tree로 검증한 뒤 billing/credit 작업 경로만 같은 내용으로 stage하여 중간본 혼재를 정리했다.
무관한 credit-separation-review-path.txt의 기존 staged/삭제 상태는 건드리지 않았다.
reset --hard, clean, 전체 checkout, commit/push는 실행하지 않았다.

0023은 신규 staged 파일이었고 Git commit 이력이 없었다. 운영 적용 여부는 조회하지 않았다.
0023의 동작을 바꾸지 않고 후속 0024를 추가했다. 마지막 Ruff 정리에서 0023의 긴 문자열 표기만
분리했으며 **최초 사본과 전체 Python AST 및 SQL 문자열 값 일치**를 확인했다. 014는 바이트 그대로다.

## 완성된 기능과 공개 계약

- billing은 상품의 소비 재화 CREDIT과 수량, 가격 정책·견적·실행 조건·만료, 예약 연결을 소유한다.
  기존 4개 공개 어댑터 함수와 Command/Info/오류, usage·매출/환불 귀속·통계는 유지했다.
- credit은 독립 currency_code + free/paid 지갑, 명시 준비와 첫 지급, 무료 우선 예약,
  저장 배분 확정/해제, 지급·소비 원장과 잔액/예약/거래 조회를 소유한다.
- 내부 지급은 서버가 확인한 사용자/재화/bucket/양수 수량/사유/업무 참조/namespace/UUID 키를 받는다.
  PAID 지급이 현금 결제 검증이나 매출을 뜻하지 않는다. bool·0·음수·범위 초과를 거절한다.
- 조회는 사용자·재화와 기간/사유/namespace, 예약 상태 필터 및 (created_at,id) 커서를 제공한다.
  예약·해제는 가짜 지급/차감 원장을 만들지 않는다. 0 견적의 예약/확정은 보존했다.
- 같은 재화의 FREE 30 / PAID 70에서 50 예약은 (30,20)이다. 이후 FREE 추가 지급에도 배분을 유지한다.
  다른 사용자·재화·namespace의 키와 잔액은 격리한다.
- 첫 지급/준비부터 지갑 잠금을 직렬화하며 명시적 상위 트랜잭션에 참여한다.
  내부 SAVEPOINT로 지급/원장/배분/billing 연결 저장 실패를 원자적으로 되돌린다. 내부 commit은 없다.
- 0024와 초기 015를 추가하여 ORM/서비스/types/mapper/초기 SQL/Alembic을 일치시켰다.
  FK·UNIQUE·CHECK·인덱스와 이력 손실 방지 downgrade 가드를 포함한다.

함수별 입력/결과·오류·키 일치 조건·잠금 순서는
[credit ARCHITECTURE](../apps/api/app/modules/commerce/credit/ARCHITECTURE.md),
[billing ARCHITECTURE](../apps/api/app/modules/commerce/billing/ARCHITECTURE.md)에 기록했다.

## 최종 원본 검증 결과

| 검사 | 결과 |
| --- | --- |
| 아래 17개 pytest 파일 묶음 | **202 passed, 0 failed, 0 skipped**, 80.07초 |
| 변경 Python 전체 Ruff E/F/I | 통과, 27개 파일 |
| 변경 Python 전체 Ruff format --check | 통과, 27개 파일 |
| credit 전체 + billing credit 어댑터/mapper + credit ORM mypy | 통과, 11개 파일, --follow-imports=silent |
| git diff HEAD --check 및 git diff --cached --check | 통과 |
| 0023 마지막 표현 정리 후 migration 재검사 | **8 passed, 0 failed, 0 skipped**, 13.88초. 최초 사본과 AST/SQL 값 동등 |

모든 DB 검사는 별도 `pgvector/pgvector:pg17`의 `credit_completion_test` 및 UUID 스키마에서 실행했다.
온라인 전체 Alembic 검사에는 `credit_schema_test_<UUID>` 임시 DB를 만들고 검사 후 제거했다.
최종 회귀 로그는 `C:/Users/smj/AppData/Local/Temp/credit-final-regression-20260922.log`에 남겼다.

검증된 항목:

- 무료만/유료만/혼합 소비, 부족, 사용자·재화 격리와 다른 재화 보충 금지, 예약 후 지급에도 배분 유지.
- 지급/예약/확정/해제 중복 및 다른 요청 충돌, 동시 첫 지급/준비·동시 예약·확정/해제 경합.
- bool/음수/0/범위 초과 지급 거절, 지갑 생성 정책, 조회/예약의 자동 생성·보정 금지.
- 원장 헤더=entry 합계, bucket 보유량=entry 누계, bucket 예약량=활성 예약 배분 합계 대사.
- 상위 rollback, 원장/entry/예약/확정/해제/billing 연결 실패를 호출자가 잡아도 부분 쓰기 없음.
- 잠금 대기 후 만료, 기존 예약 재전송, 가격/정책 변경 뒤 기존 견적·배분 보존.
- 과거 실제 revision DDL에서 만든 기존 데이터의 보존과 미분류 경로 차단, 이전 실패 시 DDL rollback,
  이력 손실 downgrade 거절. 미분류를 무료/유료 0으로 위장하지 않는 조회.
- 실제 빈 DB 전체 online Alembic upgrade 및 초기 SQL 설치와 ORM 비교.
  billing/credit 8개 테이블의 열/타입/NULL/기본값/PK/FK/UNIQUE/CHECK/인덱스를 비교했다.
  전체 저장소 테이블의 열/타입/NULL/FK/UNIQUE 비교도 기존 migration 회귀에서 수행했다.
  Alembic·초기 SQL 각각으로 만든 DB에 공개 지급→혼합 예약→확정→잔액 조회를 직접 실행했다.
- usage·상품별 매출/환불 귀속·통계·트랜잭션·chat 메시지·기존 OpenAPI/공개 계약 회귀.
  chat → credit, credit → billing/chat 및 타 모듈 repository/mapper/ORM 직접 참조 금지 검사.

중간 검사에서는 과거 테스트의 컬럼 순서 복사 및 DDL 후 prepared query 재사용 오류가 있었다.
실제 historical DDL과 명시 컬럼을 사용하도록 테스트를 수정했다. 마지막 재개 때 Docker가
종료되어 DB 연결 오류도 있었으나, 환경 복구 후 최종 전체 검사를 재실행했다. 테스트를 skip하거나
요구를 삭제하여 통과시키지 않았다. 최종 실행에는 실패/skip이 없다.

Docker 복구 시 시작을 막던 0바이트 임시 소켓 디렉터리만 확인해 `*.credit-test-stale-20260922`,
`*.credit-test-retry-20260922` 이름으로 보존했다. 컨테이너/데이터 초기화는 수행하지 않았다.
이 작업에서 만든 전용 테스트 컨테이너와 임시 볼륨만 생성 시 ID를 대조한 뒤 제거했다.

## 기존 데이터 전환 보류와 미구현 범위

사용자 결정인 **분류 승인 전 전환·활성화 보류**를 유지한다. 기존 계정/미분류 원장/예약이 있는
사용자는 신규 재화 준비·지급·잔액 활성화·예약·확정·해제를 차단한다. 이력은 조회 가능하며
기존 계정·금액·키·상태·시각을 삭제/초기화하거나 전부 FREE/PAID로 분류하지 않는다.

승인 manifest, 기준 잔액·활성 예약의 분류 근거와 합계, 원장 차이 설명, 변경 digest 검증과
활성화 조건은 [최종 계약](credit-billing-refactor-plan.md)에 명시했다. 승인 전환 writer와
provenance 구조는 승인 입력 없이 실행할 수 없도록 현재 제공하지 않는다. 승인 이후 별도
이관 코드·대사 검증이 필요하다. 이번의 합성 데이터 검증은 운영 분류 승인이 아니다.

실제 chat/answers 생성·LLM·결과 저장과 과금 연결, payment/현금 결제·환불, HTTP API,
프런트엔드/관리자 화면, billing_chat 분리, 재화 만료·교환·송금·확정 소비 환급은 범위 밖이다.
현재 운영 DB migration, 배포, 실결제·운영 분류 이관은 실행하거나 검증하지 않았다.
전체 저장소에 대한 무차별 pytest/mypy 실행을 의미하지 않으며 위 관련 회귀 범위만 검증했다.

## 재실행

전용 PostgreSQL 17 + vector 확장 및 테스트 DB 생성 권한이 필요하다. TEST_DATABASE_URL의 DB 이름에
`test`가 들어가야 한다. 운영 DATABASE_URL로 실행하지 않는다.

```powershell
$env:PYTHONPATH = 'apps/api'
$env:TEST_DATABASE_URL = '<전용 테스트 DB postgresql+asyncpg URL>'
$creditChecks = @(
  'apps/api/tests/test_billing_pricing_contracts.py'
  'apps/api/tests/test_billing_prices.py'
  'apps/api/tests/test_billing_quotes.py'
  'apps/api/tests/test_billing_credits.py'
  'apps/api/tests/test_billing_lifecycle_integration.py'
  'apps/api/tests/test_billing_quote_migrations.py'
  'apps/api/tests/test_billing_credit_migrations.py'
  'apps/api/tests/test_credit_services.py'
  'apps/api/tests/test_credit_ownership_migrations.py'
  'apps/api/tests/test_credit_wallets.py'
  'apps/api/tests/test_credit_wallet_migrations.py'
  'apps/api/tests/test_product_usage.py'
  'apps/api/tests/test_product_statistics.py'
  'apps/api/tests/test_use_case_transaction.py'
  'apps/api/tests/test_product_migrations.py'
  'apps/api/tests/test_chat_messages.py'
  'apps/api/tests/test_architecture_contracts.py'
)
.venv/Scripts/python.exe -m pytest @creditChecks -q --tb=short
```
