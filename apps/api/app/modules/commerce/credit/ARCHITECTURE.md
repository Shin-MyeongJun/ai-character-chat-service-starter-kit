# Credit 모듈

2026-09-22 최종 계약. 단일 잔액 분리만 수행하던 임시 범위는 폐기했다.

## 책임과 파일

credit은 재화별 무료/유료 보유·예약·사용 가능량, 지갑 준비, 지급, 예약·확정·해제,
원장 및 예약 조회를 소유한다. billing/chat, 모델·토큰·견적·상품 정책을 해석하지 않는다.
타 모듈 repository/mapper/ORM을 참조하지 않으며 인가 JOIN 예외도 없다.

- `service/command.py`: 검증, 무료 우선 배분, 요청 일치와 상태 전이, SAVEPOINT 경계.
- `service/query.py`: 사용자·재화별 잔액 및 원장/예약 필터·커서 검증.
- `repository.py`: credit 소유 SQL과 잠금, Entity/Row 반환. commit/rollback 없음.
- `mapper/persistence.py`: Entity/Row를 불변 Info로 변환. I/O와 외부 조회 없음.
- `types.py`: 불변 Command/Info, bucket/status enum, 업무 오류. ORM 노출 없음.

쓰기와 조회는 변경 이유가 달라 분리했다. 각각의 밀접한 기능은 한 파일에 유지한다.
빈 기존 service.py는 service 디렉터리로 대체했다. HTTP 계층은 만들지 않는다.

## 소유 테이블

| 테이블 | 계약 |
| --- | --- |
| credit_wallets | `(user_id, currency_code)` PK, users RESTRICT FK. 신규 재화별 잠금 기준 |
| credit_balances | 지갑당 free/paid 두 행. `0 <= reserved_credit <= balance`, bigint |
| credit_transactions | 지급·확정 소비 헤더. 기존 행은 operation=legacy, 재화·namespace·UUID 키 NULL |
| credit_transaction_entries | 신규 거래의 free/paid signed 배분. 0인 배분은 행을 생략 |
| credit_reservations | 예약 ID·상태·배분·키·참조·시각. 견적은 소유하지 않음 |
| credit_accounts | 기존 단일 잔액 원본 보존. 신규 경로에서 읽어 활성화 차단 여부만 확인하며 쓰지 않음 |

거래/예약·entry의 복합 FK는 사용자와 재화를 일치시킨다. CHECK는 수량·배분 합계·상태의
결과/원장/시각 조합을 보호한다. 거래 헤더=entry 합계, 잔액=entry 누계,
예약량=활성 예약 배분 합계는 같은 지갑 잠금과 트랜잭션으로 유지하고 통합 테스트에서 대사한다.
이는 임의 직접 SQL 쓰기 전체를 강제하는 트리거가 있다는 뜻은 아니다.

## 공개 service/types

모두 `session, command`를 받는다. 재화 코드는 모든 신규 Command에서 **필수**다.
`[A-Z][A-Z0-9_]{0,31}`의 독립 식별자이며 bucket과 분리한다. 현 billing v1 경로는
`CREDIT`을 명시적으로 선택한다. 다른 코드는 인증된 서버의 신규 업무 구성이 선택할 수 있고,
어떤 경로도 다른 재화의 잔액을 합산·교환하거나 부족분으로 사용하지 않는다.

| 공개 함수 | Command → 반환 |
| --- | --- |
| command.prepare_credit_wallet | PrepareCreditWalletCommand(user_id, currency_code) → CreditBalanceInfo |
| command.grant_credit | GrantCreditCommand(user_id, currency_code, bucket, amount, reason, reference_id, namespace, request_key) → CreditTransactionInfo |
| command.lock_credit_account | LockCreditAccountCommand(user_id, currency_code) → CreditBalanceInfo. 지갑 잠금 공개 계약 |
| command.reserve_credit | ReserveCreditCommand(user_id, currency_code, namespace, request_key, amount, reference_id, reason, settlement_key, created_at) → CreditReservationInfo |
| command.commit_credit_reservation | CommitCreditReservationCommand(user_id, currency_code, namespace, request_key, reservation_id, result_id) → CreditReservationInfo |
| command.release_credit_reservation | ReleaseCreditReservationCommand(user_id, currency_code, namespace, request_key, reservation_id) → CreditReservationInfo |
| query.get_credit_balance | GetCreditBalanceCommand(user_id, currency_code) → CreditBalanceInfo |
| query.get_credit_reservation | GetCreditReservationCommand(user_id, currency_code, namespace, request_key) → CreditReservationInfo 또는 None |
| query.list_credit_transactions | ListCreditTransactionsCommand → CreditTransactionPageInfo |
| query.list_credit_reservations | ListCreditReservationsCommand → CreditReservationPageInfo |

CreditBalanceInfo는 같은 재화의 free/paid 각각 balance_credit/reserved_credit/available_credit와
그 재화의 합계를 반환한다. CreditReservationInfo는 free_amount/paid_amount/allocation_status와
최초 참조/사유/키/수량/상태/결과/원장/시각을 포함한다. 원장 조회는 signed amount와 배분을 제공한다.

모든 조회는 user_id로 스코핑한다. 목록은 currency_code 필수이며 `None`은 **미분류 이력만**
선택한다. namespace, reason, `[start, end)`, 예약 status 필터를 제공한다. limit 기본 50,
1..100만 허용한다. CreditCursor(created_at, id)의 내림차순 keyset pagination으로 동률 시각을
안정적으로 정렬한다. 커서는 동일 필터와 함께 사용한다. 페이지마다 READ COMMITTED 스냅샷이며
여러 페이지 전체의 고정 스냅샷 보장은 없다. 외부로 공개할 경우 인증·커서 직렬화는 HTTP 계층 책임이다.

