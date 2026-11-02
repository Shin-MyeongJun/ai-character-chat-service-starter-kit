# U15 작업 기록 — 로어 v1 exact·regex 옵션 계약

작성일: 2026-10-29 (Asia/Seoul)

구현·범위 검증 완료. 후속 통합에서 전체 API **1337 passed / 0 failed / 288 skipped**를
확인했다. [U15-U25-INTEGRATION.md](U15-U25-INTEGRATION.md)에 최종 명령·한계를 기록하고
통합 단계에서 두 공통 REPORT의 상태를 반영했다. 아래는 U15 단독 작업 당시의 기록이다.

## 시작 상태와 경계

- AGENTS.md, 모듈 아키텍처·명명 규칙, 백엔드 코드 작성 규칙, 원본 감사 U15,
  패턴 표준화 REPORT의 최신 U14 기록, lorebook ARCHITECTURE.md를 읽었다.
- 시작 시 git status와 대상 파일의 unstaged/staged diff를 확인했다. activation.py와
  matching.py에는 기존 변경이 없었다. ARCHITECTURE.md의 기존 U06 후속 발행 기록은
  유지하고 활성화 책임·옵션 설명만 보완했다.
- 기존 staged/unstaged/untracked 변경을 복원하거나 덮어쓰지 않았다. reset/clean,
  commit/push, 별도 대화·서브에이전트를 만들지 않았다.
- 통계·태그 공통화·발행 저장소·공통 검사 설정 및 두 공통 REPORT.md를 수정하지 않았다.
  실행 로그와 테스트 임시 파일은 전용 tmp/u15-* 경로를 사용했다.

## 재현과 호출 경로

수정 전 새 exact/regex 회귀 48건을 먼저 실행했다. 결과는 **20 failed, 28 passed,
0 skipped, 23 deselected**였다. 당시 테스트 파일은 71건이었으며 이후 기본 옵션과
실제 HTTP 오류 경로 4건을 추가해 최종 75건이다. deselected는 통과에 포함하지 않는다.
재현 로그: [u15-regression-before.txt](../../../tmp/u15-regression-before.txt).

- v1 exact가 partial_match=True이면 부분 문자열, False이면 단어 경계 검색으로
  처리되어 prefix/suffix·공백·줄바꿈이 붙은 입력에도 일치했다.
- v1 regex는 case_sensitive=True여도 공통 matcher가 항상 (?i:pattern)으로
  컴파일하여 ABC가 abc에 일치했다. 캐시 키도 패턴 하나뿐이었다.
- 대화의 `conversation/service/command/context.prepare_runtime_context`는 고정
  LorebookSnapshotInfo와 activation_text/messages/manual ID를 공개
  `query.activate_snapshot_entries`에 전달한다. 이 함수와
  `query.diagnose_draft_entries`는 `activation.diagnose_entries`를 공유한다.
- 실제 `studio_diagnostics.diagnose_studio_lore`는 `studio_content.lore_entry_value`
  변환 후 도메인 초안 진단을 호출한다. 이 변환은 **contains를 생성**한다.
  따라서 도메인 exact/regex 진단 회귀와 실제 studio contains 회귀를 구분했다.
  studio에 새로운 match_mode 입력을 추가하지 않았다.
- 라이브 `query.activate_keyword_entries`는 독립 legacy 정책이다. metadata에 v1
  옵션이 있어도 해당 경로를 스냅샷 선택기와 통합하지 않았다.

## 변경 동작과 보존 계약

1. v1 exact는 기존 case_sensitive=False의 casefold 정책을 적용한 후 전체 문자열을
   비교한다. partial_match와 관계없이 접두·접미 입력은 불일치한다. trim이나 Unicode
   정규화를 추가하지 않는다. Straße/STRASSE의 기존 casefold 의미도 유지한다.
2. regex_matches에 기본 False인 keyword-only case_sensitive 옵션을 추가했다.
   내부 validator 캐시는 (pattern, case_sensitive)를 키로 사용한다. False는 기존
   scoped ignore-case flag, True는 원문 패턴으로 컴파일한다. 작성 검증은 기존 False
   정책을 사용하며 두 옵션의 캐시와 섞이지 않는다.
3. pydantic-core의 Rust 선형 시간 엔진과 최대 512개 LRU 캐시를 유지한다.
   regex 검색 의미, 패턴 자체의 플래그·앵커, 불일치 False 및 잘못된 패턴 예외 계약을
   유지한다. Python re는 기존 contains의 escaped 단어 경계 검사에만 사용한다.
4. 옵션 없는 legacy는 대소문자 무시 exact 전체 일치·contains 부분 문자열·regex
   검색, text 사용과 저장 순서를 유지한다. 라이브 query도 기존 정책을 유지한다.
