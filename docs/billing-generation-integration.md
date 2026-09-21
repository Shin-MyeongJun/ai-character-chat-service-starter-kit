# 과금 기반 검증과 다음 생성 연결 계약

이 문서는 2026-09-21의 billing 공개 구현과 현재 answers/chat 계약을 대조한 후속 작업 명세다.
현재 구현은 [과금 설계](billing-pricing-integration.md)를 따른다. 이 작업에서 외부 모듈,
라우터, 앱 조립, 운영 인증, 프로모션/통계 DB는 수정하지 않았다.
아래 생성 연결은 **미구현**이며 PostgreSQL에서 billing의 독립 동작과 상위 트랜잭션 참여만 검증했다.

## 실행 전 준비할 값

`use_cases/answers.py`가 공개 service 결과를 받아 `BillingRequestInfo`를 구성한다.
타 모듈 repository/mapper/ORM에 접근하거나 클라이언트가 제출한 가격/인가를 신뢰하지 않는다.

| 입력 | 준비 책임과 고정 규칙 |
| --- | --- |
| user_id | 인증된 사용자와 대화 소유권·유료 실행 권한을 서버에서 확인 |
| request_key | 아래 규칙에 따라 클라이언트가 보존한 UUID. 사용자 범위로 멱등 처리 |
| operation_kind | 사용자 유료 생성/리롤/이어쓰기만 분류. 내부 임베딩·요약은 청구 대상에서 제외 |
| operation_fingerprint | 정규화 버전, 입력 메시지 ID/내용·revision, 대화/이력 버전, 대상 캐릭터, 작업 종류/옵션, 최종 프롬프트 digest 등을 서버에서 SHA-256으로 고정. 전송 시각 제외 |
| product | 실행에 사용한 product_id/product_snapshot_id. 상품 없는 작업만 None |
| execution | 대체 선택을 마친 model_id/provider/model/reasoning_effort와 이름순으로 정규화한 pricing_settings |
| input_tokens / max_output_tokens | 최종 전송 프롬프트의 서버 토큰 산정값과 실제 실행에 적용할 최대 출력 예산 |
| 가격 구성 | 승인된 가격표/원가/환산율/안전 계수/TTL과 버전, 명시적으로 조립한 정책 순서. HTTP 입력이 아닌 실행 의존성 |

현재 answers는 `begin_generation` 후 문맥 검색과 최종 프롬프트 조립을 수행한다.
따라서 그 예약 위치에 billing 호출만 덧붙이면 견적의 입력 토큰을 확정할 수 없다.
후속 작업은 짧은 준비 단계에서 실행/문맥 버전을 읽고, 외부 임베딩/검색과 최종 프롬프트 준비를
DB 트랜잭션 밖에서 마친 뒤, 예약 트랜잭션에서 버전/이력을 다시 확인해야 한다.
변경되었으면 재준비/재견적을 요구하고 이전 견적으로 다른 입력을 실행하지 않는다.
현재 `prompt.estimated_tokens`는 추정값이다. 이를 가격 입력으로 사용할지 정확한 tokenizer를
도입할지 산정 방식과 버전을 먼저 정하고 견적·실행에 동일하게 적용한다.

## 요청 키와 기존 요청 확인 순서

클라이언트는 한 번의 의도적인 생성 동작을 시작할 때 UUID를 만들고, 견적 요청부터 생성 요청,
네트워크 재전송·화면 재접속·상태 확인까지 같은 키를 보존한다. 진행 중 요청에는 키·견적 ID·
대상 입력/옵션을 함께 저장하고 응답 유실 시 새 키로 자동 재실행하지 않는다.
버튼 중복 클릭도 같은 진행 작업이면 동일 키를 쓴다. 별도의 리롤/새 작업만 새 UUID를 만든다.
실행되지 않은 만료 견적의 재발급도 새 키가 필요하며 새로운 가격에 대한 사용자 동의를 받는다.

