# U25 통계 재예약 배치화 작업 기록

현재 상태(2026-11-02): **태그·통계 배치화 및 실제 PG 경합·감사 통합 완료.**
신규 PG 경합 17건을 포함한 관련 201 passed, 전체 API 오프라인 1706 passed / 446 skipped와
필수 품질 검사를 통과했다. 현재 완료 판정·명령·검증 한계는
[U25-PG-INTEGRATION.md](U25-PG-INTEGRATION.md)를 따른다. 아래는 단독 작업 당시 기록이다.

- 일자: 2026-10-29 (Asia/Seoul)
- 상태: **통계 재예약 범위 구현·검증·기록 완료. U25 전체 완료가 아니다.**
- 제외: 태그 이름 resolve 배치화, U15 로어 매칭, 발행 저장소, 공통 검사 설정.
- 공통 감사 REPORT.md 두 파일은 수정하지 않았다. 별도 대화·서브에이전트·commit/push를 만들지 않았다.

후속 U15 통합은 전체 API **1337 passed / 0 failed / 288 skipped**와 필수 품질 검사를
통과했다. [U15-U25-INTEGRATION.md](U15-U25-INTEGRATION.md)에 실행 결과·한계를 기록했고
통합 단계에서 두 공통 REPORT에 통계 범위만 완료로 반영했다. 아래는 단독 작업 당시 기록이다.

## 시작 상태와 확인 문서

루트 AGENTS.md, 모듈 아키텍처/명명 규칙, 백엔드 작성 규칙, 원본 감사 U25,
패턴 표준화 REPORT의 최신 U14 기록, product와 use_cases ARCHITECTURE를 읽었다.
처음 git status와 대상 파일의 staged/unstaged diff를 확인했다. 통계 command/queue/
repository와 DB 날짜 도우미에는 기존 diff가 없었다. product ARCHITECTURE에는 기존 U14
등 변경이 있어 보존하고 U25 통계 책임 설명만 추가했다. 기존 staged/unstaged/untracked
파일의 reset/clean/무관한 복원·삭제를 수행하지 않았다.

시작 기준은 전체 API 1229 passed / 0 failed / 288 skipped, 필수 품질 Ruff 390파일 /
mypy 369소스 / 검사 13 passed / 타입 패턴 기준선 0개다. 이 기록의 전체 API 결과는
시작 기준이며 이번 작업에서 전체 API 회귀를 재실행한 결과가 아니다.

## 실제 경로와 보존한 계약

- CLI `product/statistics_job.py --repair-recent` → use_cases/product_statistics의 기존
  enqueue_recent 재노출 → product command/statistics.enqueue_recent 순서다.
- 기존 구현은 `latest_snapshot_id IS NOT NULL`인 상품 ID를 한 번 읽고 상품마다 오늘부터
  과거로 days+1개 날짜에 단건 mark_statistics_dirty를 호출했다. 공개/승인/비공개 상태를
  추가로 필터링하지 않는다. 상품 ID 목록 자체는 기존처럼 한 번 수집한다.
- 유효 days는 1..31이며 오늘 포함 2..32개 날짜다. now가 없으면 현재 aware UTC를 쓰고
  statistics_day의 서울 날짜 변환·naive 시각 거절을 유지한다. 기존
  `statistics_day(day_bounds(day)[0])` 왕복과 같은 날짜를 직접 지연 생성한다.
- 기존 SQL은 `INSERT INTO product_stats_dirty_days (product_id, day) VALUES (...)`
  `ON CONFLICT (product_id, day) DO UPDATE SET requested_at = now()`다.
  신규 requested_at은 ORM 테이블의 DB server_default now()이고 기존 키는 now()로
  다시 갱신한다. command.now는 날짜 선택 입력이며 요청 시각 저장값이 아니다.
  PostgreSQL now()는 트랜잭션 시작 시각이므로 같은 트랜잭션 안의 단건 반복을 다중 VALUES로
  바꿔도 요청 시각의 기준은 같다. 최초 적체 시각을 보존하는 계약은 없다.
- `(product_id, day)` 유일성, 단건 공개 mark_statistics_dirty와 Command/HTTP/CLI 입력·반환,
  claim의 requested_at/product_id/day 정렬·FOR UPDATE SKIP LOCKED,
  complete의 상품/날짜 삭제와 전체 재집계 정책을 유지했다.
- 기존 use_case_transaction이 모든 재예약 배치에 적용된다. 저장소 내부 commit/rollback/
  savepoint와 동일 AsyncSession 병렬 태스크를 추가하지 않았다. 예외를 전파하고,
  상위 호출자가 내부 실패를 잡아도 rollback-only 상태로 전체 쓰기를 되돌린다.

## 구현과 책임

1. command/statistics.py는 상품×날짜 키를 generator로 저장소에 전달한다.
2. repository/statistics.py의 upsert_statistics_work_batch는 입력을 최대 500개씩 읽는다.
   각 묶음의 중복 키를 입력 순서대로 제거한 다음 다중 VALUES upsert를 순차 실행한다.
   SQL당 최대 500키·1,000개 바인딩 값이며 마지막 부분 배치도 저장한다.
