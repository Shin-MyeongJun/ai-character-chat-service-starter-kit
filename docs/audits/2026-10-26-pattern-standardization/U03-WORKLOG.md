# U03 메모리 claim별 소유권 검증

작성일: 2026-10-30 (Asia/Seoul)

상태: **구현·관련 PostgreSQL 경합/마이그레이션 검증·전체 오프라인 API 회귀 완료.**
앱 DB에 대한 마이그레이션 적용과 실제 외부 공급자 호출은 수행하지 않았다.

## 범위와 확인한 결함

사용자는 U03 작업에 필요한 테스트 실행을 위임했다. 기존 PostgreSQL 준비 기록의
전용 DB/제한 계정과 UUID 테스트 스키마만 사용했다. 시작 시 git 상태와 대상 diff,
AGENTS.md·아키텍처/백엔드 규칙·U03 감사·최신 감사 기록·memory/chat ARCHITECTURE를
확인했다. 기존 U29 전체 기한과 다른 staged/unstaged/untracked 변경은 보존했다.

수정 전 실제 PostgreSQL에서 같은 worker·같은 scope로 만료 작업을 다시 claim한 뒤
이전 실행의 완료/실패를 호출했다. 새 실행의 running 상태가 각각 pending/failed로
바뀌어 회귀 **2 failed / 0 passed / 0 skipped**를 확인했다.
로그: [u03-before.txt](../../../tmp/u03-before.txt).

기존 원문 revision과 요약 출처 UNIQUE는 저장 내용의 유효성/중복을 검증하지만 실행
소유권을 대신하지 못했다. 요약·임베딩 저장도 현재 claim을 확인하지 않았다.

## 구현과 보존한 계약

- scheduling service가 매 claim마다 UUID claim_token을 생성하고 repository가 잠긴
  memory_jobs 행에 기록한다. mapper는 이를 MemoryWorkInfo로 전달한다. 같은 worker,
  scope, attempt의 재시도나 행 재생성도 구별한다. 잠금 조회는 identity map을 갱신한다.
- 완료/실패는 conversation·owner·running·worker·scope·nonnull token을 함께 비교한다.
  오래된 실행은 무변경이며 현재 실행만 전이와 토큰 해제를 수행한다.
- SaveSummaryCommand/SaveEmbeddingCommand에 work가 필수다. 저장 service는 결과의
  conversation/owner를 비교하고 현재 claim 행을 FOR UPDATE로 잠근다. 불일치는 기존
  StaleMemoryWorkError로 거절한다. 검사부터 쓰기·상위 commit/rollback까지 잠금을
  유지하여 검사 직후 재claim이 끼어드는 경쟁을 막는다.
- workflow는 conversation → memory_jobs → conversation_memories 순으로 잠근다.
  claim/완료/실패 경로는 conversation을 다시 잠그지 않는다. 외부 I/O 전 읽기 세션을
  닫는 순서와 원문 revision/범위·digest, 임베딩 내용 digest 재검증을 유지한다.
- 요청 세대 합치기, more_work, pending 요약 재사용, source UNIQUE, 소유권, backoff와
  최대 시도 횟수, U29 전체 처리 예산, worker 동시성·종료 계약을 유지한다.
- lease 만료는 재획득 자격이다. 새 claim이 토큰을 대체하기 전에는 이전 토큰이 유효하다.
  만료 순간 쓰기를 금지하거나 lease 갱신/외부 호출의 exactly-once를 추가한 것은 아니다.
- MemoryWorkInfo의 기존 다섯 위치 인자는 유지하되 claim_token 키워드를 필수로 추가했다.
  호출부/대역을 함께 갱신했다. HTTP 계약·저장 요약·벡터·metadata 표현은 바꾸지 않았다.