기존 answers/chat의 `request_key: str` 계약은 유지되어 있다. 후속 HTTP 경계에서 신규 과금
요청의 UUID 문자열을 검증·파싱하되 기존 비-UUID 요청의 호환 경로를 별도로 정한다.
서버가 재전송마다 UUID를 발급하거나 누락 키를 조용히 대체해서는 안 된다.

처리 순서:

1. 인증·소유권을 확인하고 `ChatService.get_answer_request`로 사용자·키에 해당하는
   기존 요청을 잠금 아래 확인한다. 기존 입력/대화/이력 식별 정보가 다르면 충돌이다.
2. 기존 요청이 있으면 저장한 실행/과금 스냅샷과 상태를 이용한다. 완료 결과는 재사용하고
   진행 요청은 상태/복구 경로로 보낸다. 현재 문맥/최신 가격을 재계산하거나 LLM을 재호출하지 않는다.
3. **기존 요청 확인 전에 `validate_billing_quote`로 만료를 거절하지 않는다.**
   기존 예약의 `reserve_credit` 재호출은 전체 실행 조건을 비교하되 만료 뒤에도 기존
   RESERVED/COMMITTED/RELEASED를 반환한다. RESERVED 반환은 새 실행권이 아니다.
4. 신규 요청만 확정된 실행 입력으로 예약한다. `reserve_credit`가 계정 잠금 후 시각으로
   신규 견적의 만료와 잔액을 최종 검사한다. 사전 만료 검사만으로 예약 가능성을 보장하지 않는다.
5. RELEASED는 같은 키로 재실행하지 않는다. COMMITTED는 저장 결과와 일치해야 한다.
   생성/과금 상태가 어긋나면 복구 대상으로 두며 다른 키로 우회 차감하지 않는다.

`create_billing_quote` 재호출은 같은 키의 최초 견적과 원래 만료를 반환한다.
가격표가 바뀌거나 제거되어도 기존 견적은 보존하며, 다른 실행 조건으로 덮어쓰지 않는다.

## 트랜잭션 경계

`create_billing_quote`는 단독 호출 시 `use_case_transaction`을 열고, 같은 관리자가 연
외부 범위에는 참여한다. 임의 `session.begin()` 안에 이 함수를 중첩하면 관리자가 기존
트랜잭션을 채택하지 않으므로 조합 시 반드시 `use_case_transaction(session)`을 사용한다.
크레딧 쓰기는 명시적인 `session.begin()` 또는 `use_case_transaction`이 필수다.
조회로 생긴 AUTOBEGIN은 쓰기 경계로 인정하지 않는다. 모든 모듈 호출은 동일 AsyncSession을 쓴다.

| 경계 | 하나의 상위 트랜잭션에서 수행할 작업 | 실패 시 |
| --- | --- | --- |
| 생성 예약 | 기존 요청 확인/실행권 확보 → 이력·실행 조건 재검증 → `begin_generation` → `reserve_credit` → 생성에 quote_id/reservation_id/불변 요청 연결 저장 | 생성 예약과 크레딧 예약 함께 rollback. 이미 별도 발급한 견적은 유지 |
| 외부 실행 | 예약 트랜잭션 commit과 세션 종료 후 LLM 호출. calling/result_ready staging은 각각 짧은 별도 트랜잭션 | DB와 공급자 사이의 원자성을 가정하지 않음 |
| 성공 저장 | 생성 잠금 → 결과/usage 저장과 기존 memory 작업 예약 → 실제 저장 상태 확인 → `commit_credit_reservation` | 결과·usage·memory 예약·차감 전체 rollback, 실행 전의 영속 크레딧 예약은 RESERVED로 남음 |
| 실패 저장 | 생성 잠금 → failed/cancelled/stale 상태와 필요한 사용량 사실 저장 → `release_credit_reservation` | 실패 기록과 해제 함께 rollback, 같은 키로 복구 |