3. PostgreSQL은 한 INSERT 안에서 동일 conflict 키를 두 번 갱신할 수 없으므로 배치 내부를
   중복 제거한다. 배치 사이 같은 키는 다시 upsert할 수 있고 최종 작업은 하나다.
   전체 조합 목록이나 전체 키 중복 집합은 만들지 않는다. 추가 버퍼는 배치 크기에 제한된다.
4. 기존 저장소 단건 upsert_statistics_work는 같은 구현에 키 하나를 전달한다.
   공개 statistics_queue.mark_statistics_dirty와 호출자는 변경하지 않았다.
5. 기존 통계 계약 테스트의 대역은 새 배치 경계에서 입력을 소비하도록 수정했다.
   해당 테스트 파일의 시그니처를 명시해 변경 파일 전체의 직접 Ruff/mypy도 통과시켰다.
   Any/ignore/근거 없는 cast/기준선 예외를 추가하지 않았다.
6. product ARCHITECTURE에 배치 상한·중복·시각·트랜잭션 책임과 검증 한계를 추가했다.
   use_cases는 기존 재노출/조립 책임을 유지하므로 수정하지 않았다.

## 변경 전후 SQL 측정

신규 test_statistics_repair_batch_contracts의 같은 SQLite 메모리 검증기로, **구현 변경 전**
먼저 5개 조건을 실행해 5 passed를 확인했다. 구현 후 같은 5개 조건과 배치 경계 조건을
실행했다. before_cursor_execute 이벤트로 실제 SQLite SELECT/INSERT 문 실행을 센다.
건수는 실행 시간·네트워크 왕복·실제 PostgreSQL 처리량 측정이 아니다.

| 상품 수 | days | 실제 날짜 수 | 변경 전 upsert | 변경 후 upsert | 상품 조회 전/후 |
|---:|---:|---:|---:|---:|---:|
| 0 | 31 | 32 | 0 | 0 | 1 / 1 |
| 1 | 1 | 2 | 2 | 1 | 1 / 1 |
| 1 | 31 | 32 | 32 | 1 | 1 / 1 |
| 3 | 7 | 8 | 24 | 1 | 1 / 1 |
| 16 | 31 | 32 | 512 | 2 | 1 / 1 |

16상품×32일의 upsert 호출은 99.609375% 감소했다. 상품 조회를 포함하면 513→3 SQL이다.
중복 없는 입력의 upsert 호출 수는 `ceil(상품 수 × (days+1) / 500)`이다.
추가 경계 측정은 249상품×2일=498키→1회, 250×2일=500키→1회,
251×2일=502키→2회다. 저장소 직접 검증에서 499/500/501/1001키의 SQL 크기는 각각
[499], [500], [500,1], [500,500,1]이었다. 입력 소비 전에 이전 SQL이 끝났는지도 검사했다.

대역과 범위:

- 업무 경로의 실제 enqueue_recent·상품 선택 SQL·upsert SQL을 실행했다. 상품 선택과
  upsert 결과를 대역으로 바꾸지 않았다. engine은 SQLite 메모리, AsyncSession의 SQL
  메서드는 동기 Session에 연결한 AsyncMock 어댑터다. 실제 AsyncSession의
  transaction event를 SQLite commit/rollback에 연결했다.
- 최소 products 테이블과 dirty 큐의 복합 PK·product FK를 SQLite에 구성했다.
  상품 snapshot FK나 전체 운영 스키마를 복제한 검증은 아니다.
- 같은 명령을 PostgreSQL dialect로 컴파일해 conflict 대상·now()·배치 내부 키 유일성·
  최대 바인딩 수와 SKIP LOCKED 요청을 확인했다. PG 서버에서 실행한 것은 아니다.
- job 연결 검사는 실제 repair/claim/complete 경로를 사용하지만 엔진 생성과 rebuild_day는
  대역이다. 기존 집계·reporting 계약은 별도 관련 테스트로 검증했다.
- SQLite CURRENT_TIMESTAMP는 PostgreSQL의 트랜잭션 시각 고정 의미를 증명하지 않는다.
  시간 갱신은 SQLite 실행으로, PG now() 표현과 기존 server_default는 코드/컴파일로 구분해 확인했다.

## 회귀와 검증 결과

신규 테스트는 33건이며 다음을 포함한다.

- 빈 상품·days 최소/최대·범위 밖·naive 거절, 서울 자정 직전/정각·연도/윤년 날짜 경계.
- snapshot 유무만으로 상품 선택, 신규 예약/기존 키의 요청 시각 갱신·범위 밖 키 보존,
  기존 단건 서비스의 신규 예약과 재예약, 1,003개 중복 입력의 배치 내부 유일성.
- 500개 경계 전/정각/후·부분 배치·지연 입력 소비와 SQL 호출 수.
- 2·3번째 실제 쓰기 뒤 주입한 실패, 상위에서 잡은 실패의 rollback-only,
  신규 키·기존 요청 시각·상위의 다른 쓰기 전체 rollback.
