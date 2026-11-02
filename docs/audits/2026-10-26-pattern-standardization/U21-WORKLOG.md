# U21 billing→credit 반복 잠금·SAVEPOINT 정리

작성일: 2026-10-30 (Asia/Seoul)

상태: **중복 경계 정리·SQL 전후 측정·관련 PostgreSQL 회귀 완료.**

## 변경과 보존한 계약

billing은 예약·확정·해제마다 SAVEPOINT를 만들고 요청 키와 지갑을 잠근 뒤 credit의
공개 쓰기 서비스를 호출했다. 하위 서비스는 다시 SAVEPOINT, 지갑 advisory/FOR UPDATE,
legacy 확인과 잔액 조회를 실행했다. 같은 트랜잭션의 자기 잠금 대기가 아니라 중복 SQL과
SAVEPOINT 왕복 비용이며, binding 실패 시 부분 예약을 되돌리는 경계는 필요하다.

credit의 공개 실행 문맥 `use_credit_write_scope(session)`으로 이 경계를 공유한다.
billing의 세 경로와 credit의 예약·확정·해제가 같은 SAVEPOINT에 참여하며, credit의
독립 공개 호출은 자체 SAVEPOINT를 연다. billing 요청 키 잠금은 기존처럼 SAVEPOINT
안에서 지갑보다 먼저 획득한다. 공급자 호출·quote 정책·가격·예약 배분·HTTP/Python
Command/Info·저장 JSON/테이블/migration은 변경하지 않았다.

잠금 근거는 credit service 내부 session.info 상태로 보관한다. 상위 트랜잭션과 현재
SAVEPOINT의 객체/활성 상태가 일치하는 동안 같은 `(user_id, currency_code)`에 대해서만
지갑 잠금·legacy 확인을 재사용한다. 잔액은 매번 다시 조회하여 중간 예약·지급을 반영한다.
다른 사용자/재화, 새 트랜잭션, 별도 하위 SAVEPOINT에는 재사용하지 않는다. 하위 scope
종료 시 부모 상태를 복구하고 최종 종료 시 실행 상태를 제거한다. ORM/Row·내부 scope를
다른 모듈에 전달하거나 skip_validation 같은 우회 옵션을 공개하지 않았다.

참여 작업의 오류/취소를 내부에서 잡아도 scope에 실패 표식을 남겨 추가 참여와 정상
종료를 거절한다. 전체 SAVEPOINT가 rollback되므로 호출자는 바깥 트랜잭션을 계속 쓰거나
같은 키로 새 scope에서 재시도할 수 있다. 예외가 밖으로 전파될 때는 원래 SQL 오류·
CancelledError를 보존한다. 상위 rollback도 여전히 모든 쓰기를 취소한다.

지갑 준비/지급의 별도 SAVEPOINT, 다른 모듈의 공통 use_case_transaction, 서비스 입력
검증·FREE 우선 배분·기존 최종 상태 재생과 result_id 충돌 검사는 유지한다. 기존 command
파일의 실행 책임에 scope를 두고 billing은 공개 서비스만 호출한다. 두 모듈의
ARCHITECTURE.md에 공개 실행 경계와 실패/잠금 수명을 기록했다.

## PostgreSQL SQL 전후 측정

동일한 전용 PostgreSQL/UUID 스키마 fixture와 SQLAlchemy before_cursor_execute 이벤트로
실제 실행 문장을 셌다. 기존 코드에서 새 회귀 테스트를 먼저 실행해 중복을 확인한 뒤
같은 테스트를 변경 코드에서 실행했다. 초기 테스트는 목표인 1회 제한을 넘는 신규
예약/확정/해제 3건이 실패하고 재생 1건은 통과했다.

| 한 건 서비스 호출 | 변경 전 SQL | 변경 후 SQL | SAVEPOINT 전→후 | 지갑 FOR UPDATE 전→후 |
| --- | ---: | ---: | --- | --- |
| 신규 예약 | 22 | 17 | 2→1 | 2→1 |
| 동일 키 예약 재생 | 10 | 10 | 1→1 | 1→1 |
| 확정 | 20 | 15 | 2→1 | 2→1 |
| 해제 | 18 | 13 | 2→1 | 2→1 |