5. 잘못된 패턴의 InvalidLorebookRegex(ValueError)와 고정 오류 문구를 유지한다.
   legacy 스냅샷/라이브 query의 Stored lorebook 오류 번역, v1 및 초안 작성 검증의
   원래 예외 전달, 공통 ValueError→422, 일반 lorebook HTTP의 고정 422 입력 오류를
   변경하지 않았다.
6. 키워드 any/all, 화자 필터 전 메시지 깊이 적용, 우선순위 내림차순/order·ID 오름차순,
   UTF-8 바이트 예산과 배타 그룹, 수동·비활성·시작·semantic 처리 및 깊은 복사를
   유지한다. 입력·metadata·스냅샷을 변경하지 않는다.

## 수정 파일

| 파일 | 책임 |
|---|---|
| apps/api/app/modules/content/lorebook/service/activation.py | v1 exact 전체 일치와 regex 옵션 전달 |
| apps/api/app/modules/content/lorebook/service/util/matching.py | 대소문자별 컴파일·캐시 키, legacy 기본값 |
| apps/api/app/modules/content/lorebook/ARCHITECTURE.md | 선택기/라이브 query 책임과 실제 studio 변환·오류 계약 |
| apps/api/tests/test_lorebook_activation_contracts.py | 신규 오프라인 회귀 75건 |
| docs/audits/2026-10-26-pattern-standardization/U15-WORKLOG.md | 전용 작업·검증·통합 기록 |

신규 회귀는 exact 전체/접두/접미/공백/줄바꿈/Unicode와 partial_match 양쪽,
regex 대소문자 조합·검색·앵커·기본값, 같은 패턴의 옵션 교차·legacy 작성 검증 캐시,
legacy 옵션 부재, 잘못된 패턴·lookbehind/backreference 거절, 실제 저장 HTTP 422,
스냅샷 text/messages와 초안 진단의 일관성, 입력/중첩 metadata 복사 격리,
키워드 any/all·깊이/화자·정렬/예산/배타 그룹, 라이브 legacy 정책과 studio contains를
확인한다. 실제 HTTP 오류 테스트는 작성 검증 전에 저장소 접근을 대체하지 않으며,
바인드 없는 AsyncSession에서 잘못된 패턴을 DB 접근 전에 거절하는 실제 서비스를 쓴다.

## 검증 결과

모든 Python 실행은 프로젝트 `.venv/Scripts/python.exe`를 사용했다. 업무·품질 검사
실행에서 TEST_DATABASE_URL과 TEST_AUTH_DATABASE_URL을 제거했다.

| 검증 | passed | failed | skipped | 결과 |
|---|---:|---:|---:|---|
| 변경 Python 3파일 Ruff format/check·직접 mypy | — | 0 | — | 통과, mypy 3소스 |
| lorebook·studio·기존 활성화 업무 9파일 | 236 | 0 | 3 | 신규 75건 포함 |
| 대화 command/query·프롬프트 기존 회귀 3파일 | 56 | 0 | 0 | 통과 |
| 위 업무 회귀 합계 | **292** | **0** | **3** | 서로 다른 12파일 |
| 필수 tools/check_backend_quality.py | 13 | 0 | 0 | Ruff 390파일, mypy 369소스, 타입 패턴 기준선 0개 |
| 변경 범위 git diff --check | — | 0 | — | 통과 |

업무 로그: [u15-business-final-tests.txt](../../../tmp/u15-business-final-tests.txt),
[u15-context-tests.txt](../../../tmp/u15-context-tests.txt).
품질 로그: [u15-backend-quality.txt](../../../tmp/u15-backend-quality.txt).
3 skipped는 test_repository_workflows의 PostgreSQL 통합 테스트이며 통과로 계산하지
않았다. 실제 저장 HTTP 검증의 경고 2개는 기존 Starlette 422 상수의 deprecation이다.

실행 중의 실패·제약도 보존한다.

- 최초 업무 묶음은 Windows 샌드박스의 asyncio 대기에서 출력 없이 멈춰 중단했다.
  동기 회귀 69건 통과를 확인한 뒤 승인된 오프라인 실행으로 같은 업무 묶음을 재실행했다.
- 추가한 실제 HTTP 테스트의 첫 경로를 /lorebooks/me/entries로 잘못 지정해 405 두 건이
  발생했다(234 passed, 2 failed, 3 skipped). 실제 POST /lorebooks/entries로 수정한 후
  최종 236 passed, 0 failed, 3 skipped를 확인했다. 제품 라우트는 변경하지 않았다.
- 전체 API는 이번 U15 범위에서 실행하지 않았다. U14의 1229 passed/288 skipped는
  이전 기준이며 이번 변경과 U25 통합 결과로 제시하지 않는다.
