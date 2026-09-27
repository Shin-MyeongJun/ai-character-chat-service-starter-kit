# 백엔드 workflow 정리 진행 기록

## 목표·결정·제외 범위

- chat이 답변 생성·완료·복구와 기억 작업 실행을 소유한다. prompt는 전달받은 자체 입력 타입으로만 프롬프트를 구성한다.
- workflow는 다단계 실행에만 사용한다. command의 인가·상태 전이·불변 조건과 기존 트랜잭션/취소 계약을 보존한다.
- 신규 대화의 첫 대사는 최초 상품 스냅샷의 고정 시작 내용이며 messages에 저장하지 않는다. 기존 데이터는 명시적 상태로 구분한다.
- character 미디어 외부 저장/삭제, identity OAuth/메일 실행을 선택적으로 분리한다.
- 상품 발행·기억 검색·통계 실행 및 큐 소유권·공통 HTTP·무관한 기존 규칙 위반은 제외한다. reporting은 향후 방향만 기록한다.

## 시작 상태 (2026-09-26)

- AGENTS.md, 모듈 규칙, chat/conversation/memory/prompt/character/identity/use_cases ARCHITECTURE를 확인했다.
- 기존 변경: 답변 과금 및 복구 구현, billing 설정, 답변 HTTP/main, 관련 테스트와 문서 및 .env.example. 기존 변경을 보존하고 현재 작업 트리 위에서 이전한다. staged 상태를 임의 변경하지 않는다.
- 기존 tmp/는 보존한다.

## 단계·완료 조건·상태

1. **완료**: 코드·기존 diff·의존성과 실행 환경 확인. `.venv/Scripts/python.exe`, `PYTHONPATH=apps/api`를 사용한다.
2. **완료**: chat workflow/HTTP 이전, 업무 types 정리, prompt 자체 메시지 입력 및 순수 mapper. 생성·동시 요청·staging·취소·정산·복구·기억 예약 회귀 통과.
3. **완료**: 최초 시작 내용 GET 계약, opening_mode 및 0025/초기 SQL, 신규 첫 대사 미저장, 최초 start 옵션 고정, 로컬 UI 반영. 신규/legacy/전환/프롬프트/권한/downgrade 및 초기 SQL/ORM/Alembic 검증 통과.
4. **완료**: character workflow에서 예약 확정 → 잠금 유지 I/O → 상태 완료. 읽기·첨부·상태 검증은 하위 media 서비스에 유지. 기존 로컬/가짜 S3 잠금·취소·실패·첨부 경쟁 회귀 통과.
5. **완료**: identity mail/Google workflow 분리. 계정·토큰·state·세션은 하위 서비스에 유지. DB 보안/메일 실패/OAuth state/refresh 회귀 통과.
6. **완료**: 모듈 문서·아키텍처/명명 규칙·실행 문서 갱신. 정적 경계·HTTP/OpenAPI·fresh import·실제 로컬 화면 확인 통과. 외부 환경을 요구하는 선택 검사 4개는 미실행으로 구분한다.

## 변경 파일·공개 계약

- `chat/service/workflow/{answers,answer_preparation,memory}.py`: 기존 use_cases 이동. 완료+기억 예약은 answers에 통합. 기존 use_cases 구현은 삭제하고 통계만 남긴다.
- `chat/router/{answers,messages}.py`, `schemas/{answers,messages}.py`, `mapper/schema/{answers,messages}.py`, `dependencies.py`, `mapper/prompt.py`: HTTP 계층 및 순수 입력 변환. 같은 이름의 단일 파일/폴더와 임시 이전 경로는 동시에 남기지 않았다. 답변 HTTP 계약 유지.
- `chat/types.py`, `memory/types.py`: workflow의 Command/Info/config/오류 이동. main/memory_worker 및 테스트 import 갱신.
- `conversation` types/schema/router/repository/mapper/service, `db/models/chat.py`, `0025_conversation_opening.py`, `016_conversation_opening.sql`: GET `/conversations/{id}/start` 추가. 최초 snapshot/start, opening_mode, opening_message 및 현재 participants/primary_product_character_id 제공. POST 시작 응답은 유지.
- 기존 행과 직접 legacy 생성은 `legacy_messages`(snapshot 첫 대사 추가 표시/삽입 없음), 신규 서비스 생성은 `snapshot`(messages 미저장). 본문 비교/가짜 ID/일괄 삭제를 사용하지 않는다. snapshot 대화가 있으면 손실성 downgrade를 거절한다.
- character `service/workflow/media.py`, identity `service/workflow/{google,mail}.py`와 하위 서비스, types, main, router, CLI 호출부 변경.
- `.local_test/static/app.js`, `.local_test/local_lab/worker.py`, `.local_test/tests/opening.test.cjs`: 시작 내용 별도 표시/참여자 ID 선택 및 새 workflow 경로, 실제 화면 회귀. `.local_test/`는 기존 `.git/info/exclude` 대상이다. 이 로컬 변경을 git diff가 담지 않으므로 해당 경로도 인계 시 보존한다. 공개 클라이언트 계약은 추적되는 API schema·test_conversation_opening·모듈/실행 문서에 기록했다. 비어 있는 apps/web에 새 UI를 만들지는 않았다.
- `references_document/reference/module-architecture-and-naming.md`: Workflow 분류·별칭·호출 방향·외부 호출별 트랜잭션 책임 추가. 이 기존 지침 경로 역시 저장소 ignore 대상이며 로컬 파일을 갱신했다.
- 기존 billing 가격/과금 변경은 보존했다. auth_cleanup은 메일 의존성 없이 하위 인증 서비스를 사용한다. 통계 실행/저장/큐 및 상품 발행·기억 검색 위치는 유지했다.

