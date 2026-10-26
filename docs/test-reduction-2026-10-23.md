# 백엔드 테스트 축소 기록 (2026-10-23)

제품 코드·공개 API·테스트 검색 설정은 변경하지 않았다. 아래 수치는 작업 시작 시의
작업 트리와 비교했으며, 기존 staged/unstaged 변경은 보존했다.

| 항목 | 변경 전 | 변경 후 | 감소 |
| --- | ---: | ---: | ---: |
| 테스트 함수 정의 | 445 | 434 | 11 |
| pytest 수집 케이스 (매개변수 확장 포함) | 823 | 787 | 36 |
| `apps/api/tests` Python 코드 줄 (fixture·보조 코드 포함) | 19,973 | 19,744 | 229 |
| `test_*.py` 파일 | 76 | 75 | 1 |

처음 예상했던 50~80개 함수 삭제는 강제하지 않았다. 프롬프트의 command/workflow
검사는 실제 DB 검사가 건너뛰어지는 환경에서도 실행권·원문 불변성·예약 검증·저장 실패·
commit 응답 유실을 확인한다. 이러한 검증과 모든 프롬프트 DB/마이그레이션 검사는 유지했다.

## 삭제 근거와 남긴 검증

아래 파일은 모두 `apps/api/tests/` 아래에 있다. 단순 전달 검사는 동일 동작을 완전히
대체하는 테스트가 있다고 주장하지 않고, 별도 유지할 업무 판단이 없는 검사로 구분했다.

| 삭제한 테스트 | 근거 및 남긴 검증 |
| --- | --- |
| `test_architecture_contracts.py::test_openapi_contract_is_unchanged` | 파일명으로 router를 탐색해 가상 앱을 구성하고 같은 기준 JSON을 비교하던 검사. `test_assembled_routes_preserve_the_same_openapi_contract`가 실제 `create_app()`의 계약을 한 번 비교하도록 변경했다. 인증 경로와 기존 경로·스키마 비교를 보존했다. |
| `test_architecture_contracts.py::test_moved_implementations_have_no_old_compatibility_copies` | 과거 파일 이름의 존재 여부를 고정하는 일회성 이전 검사. 모듈 공개 경계·ORM 접근·mapper 순수성·workflow 의존 방향 검사는 유지했다. |
| `test_product_http.py::test_product_and_conversation_contracts_are_registered` | 경로 등록은 실제 앱 OpenAPI 검사가 보호한다. 위조 owner 요청에 단지 `!= 201`을 요구하던 검사는 `test_product_draft.py::test_unconfigured_identity_fails_closed`의 명시적인 503 검사와 `test_product_boundaries.py::test_composition_adapter_maps_nested_commands_and_rejects_extra_fields` 등의 인증 주체·필드 주입 검사로 대체된다. 이 파일만 삭제했다. |
| `test_lorebook_schema.py::test_static_me_routes_are_registered_before_uuid_routes` | OpenAPI 경로 순서보다 실제 라우팅 동작을 검사하는 `test_content_actor_routes.py::test_owner_path_is_not_captured_by_admin_uuid_path`를 유지했다. 이 검사는 `/lorebooks/me`의 성공, 관리자 가드 거절, owner 전달과 관리자 조회 미호출을 확인한다. |
| `test_lorebook_schema.py::test_cursor_mapper_preserves_valid_cursor` | cursor 두 필드를 값 객체로 옮기는 단순 변환 검사. 불완전한 cursor/시각대 거절 검사와 실제 SQLite 목록의 cursor 동률·owner 범위 검사는 유지했다. 정상 cursor mapper의 독립 검사는 종료했다. |
| `test_lorebook_query.py::test_entry_page_forwards_parent_cursor_and_limit` | repository 대역에 같은 parent/cursor/limit를 전달하는지 확인하는 단순 전달 검사. owned entry 목록의 부모 권한 확인, entry 조회의 parent 범위와 소유권 거절 검사는 유지했다. 이 전달 함수의 임의 cursor/limit 인자 조합에 대한 독립 검사는 종료했다. |
| `test_generation_prompt_http.py::test_reporting_view_is_detached_and_credential_free` | 입력 dataclass를 다시 dataclass로 변환해 비교하는 검사이며, 이름과 달리 변경 격리는 검사하지 않았다. 실제 HTTP 목록의 민감 필드 비노출, 상세 원문·digest·형식 버전, 비관리자·비활성 계정·미인증 차단 검사는 유지했다. |
| `test_moderation_services.py::test_all_new_module_functions_have_korean_docstrings` | 함수 설명문의 한국어 포함 여부만 검사하며 기능·권한·저장 계약은 검증하지 않는다. 신고·평가·조치·증거 보존·인가·DB 검사는 모두 유지했다. |
| `test_nonstream_answers.py::test_http_to_postgres_returns_one_persisted_answer` | 같은 DB fixture를 요구하는 `test_first_answer_integration.py::test_signup_to_first_answer_and_completed_replay`가 실제 앱의 HTTP 답변과 재요청, 신규 세션의 저장 결과, 단일 공급자 호출까지 검증한다. DB 없는 HTTP 상태/인증 검사도 유지했다. |
| `test_nonstream_answers.py::test_cancel_releases_pending_and_does_not_repeat` | 같은 `setup_answer`로 취소 후 재호출과 호출 횟수를 검사하는 `test_answer_billing_integration.py::test_cancel_is_atomic_release_and_cannot_be_reexecuted`를 유지했다. 기존 검사에만 있던 `uncertain` 검증을 그 테스트에 옮겼다. 잔액·예약 해제·청구 검증도 보존된다. 두 검사는 모두 PostgreSQL 환경을 요구한다. |
| `test_product_expiry.py::test_administration_requires_active_admin` | 같은 `require_admin` 정책의 활성 일반 사용자·정지 관리자 거절은 DB 없는 `test_generation_prompt_http.py::test_nonadmin_and_inactive_admin_cannot_reach_chat_queries`가 실제 HTTP와 query 미호출까지 검증한다. 직접 query 공개 경계의 관리자 검증 테스트도 유지했다. |