- 실제 PostgreSQL 경합·격리·실행 계획, DB migration/초기화/삭제 및 외부 공급자 요청은
  실행하지 않았다. 인가/저장 조회 경계 일부는 대역이며 실제 DB E2E 완료를 의미하지 않는다.
- Any/ignore/근거 없는 cast/기준선 예외를 추가하지 않았다.

## 재실행 명령

저장소 루트의 PowerShell에서 실행한다. 테스트 전용 basetemp를 다른 병렬 작업과
공유하지 않는다. 실행 도구에서 Windows asyncio 샌드박스 대기가 재현되면 이와 같은
오프라인 명령에 대해 실행 권한을 조정한다.

```powershell
$env:PYTHONPATH = 'apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL, Env:TEST_AUTH_DATABASE_URL -ErrorAction SilentlyContinue

.venv/Scripts/python.exe -m ruff format --check --config apps/api/pyproject.toml apps/api/app/modules/content/lorebook/service/activation.py apps/api/app/modules/content/lorebook/service/util/matching.py apps/api/tests/test_lorebook_activation_contracts.py
.venv/Scripts/python.exe -m ruff check --config apps/api/pyproject.toml apps/api/app/modules/content/lorebook/service/activation.py apps/api/app/modules/content/lorebook/service/util/matching.py apps/api/tests/test_lorebook_activation_contracts.py
.venv/Scripts/python.exe -m mypy --config-file apps/api/pyproject.toml apps/api/app/modules/content/lorebook/service/activation.py apps/api/app/modules/content/lorebook/service/util/matching.py apps/api/tests/test_lorebook_activation_contracts.py

$env:PYTEST_ADDOPTS = '--basetemp=tmp/u15-quality-tests'
.venv/Scripts/python.exe tools/check_backend_quality.py
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue

.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests/test_lorebook_activation_contracts.py apps/api/tests/test_lorebook_snapshot_activation.py apps/api/tests/test_lorebook_query.py apps/api/tests/test_lorebook_command.py apps/api/tests/test_lorebook_schema.py apps/api/tests/test_lorebook_http.py apps/api/tests/test_studio_type_contracts.py apps/api/tests/test_studio_validation_contracts.py apps/api/tests/test_repository_workflows.py -q -rs --tb=short --basetemp=tmp/u15-business-final-tests
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests/test_conversation_command_contracts.py apps/api/tests/test_conversation_query_contracts.py apps/api/tests/test_answer_prompt.py -q -rs --tb=short --basetemp=tmp/u15-context-tests

git diff HEAD --check -- apps/api/app/modules/content/lorebook/ARCHITECTURE.md apps/api/app/modules/content/lorebook/service/activation.py apps/api/app/modules/content/lorebook/service/util/matching.py apps/api/tests/test_lorebook_activation_contracts.py docs/audits/2026-10-26-pattern-standardization/U15-WORKLOG.md
```

U25 등 병렬 변경 통합 **후** 전체 API 오프라인 회귀 명령:

```powershell
$env:PYTHONPATH = 'apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL, Env:TEST_AUTH_DATABASE_URL, Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests -q -rs --tb=short --basetemp=tmp/u15-u25-integrated-api-tests
```

## 통합 시 주의점과 다음 병렬 후보

- U15 변경은 위 5파일이다. ARCHITECTURE.md의 기존 U06 수정과 기존 index/worktree
  변경을 포함해 보존한다. tmp 로그는 검증 근거이며 무관한 변경을 함께 정리하지 않는다.
- 공통 감사 REPORT 두 파일은 통합 담당자가 U15/U25 결과를 모아 갱신한다. 이번
  업무 통과 수에 U25 결과나 이전 전체 API 수를 합산하지 않는다.
- v1 exact의 결과 축소와 case_sensitive=True regex의 대소문자 구별은 의도한 수정이다.
  legacy 라이브 query를 함께 바꾸거나 studio에 exact/regex 노출을 추가하지 않는다.
- U25 진행 중 새 병렬 작업 후보는 **U23 로컬 저장소 reader/삭제 수명·키별 락 정리**와
  **U19 이미지 기본값/감정 태그의 예상 제약 충돌 번역**이다. 각각 test_local_storage
  어댑터와 character/service/media.py 중심으로 범위를 분리할 수 있다. U19는 새 기본
  이미지의 대체/거절 정책을 먼저 명시하고 동시 삽입 계약을 검증해야 한다. U23은 열린
  reader의 수명과 Windows 삭제 동작을 검증하며 공용 S3 변경으로 확대하지 않는다.
- U16 태그 공통화는 U25의 태그 해석·이름 잠금 범위와 겹칠 수 있으므로 동시 착수보다
  U25의 실제 변경 범위를 확인한 뒤 진행하는 편이 낫다. 추천만 기록하며 작업을 생성하거나
  다른 대화에 메시지를 보내지 않았다.