## 의존 관계·남은 문제

- 기존 product pending-update View → conversation query 관계는 범위 밖이다.
- 대화 runtime이 현재 스냅샷에서 최초 start_set_id를 찾던 문제는 해결했다. 최초 snapshot의 start 옵션과 현재 참여자/모델/로어를 구분하며, 최초 버전이 만료되어도 시작 이력은 조회된다.
- 기존 기억 작업 lease에는 주기 갱신이 없다. 이번 이전으로 정책을 추가하지 않는다.
- legacy_messages 대화의 첫 대사는 이미 저장된 이력으로 보존한다. snapshot 첫 대사를 추가하지 않고 기존 메시지/기억의 의미를 소급 재작성하지 않는다. 신규 고정 첫 대사는 메시지·요약 범위 밖의 고정 프롬프트 문맥이다.
- 신규 migration은 테스트 DB에만 실행했다. 운영/개인 DB 업그레이드는 하지 않았다. 배포 시 구형 writer 중지 → migration 0025 → 새 API/클라이언트 순서가 필요하다.

## 검증 명령·실제 결과

- `git status --short`, `git diff --stat`: 기존 변경 확인. 사용자 전역 git ignore 읽기 권한 경고가 있지만 저장소 상태 조회는 성공.
- 변경 전 관련 단위/HTTP/정적 검사: `PYTHONPATH=apps/api .venv/Scripts/python.exe -m pytest apps/api/tests/test_architecture_contracts.py apps/api/tests/test_answer_prompt.py apps/api/tests/test_answer_http.py -q --tb=short` → **32 passed**.
- 이전 중 실패한 모듈 경로/API 추가 목록/실행 의존성 검사 및 runtime mock은 수정했다.
- 2026-09-27 DB 준비 전: `$env:PYTHONPATH='apps/api'; .venv/Scripts/python.exe -m pytest apps/api/tests -q --tb=short --basetemp=tmp/workflow-tests-1` → **406 passed, 1 failed, 246 skipped**. 새 방향 검사에서 유지 대상 product/statistics_job의 정확한 두 CLI 조립 import만 예외로 수정했다. 기존 경계 검사를 약화하지 않았다.
- 초기 Docker pipe 부재는 Docker Desktop 시작 후 해결했다. 기존/운영 DB 대신 새 컨테이너 `chatkit-workflow-test-20260927`, loopback 55447의 `chatkit_workflow_test`를 사용했다. pgvector/pgvector:pg17 로컬 이미지를 사용했다.
- 작업 종료 시 해당 테스트 컨테이너를 stop했다. 재검증용 데이터는 보존하며 Docker Desktop이나 다른 컨테이너는 종료하지 않았다. 이번 작업의 일회성 변환 스크립트만 제거했고 기존 tmp/backend-assessment 및 사용자 변경은 보존했다.
- DB 전체 실행: `.venv/Scripts/python.exe -m pytest apps/api/tests -q --tb=short --basetemp=tmp/workflow-db-1` → **638 passed, 11 failed, 4 skipped, 169.20초**. 실패 11개는 신규 첫 대사 미저장에 따른 메시지 개수/인덱스·페이지 테스트 fixture 및 최신 revision 기대값(0024→0025)이었다. 구현/계약에 맞게 고쳤다. 메시지 HTTP의 페이지/캐릭터 수정 금지 검증은 별도 authored character fixture로 계속 보호한다.
- 실패 수정 및 media 완료 단계 추가 인가 검증 후 관련 재실행: 아래 `$checks` 명령 → **81 passed, 0 failed, 0 skipped, 48.52초**. 최초 실패 11개를 모두 포함한다.
- 신규 시작 내용 회귀 1차 `test_conversation_opening.py` → **5 passed**. 이후 downgrade guard와 공개 기억 workflow 실패 기록 회귀를 추가했다.
- 최종 신규/경계 검사: `.venv/Scripts/python.exe -m pytest apps/api/tests/test_architecture_contracts.py apps/api/tests/test_hypha_memory.py apps/api/tests/test_conversation_opening.py -q --tb=short --basetemp=tmp/workflow-final-boundaries` → **26 passed, 0 failed, 0 skipped, 6.98초**.
- 마지막 인가/방향 검사 강화 및 사용하지 않는 mapper 인자 제거 후 해당 2개 검사 → **2 passed**. 이후 자기 모듈 alias 정리와 포맷은 동작 변경이 아니다.
- 현재 수집 **660개**. 위 전체 실행과 필요한 부분 재검증을 합치면 **656개 항목 통과, 선택 외부 4개 미실행, 미해결 실패 0**이다. 최종 전체를 다시 한 번 실행한 결과라고 표현하지 않는다.
- 실제 Chrome headless `.local_test/tests/opening.test.cjs` → **PASS**. 신규 시작 aside/일반 메시지 분리, legacy 한 번 표시, 동일 본문의 사용자 메시지 보존, 현재 스냅샷 추정 대신 명시적 participant 계약 사용, JS 오류 없음. synthetic HTTP만 사용했다. 스크린샷 `tmp/workflow-client.png`를 확인했다.
- 변경 Python 72개 Ruff `--select F,I` 및 format check → 통과. 저장소 전체 기본 Ruff 진단의 기존 commerce/test 경고는 무관한 정리 범위에서 제외했고 전체 기본 Ruff 통과로 표현하지 않는다.
- fresh Python 프로세스에서 모듈 217개 + main/memory_worker/media_cleanup/auth_cleanup import, 변경 dataclass 타입 힌트 해석 → 통과. 구 use_cases/HTTP 경로와 PreparedConversationInfo/create_product_conversation 호출 잔존 없음. `git diff --check HEAD` 통과(전역 ignore 읽기/CRLF 안내 경고만 있음).