U29 기한 회귀에서는 첫 통합 실행이 **56 passed / 1 failed**였고 단독 재실행은 2 passed였다.
취소를 삼킨 공급자의 결과가 시각 비교를 통과하는 상황이었다. asyncio 타이머는 시계
정밀도 안에서 deadline 시각보다 일찍 실행될 수 있으므로 workflow에 동일 Timeout 객체를
전달하고 expired()도 검사하도록 보완했다. 미래의 when()과 expired=True 조합을 고정한
회귀 1건을 추가했다. 예산·재시도/취소 분류는 유지한다.
초기 로그: [u03-business.txt](../../../tmp/u03-business.txt),
[u03-deadline-recheck.txt](../../../tmp/u03-deadline-recheck.txt).

## 수정 파일

- `apps/api/app/db/models/memory.py`: nullable UUID claim_token 컬럼.
- `apps/api/app/modules/chatting/memory/{types.py,repository.py,mapper/persistence.py}`:
  공개 work/저장 Command, claim 저장·잠금·조건 UPDATE, 순수 토큰 매핑.
- `apps/api/app/modules/chatting/memory/service/command/{scheduling,summarization,indexing}.py`:
  토큰 발급 및 결과 저장의 소유권 판단.
- `apps/api/app/modules/chatting/chat/service/workflow/memory.py`: work 전달과 deadline 상태.
- `apps/api/alembic/versions/0031_memory_claim_token.py`,
  `infra/postgres/init/021_memory_claim_token.sql`: 기존 DB/신규 설치 스키마 경로.
- `apps/api/tests/test_memory_claim_fencing.py`: 신규 실제 PG 회귀 18건.
- `apps/api/tests/test_memory_claim_migrations.py`: 신규 실제 PG 회귀 2건.
- `apps/api/tests/test_memory_deadlines.py`: 신규 기한 회귀 1건과 토큰 fixture.
- `apps/api/tests/{test_hypha_memory,test_runtime_entrypoint_contracts}.py`: 토큰 fixture.
- `apps/api/tests/test_credit_wallet_migrations.py`: 전체 Alembic head 기대값 0030→0031.
  이 파일의 CREATE DATABASE를 요구하는 온라인 검사는 이번 전용 계정으로 실행하지 않았다.
- memory/chat의 `ARCHITECTURE.md`, 이 작업 기록.

기존 기능 파일의 책임 안에서 수정했다. 통계·태그·발행 저장소·공통 트랜잭션/검사 설정과
공통 감사 REPORT 두 파일은 수정하지 않았다. Any/ignore/cast/기준선 예외는 추가하지 않았다.

## 최종 검증

| 검증 | passed | failed | skipped |
|---|---:|---:|---:|
| memory claim/마이그레이션/기존 memory·기한·worker 6파일, DB 활성화 | 84 | 0 | 0 |
| 기존 chat_messages/nonstream_answers 2파일, DB 활성화 | 28 | 0 | 0 |
| 전체 API, 오프라인 | 1464 | 0 | 308 |
| 필수 아키텍처/패턴 검사 | 13 | 0 | 0 |

- 신규 회귀는 총 21건(실제 PostgreSQL 20건 + 기한 1건)이다. 전체 오프라인에서는
  신규 PG 20건이 skip되며 위의 DB 활성화 실행에서 실제 통과했다. 기존 288 skipped에
  신규 20건이 더해져 308이다. skipped를 passed로 계산하거나 중복 실행을 합산하지 않는다.
- 필수 `check_backend_quality.py`: **Ruff 393파일, mypy 372소스, 타입 패턴 기준선 0개**.
- 변경 생산 코드·새 마이그레이션·새 회귀 11파일의 Ruff format/check·mypy도 통과했다.
  기존 테스트는 토큰 fixture/head 기대값만 필요한 범위에서 수정했다.
- 변경 범위 `git diff --check`, 신규 파일의 no-index 공백 검사 통과.
- DB 검증 후 API/auth 테스트 DB의 잔여 test_/auth_test_ 스키마는 각각 **0개**였다.
- 경고: 기존 Starlette 422 경고 2개(전체 API), 기존 Alembic path_separator 설정 경고
  3개(새 마이그레이션 테스트). 공통 설정을 변경하거나 경고를 숨기지 않았다.

