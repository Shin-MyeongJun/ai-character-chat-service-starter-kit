# U27 사용 조사·안전한 정리 (2026-11-02)

저장소 안에서 import·실행 진입점·사용처가 없는 것으로 확인한 0바이트 Python 파일
5개만 제거했다. legacy 모델·테이블·재노출 API·가격 정책은 보존했다. 기존
staged/unstaged/untracked 변경이 있는 작업 트리를 기준으로 조사·검증했다.

## 삭제한 파일과 실제 경로

아래 경로는 `apps/api/app/modules/` 기준이다. 다섯 파일 모두 변경 전 0바이트이고
SHA-256은 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`였다.
`__init__.py`와 내용이 있는 작은 파일은 삭제하지 않았다.

| 삭제 파일 | 현재 실행 경계 |
| --- | --- |
| `chatting/chat/stream.py` | 비스트리밍 답변은 `chat/router/answers.py` → `chat/service/workflow/answers.py`. 스트리밍 구현은 없음 |
| `chatting/memory/schemas.py` | memory 공개 service/types와 chat 기억 workflow. memory 자체 HTTP DTO 없음 |
| `commerce/billing/router.py` | `app/http/routes.py`는 billing 전용 라우터를 등록하지 않음. 답변 HTTP와 account credit HTTP는 기존 경로 유지 |
| `commerce/billing/schemas.py` | billing 공개 Command/Info 및 견적 persistence mapper. 전용 결제 HTTP DTO 없음 |
| `governance/admin/router.py` | `app/http/routes.py`가 character/lorebook/product/model/tag 기능별 라우터를 명시적으로 등록 |

다섯 파일이 소유한 함수·DTO·라우터 객체는 없었다. 해당 모듈 ARCHITECTURE.md와
routes.py의 설명을 현재 구조로 갱신했다. 기존 감사 source-baseline.json과 과거
검토 체크리스트는 당시 스냅샷이므로 수정하지 않았다.

## 조사 방법과 진입점

- `apps/api`(앱·테스트·Alembic)와 `tools`의 Python **792개 → 787개**를 AST로
  읽었다. `import`, `from ... import ...`, 상대 import를 절대 경로로 해석하고
  부모 패키지에서 후보 모듈을 가져오는 경우도 확인했다. 후보 5개를 가리키는
  import 또는 모듈명 문자열 상수는 변경 전후 모두 0건이다.
- `apps/api/app`의 `import_module`, `__import__`, pkgutil 순회, 파일 기반 로더,
  runpy 및 entry point 자동 발견 호출을 검색했다. 후보를 자동 로드하는 앱 경로는
  발견하지 못했다. 테스트의 동적 import는 콘텐츠 태그 모듈·HTTP 계약과 명시된
  migration/검사기 파일을 대상으로 하므로 삭제 대상과 겹치지 않는다.
- `apps`, `tools`, `infra`, `contracts`, README/package/compose 및 관련 문서에서
  후보의 점·슬래시 경로를 검색했다. 실행 참조는 없고 과거 감사 해시·검토 기록과
  설명만 있었다. 배포 설정·pyproject에 후보를 지정한 entry point도 없다.
- Dockerfile의 API 진입점은 `uvicorn app.main:app`이다. compose는 PostgreSQL과
  Redis만 정의한다. Python 패키징은 `app*`를 포함하지만 모듈 자동 실행은 하지 않는다.
- 별도 프로세스에서 아래 8개 모듈을 변경 전후 모두 import했다. 서비스 lifespan이나
  CLI 업무 함수를 실행하지 않았으며 DB/스토리지/공급자 요청은 하지 않았다.

| 구분 | import 확인 |
| --- | --- |
| API | `app.main` |
| worker | `app.memory_worker`, `app.auth_mail_worker` |
| 운영 CLI | `app.auth_cleanup`, `app.media_cleanup`, `app.answer_recovery` |
| 일회 통계 작업 | `app.modules.content.product.statistics_job` |
| 수동 저장소 예제 | `app.modules.asset_storage.example` |

이 조사는 현재 저장소와 명시된 실행 설정에 한정한다. 별도 배포 환경의 사용자 정의
스크립트·외부 Python 소비자·저장소 밖의 스케줄러 사용 여부까지 증명하지는 않는다.
삭제된 빈 모듈 자체를 외부에서 import하던 경우에는 ModuleNotFoundError가 발생한다.
기존 저장소 내부 호출과 HTTP/DB 계약의 보존은 아래 비교와 회귀로 확인했다.

## 보존한 legacy·호환 코드

| 대상 | 확인한 사용·의존 근거 | 판단 |
| --- | --- | --- |
| `SubscriptionPlan`, `UserSubscription` | `db/models/__init__.py` import/`__all__`, `billing.py`의 `Payment.subscription_id → user_subscriptions.id`와 `UserSubscription.plan_id → subscription_plans.id`, baseline/초기 SQL | 업무 서비스의 직접 호출은 없지만 모델 등록·FK·기존 스키마 계약이 있으므로 유지 |
| `ModerationFlag` 및 관련 enum | 모델 등록/재노출, baseline/초기 SQL, `0027_moderation_review.py`의 테이블 잠금과 SQL의 `FROM moderation_flags` | 0027/초기 SQL 018이 기존 행을 같은 ID/request_key의 moderation_reports로 복사하는 입력. 미사용 삭제 대상 아님 |
| `LegacyModerationFlag` TypedDict·변환 | moderation mapper와 validation이 evidence_snapshot의 legacy 상태/검토 메타데이터를 읽음 | 실제 이관 provenance 조회 계약이므로 유지 |
| billing 모델의 `CreditAccount`, `CreditTransaction`, `CreditTransactionReason` 재노출 | `test_chat_messages.py`의 기존 billing import로 계정/원장을 생성·검증. 실제 모델 소유자는 credit | 기존 Python 호환 경로 유지 |
| `use_cases/conversation_directory.py` | HTTP conversation directory와 schema mapper가 함수/View를 import | 실제 HTTP 진입점의 호환 함수·타입 재노출이므로 유지 |
| memory/service 및 command/query `__init__.py` | chat 메시지 command가 invalidate 함수를, worker/workflow가 공개 memory 서비스를 호출 | 패키지 초기화·공개 API 역할이 있으므로 유지 |
| 무효과 가격 정책 3개 | `service/policies.py` 기본 registry → pricing.calculate_billing_price의 순서 실행 → `quote_info_to_snapshots`가 price.policy_results를 저장하고 역변환 | UNIMPLEMENTED/DISABLED·noop-v1·정책 순서도 실제 계산/견적 JSON 계약. 삭제하면 저장·반환 구조가 달라져 유지 |

운영 DB의 행 수·구독/결제 연결·이관 완전성·외부 소비자는 조사하지 않았다.
향후 legacy 삭제에는 배포별 데이터/참조 조사, 이관·보존 정책과 검증, 명시적
migration 및 롤백 계획이 필요하다. 이번 작업은 DB 삭제나 구조 이전을 수행하지 않았다.

## 검증

프로젝트 `.venv/Scripts/python.exe`를 사용했다. 신규 동작이나 구현 배치에 종속된
테스트는 추가하지 않고 기존 계약 검사를 실행했다. 검사 범위·기준선 예외도 유지했다.

| 검증 | 결과 |
| --- | --- |
| 전후 import 조사 및 실행 진입점 import | 후보 참조 0건, 위 8개 모듈 import 성공 |
| 전후 전체 OpenAPI JSON 비교 | **84개 경로·114개 연산**, 전체 JSON 해시 동일 |
| 전후 PostgreSQL DDL/인덱스 컴파일 및 모든 FK 대상 해석 | **76개 테이블**, 전체 DDL/인덱스 해시 동일, FK 대상 해석 성공 |
| 전후 `app.db.models.__all__` | **58개 export**, 이름·순서 해시 동일 |
| `tools/check_backend_quality.py` | **통과**. 패턴 진단/예외 0건, Ruff format 395파일·lint 통과, mypy 374소스 통과, 아키텍처/검사기 **13 passed** |
| 관련 업무·HTTP·runtime 회귀 9파일 | **281 passed / 0 failed / 0 skipped**, 8.15초 |
| 변경 파일 `git diff --check` | 통과 |

전후 해시는 정렬한 JSON의 SHA-256이다. DDL은 테이블명별 CreateTable 및 정렬된
CreateIndex 문자열을 비교했다. 실제 DB의 스키마·데이터 비교를 대신하지 않는다.

| 계약 | 변경 전 = 변경 후 SHA-256 |
| --- | --- |
| OpenAPI | `a6faaba4d2ab1203aebc735d4c08f446b85c2eb0e2cf5e4bdd29ab8016e94d3e` |
| PostgreSQL DDL/인덱스 | `56cce9ebeb8221b23940b8982978bad519e7d94b76cb3b2e5c4776dd7942c84d` |
| 모델 export | `5d856198367d68cb0211ad192d6c2520c4131474a9e4185fe98bb640149597fa` |

실행 명령(저장소 루트, PowerShell):

```powershell
$env:PYTEST_ADDOPTS = '--basetemp=tmp/u27-quality-' + [guid]::NewGuid().ToString('N').Substring(0,8)
.venv/Scripts/python.exe tools/check_backend_quality.py