원장 `result_id`는 성공 저장된 `GenerationInfo.id`로 연결할 예정이다. 현재 billing은 UUID만
검증하고 외부 결과 존재 여부를 조회하지 않는다. 결과 ID를 전달하는 행위만으로 원자성이 생기지 않는다.
`commit_credit_reservation`은 새 가격/실제 출력 토큰으로 재계산하지 않고 저장된 예약액을 차감한다.
세션의 SAVEPOINT 성공은 외부 commit이 아니다. 서비스 뒤 발생한 오류는 최상위까지 전달한다.
`begin_nested()`가 진입 전에 호출자의 pending 변경을 flush할 수 있으므로 flush 오류도 같은 경계에서 처리한다.

현재 chat의 `finish_generation`은 상품 버전 변경/이용 불가 시 succeeded 입력을 stale로 저장하고,
실패·취소·stale에도 `record_usage`를 호출한다. 현재 answers는 여기에 `cost_credit=0`을 전달한다.
후속 구현은 **반환된 실제 성공 상태**에만 차감을 연결해야 한다. 또한 usage의 cost_credit을
실제 확정액(실패/stale은 별도 청구 0)과 일치시키는 공개 계약을 설계해야 한다.
단순히 성공 후보 금액을 지금의 `GenerationResult.cost_credit`에 넣으면 stale usage에 요금이
남을 수 있다. 이 조정은 chat/use_cases 후속 작업이며 기존 usage가 차감 기능이라는 뜻이 아니다.

예약은 현재의 사용자 요청 키 → 대화 → 생성 잠금 이후 billing 계정 → 예약 잠금 순으로
조합하고, 성공/실패/복구에서도 대화·생성을 먼저 잠근다. billing 잠금을 잡은 후 chat 잠금을
획득하는 역순 경로를 만들지 않는다. 여러 계정은 user_id 순으로 잠근다. 전체 연결 시 이 순서의
교착 검증이 필요하며 serialization failure/deadlock은 같은 키로 상위 트랜잭션을 재시도한다.
DB 재시도가 외부 LLM 재실행을 뜻해서는 안 된다.

## 저장 실패·불확실성·복구

| 관찰한 상태 | 예약 처리 |
| --- | --- |
| 성공 결과 staging이 영속화됐지만 최종 저장 실패 | RESERVED를 유지하고 저장된 결과로 최종 저장+확정을 재시도. 공급자 재호출 금지 |
| 결과를 복구할 수 없고 실패를 확정하기로 결정 | 원래 저장 트랜잭션 rollback 후 별도 트랜잭션에서 실패 상태+해제. 이후 같은 실행의 늦은 성공 저장을 차단 |
| calling 이후 timeout/프로세스 중단, 외부 성공 여부 불명 | 실행 lease/소유권·영속 staging을 먼저 확인. 실행 중이면 예약 유지. 복구가 실행권을 회수해 실패/uncertain을 확정할 때 상태 저장+해제를 함께 수행 |
| commit 응답 유실로 DB 성공 여부 불명 | 새 세션에서 생성 상태와 동일 예약 재전송 결과를 확인. COMMITTED이면 결과 재사용, 무조건 해제 금지 |
| 해제 트랜잭션 실패 | RESERVED와 실패 저장 여부를 다시 확인하고 같은 키로 원자적 실패 저장+해제 재시도 |
| 견적 TTL 경과 또는 오래된 RESERVED | TTL만으로 해제 금지. 견적 만료는 신규 예약용이며 생성 lease와 다름 |

복구는 정상 완료와 같은 생성 잠금/실행권을 사용하고, lease를 잃은 작업자의 늦은 staging/완료가
실패 확정 뒤 성공을 저장하지 못하게 해야 한다. 현재 과금 기반에는 TTL 해제 워커나 외부 호출
재조정 기능이 없다. 불확실한 공급자 비용은 사용자 청구 성공의 증거가 아니다.

## 리롤·OCP·정책 데이터 후속 계약

리롤은 `USER_REGENERATION`으로 새 사용자 동작마다 새 키/견적을 만들고 원본 결과 ID,
대상 캐릭터, 이력 버전, 옵션을 작업 지문에 포함한다. 원본의 확정 차감을 release로 환불하지 않는다.
이어쓰기는 `USER_CONTINUATION` 입력으로 같은 예약/확정 경계를 재사용한다.

