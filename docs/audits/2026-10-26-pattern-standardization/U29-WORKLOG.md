# U29 SDK 오류 분류·메모리 작업 전체 기한

작성일: 2026-10-30 (Asia/Seoul)

상태: **U29 수정·오프라인 검증 완료. 실제 공급자/DB 경쟁 검증과 U03 claim fencing은 별도다.**

## 변경 계약

- `llm/adapters/base.py`: 상태 코드가 없는 예외를 일시 공급자 장애로 추정하지 않는다.
  TypeError·JSONDecodeError·RuntimeError·미분류 SDK APIError는 기존
  LLMError(PROVIDER, retryable=False)다. SDK timeout/connection/rate limit과
  401/403·429·나머지 4xx·5xx는 기존 분류다. 오류 enum·cause·provider/model·요청 ID/
  상태 코드, SDK 재시도 설정을 보존한다. 호출 후 파싱 오류는 기존대로 전파하고,
  usage 검증/정규화·Voyage의 기존 분류나 client 종료 계약은 바꾸지 않았다.
- `chat/types.py`: ProcessMemoryWorkCommand의 세 위치 인자를 유지하며
  timeout_seconds=240.0을 추가한다. 요청 데이터에 해당하는 Command에 기한을 두고
  기존 MemoryPolicy의 토큰/선택 정책과 섞지 않았다.
- `chat/service/workflow/memory.py`: workflow 진입 시 단일 asyncio timeout을 만들고
  동일한 단조 시계 deadline을 pending 색인·원문 조회·요약·저장·임베딩·완료에 적용한다.
  각 SDK 요청이나 단계마다 시간 예산을 초기화하지 않는다. 기한이 지난 공급자 결과는
  저장 전에 거절한다. 별도 태스크나 shield로 작업을 분리하지 않으며 취소된 DB/공급자
  실행의 정리가 끝난 뒤 실패를 기록한다.
- `memory/types.py`: MemoryWorkDeadlineExceededError는 TimeoutError의 하위 타입이다.
  실제 요청 timeout과 구별되는 error_kind를 큐/로그에 남기되 기존 재시도 정책을 쓴다.
  최대 5회·5초 시작/300초 상한 backoff, 처리 중 추가 예약 세대와 pending 요약 재사용을
  유지한다. shutdown CancelledError는 전파하며 별도 실패 기록을 하지 않는다.
- `app.memory_worker`: MEMORY_WORK_TIMEOUT_SECONDS(기본 240)를 읽고 자원 생성 전에
  유한 양수·timeout<lease를 검사한다. lease 기본 300초·1~3600초는 유지한다.
  `.env.example`에 설정을 추가했다. lease를 240초 이하로 낮추면 timeout도 함께 낮춰야
  시작할 수 있다. worker의 기존 동시성·once drain·종료 순서는 유지한다.

기존 workflow와 adapter의 책임 안에서 수정했다. 새 범용 실행 계층이나 재시도 wrapper,
데이터베이스 컬럼·migration·새 HTTP 오류 종류를 만들지 않았다. 세 모듈의 ARCHITECTURE를
갱신했다. 작업 트리의 앞선 U09/U11/U13·SDK 타입 정리 등 기존 변경을 덮어쓰지 않았다.

## 검증

프로젝트 `.venv/Scripts/python.exe`를 사용했다. TEST_DATABASE_URL,
TEST_AUTH_DATABASE_URL, VOYAGE_API_KEY를 제거하여 실제 DB/live 공급자 호출을 피했다.

| 범위 | 결과 |
|---|---|
| 수정 전 상태 없는 예외 분류식을 별도 프로세스 메모리에만 복원 | 신규 SDK 테스트 **8 failed / 4 passed** |
| test_llm_error_classification 신규 | **12 passed** |
| test_memory_deadlines 신규 | **22 passed** |
| 관련 7파일 | **113 passed / 0 failed / 1 skipped** |
| 필수 품질 검사 | 기준선 0개, Ruff 390파일, mypy 369소스, **13 passed** |
| 전체 API | **1418 passed / 0 failed / 288 skipped**, 기존 422 경고 2개 |
| 변경 파일 Ruff format/check·git diff --check | 통과 |

SDK 테스트는 실제 설치된 OpenAI/Anthropic 예외 클래스와 주입 client를 사용한다.
TypeError·JSON 파싱·일반 오류·미분류 APIError·200 응답 검증 오류의 비재시도,
원인 보존·단일 호출·취소 전파를 확인한다. 기존 테스트로 실제 SDK timeout/connection/
인증/429/5xx 및 하위 클래스, 호출 이후 Anthropic usage TypeError, Voyage 오류도 확인했다.