최종 로그: [관련 84건](../../../tmp/u03-business-final.txt),
[채팅 DB 28건](../../../tmp/u03-chat-db.txt),
[품질 검사](../../../tmp/u03-quality.txt),
[전체 API](../../../tmp/u03-api-offline.txt).

PostgreSQL 회귀는 별도 세션과 실제 SQL을 사용한다. writer가 잠긴 claim을 커밋/롤백하기
전에는 SKIP LOCKED가 재획득하지 못하며, 반대로 재claim이 먼저 행을 잠근 경우에는
pg_blocking_pids로 실제 DB 잠금 대기를 관찰한 뒤 commit한다. 대기하던 이전 writer가
새 토큰을 다시 평가하고 저장을 거절하는 것까지 확인했다. 공급자만 대역을 사용했다.

## 실행 명령

프로젝트 루트에서 프로젝트 Python으로 실행한다. DB 도우미는 Git 제외 접속 파일을
읽고 전용 DB 접두사/로컬 주소를 검사하며 외부 공급자 키를 제거한다.

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_memory_claim_fencing.py apps/api/tests/test_memory_claim_migrations.py apps/api/tests/test_hypha_memory.py apps/api/tests/test_memory_deadlines.py apps/api/tests/test_memory_query.py apps/api/tests/test_runtime_entrypoint_contracts.py
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_chat_messages.py apps/api/tests/test_nonstream_answers.py

Remove-Item Env:TEST_DATABASE_URL,Env:TEST_AUTH_DATABASE_URL -ErrorAction SilentlyContinue
$env:PYTEST_ADDOPTS = '--basetemp=tmp/q03-' + [guid]::NewGuid().ToString('N').Substring(0,6)
.venv/Scripts/python.exe tools/check_backend_quality.py

Remove-Item Env:TEST_DATABASE_URL,Env:TEST_AUTH_DATABASE_URL,Env:VOYAGE_API_KEY,Env:OPENAI_API_KEY,Env:ANTHROPIC_API_KEY,Env:RUN_ASSET_STORAGE_S3_INTEGRATION,Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
$env:PYTHONPATH = (Resolve-Path apps/api).Path
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$u03BaseTemp = 'tmp/a03-' + [guid]::NewGuid().ToString('N').Substring(0,6)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests -q -rs --tb=short --basetemp=$u03BaseTemp
```

Docker/asyncio의 Windows 샌드박스 제한이 있는 실행은 승인된 권한으로 수행했다.
접속 URL/비밀번호는 로그나 문서에 출력하지 않았고 전역/사용자 환경은 변경하지 않았다.

## 통합·배포 주의와 한계

1. 배포 시 **구 memory worker 중지 → 0031 적용 → 새 코드의 API/worker 시작** 순서가 필요하다.
   구 worker의 SQL은 토큰 조건이 없으므로 구/신 worker 혼용으로 fencing을 보장할 수 없다.
   이번 작업은 앱 DB에 적용하지 않았으며, 테스트 fixture 소유 스키마에서만 DDL을 실행했다.
2. 업그레이드는 기존 큐의 상태/세대/시각을 보존한다. 토큰 없는 기존 running 행은 lease가
   만료되면 새 worker가 재claim한다. downgrade는 running 행이 있는 동안 거절한다.
3. 다른 병렬 작업이 마이그레이션을 추가하면 Alembic head/번호를 다시 확인하고 기존 wallet
   migration 테스트의 head 기대값도 맞춘다. 공통 REPORT 통합은 이후 담당자가 이 기록으로
   수행한다. U21이나 다른 작업의 파일/commit은 생성하지 않았다.
4. 전체 API 결과는 현재 미커밋 작업 트리의 통합 결과다. 전체 DB 활성화 API·전체 빈 DB
   Alembic 온라인 구축·실제 공급자·운영 처리량/장애 복구까지 검증한 것은 아니다.
   운영 timeout/lease 정책과 외부 요청 중복 가능성은 남는다.
5. 별도 대화·서브에이전트·commit/push, 앱 DB 초기화/삭제, Docker 재생성/볼륨 삭제는 없다.
