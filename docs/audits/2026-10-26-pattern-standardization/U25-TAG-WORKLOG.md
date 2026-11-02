# U25 잔여 태그 이름 resolve 배치화

작성일: 2026-10-30 (Asia/Seoul)

현재 상태(2026-11-02): **태그·통계 배치화 및 실제 PG 경합·감사 통합 완료.**
신규 PG 경합 17건을 포함한 관련 201 passed, 전체 API 오프라인 1706 passed / 446 skipped와
필수 품질 검사를 통과했다. 현재 완료 판정·명령·검증 한계는
[U25-PG-INTEGRATION.md](U25-PG-INTEGRATION.md)를 따른다. 아래는 2026-10-30 단독 작업 기록이다.

당시 상태: **태그 resolve 배치화 구현·범위 검증 완료. U29와의 통합 전체 회귀는 별도 실행.**
앞선 통계 범위는 [U25-STATISTICS-WORKLOG.md](U25-STATISTICS-WORKLOG.md)에 기록돼 있다.
두 범위의 구현 결과를 통합할 때 공통 감사 REPORT의 U25 완료 상태를 갱신한다.

## 시작 상태와 경계

AGENTS.md, 모듈 아키텍처/명명·백엔드 작성 규칙, tag ARCHITECTURE, 원본 U25와 최신
감사/통계 기록을 읽고 git 상태와 대상 staged/unstaged diff를 확인했다. tag 모듈과
test_tag_management.py에는 기존 변경이 없었다. 다른 작업의 기존 변경을 보존했다.

U29 LLM/메모리 영역, U19 이미지 개편, 통계 구현·발행 저장소·세 도메인 태그 공통화,
공통 검사 설정·두 공통 REPORT는 수정하지 않았다. 별도 대화/서브에이전트·commit/push,
reset/clean·무관한 복원/삭제는 하지 않았다. 새 로그/임시 경로는 u25-tag 및 t25/qt25로
분리했다. 이전 중단된 요청에서는 이 작업의 도구 실행이 없었으며 현재 범위에서 시작했다.

## 구현과 보존한 계약

- service/command.resolve_tags는 기존 trim·첫 등장 순 중복 제거 정책을 유지한다.
  내부 공백·대소문자·Unicode 조합형·동의어를 통합하지 않는다. 입력 Command와
  retained_ids를 변경하지 않으며 반환은 기존 TagInfo tuple과 입력 순서다.
- repository.resolve_tags는 정렬·중복 제거한 정확한 이름을 최대 500개씩 처리한다.
  다중 VALUES INSERT ON CONFLICT (name) DO NOTHING 뒤 같은 묶음을 FOR SHARE로 읽는다.
  기존 행의 id·description·is_active·created_at·updated_at을 덮어쓰지 않는다.
- SELECT의 ORDER BY CASE는 Python 이름 순번을 직접 바인딩한다. DB collation과 Python
  정렬이 다르더라도 INSERT 값 목록과 잠금 조회의 요청 순서가 일치하게 한다.
  populate_existing으로 이미 로드된 Entity의 오래된 name/is_active를 재사용하지 않는다.
- service는 mapper로 Entity 목록을 Info로 변환한 뒤 업무 판단한다. 이름순 첫 누락은
  기존 `Tag name changed concurrently; retry the request.` 오류, 허용된 retained_ids에
  없는 비활성 태그는 기존 `Inactive tags cannot be newly assigned.` 오류를 유지한다.
- 이미 인가하고 부모를 잠근 콘텐츠 호출자가 읽은 기존 연결 ID만 retained_ids로
  전달한다. 세 도메인의 공개/내부·admin/system 보호와 응답 노출 정책은 바꾸지 않았다.
- 단건 repository.resolve_tag와 관리자 create/update/deactivate의 인가·설명 보존·오류
  번역은 그대로다. 새로운 공개 Command/API·DB 스키마·저장 JSON은 없다.
- 모든 배치는 하나의 use_case_transaction에 순차 참여한다. 내부 commit/rollback/
  savepoint·같은 AsyncSession의 병렬 실행은 없다. 중간 SQL 실패와 취소, 이후 상위
  실패를 전파하며 전체 신규 사전 행과 상위 쓰기를 rollback한다. 상위가 내부 실패를
  잡더라도 기존 rollback-only 계약으로 전체를 되돌린다.

## 변경 전후 SQL 측정

코드를 바꾸기 전 같은 test_tag_resolve_batch_contracts의 5개 입력을 실행해 **5 passed**를
확인했다. 수정 뒤 같은 입력과 추가 경계를 실행했다. before_cursor_execute의 실제
SQLite INSERT/SELECT event 수이며 네트워크 왕복·처리량·PostgreSQL 실행 계획 측정은 아니다.

