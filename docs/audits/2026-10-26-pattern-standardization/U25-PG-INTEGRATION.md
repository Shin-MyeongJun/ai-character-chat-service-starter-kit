# U25 실제 PostgreSQL 경합 검증·감사 통합

일자: 2026-11-02 (Asia/Seoul)

상태: **U25 통계 재예약·태그 이름 resolve 배치화와 실제 PG 경합 회귀·감사 통합 완료.**
운영 부하·모든 실행 순서의 교착 부재를 보장하는 판정은 아니다.

## 구현 근거와 이번 변경

기존 [통계 기록](U25-STATISTICS-WORKLOG.md)과 [태그 기록](U25-TAG-WORKLOG.md)의 구현을
현재 작업 트리에서 확인했다. 통계는 최대 500개 키의 지연·순차 upsert, 태그는 정확한
이름을 Python 순서로 정렬한 최대 500개 INSERT/공유 잠금 SELECT 묶음이다.
통계 16상품×32일의 upsert 512→2회, 태그 1,001이름의 INSERT/SELECT 각각 1,001→3회는
앞선 동일 SQLite 검증기의 측정이다. 이번 실제 PG 검증으로 운영 성능 개선율을 새로
측정한 것으로 바꾸어 해석하지 않는다.

제품 Python·SQL·공개 Command/Info·HTTP·스키마·잠금·격리/재시도 정책은 변경하지 않았다.
새 `test_u25_postgres_concurrency.py`와 두 모듈의 검증 설명, 두 공통 REPORT 및 전용 기록을
갱신했다. 테스트 안의 barrier·연결/태스크 정리만 공통화하고 업무 계층을 추가하지 않았다.
기존 staged/unstaged 변경, 검사 범위·기준선·타입 예외를 보존했다.

## 실제 DB와 실행 방법

- PostgreSQL **17.11 (Debian 17.11-1.pgdg12+2)**, READ COMMITTED,
  DB collation `en_US.utf8`, encoding UTF8에서 실행했다.
- `tools/run_postgres_audit_tests.py`가 `.env.audit-test.local`의 전용 localhost DB·테스트
  사용자 URL만 허용한다. 비밀번호/URL을 로그나 문서에 복사하지 않았다.
- 기존 `db` fixture가 테스트마다 UUID 스키마를 생성하고 ORM 테이블 및 기존 이력
  trigger SQL을 구성한 뒤 스키마를 정리한다. 실제 FK/UNIQUE와 asyncpg를 사용한다.
  `create_all(checkfirst=False)`로 public의 동명 테이블을 재사용하지 않는다.
  Alembic 전체 업그레이드 또는 운영 데이터 이관 검증은 아니다.
- 작업마다 독립 AsyncSession/연결을 사용한다. 17건 중 INSERT/SELECT 사이 이름 변경
  1건을 제외한 **16건**은 별도 관찰 연결의 `pg_blocking_pids`에 선행 backend가 나타난
  뒤에만 선행 트랜잭션을 commit/rollback하거나 대기 태스크를 취소한다.
  단순 sleep이나 gather 완료만으로 경합을 주장하지 않는다.
- 작업 연결은 READ COMMITTED를 확인하고 statement_timeout=10초, lock_timeout=8초를
  설정한다. blocker 관찰은 5초, 작업 조합은 20초로 제한하고 finally에서 태스크를
  취소·회수한 뒤 세션을 종료한다. 이름 변경 gap 검증은 15초로 제한한다.
- gap 검증은 실제 resolver 세션의 SELECT 직전만 Event로 멈춘다. 관리자 서비스가
  별도 연결에서 실제 이름 변경을 commit한 뒤 원래 SELECT를 실행한다. 반환값·SQL
  결과·DB 잠금을 대역으로 만들지 않는다.

## 경합 17건과 관찰한 결과

