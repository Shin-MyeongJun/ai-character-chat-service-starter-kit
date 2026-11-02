# U17 답변 복구 실행 계획·pending 인덱스·종료 lease

작성일: 2026-11-02 (Asia/Seoul)

## 판단과 변경

복구 조회는 status=pending, answer_lease_until<=now로 lease 오름차순 최대 100건을
읽는다. 기존 전체 lease 인덱스는 종료 행까지 후보로 읽고 status로 제거할 수 있다.
항상 전체 테이블을 선형 스캔하는 오류는 아니다. 실제로 pending이 많은 분포에서는
기존 인덱스도 필요한 100건을 빠르게 반환했다.

`tools/measure_answer_recovery.py`로 실제 repository가 실행한 SQL/타입 바인드를
수집하고, 같은 테이블에서 전체 인덱스/부분 인덱스/부분 인덱스+종료 lease NULL을
비교했다. 부분 인덱스는 종료 행이 많은 경우 효과가 컸다. 다만 기존 `status=$1`의
generic plan에서는 pending임을 입증하지 못해 병렬 순차 조회/정렬로 돌아갔다.
인덱스만 교체하면 일부 계획에서 오히려 느려질 수 있어 조회의 고정 pending 조건을
`literal_column("'pending'")`으로 표현했다. 외부 입력은 포함하지 않으며 now/LIMIT의
바인딩, 조회·정렬·배치 크기·반환 타입은 유지한다.

Alembic 0035, 새 DB 초기 SQL 025, ORM은
`ix_product_generations_answer_lease_until`을 다음 인덱스로 교체한다.

```sql
CREATE INDEX ix_generation_pending_answer_lease
ON product_generations(answer_lease_until)
WHERE status = 'pending' AND answer_lease_until IS NOT NULL;
```

종료 lease를 이력으로 소비하는 경로는 없었다. 실행권 검사는 pending 상태에 적용되며
완료 이력은 status/finished_at/result_digest/answer_metadata와 usage/과금에 남는다.
기존 `repository.finish_generation`에서 모든 종료 상태와 함께 lease를 NULL로 만든다.
상위 완료/과금/메모리 트랜잭션이 실패하면 pending 상태와 원래 lease도 복원된다.
완료 재생은 쓰지 않으며 metadata/token/digest와 메시지/사용량/과금 계약은 유지한다.

기존 종료 행은 migration에서 대량 갱신하지 않는다. 이미 부분 인덱스 밖이므로 이들을
NULL로 바꾸는 추가 조회 이득은 확인하지 못했다. 새 종료의 NULL은 실행권 수명 의미를
명확히 하는 변경이다. NULL 갱신만으로 모든 인덱스/MVCC/WAL 비용이 사라진다고 보지 않는다.
새 계층·테이블·공개 service는 추가하지 않고 기존 repository/command/workflow 책임에
유지했다. chat과 DB의 ARCHITECTURE.md를 함께 갱신했다.

## 실행 계획 실측

PostgreSQL 17.11, SQLAlchemy/asyncpg, 전용 localhost 감사 테스트 DB의 UUID 임시
스키마에서 측정했다. 각 분포는 합성 100,000행이며 현재 ProductGeneration 컬럼/
제약/일반 인덱스를 사용하되 벤치마크 테이블에서만 FK를 생략했다. 약 1KB의 합성
answer_metadata를 포함한다. 각 인덱스 구성 뒤 VACUUM ANALYZE를 실행하고 계획별
1회 준비 실행 후 5회 EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)의 서버 실행 시간
중앙값을 기록했다. 조회 LIMIT은 100이다. custom/generic을 각각 강제해 경계를 확인했다.

| 분포 | pending / 만료 | 기존 전체·custom ms | 최종 부분·custom ms | 기존 전체·generic ms | 최종 부분·generic ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 종료 lease 99,000개 뒤의 pending | 1,000 / 500 | 50.902 | 0.029 | 38.297 | 0.031 |
| 100행마다 pending 분산 | 1,000 / 1,000 | 1.349 | 0.040 | 1.225 | 0.042 |
| 절반이 pending인 backlog | 50,000 / 50,000 | 0.048 | 0.030 | 0.043 | 0.033 |
| 종료 행은 만료, pending은 모두 미래 | 1,000 / 0 | 32.789 | 0.009 | 30.710 | 0.012 |

기존/최종은 각각 변경 전 `status=$1 + 전체 인덱스`, 변경 후 `status='pending' + 부분
인덱스`다. 실행 간 캐시·동시 로컬 부하의 차이가 있으므로 운영 개선율로 일반화하지 않는다.
변경 후 SQL에서도 전체 인덱스만 둔 대조군은 tail custom 41.131ms/generic 29.360ms였다.

tail 분포의 전체 인덱스는 100건을 반환하기 전에 종료 행 **99,000개**를 제거했다.
최종 부분 인덱스에서는 제거한 행이 0개이며 첫 실행의 shared hit는 **36 blocks**다.
no_due에서도 부분 인덱스는 반환 0행/shared hit 1 block이다. 분산 분포의 전체 인덱스는
9,900행, backlog에서는 100행만 제거하므로 모든 분포에서 비용이 같다는 단정은 하지 않는다.

| 분포 | 전체 인덱스 bytes | 부분 인덱스 bytes |
| --- | ---: | ---: |
| tail | 2,252,800 | 32,768 |
| spread | 2,260,992 | 40,960 |
| backlog | 2,260,992 | 1,138,688 |
| no_due | 2,244,608 | 16,384 |