| 고유 이름 수 | 변경 전 INSERT | 변경 전 SELECT | 변경 후 INSERT | 변경 후 SELECT |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 | 0 |
| 1 | 1 | 1 | 1 | 1 |
| 3 | 3 | 3 | 1 | 1 |
| 501 | 501 | 501 | 2 | 2 |
| 1,001 | 1,001 | 1,001 | 3 | 3 |

추가 499/500개 경계는 각각 INSERT 1회·SELECT 1회다. 고유 이름 N개의 각 SQL 횟수는
ceil(N/500)이며 빈 입력에서는 SQL이 없다. INSERT는 최대 500개 바인딩, SELECT는 IN과
CASE의 이름/순번을 합쳐 최대 1,500개 바인딩이다. SQL 크기를 제한하지만 전체 정규화
이름·Entity·Info·반환 목록의 메모리가 O(500)이라는 뜻은 아니다. 반환을 위해 O(N) 메모리를 쓴다.

검증기 범위:

- 실제 공개 resolve_tags와 실제 repository SQL/mapper를 사용한다. SQL 결과를 대역으로
  만들지 않았다. 최소 tags 테이블의 정확한 이름 UNIQUE·빈 이름 CHECK와 DB UUID/시각/
  활성 기본값을 SQLite에 구성했다. SQLite UUID 기본값 함수만 테스트에서 공급한다.
- AsyncSession의 SQL 메서드는 동기 SQLite Session에 연결한 AsyncMock 어댑터다.
  실제 AsyncSession transaction event를 SQLite commit/rollback에 연결한다.
- PostgreSQL dialect 컴파일로 conflict 대상, FOR SHARE, CASE 이름 순서와 바인딩 상한을
  확인했다. SQLite는 PG 행 잠금·unique 충돌 대기·격리·DB collation 차이를 실행하지 않는다.
- 동시 이름 변경의 누락 오류는 INSERT와 SELECT 사이에 테스트가 이름을 바꾸어 재현한다.
  실제 두 PostgreSQL 세션의 경합 시험이 아니다. 콘텐츠 인가/연결·HTTP는 기존 대역 회귀다.

로그: [변경 전](../../../tmp/u25-tag-before.txt),
[최종 업무·SQL 측정](../../../tmp/u25-tag-business-final.txt),
[필수 품질](../../../tmp/u25-tag-quality.txt).

## 회귀와 검증 결과

신규 회귀 **25건**은 SQL 0/1/3/499/500/501/1001개 경계, 입력 순서·trim/중복/Unicode,
기존 ID 재사용·설명/활성/시각 보존, 비활성 유지와 신규 연결 거절, identity map 갱신,
빈 이름 검증·누락 재시도 오류, INSERT/SELECT 두 번째 배치 실패와 상위가 잡은 실패,
이후 상위 실패·취소 rollback, 무관한 기존 transaction 거절, 저장소 중복 제거 및 단건
관리자 생성의 기존 계약을 검사한다.

| 검증 | 결과 |
|---|---|
| 변경 전 동일 SQL 검증기 | 5 passed / 0 failed / 0 skipped |
| 관련 9파일 최종 업무 회귀 | **103 passed / 0 failed / 11 skipped**, 신규 25건 포함 |
| 필수 check_backend_quality.py | Ruff 390파일·mypy 369소스·13 passed / 0 failed / 0 skipped·기준선 0개 |
| repository/command/신규 테스트 직접 Ruff format/check·mypy | 통과, mypy 3소스 |
| 기존 test_tag_management 대역 수정 | format 및 E4/E7/E9/F/I 검사 통과; 새 helper는 입력/반환 타입 명시 |
| 변경 범위 git diff --check | 통과 |
| 전체 API | 이번 범위에서는 미실행; U29 통합 후 별도 실행 |

기존 test_tag_management.py 전체의 미주석 fixture를 새로 엄격 타입 검사에 편입한 것은
아니다. 배치 저장소 mock을 추가하는 데 한정했고 검사 설정·기준선·Any/ignore/cast 예외를
추가하지 않았다. 새 테스트와 제품 코드에는 전체 설정의 Ruff/mypy를 직접 적용했다.
11 skipped는 PostgreSQL 환경이 필요한 기존 태그 통합/schema 테스트이며 passed로
세지 않았다. 이전 U23의 전체 API 1359 passed도 이번 통합 결과로 제시하지 않는다.

모든 Python은 프로젝트 .venv/Scripts/python.exe를 사용하고 TEST_DATABASE_URL 및
TEST_AUTH_DATABASE_URL을 제거했다. 실제 DB migration/초기화/삭제와 외부 공급자 요청은
실행하지 않았다. Windows asyncio 샌드박스 제약이 알려진 업무 테스트는 승인된 오프라인
실행을 사용했다.