## 지급·생성·수량

인증과 지급 자격은 서버 호출자가 확인한다. 이 내부 서비스는 클라이언트 입력을 직접 받는
인가 API가 아니다. PAID 지급은 현금 결제 검증이나 매출 귀속을 의미하지 않는다.
reference_id/namespace/reason은 불투명 업무 값이며 다른 모듈을 조회하지 않는다.

준비와 첫 지급만 신규 지갑+두 bucket을 생성한다. 첫 지급 동시 요청도 같은 지갑 advisory lock으로
직렬화한다. 사용자 미존재는 users FK가 거절한다. 기존 지갑이 불완전하면 보정하지 않고 오류다.
조회·예약은 지갑을 생성하거나 잔액을 수정하지 않는다.

UUID 식별자를 요구하고, metadata는 앞뒤 공백 없는 비어 있지 않은 문자열이다.
지급은 bool을 제외한 정수 `1..2^63-1`, 예약은 `0..2^63-1`이다. 지급 후 같은 재화의
전체 보유량도 bigint 범위를 넘지 못한다. 시각은 timezone-aware datetime이어야 한다.

FREE 가용량부터 예약하고 부족분만 PAID에서 예약한다. (30,70)에서 50은 (30,20)을 저장한다.
그 뒤 FREE를 지급해도 기존 배분은 바뀌지 않는다. 확정은 저장 배분대로 보유/예약량을 줄이고,
해제는 같은 배분의 예약량만 줄인다. 예약·해제는 지급/차감 거래를 만들지 않는다.
0 예약은 (0,0), 0 확정은 amount=0 헤더 1개와 entry 0개를 남겨 기존 계약을 보존한다.

## 멱등성·상태·잠금

- 준비: `(user_id, currency_code)`. 같은 지갑 준비 재호출은 현재 잔액을 반환한다.
- 지급: `(user_id, currency_code, namespace, grant, request_key)`. amount/bucket/reason/reference_id
  모두 같아야 최초 거래를 반환한다. 동일 키의 다른 내용은 CreditGrantConflictError다.
- 예약: `(user_id, currency_code, namespace, request_key)`. amount/reference_id/reason/settlement_key
  모두 비교한다. created_at은 최초 값만 보존하고 재전송 비교에서 제외한다.
- settlement_key도 `(user_id, currency_code, namespace)` 안에서 유일하다. 다른 사용자·재화·업무와
  우연히 문자열이 같아도 충돌하지 않는다. 기존 미분류 키의 전역 유일성은 부분 인덱스로 보존한다.
- 확정/해제: 기존 예약 키+reservation_id가 멱등 식별자다. 새 키를 발급하지 않는다.
  확정 재호출은 result_id도 일치해야 한다. RESERVED → COMMITTED 또는 RELEASED만 허용하며
  최종 상태 간 변경은 충돌이다. 예약 재호출은 기존 최종 상태도 그대로 반환한다.

잠금 순서는 billing 요청 키(해당 경로만) → credit-wallet(user_id/currency) advisory lock →
credit_wallets FOR UPDATE → billing 연결(해당 경로만) → 예약 FOR UPDATE → free/paid 순 잔액 쓰기다.
모든 쓰기는 같은 지갑 잠금을 사용한다. 지갑이 없는 첫 생성도 advisory lock이 직렬화한다.
다른 지갑은 독립적이다. 여러 지갑을 한 트랜잭션에서 조합하는 호출자는 user_id/currency_code 순으로
미리 준비·잠그며 역순으로 billing 요청 키를 추가 획득하지 않는다.

명시적 session.begin() 또는 상위 use_case_transaction이 필수다. AUTOBEGIN/트랜잭션 부재는
RuntimeError다. 내부 SAVEPOINT는 오류를 잡는 호출자에게도 부분 쓰기를 남기지 않는다.
상위 commit/rollback을 수행하지 않고, 상위 rollback은 지급·예약·확정·해제 모두를 취소한다.
billing SAVEPOINT가 연결 저장과 credit 변경을 함께 감싼다. begin_nested 진입 전의 호출자 pending
flush 오류는 상위 트랜잭션이 처리한다. PostgreSQL READ COMMITTED 기준이며 deadlock/serialization
failure는 상위 전체 트랜잭션을 같은 키로 재시도한다.

## 기존 데이터와 오류

0023/014의 소유권 이전은 유지하고 0024/015에서 지갑·배분·신규 키 구조를 추가한다.
기존 계정·거래·예약·연결·키·상태·수량·시각을 삭제하거나 분류하지 않는다. legacy 원장은
배분 None, legacy_unknown 예약은 배분 None으로 조회한다. 제3의 가용 잔액으로 사용하지 않는다.

기존 계정 또는 미분류 원장/예약이 하나라도 있는 사용자는 어떤 재화의 준비·지급·잔액 활성화·
예약·확정·해제도 CreditClassificationRequiredError로 차단한다. 이 오류는
CreditAccountNotFoundError(LookupError)의 하위 타입이며 billing의 기존 오류 계약으로 변환한다.
단순히 wallet 행을 직접 추가해도 차단을 우회하지 못한다. 자동 전환이나 승인 플래그는 없다.
승인 입력·검증·활성화 조건은 [최종 설계](../../../../../../docs/credit-billing-refactor-plan.md)를 따른다.

미존재 예약은 CreditReservationNotFoundError, 잔액 부족은 InsufficientCreditError,
키/상태 충돌은 CreditReservationConflictError, 입력 오류는 InvalidCreditCommandError다.
예상하지 못한 DB 오류는 숨기지 않는다. 손실이 생기는 downgrade는 사전 가드로 거절한다.

검증은 [완료 보고](../../../../../../docs/credit-billing-separation-handoff.md)를 참조한다.