메모리 테스트는 전체 예산 공유, 실행/세션 정리→실패 기록 순서, 요청 timeout과 전체
deadline 구분, 비재시도 내부 오류, shutdown 취소, 유한 양수 검증, lease보다 짧은 설정,
취소를 잡아 늦게 반환하는 요약/임베딩 결과 거절, 정상 완료와 worker 설정 전달을 확인한다.
실제 SQLite MemoryJob UPDATE를 동기 Session에 위임한 비동기 대역으로 실행해
pending/failed·최대 횟수·backoff·lease 해제·추가 requested_generation 보존을 확인했다.
이 대역은 PostgreSQL 잠금·격리나 실제 DB I/O 취소를 검증하지 않는다.

로그:

- `tmp/u29-focused-final.txt`
- `tmp/u29-backend-quality-final.txt`
- `tmp/u29-api-regression.txt`

주요 명령(각 basetemp는 새 프로젝트 경로를 사용):

```powershell
$env:PYTHONPATH='apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:TEST_AUTH_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:VOYAGE_API_KEY -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p no:cacheprovider apps/api/tests/test_llm_error_classification.py apps/api/tests/test_memory_deadlines.py apps/api/tests/test_llm.py apps/api/tests/test_llm_sdk_contracts.py apps/api/tests/test_embeddings.py apps/api/tests/test_hypha_memory.py apps/api/tests/test_runtime_entrypoint_contracts.py -q --tb=short --basetemp=tmp/u29-focused-final
$env:PYTEST_ADDOPTS='--basetemp=tmp/u29-quality'
.venv/Scripts/python.exe tools/check_backend_quality.py
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p no:cacheprovider apps/api/tests -q -rs --tb=short --basetemp=tmp/u29a-<새 식별자>
```

초기 샌드박스 실행은 Windows asyncio 초기화의 socketpair accept에서 멈췄다.
faulthandler로 표준 라이브러리 스택을 확인하고 중단한 뒤, 승인된 샌드박스 밖의
오프라인 실행으로 위 결과를 얻었다. 품질 검사의 첫 실행은 pytest 기본 Temp의
권한으로 11 passed / 2 errors였다. PYTEST_ADDOPTS로 새 프로젝트 basetemp를 지정한
동일 명령은 13 passed였다. 테스트·품질 설정을 수정하거나 검사를 제외하지 않았다.
최종 전체 API 수는 기존의 다른 미커밋 작업도 포함한 현재 작업 트리의 통합 결과이며
신규 34건과 품질 13건을 다시 더하지 않는다.

## 출처와 한계

OpenAI Docs 스킬을 적용해 [공식 Python 오류·재시도·timeout 계약](https://developers.openai.com/api/reference/python)을
2026-10-30에 대조했다. SDK timeout/연결/HTTP 상태 실패를 구분하고 SDK 재시도 설정을
그대로 유지하는 근거로 사용했다. 설치 소스(openai 2.54.0, anthropic 0.125.0)의 예외
상속/생성자와 기존 로컬 테스트가 구현 기준이며 최신 문서에 맞춘 SDK 업그레이드는 없다.

전체 기한은 workflow 진입부터 **한 시도**의 처리 예산이다. claim 트랜잭션 대기나
모든 재시도에 걸친 누적 SLA가 아니다. 취소는 협력적이며 동기 파싱, 취소를 무시하는
코드, DB rollback/commit, 실패 기록까지 벽시계로 강제 종료하지 않는다. 이미 commit된
pending 요약/색인은 다음 시도에서 재사용될 수 있다. commit 결과 불확실성을 제거하는
보장도 추가하지 않았다.

lease 갱신·claim별 실행 토큰/fencing은 추가하지 않았다. claim이 오래 걸리거나 cleanup이
lease를 넘으면 재claim·중복 외부 호출은 가능하며 **U03은 미완료**다. 정확히 한 번 실행을
보장하지 않는다. 실제 PostgreSQL 경합/잠금/격리, 네트워크 timeout과 공급자 취소,
운영 지연/처리량은 미검증이다. DB 초기화·삭제·migration, 외부 공급자 요청, commit/push는
수행하지 않았다. 타입 기준선·Any/ignore/cast 예외·공통 검사 설정도 추가하지 않았다.