### 검증 재현 명령

PowerShell, 저장소 루트 기준. 임시 테스트 DB의 공개 로컬 전용 자격증명이며 운영 비밀값이 아니다.

```powershell
$env:PYTHONPATH='apps/api'
$env:TEST_DATABASE_URL='postgresql+asyncpg://workflow_test:workflow_test_only@127.0.0.1:55447/chatkit_workflow_test'
$env:TEST_AUTH_DATABASE_URL=$env:TEST_DATABASE_URL
$checks=@('test_chat_http.py','test_credit_wallet_migrations.py','test_first_answer_integration.py','test_product_integration.py','test_product_migrations.py','test_architecture_contracts.py','test_character_media.py','test_answer_http.py','test_answer_billing_configuration.py') | ForEach-Object { "apps/api/tests/$_" }
.venv/Scripts/python.exe -m pytest @checks -q --tb=short --basetemp=tmp/workflow-db-2
$env:NODE_PATH='C:/Users/smj/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
node .local_test/tests/opening.test.cjs
```

재실행 시 basetemp는 새 경로를 지정한다. 외부 4개는 실제 S3 2개·Mailpit 1개·Voyage 1개로 해당 설정을 주입하지 않았으며 실제 외부 LLM/메일/저장소 호출 없이 검증했다.

## 다음 행동

요청된 구현과 로컬 검증은 완료했다. 추가 코드 작업은 남아 있지 않다. 다음 작업자는 `git diff HEAD`와 위 ignore 대상 로컬 문서/UI를 함께 검토한다. 배포를 진행하는 별도 작업에서는 DB 백업/0025 업그레이드와 클라이언트의 `/start` 사용을 적용한다. 선택 외부 검증이 필요하면 해당 테스트 환경을 별도로 준비한다. 테스트 컨테이너를 재사용할 때는 `docker start chatkit-workflow-test-20260927` 후 위 환경으로 필요한 검사만 실행한다.
