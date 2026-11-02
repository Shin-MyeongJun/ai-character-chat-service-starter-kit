# U18 오류 분류·복구 진단

작성일: 2026-10-30 (Asia/Seoul)

상태: **분류·진단 및 영속 복구 상한·격리·수동 복구 구현/검증 완료. 운영 DB 적용과 실제 네트워크 장애·live 공급자 검증은 별도다.**

2026-10-30의 프로세스 진단 횟수와 미확정 정책 설명은 아래 「U18 잔여 정책 구현」에서
대체한다. 앞선 날짜의 실행 결과와 검증 범위는 당시 기록으로 보존한다.

## 확인한 문제와 변경

예약 전 문맥 준비의 catch-all이 TypeError·임의 ValueError·저장소 오류까지 영구 실패
receipt로 저장해 request_key를 소진했다. 이제 예산 초과·지원 모델·공급자·timeout의
예상 실패만 기존 unbilled receipt로 저장한다. SQLAlchemy 오류는 기존 AnswerStorageError,
그 밖의 내부 오류는 안전한 RuntimeError로 전파한다. 생성·과금 예약·텍스트 호출이 없는
시점이므로 같은 키로 다시 시도할 수 있다. 공급자 호출 후에는 결과가 불확실할 수 있어
기존 terminal 실패/uncertain 및 같은 키 재생을 유지한다.

결과 검증의 `empty_response`·`invalid_result`·`invalid_usage`는 내부 전용 예외의 code로
분류한다. 임의 예외 메시지가 같다고 검증 실패로 오인하지 않는다. durable billing binding
누락·예약액 불일치 등은 AnswerStorageError의 하위 타입인 AnswerStateError로 식별한다.
이 하위 타입도 기존 HTTP 503/storage_pending_recovery/retry_same_key=True 계약을 따른다.

예약·calling staging·결과 staging·완료·취소 정리·복구 scan·재조회 실패를 구분해 기록한다.
내부 오류·불변 조건·DB 제약·DB 연결/풀 장애·기타 저장소 오류·공급자 오류를 타입으로
분류한다. OperationalError라는 이름만으로 일시 장애라고 단정하지 않는다. failure_class는
원인의 종류이고 storage_uncertain은 commit 확인 여부이며 자동 재시도 허가와 다르다.

예약 전에는 임의 diagnostic_id를 쓰고 예약 commit/재조회 로그에서 generation_id와 연결한다.
그 이후 로그는 generation_id로 상관시킨다. 실행 token·request_key·사용자 원문을 상관 값으로
사용하지 않는다. 원인 체인은 최대 4개 예외 타입, app 내부 stack_frames는 최대 24개
상대 파일/함수/행 번호다. 예외 str/repr·SQL·params·locals·source·절대 경로·공급자 메시지와
raw traceback은 출력하지 않는다. structlog의 예약 필드인 stack과 충돌하지 않는
stack_frames를 사용하며 실제 기본 렌더러에서도 검증했다.

같은 키 재생과 background 복구도 일반 완료와 동일한 완료·재조회 경계를 사용한다.
commit 응답 유실 뒤 새 세션의 terminal 상태를 확인하면 저장된 답변을 반환한다.
재조회도 실패하면 원래 실패와 재조회 오류를 각각 진단하고 최초 cause를 보존한다.
staging/과금 예약을 임의로 해제하거나 공급자를 다시 호출하지 않는다.

복구 attempt_count는 orchestrator 인스턴스의 최근 1,024개 생성에 대해 집계한다.
terminal 확인 시 제거하고 재시작·LRU 퇴출 시 초기화된다. 영속/전역 시도 횟수나 재시도
예산이 아니다. 개별 생성 실패는 다른 복구를 막지 않고 CancelledError는 전파한다.
새 테이블·migration·저장 JSON 필드·복구 backoff/상한·격리·강제 예약 해제는 추가하지 않았다.

오케스트레이션은 기존 answers workflow에 유지하고 타입/코드 위치 정제는
service/util/answer_diagnostics.py로 분리했다. 이 보조 함수는 DB 조회·업무 실행을 하지 않는다.
chat/ARCHITECTURE.md를 갱신했고 기존 작업 트리의 다른 변경은 보존했다.

## 검증

프로젝트 `.venv/Scripts/python.exe`를 사용하고 TEST_DATABASE_URL,
TEST_AUTH_DATABASE_URL, VOYAGE_API_KEY를 제거한 오프라인 실행이다.