## 잠금 범위의 변화와 한계

이름순 INSERT와 공유 잠금 모드/조회 순서는 유지하지만 기존 이름마다 INSERT→SHARE가
교차하던 동작은 **배치마다 INSERT→SHARE**로 바뀐다. 새 이름 삽입 및 기존 행 잠금의
획득 시점이 전부 이전과 같다고 주장하지 않는다. 비활성 검증도 묶음 조회가 끝난 뒤 하므로
실패 전 잠시 생성한 다른 이름은 상위 트랜잭션에서 함께 rollback된다.

실제 PostgreSQL에서 겹치는 다중 이름 resolve, 관리자 이름 변경·비활성화·생성 및
unique 충돌 대기의 조합을 추가 검증해야 한다. 정렬된 SQL 요청과 SQLite rollback만으로
교착 부재나 운영 경합/성능을 보장하지 않는다. 이를 우회하는 전역 advisory lock,
FOR UPDATE 강화·새 격리 수준·범용 재시도 정책을 추가하지 않았다.

## 재실행·통합 명령

저장소 루트 PowerShell에서 실행한다. 다른 작업과 basetemp를 공유하지 않고 매번 짧은
새 경로를 생성한다.

```powershell
$env:PYTHONPATH = 'apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL, Env:TEST_AUTH_DATABASE_URL, Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
$tagTemp = 'tmp/t25-' + [guid]::NewGuid().ToString('N').Substring(0,6)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests/test_tag_resolve_batch_contracts.py apps/api/tests/test_tag_management.py apps/api/tests/test_tag_management_db.py apps/api/tests/test_tag_schema.py apps/api/tests/test_character_http.py apps/api/tests/test_lorebook_http.py apps/api/tests/test_product_http.py apps/api/tests/test_studio_republication_contracts.py apps/api/tests/test_studio_publication.py -q -s -rs --tb=short --basetemp=$tagTemp

$env:PYTEST_ADDOPTS = '--basetemp=tmp/qt25-' + [guid]::NewGuid().ToString('N').Substring(0,6)
.venv/Scripts/python.exe tools/check_backend_quality.py
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue

.venv/Scripts/python.exe -m ruff format --check --config apps/api/pyproject.toml apps/api/app/modules/content/tag/repository.py apps/api/app/modules/content/tag/service/command.py apps/api/tests/test_tag_resolve_batch_contracts.py apps/api/tests/test_tag_management.py
.venv/Scripts/python.exe -m ruff check --config apps/api/pyproject.toml apps/api/app/modules/content/tag/repository.py apps/api/app/modules/content/tag/service/command.py apps/api/tests/test_tag_resolve_batch_contracts.py
.venv/Scripts/python.exe -m ruff check --config apps/api/pyproject.toml --select E4,E7,E9,F,I apps/api/tests/test_tag_management.py
.venv/Scripts/python.exe -m mypy --config-file apps/api/pyproject.toml apps/api/app/modules/content/tag/repository.py apps/api/app/modules/content/tag/service/command.py apps/api/tests/test_tag_resolve_batch_contracts.py
```

U29 등 병렬 변경을 통합한 뒤 전체 API 오프라인 회귀:

```powershell
$env:PYTHONPATH = 'apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL, Env:TEST_AUTH_DATABASE_URL, Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
$integratedTemp = 'tmp/it25-' + [guid]::NewGuid().ToString('N').Substring(0,6)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests -q -rs --tb=short --basetemp=$integratedTemp
```

## 수정 파일과 통합 시 주의점

- tag/repository.py: 정렬·중복 제거·500개 SQL 배치와 명시적 공유 잠금 조회 순서.
- tag/service/command.py: 목록 mapper 후 기존 검증·반환 순서 적용.
- tag/ARCHITECTURE.md: 배치 책임·트랜잭션·잠금 시점 변화·검증 한계.
- tests/test_tag_resolve_batch_contracts.py: 신규 SQL·정책·rollback 회귀 25건.
- tests/test_tag_management.py: 기존 3개 콘텐츠 도메인 fixture에 배치 저장소 대역 추가.
- 이 U25-TAG-WORKLOG.md: 전용 결과와 통합 명령.

공통 REPORT와 U25 통계 전용 기록은 이번에 수정하지 않았다. U29 완료 후 통합 담당자가
이 기록과 통계 범위·U29 결과를 모아 공통 상태를 반영하고 전체 API 회귀를 실행한다.
통계·LLM/메모리·발행 저장소·U19 개편과 기타 기존 변경을 함께 복원하거나 덮어쓰지 않는다.