부분 인덱스만 추가하고 기존 바인딩 SQL을 유지했을 때 generic 중앙값은 tail 17.642ms,
spread 16.855ms, backlog 22.006ms, no_due 15.538ms였다. 모두 병렬 순차 조회/정렬이며
특히 backlog에서는 기존 전체 인덱스보다 느렸다. 고정 SQL predicate가 필요한 근거다.
종료 lease NULL까지 적용한 최종 부분 인덱스 대조군의 generic은 각각 0.041/0.041/
0.032/0.010ms로, 부분 인덱스 단독과 같은 규모다. 일괄 backfill의 근거로 삼지 않는다.

[측정 증거 JSON](U17-RECOVERY-PLANS.json)은 변경 전/후 SQL, 분포별 pending/만료 수,
인덱스 크기, 5회 실행 시간과 첫 EXPLAIN 전체 계획을 보존한다. 원본 전체 5회 계획은
`tmp/u17-recovery-before.json`, `tmp/u17-recovery-after.json`에 있다. 운영 데이터·차가운
캐시·동시 완료 부하·WAL/HOT/update 처리량·실제 API 지연을 측정한 결과는 아니다.

## 검증과 재현

- 최종 관련 10파일: **146 passed / 0 failed / 0 skipped**. 실제 PostgreSQL과 연결 없는
  완료 계약/HTTP 테스트를 함께 실행했다. 새 DB 회귀 8건은 만료 경계(<=)·lease 정렬·LIMIT·
  terminal/legacy/live 제외, 2만 종료 행이 있는 prepared generic 계획의 부분 인덱스 선택,
  ORM/Alembic/init 인덱스 일치와 upgrade/downgrade 시 모든 행 보존, 4개 종료 상태의
  lease NULL·상위 rollback 복원·metadata/완료 시각·동일 결과 재생을 검증한다.
- 기존 답변/과금/프롬프트/usage/전체 init 및 head migration 회귀에서 동시 복구,
  공급자 재호출 방지, 토큰/lease 쓰기 보호, staging·과금·메모리 원자성과 commit 응답
  유실 뒤 같은 키 재생을 확인했다. 완료 계약 테스트에도 lease 해제·복원 검증을 추가했다.
- `tools/check_backend_quality.py`: **통과**. 시그니처 기준선 0, Ruff 396파일,
  mypy 375소스, 아키텍처/패턴 13건. 타입 예외·기준선·검사 규칙을 완화하지 않았다.
  신규 테스트/측정 도구/0035의 별도 Ruff lint(ANN 포함)·포맷, diff 공백 검사도 통과했다.
  Alembic head는 0035 하나다.
- 초기 통합 실행은 121 passed/8 failed였다. 추가 상태 확인 SELECT가 기존 SQL 횟수
  측정에 섞인 테스트 순서를 교정했다. 다음 실행의 144 passed/2 failed는 새 실패/취소
  입력에 메시지를 넣은 경우로, 기존 결과 계약에 맞춰 빈 메시지로 교정했다. production
  조건/검증을 완화하지 않았으며 위 최종 146건은 이 교정 후 결과다.
- Alembic의 기존 path_separator 미설정 DeprecationWarning 3개가 있다. 전체 API/
  브라우저/live 공급자/운영 부하 테스트를 수행한 결과는 아니다. 로그는
  `tmp/u17-db-final.txt`에 있다.

```powershell
.venv/Scripts/python.exe tools/measure_answer_recovery.py --output tmp/u17-recovery-after.json
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_answer_recovery_db.py apps/api/tests/test_nonstream_answers.py apps/api/tests/test_answer_billing_integration.py apps/api/tests/test_generation_completion_contracts.py apps/api/tests/test_answer_error_diagnostics.py apps/api/tests/test_product_usage.py apps/api/tests/test_generation_prompts_db.py apps/api/tests/test_product_migrations.py apps/api/tests/test_answer_http.py apps/api/tests/test_answer_price_response.py
$env:PYTEST_ADDOPTS='--basetemp=tmp/u17-quality'
.venv/Scripts/python.exe tools/check_backend_quality.py
```

측정 도구는 Git 제외 `.env.audit-test.local`의 localhost 전용 감사 DB/계정만 허용한다.
운영 URL을 받지 않고 성공/실패 시 UUID 임시 스키마를 삭제한다. 테스트는 기존 전용
DB runner와 테스트별 스키마를 사용했다. Windows의 로컬 DB 접근에는 승인된
샌드박스 밖 실행을 사용했다. 앱 DB·전역 환경·Docker 설정은 변경하지 않았다.

## 운영 적용

운영 DB에는 적용하지 않았다. 기존 DB는 API/답변 supervisor/관련 worker를 중지하고
0035까지 migration한 뒤 새 코드를 함께 시작한다. 일반 CREATE/DROP INDEX이므로
인덱스 생성 시간과 잠금 대기를 배포 전에 산정한다. 새 초기 SQL은 빈 DB의 초기화
경로이며 기존 DB에 전체 init을 재실행하지 않는다. downgrade는 전체 인덱스를 먼저
복원하고 부분 인덱스를 제거하며 기존 행을 재작성하지 않는다. 새 코드가 이미 해제한
종료 lease의 과거 시각을 합성하지 않는다.