변경한 세 경로에서 RELEASE SAVEPOINT도 2→1, advisory lock은 3→2,
legacy 검사는 2→1이다. 남은 advisory 두 개는 billing 요청 키와 credit 지갑으로
보호 대상이 다르다. 잔액 조회를 캐시하지 않아 오래된 잔액으로 배분하지 않는다.

수치는 준비된 FREE 20 CREDIT 지갑, 이미 발급된 10 CREDIT 견적을 사용한 서비스 경계의
실측이다. fixture 준비와 외부 트랜잭션 commit은 SQL 이벤트 계수에 포함하지 않았다.
운영 데이터 분포·네트워크 지연·처리량·잠금 대기 시간의 성능 개선율을 측정한 것은 아니다.

## 검증

프로젝트 `.venv/Scripts/python.exe`와 기존 `tools/run_postgres_audit_tests.py`를 사용했다.
도우미는 Git 제외 설정 파일의 localhost 전용 감사 DB/계정만 허용하고 live 공급자 키를
제거한다. 테스트마다 UUID 스키마를 만들고 정리하며 앱 DB·전역 환경·Docker 구성을
바꾸지 않았다. Windows asyncio/로컬 DB 접근을 위해 승인된 샌드박스 밖 실행을 사용했다.

- 신규 `test_billing_credit_scope.py` **16 passed**: SQL 횟수 4경로, 실제 SQL 오류/취소
  6조합, 잡힌 하위 실패의 scope 전체 rollback과 상위 계속 실행, 중간 예약/지급 뒤
  최신 무료/유료 배분, 다른 사용자/재화 격리, 하위 rollback/새 트랜잭션 잠금 재획득,
  billing/독립 credit의 동시 예약 잔액 부족을 확인했다.
- 기존 billing/credit 회귀와 초기 SQL 테스트를 합친 **96 passed**에서 견적 만료의
  지갑 잠금 후 검사, 중복 확정/해제·최종 상태 경쟁, 부족 잔액, legacy 차단, 연결/원장
  저장 실패와 외부 rollback을 확인했다.
- 답변·과금까지 확장한 첫 실행에서 **149 passed / 3 failed**였다. 실패 3건은 기존
  commit 응답 유실 테스트가 현재 `_locked_generation`의 실제 트랜잭션 소유 경계에
  오류를 주입하지 못한 경우다(`injected=False`). production 완료 로직을 바꾸지 않고
  generation command의 가져온 transaction 경계에도 failpoint를 연결했다. 수정 후
  응답 유실 4단계와 신규 scope 16건은 **20 passed**다.
- 최종 관련 8파일 통합 실행은 **152 passed / 0 failed / 0 skipped**다. 실제 PostgreSQL에서
  답변 저장·usage·메모리 예약·과금 확정의 원자성, commit 응답 유실과 동일 키 재생까지
  검증했다. 앞선 96/16/20건과 중복되는 테스트를 포함하므로 합산하지 않는다.
- 필수 품질 검사는 기준선 0, Ruff 393파일, mypy 372소스, 아키텍처/패턴 13건이 통과했다.
  타입 예외·검사 규칙을 완화하지 않았다.

재현 명령:

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_billing_credit_scope.py -s
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_billing_credit_scope.py apps/api/tests/test_billing_credits.py apps/api/tests/test_credit_services.py apps/api/tests/test_credit_wallets.py apps/api/tests/test_billing_lifecycle_integration.py apps/api/tests/test_answer_billing_integration.py apps/api/tests/test_nonstream_answers.py apps/api/tests/test_use_case_transaction.py
$env:PYTEST_ADDOPTS='--basetemp=tmp/u21-quality-final-20261030'
.venv/Scripts/python.exe tools/check_backend_quality.py
```

실제 PostgreSQL 잠금·경합·SAVEPOINT rollback은 위 범위에서 검증했다. 전체 API/브라우저
회귀, live 공급자, 실제 현금 결제 시스템 또는 운영 부하 측정은 이번 작업 범위가 아니다.