| 교차 실행 | 건수 | 확인한 계약 |
|---|---:|---|
| 겹치는 501이름 resolve 두 요청, 역순 입력+추가 이름 | 1 | 500개 경계 통과, unique 대기, 동일 이름 ID 재사용, 입력 반환 순서, 총 502행 |
| resolve 공유 잠금 → 관리자 rename/deactivate | 2 | 관리자 실제 대기, 선행 resolve의 기존 활성/이름 Info와 commit 후 관리자 상태 |
| 관리자 deactivate → resolve, retained 유무×관리자 commit/rollback | 4 | 갱신 잠금 대기 후 최신 활성 상태, 신규 비활성 거절과 임시 신규 이름 rollback, retained 유지·관리자 rollback 복원 |
| 관리자 create ↔ resolve, 양방향 | 2 | 미확정 unique 삽입 대기, 동일 ID, 먼저 생성한 설명 보존 |
| 관리자 rename → resolve INSERT, 관리자 commit/rollback | 2 | commit 시 비워진 옛 이름에 새 ID 생성, rollback 시 기존 ID·설명 재사용 |
| resolve INSERT → 관리자 rename commit → resolve SELECT | 1 | 기존 `Tag name changed concurrently; retry the request.` 오류와 같은 트랜잭션의 새 이름 rollback |
| resolve 첫 500이름 INSERT/SHARE → 둘째 배치 잠금 대기 중 취소 | 1 | CancelledError 전달·선행 배치 전체 rollback, 관리자 비활성화는 독립 commit |
| 251상품×2일 repair 두 요청 | 1 | 502키/두 배치가 unique 충돌 후 하나씩 남음, 모든 requested_at은 후행 트랜잭션 now() |
| worker claim·다른 worker SKIP LOCKED·미확정 complete DELETE → repair, worker commit/rollback | 2 | repair 실제 대기, 삭제 commit 뒤 재삽입 또는 rollback 뒤 갱신, 두 날짜 모두 새 요청 보존 |
| 미확정 repair → 단건 dirty 요청·별도 worker | 1 | worker의 미확정 작업 건너뛰기, 단건 upsert 대기·해당 날짜 시각만 갱신, 이후 claim/complete로 정상 소진 |

rename이 INSERT 전에 완료되어 옛 이름을 다시 생성할 수 있는 경우와, INSERT에서 기존
이름을 확인한 뒤 SELECT 전에 이름이 사라져 재시도 오류가 나는 경우를 구분했다.
두 경우 모두 기존 구현의 관찰 가능한 계약으로 고정했다.

`requested_at` 비교는 테스트가 주입한 날짜 입력 NOW가 아니라 각 DB 트랜잭션의
`transaction_timestamp()`와 일치하는지 검사한다. 모든 실행에서 시각의 단조 증가를
보장한다는 뜻은 아니다. 먼저 시작하고 오래 대기한 트랜잭션은 더 이른 now()를 저장할
수 있으며 이를 바꾸는 정책은 도입하지 않았다.

## 최종 검증 결과

| 범위 | 결과 |
|---|---|
| 신규 실제 PG 경합 | **17 passed / 0 failed / 0 skipped**, 아래 관련 201건에 포함 |
| 태그/통계/정책/HTTP/스튜디오 발행 관련 15파일 | **201 passed / 0 failed / 0 skipped** (24.97초) |
| 전체 API 오프라인 | **1706 passed / 0 failed / 446 skipped / 2 warnings** (32.73초) |
| 필수 check_backend_quality.py | 패턴 진단·예외 0, Ruff 395파일, mypy 374소스, 아키텍처/패턴 **13 passed** |
| 신규 테스트 직접 Ruff format/check·mypy | 통과, mypy 1소스 |
| 이번 변경 파일 git diff --check | 통과 |

전체 API에는 현재 작업 트리의 다른 미커밋 변경도 포함된다. PG 201건과 오프라인
1706건은 중복된 회귀를 포함하므로 합산하지 않는다. 신규 17건은 오프라인 실행에서
DB 미설정으로 skip되며 PG 실행에서 통과했다. 전체 446 skipped에는 다른 PG·인증 DB·
live 공급자 조건이 포함되고, 그 전체를 이번 PG 실행으로 검증했다고 주장하지 않는다.
2 warnings는 기존 lorebook HTTP 테스트의 Starlette 422 상수 deprecation이다.