- 신규 test_answer_error_diagnostics: 23개. 준비 내부/DB 오류에서 예약·호출 차단과
  같은 키 재시도, 예상 준비 실패의 receipt 유지, SQL/메시지/locals 제외, 원인 체인 순환,
  타입 분류, 복구 격리·시도 횟수·상한 메모리·취소 전파를 확인한다.
- 일반 완료·같은 키 재생·background 복구에서 실제 SQLite commit 뒤 예외를 주입해
  새 세션 terminal 재조회와 usage/credit/memory 효과 각 1회를 확인한다. 기존 completion
  테스트의 DB 대역을 사용하며 PostgreSQL 행 잠금·격리 검증을 대신하지 않는다.
- 관련 답변 workflow/완료/HTTP 5파일: **111 passed**.
- 신규 진단과 기존 메모리 기한 테스트 단독 실행: **45 passed**.
- 필수 품질 검사: 기준선 **0**, Ruff **393파일**, mypy **372소스**,
  아키텍처/패턴 **13 passed**.

- 최종 전체 API: **1463 passed / 0 failed / 288 skipped**, 기존 422 경고 2개.
  최종 상관 ID 연결 검증을 포함한 현재 작업 트리 전체 결과다. 신규 23건과 품질 13건을
  다시 더하지 않으며 앞선 다른 미커밋 작업도 포함한다.
- 변경 파일 Ruff format/check와 git diff --check 통과.

로그:

- `tmp/u18-focused-3.txt` — 관련 답변 111개
- `tmp/u18-focused-final.txt` — 진단/메모리 기한 45개
- `tmp/u18-backend-quality-complete.txt` — 최종 필수 품질 검사
- `tmp/u18-api-regression-complete.txt` — 최종 전체 API

주요 명령(각 basetemp는 새 프로젝트 경로):

```powershell
$env:PYTHONPATH='apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
Remove-Item Env:TEST_DATABASE_URL,Env:TEST_AUTH_DATABASE_URL,Env:VOYAGE_API_KEY -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p no:cacheprovider apps/api/tests -q -rs --tb=short --basetemp=tmp/u18-api-complete
$env:PYTEST_ADDOPTS='--basetemp=tmp/u18-quality-complete'
.venv/Scripts/python.exe tools/check_backend_quality.py
```

초기 샌드박스 실행은 Windows asyncio의 socketpair accept에서 정지했다. faulthandler로
위치를 확인해 중단하고 승인된 샌드박스 밖 오프라인 실행으로 검증했다. 초기 회귀에서
structlog 예약 필드 충돌을 수정했고 품질 검사에서 SQLAlchemy 예외 import 경로와 정렬을
교정했다. 검사 규칙·기준선을 완화하거나 새 타입 예외를 추가하지 않았다.

품질 검사와 겹친 전체 회귀 실행에서 기존 메모리 기한 테스트의 summary 케이스 1건이
실패했다. 진단/기한 테스트 45건의 단독 재실행은 통과했고 최종 전체 실행은 검사와
겹치지 않게 수행했다. 메모리 코드나 그 테스트를 이번 작업에서 변경하지 않았다.

## 남은 정책과 운영 진단

동일 generation_id의 recovery_finalize 실패를 attempt_count·failure_class·stack_frames로
조사한다. invariant/internal/storage_constraint는 코드·저장 데이터·과금 불변 조건을,
storage_unavailable은 풀/연결 상태를 확인한다. storage_error는 그 자체로 일시 장애의
증거가 아니다. 새 request_key나 공급자 재호출·수동 예약 해제로 해결하지 않는다.

미확정 commit에서 단순 횟수 제한 후 terminal 실패·격리·환불을 강제하면 이미 저장된
결과와 과금의 원자성을 깨뜨릴 수 있다. 재시도 상한·영속 시도 횟수·운영 경보 임계치·
격리 및 재개/수동 확인 정책은 그 처리 계약과 함께 정해야 한다. 이번 진단값은 이를
대신하지 않는다. 실제 PostgreSQL 경쟁·네트워크 commit 불확실성·live 공급자는 미검증이다.

## 초기 조회 진단 경계 재점검 (2026-10-30)

기존 분류·진단 구현을 재검토해 최초 세션/요청/문맥 조회가 catch 경계 밖에 남아 있음을
확인했다. 이 단계의 DB 장애는 안전한 진단 없이 일반 500으로 전달되고 동일 키 재시도
안내가 누락됐다. 최초 조회와 읽기 트랜잭션 종료를 `preparation_read` 경계로 묶고,
SQLAlchemy 오류를 기존 AnswerStorageError/503 응답으로 연결했다. 이 단계에서는 새
생성·과금 예약·공급자 호출이 없으므로 storage_uncertain=False로 기록한다.