$env:PYTHONPATH = (Join-Path (Get-Location) 'apps/api')
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p anyio.pytest_plugin -p no:cacheprovider --basetemp=tmp/u27-regression-02 apps/api/tests/test_runtime_entrypoint_contracts.py apps/api/tests/test_chat_router_http_contracts.py apps/api/tests/test_chat_message_contracts.py apps/api/tests/test_admin_authorization_http.py apps/api/tests/test_content_actor_routes.py apps/api/tests/test_billing_pricing_contracts.py apps/api/tests/test_billing_prices.py apps/api/tests/test_billing_persistence_contracts.py apps/api/tests/test_memory_query.py -q --tb=short
```

최초 회귀 실행은 Windows 샌드박스의 asyncio 루프 초기화에서 진행하지 않아 중단했다.
별도 `asyncio.run(asyncio.sleep(0))` 프로세스도 8초 제한 안에 끝나지 않는 것을 확인한
뒤 같은 테스트를 승인된 일반 실행 환경에서 재실행해 통과했다. 제품/테스트의 이벤트
루프를 바꾸어 우회하지 않았다. 로컬 로그는 `tmp/u27-quality.log`,
`tmp/u27-regression-approved.log`에 보존한다. 일회 조사 스크립트와 비교 기준도
`tmp/u27_audit.py`, `tmp/u27-contracts-before.json`에 로컬 보존했다.

전체 API·실제 PostgreSQL 데이터/잠금·운영 배포·외부 공급자·브라우저는 검증하지
않았다. 현재 미커밋 작업 트리의 관련 회귀 결과다. 안전성이 확인된 빈 파일 정리는
완료했고 legacy 스키마의 삭제는 보류한다. commit/push는 하지 않았다.