초기 샌드박스 실행은 Windows asyncio/socket 제한으로 진행되지 않아 중단하고 승인된
실행으로 검증했다. 첫 실제 PG 실행의 **14 passed / 1 failed**는 테스트의
`dict(CursorResult)` 변환 오류였다. `.tuples().all()`로 고치고 이름 변경 선행 2건을
추가한 뒤 최종 201건을 통과했다. 초기 mypy의 nullable task/kw-only Command 호출도
테스트에서 교정했다. 환경 정보 수집의 `lc_collate` 설정 조회 오류는 `pg_database.datcollate`
조회로 교정했다. 이 실패들을 제품 경합 결함으로 기록하지 않는다.

## 재실행 명령과 로그

저장소 루트 PowerShell, 프로젝트 `.venv/Scripts/python.exe`를 사용한다. PG runner는
새 basetemp를 자동 지정하며 외부 OpenAI/Anthropic/Voyage·S3 통합 opt-in을 제거한다.

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_u25_postgres_concurrency.py apps/api/tests/test_tag_resolve_batch_contracts.py apps/api/tests/test_tag_management.py apps/api/tests/test_tag_management_db.py apps/api/tests/test_tag_schema.py apps/api/tests/test_statistics_repair_batch_contracts.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_product_statistics.py apps/api/tests/test_product_statistics_job.py apps/api/tests/test_tag_policy.py apps/api/tests/test_character_http.py apps/api/tests/test_lorebook_http.py apps/api/tests/test_product_http.py apps/api/tests/test_studio_republication_contracts.py apps/api/tests/test_studio_publication.py

$env:PYTHONPATH='apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
Remove-Item Env:TEST_DATABASE_URL,Env:TEST_AUTH_DATABASE_URL,Env:PYTEST_ADDOPTS,Env:VOYAGE_API_KEY,Env:OPENAI_API_KEY,Env:ANTHROPIC_API_KEY,Env:RUN_ASSET_STORAGE_S3_INTEGRATION -ErrorAction SilentlyContinue
$u25Temp='tmp/u25-all-' + [guid]::NewGuid().ToString('N').Substring(0,6)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests -q -rs --tb=short --basetemp=$u25Temp
$env:PYTEST_ADDOPTS='--basetemp=tmp/u25-q-' + [guid]::NewGuid().ToString('N').Substring(0,6)
.venv/Scripts/python.exe tools/check_backend_quality.py
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m ruff format --check --config apps/api/pyproject.toml apps/api/tests/test_u25_postgres_concurrency.py
.venv/Scripts/python.exe -m ruff check --config apps/api/pyproject.toml apps/api/tests/test_u25_postgres_concurrency.py
.venv/Scripts/python.exe -m mypy --config-file apps/api/pyproject.toml apps/api/tests/test_u25_postgres_concurrency.py
```

최종 로그: [PG 관련 회귀](../../../tmp/u25-postgres-final.txt),
[전체 API 오프라인](../../../tmp/u25-api-offline-final.txt),
[필수 품질](../../../tmp/u25-quality-final.txt). 임시 로그는 Git 보존 대상이 아니므로
장기 감사 근거는 이 기록의 조건·건수와 저장된 테스트를 사용한다.

## 완료 판정과 남는 한계

두 배치화 구현·SQL 수 감소의 기존 측정·실제 PG의 지정 경합 회귀와 통합 검증을 모아
U25를 완료로 갱신한다. 운영 데이터/설정 변경·commit/push는 수행하지 않았다.

한 버전·한 DB collation·READ COMMITTED의 유한한 실행 순서 검증이다. 다른 collation/
격리 수준·운영 풀/네트워크·프로세스 중단·장시간 트랜잭션·다수 요청의 임의 잠금 순서와
모든 교착/serialization 오류 부재를 증명하지 않는다. SQL CASE와 Python 정렬의 계약은
기존 컴파일/SQLite 검증을 함께 참고한다. 실제 실행 계획·WAL/메모리·지연·처리량·운영
부하나 live 외부 공급자는 측정하지 않았다. 통계 worker의 사실 수집 전체와 모든 writer의
교차 실행도 이 17건의 대상이 아니다. 새 전역 잠금·범용 재시도·검증 우회 없이 기존
트랜잭션 및 오류 계약을 유지한 범위의 완료다.