SQLAlchemy NoSuchColumnError는 LookupError이기도 하므로 저장소 분류가 먼저 적용된다.
나머지 기존 ValueError·LookupError·MessageConflictError의 입력/인가/설정 응답과 취소
전파는 유지한다. 그 밖의 내부 오류는 원인 타입을 안전하게 진단한 뒤 RuntimeError로
전달한다. diagnostic_id를 최초 조회 전에 만들고 기존 준비/예약 연결에 재사용한다.
저장 JSON·스키마·공급자 재호출·과금·복구 상한 정책은 변경하지 않았다.

추가 회귀 16건은 세션 열기/기존 요청/문맥/읽기 commit 실패 8조합, 기존 업무 예외 4종,
조회 취소 2종, 실제 ASGI 경계의 DB 503/내부 오류 500 응답을 확인한다. 실패 시 예약과
공급자 호출 차단, 원인 보존·민감정보 제외, 동일 키로 정상 재시도도 검증한다.

이번 실행 결과(앞선 전체 API 검증 결과와 구별):

- 진단/프롬프트 workflow/완료/HTTP/비스트리밍 답변 5파일: **83 passed / 16 skipped**.
  skip은 TEST_DATABASE_URL이 필요한 기존 PostgreSQL 테스트다.
- 필수 `tools/check_backend_quality.py`: 기준선 0, Ruff 393파일, mypy 372소스,
  아키텍처·패턴 **13 passed**. 검사 규칙이나 타입 예외를 완화하지 않았다.
- 기존처럼 샌드박스 실행이 Windows asyncio socketpair 생성에서 정지한 것을
  faulthandler로 확인하고 해당 프로세스를 종료했다. 승인된 샌드박스 밖에서 DB/live
  공급자 환경변수를 제거한 오프라인 테스트를 실행했다. 품질 검사는 샌드박스 안에서 통과했다.
- 이번 재점검에서 전체 API·실제 PostgreSQL·live 공급자 검증은 실행하지 않았다.

프로젝트 가상환경 Python으로 실행한 명령:

```powershell
$env:PYTHONPATH='apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
Remove-Item Env:TEST_DATABASE_URL,Env:TEST_AUTH_DATABASE_URL,Env:VOYAGE_API_KEY -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p no:cacheprovider apps/api/tests/test_answer_error_diagnostics.py apps/api/tests/test_generation_prompt_workflow.py apps/api/tests/test_generation_completion_contracts.py apps/api/tests/test_answer_http.py apps/api/tests/test_nonstream_answers.py -q --tb=short -o faulthandler_timeout=30 --basetemp=tmp/u18-read-boundary-focused-20261030
$env:PYTEST_ADDOPTS='--basetemp=tmp/u18-read-boundary-quality-20261030'
.venv/Scripts/python.exe tools/check_backend_quality.py
```

## U18 잔여 정책 구현 (2026-11-02)

프로세스별 LRU 횟수를 제거하고 DB admission으로 대체했다. 자동 복구는 생성당 최대
5회이며 동일 키 재생과 supervisor가 같은 예산·지수 대기·격리를 사용한다. 30초부터
최대 900초의 대기와 invariant/internal/storage_constraint의 첫 실패 격리를 적용한다.
5번째 시도는 선점 직후 격리 표시를 저장하고 해당 시도의 완료만 허용한다.

conversation → generation 잠금 아래 총 횟수·다음 시각·격리 시각과 시도별 감사 행을
먼저 commit한다. 완료 예외/취소/프로세스 종료/선점 응답 유실로 예산이 초기화되지 않는다.
선점 확인 실패는 finalizer를 실행하지 않는다. 격리된 생성은 pending 상태·metadata·
실행 lease·과금 예약을 보존한다. 실패 진단 저장이 실패해도 먼저 commit한 예산은 유지된다.
늦은 실패는 횟수와 pending 상태를 재검사하고 새 시도/종료 사실에 영향을 주지 않는다.

`service/command/answer_recovery.py`에 정책/선점/진단 저장을 두고 기존 workflow가
commit 순서와 finalizer/terminal 재조회를 조율한다. raw ORM은 repository/mapper에만
둔다. `service/query/answer_recovery.py`와 기본 읽기 전용 `app.answer_recovery` CLI는
소유자 범위로 정제된 감사 이력을 제공한다. 수동 `--retry`는 운영자와 사유를 감사한 뒤
한 번만 실행하며 예산·격리를 초기화하거나 공급자를 호출하지 않는다. DB 접근 권한이
운영 경계이며 operator 문자열 자체를 인증 수단으로 사용하지 않는다.