`test_reporting_import_boundaries_and_korean_function_docs`는 설명문 언어 검사만 제거하고
`test_reporting_import_boundaries`로 이름을 바꿨다. reporting 영역 간 참조·ORM 접근·
core 역참조 금지는 그대로 검사한다. 함수 수 감소에 이 이름 변경을 포함하지 않았다.

## 중복 입력 조합 축소

공유 validator의 모든 실패 조건은 남기고, 생성과 수정에 동일 표를 전부 반복 적용하던
교차 조합을 줄였다. 수정 경로에서도 대표 실패 입력의 쓰기 차단과 rollback을 확인한다.

| 검사 | 변경 전 케이스 | 변경 후 케이스 |
| --- | ---: | ---: |
| 캐릭터 profile validation | 6 | 4 |
| 로어북 profile validation | 8 | 5 |
| 로어북 entry validation | 32 | 17 |
| 스튜디오 각 section의 공통 tag validation | 9 | 5 |

이렇게 24개 조합을 줄였다. 나머지 12개 케이스는 함수 11개 삭제에 따른 감소다.
프롬프트 workflow에서는 전체 내부 이벤트 배열 일치 대신 저장 시 트랜잭션 활성 상태,
외부 호출 전 commit·트랜잭션 종료, 저장 실패 rollback, 외부 호출 차단을 검사한다.
commit 응답 유실 테스트는 정상 트랜잭션을 끝낸 후 응답 유실을 발생시키도록 맞췄다.

## 실행 결과와 공백

- 변경 전 전체 실행: **529 passed, 290 skipped, 4 failed**.
- 변경 후 전체 실행: **498 passed, 288 skipped, 1 failed** (13.30초).
- catalog 테스트의 오래된 snapshot fixture 구조와 studio publication 테스트의 제거된
  `ProductQuery` Mock 참조를 정리해 기존 실패 3개를 수정했다. 테스트를 삭제해 없앤 실패는 없다.
- 남은 실패는 변경하지 않은 `test_studio_draft_guard.py::test_edit_after_first_publication_does_not_change_product_visibility`다.
  기존 fixture에 `product_id`가 없어 persistence mapper에서 `AttributeError`가 발생한다.
  해당 테스트를 삭제하거나 기대 정책을 바꾸지 않았다.
- `TEST_DATABASE_URL`이 없고 Docker Desktop 엔진에 연결되지 않아 PostgreSQL 검사는
  실행되지 않았다. 그 밖에 인증 DB·S3·Voyage 등 외부 환경을 요구하는 기존 skip도 남는다.
  삭제한 중복 DB 시나리오 2개 때문에 skip 수가 290에서 288로 감소했다.
- Ruff의 미사용 import·중복 정의·미정의 이름 검사(`F401,F811,F821`)는 통과했다.
  전체 규칙 검사는 기존 진단 46개에서 44개로 줄었으며, 작업 전 파일 내용과 비교한 신규 진단은 0개다.
- `git diff --check -- apps/api/tests`는 통과했다.

전체 실행 명령 (PowerShell):

```powershell
$env:PYTHONPATH = 'apps/api'
& .venv/Scripts/python.exe -m pytest apps/api/tests -q -p no:cacheprovider --basetemp=tmp/test-reduction-final-20261023 --tb=short -ra
```

최종 로그: `tmp/test-reduction-final-20261023.log`.
`--basetemp`는 기존 디렉터리를 재사용하지 않고 새 경로로 지정한다.