OCP는 현재 billing에 전용 작업 종류나 실행 단위 계약이 없다. 후속 OCP 조율 계층에서
사용자에게 판매하는 결과 단위, 여러 모델/단계의 가격 기준, 부분 성공/취소 기준을 먼저 정한다.
내부 단계별 LLM/임베딩/요약 호출마다 별도 예약하지 않는다. 하나의 BillingExecutionInfo로
표현할 수 없는 실행을 임의로 끼워 넣지 말고 공개 가격 입력 계약부터 확장한다.
확정된 유료 결과 단위의 실행 전 예약·성공 저장 확정·실패 해제 지점에 연결한다.

현재 `product_author`, `promotion`, `unpopular_product`는 모두 `noop-v1` 무효과 어댑터다.
테스트의 할인 어댑터는 fixture이며 운영 할인 구현이 아니다.

| 후속 제공 주체 | 어댑터에 필요한 불변 공개 데이터 |
| --- | --- |
| 상품/작가 | 상품/버전·작가 식별자, 공개/판매/적용 상태, 작가 가격 정책과 버전, 유효 시점 |
| 프로모션 | 프로모션 ID/버전, 판정된 사용자/상품 자격, 기간/기준 시각, 할인 방식/한도/중첩 순서. 사용 횟수 제한이 있으면 별도 소유 모듈의 예약·소비·취소 계약 |
| 순위/인기도 | 상품 ID, 순위/비인기 판정, 지표 정의·집계 구간/기준 시각·버전, 누락/지연 데이터 처리 규칙 |

해당 소유 모듈의 공개 service를 조율 계층이 호출하고 billing Command/Info로 변환한다.
순수 어댑터에 ORM·외부 조회를 넣지 않는다. 새 프로모션/통계 모듈이나 DB는 이번 범위에 없다.
원가 하한과 올림은 최종 계산 고정 단계로 유지하고 할인율은 정상가격과 확정가격에서 계산한다.

## 다음 커밋의 외부 수정 대상

| 대상 | 필요한 변경 |
| --- | --- |
| use_cases/answers.py 및 answer_preparation.py | 최종 문맥 준비 순서, 가격 입력 고정, 견적/예약 연결, 성공/실패 원자성, lease·staging 복구 |
| chat 공개 service/types 및 필요시 소유 저장 계층 | 생성에 과금 연결 정보 보존, 재전송/복구용 공개 정보, 실제 최종 상태에 맞는 usage 금액과 늦은 완료 차단 계약 |
| use_cases/memory.py | 기존 결과·usage·memory 작업 예약의 원자성을 유지하면서 상위 billing 확정과 조합하는 경계 검증. 내부 기억 작업은 별도 사용자 청구 없음 |
| HTTP 경계와 클라이언트 | 견적 발급/표시, UUID 요청 키 생성·보존·호환, 만료/잔액 부족/충돌 오류 매핑 |
| 앱 조립/설정 | 승인된 운영 가격표/정책/TTL 주입, 실제 생성 사용 경로 연결 |

conversation/product/llm/identity는 기존 공개 정보로 우선 연결한다. 토큰 산정·유료 권한·정책
정보가 부족할 때만 해당 소유 모듈의 공개 계약을 별도 확장한다. 인증 완화는 필요하지 않다.
충전/환불, 사용자 삭제/보존 정책, 프로모션/순위 실제 구현은 별도 범위다.

## PostgreSQL 검증 범위

`test_billing_lifecycle_integration.py`는 공개 서비스만 조합해 견적→예약→확정/실패 해제,
만료 후 전체 재전송, 가격 정책 변경 전후의 저장 견적·확정액, 견적/예약/확정/해제 이후
상위 예외 시 전체 rollback과 같은 키 재시도를 확인한다. 결과 ID는 합성 UUID다.
**실제 chat 결과 저장·LLM 호출·HTTP 인증 연결을 검증한 테스트가 아니다.**