Alembic 0036/초기 SQL 026/ORM에 제어 필드와 `answer_recovery_attempts`를 추가했다.
기존 사실/metadata/lease를 보존하고 횟수는 0부터 시작한다. 감사/제어 기록이 있으면
downgrade를 거절한다. API/worker를 멈추고 migration한 뒤 함께 교체하며 이전 코드와
혼합 실행하지 않는다. 운영 DB에 migration은 실행하지 않았다.

공개 HTTP 필드는 유지한다. 대기/격리는 기존 503/storage_pending_recovery/
retry_same_key=True를 사용한다. 새 request_key·새 공급자 호출·임의 예약 해제를
복구 수단으로 추가하지 않았다. 실제 절차/조회 SQL과 CLI는
[답변 복구 운영 정책](../../../references_document/reference/answer-recovery-policy.md)을 따른다.
chat/db 아키텍처와 두 감사 REPORT도 현재 정책을 연결하도록 갱신했다.

### 검증 결과

- 신규 오프라인 정책 17건·CLI/대기 경계 3건, PostgreSQL 정책/migration 4건.
  재시작/다중 인스턴스 공유 상한, 동일 키 우회 차단, 대기, 결정론적 오류 격리,
  취소/선점 응답 유실, 진단 저장 실패, terminal 무쓰기, 운영자/사유 유효성,
  다른 생성 복구 지속과 사용자 범위/민감 출력 제외를 확인했다. 기존 프로세스 LRU
  전용 2건은 제거하고 영속 정책 검증으로 대체했다.
- 전체 오프라인 API: **1706 passed / 429 skipped / 0 failed**, 기존 Starlette 422 경고 2건.
  skip은 DB/외부 의존 opt-in 테스트이며 전체 현재 작업 트리(기존 미커밋 작업 포함) 결과다.
- 실제 전용 localhost PostgreSQL의 답변·과금·프롬프트·복구·migration 6파일:
  **64 passed / 0 failed**, 기존 Alembic 설정 경고 8건. 동시 12세션 선점 1회,
  상한 후 감사된 수동 복구, 실제 commit 뒤 예외/terminal 재조회와 usage·답변·기억 각 1회,
  migration/init 일치·사실 보존·downgrade 거절을 확인했다. 기존 late worker 테스트는
  내부 실패 격리 뒤 즉시 자동 재생 대신 조사된 수동 재개를 요구하도록 바꿨다.
- 필수 `tools/check_backend_quality.py`: 시그니처 기준선 0, Ruff **400파일**,
  mypy **379소스**, 아키텍처/패턴 **13 passed**. 진단 결과는 TypedDict로 구체화했으며
  검사 규칙/기준선/타입 예외를 완화하지 않았다. 변경 Python Ruff와 git diff --check 통과.

초기 샌드박스 비동기 검사는 기존 Windows asyncio socketpair accept에서 정지해 종료했다.
승인된 샌드박스 밖 오프라인 검사와 전용 로컬 DB 실행기를 사용했고 공급자 키는 제거했다.
초기 PostgreSQL 검증에서 asyncpg의 다중 prepared DDL 제한을 확인해 upgrade/init을
단일 DO 문으로 묶고 downgrade 작업을 문장별로 분리했다. 테스트 세션의 오래된 ORM
캐시도 populate_existing으로 교정했다. 이후 같은 PostgreSQL 6파일 전부 통과했다.

로그: `tmp/u18-policy-api-final.txt`, `tmp/u18-policy-postgres-final.txt`.
필수 품질 검사 결과는 도구 실행 출력에 기록했다. 실행 명령:

```powershell
$env:PYTHONPATH='apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
Remove-Item Env:TEST_DATABASE_URL,Env:TEST_AUTH_DATABASE_URL,Env:VOYAGE_API_KEY -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p no:cacheprovider apps/api/tests -q --tb=short --basetemp=tmp/u18-policy-api-final
$env:PYTEST_ADDOPTS='--basetemp=tmp/u18-policy-quality-final'
.venv/Scripts/python.exe tools/check_backend_quality.py
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_answer_recovery_policy_db.py apps/api/tests/test_answer_recovery_db.py apps/api/tests/test_nonstream_answers.py apps/api/tests/test_answer_billing_integration.py apps/api/tests/test_generation_prompts_db.py apps/api/tests/test_product_migrations.py
```

실제 운영 DB·live 공급자·물리적 네트워크 단절·실제 프로세스 강제 종료는 실행하지 않았다.
commit/취소 장애는 예외 주입으로 검증했다. 외부 경보 전송은 연결하지 않았으며 운영
문서에 pending 격리/상한 목록의 조사 기준과 조회 SQL을 명시했다.