- 두 번째 부분 배치의 실제 SQLite FK 오류로 첫 배치 rollback,
  성공한 enqueue 뒤 상위 실패 rollback, 무관한 기존 transaction의 채택 거절.
- 기존 CLI repair → claim → rebuild 대역 → complete와 출력·engine 정리 연결.

| 검사 | 결과 |
|---|---|
| 변경 전 동일 SQL 검증기 | 5 passed / 0 failed / 0 skipped |
| 변경 Python 4파일 직접 Ruff format/check | 통과 |
| 변경 Python 4파일 직접 mypy | 4소스, 오류 0 |
| 필수 check_backend_quality.py | Ruff 390파일 / mypy 369소스 / 13 passed / 0 failed / 0 skipped / 기준선 0개 |
| 통계·job·reporting·conversation/generation 단건 호출자·billing 관련 11파일 | **157 passed / 0 failed / 13 skipped** (신규 33건 포함) |
| 변경 범위 git diff --check 및 신규 파일 공백 검사 | 통과 |
| 전체 API 회귀 | 이번 범위에서는 미실행; 병렬 작업 통합 후 아래 명령으로 실행 |

모든 실행은 프로젝트 .venv/Scripts/python.exe를 사용했고 TEST_DATABASE_URL과
TEST_AUTH_DATABASE_URL을 제거했다. skipped 13건은 DB 환경이 필요한 통합 테스트이며
passed로 계산하지 않았다. 최초 기본 샌드박스 실행은 출력 없이 대기해 중단했고,
Windows asyncio 제약 밖의 승인된 오프라인 실행에서 변경 전/후를 모두 검증했다.
최초 직접 mypy의 테스트 어댑터 인자 타입 오류 1건은 SQLAlchemy Executable로 바로잡은 뒤
재검증했다. 실패를 숨기거나 기준선을 완화하지 않았다.

실제 PostgreSQL 행 잠금·경합·격리·동시 재예약/claim·실행 계획·처리량은 **미검증**이다.
실제 DB migration/초기화/삭제와 외부 공급자 요청은 실행하지 않았다.

## 재현 및 통합 명령

저장소 루트 PowerShell에서 다음 환경을 설정한다. basetemp는 기존 파일을 건드리지 않도록
매 실행 새 이름을 사용한다.

```powershell
$env:PYTHONPATH = 'apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:TEST_AUTH_DATABASE_URL -ErrorAction SilentlyContinue
$u25RunId = [guid]::NewGuid().ToString('N')
$env:PYTEST_ADDOPTS = '--basetemp=tmp/u25-statistics-' + $u25RunId
```

관련 업무 회귀:

```powershell
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p no:cacheprovider apps/api/tests/test_statistics_repair_batch_contracts.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_product_statistics.py apps/api/tests/test_product_statistics_job.py apps/api/tests/test_product_reporting_contracts.py apps/api/tests/test_reporting_contracts.py apps/api/tests/test_reporting.py apps/api/tests/test_reporting_db.py apps/api/tests/test_conversation_command_contracts.py apps/api/tests/test_generation_completion_contracts.py apps/api/tests/test_billing_lifecycle_integration.py -q -s --tb=short
```

직접 정적 검사와 필수 품질 검사:

```powershell
.venv/Scripts/python.exe -m ruff format --check --config apps/api/pyproject.toml apps/api/app/modules/content/product/service/command/statistics.py apps/api/app/modules/content/product/repository/statistics.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_statistics_repair_batch_contracts.py
.venv/Scripts/python.exe -m ruff check --config apps/api/pyproject.toml apps/api/app/modules/content/product/service/command/statistics.py apps/api/app/modules/content/product/repository/statistics.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_statistics_repair_batch_contracts.py
.venv/Scripts/python.exe -m mypy --config-file apps/api/pyproject.toml apps/api/app/modules/content/product/service/command/statistics.py apps/api/app/modules/content/product/repository/statistics.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_statistics_repair_batch_contracts.py
.venv/Scripts/python.exe tools/check_backend_quality.py
git diff --check -- apps/api/app/modules/content/product/ARCHITECTURE.md apps/api/app/modules/content/product/service/command/statistics.py apps/api/app/modules/content/product/repository/statistics.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_statistics_repair_batch_contracts.py docs/audits/2026-10-26-pattern-standardization/U25-STATISTICS-WORKLOG.md
```

**병렬 U15 통합 후 전체 API 회귀**: 위 환경 설정에서 새 basetemp를 지정한 다음 실행한다.

```powershell
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p no:cacheprovider apps/api/tests -q --tb=short
```

통합 시 기존 U14/product ARCHITECTURE 변경과 U15 변경을 보존한다. 두 공통 REPORT의
상태 반영은 통합 작업에서 이 기록을 참고하되 **U25 통계 재예약 범위만 완료**로 표시한다.
태그 resolve 배치화는 남은 별도 범위다. 실제 PostgreSQL 검증과 전체 API 회귀 결과를
이번 SQLite/컴파일/대역 결과로 대체하지 않는다.