기존 `test_billing_credits.py`의 별도 세션 동시 요청·잔액 부족·동일 키 재전송·확정/해제 경합,
다른 사용자·실행 조건 거절, 영속 예약 뒤 확정/해제 rollback 검사도 함께 실행한다.
스키마는 TEST_DATABASE_URL의 전용 PostgreSQL에 테스트별 UUID로 격리한다.
DB URL 미설정으로 skipped되면 통합 검증 완료로 기록하지 않는다.

### 2026-09-21 실행 결과

일회용 `pgvector/pgvector:pg17` 컨테이너의 `billing_test` DB, 루프백 자동 할당 포트,
테스트별 UUID 스키마를 사용했다. 운영/기존 DB는 사용하지 않았으며 검증 후 컨테이너를 제거했다.

| 검사 | 최종 결과 |
| --- | --- |
| 아래 pytest 전체 묶음 | **110 passed / 0 failed / 0 skipped** (21.96초) |
| 새 독립 생명주기 시나리오 | 6 passed, 위 합계에 포함 |
| 기존 동시성/멱등성/다른 사용자·실행 조건/상위 rollback | passed, 위 합계에 포함 |
| migration 0021/0022 범위·보존 가드 및 0022 online upgrade/downgrade | passed, 위 합계에 포함 |
| 실제 PostgreSQL 초기 SQL/전체 Alembic/ORM 비교 | passed, 열·타입·NULL·FK·UNIQUE 비교. 모든 인덱스/기본값 동등성을 주장하지 않음 |
| billing 모듈과 변경 테스트 Ruff E/F/I·format | passed (format 20개 파일) |
| 기존 billing 테스트·소유 모델·0021/0022 Ruff E/F/I | passed |
| types, policies, pricing, quotes, credits, 두 mapper, repository mypy | passed, 8개 파일, `--follow-imports=silent` |
| git diff --check | passed |

첫 전체 실행은 109 passed / 1 failed / 0 skipped였다. 공통 정적 검사가 billing의
keyword-only 가격 구성/시계를 업무 Command로 오인한 것이 원인이었다. 네 공개 함수의
파일·함수·인자·타입을 명시한 실행 의존성 구분으로 보완했으며 다른 모듈 예외를 추가하지 않았다.
별도 Ruff 검사에서 발견한 billing 기존 주석의 E501 7건은 주석 줄바꿈만 수정했다.
업무 동작·인증·다른 모듈 정책·DB 스키마 변경은 없고 재검사는 모두 통과했다.

재실행(저장소 루트 PowerShell, vector 확장을 지원하는 전용 DB 필요):

```powershell
$env:PYTHONPATH = 'apps/api'
$env:TEST_DATABASE_URL = '<test가 이름에 포함된 전용 DB의 postgresql+asyncpg URL>'
$billingChecks = @(
  'apps/api/tests/test_billing_lifecycle_integration.py'
  'apps/api/tests/test_billing_credits.py'
  'apps/api/tests/test_billing_credit_migrations.py'
  'apps/api/tests/test_billing_pricing_contracts.py'
  'apps/api/tests/test_billing_prices.py'
  'apps/api/tests/test_billing_quotes.py'
  'apps/api/tests/test_billing_quote_migrations.py'
  'apps/api/tests/test_product_usage.py'
  'apps/api/tests/test_product_statistics.py'
  'apps/api/tests/test_use_case_transaction.py'
  'apps/api/tests/test_product_migrations.py'
  'apps/api/tests/test_architecture_contracts.py'
)
.venv/Scripts/python.exe -m pytest @billingChecks -q -ra
```

이번 변경은 새 테스트 1개 파일, 공통 정적 검사 보완, billing 주석 4개 파일,
ARCHITECTURE 및 과금 문서 2개 파일에 한정했다. 작업 시작 시의 외부 모듈/DB 모델/마이그레이션/
기존 과금 구현 미커밋 파일은 해시 대조로 보존을 확인했다. git commit/push는 실행하지 않았다.
제안 커밋명: `test(billing): verify pricing and credit lifecycle contracts`.
