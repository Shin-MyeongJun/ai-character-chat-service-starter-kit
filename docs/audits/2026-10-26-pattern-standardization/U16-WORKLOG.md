# U16 태그 정책 공통화 (2026-10-30)

## 변경과 경계

세 콘텐츠의 service/tags.py에 반복된 순수 업무 판단을 content/tag/service/policy.py로
추출했다. 기존 공개 Python 함수와 Command, HTTP 경로/응답/오류, DB 스키마는 유지한다.

- 공개 연결: 추가 시 기존 순서 뒤에 신규 ID를 중복 없이 붙인다. 교체는 요청 순서이며
  빈 교체는 전체 해제다. 기존 연결의 부여자/생성 시각 보존은 기존 저장소가 수행한다.
- 내부 연결: 삭제할 ID와 설정할 ID를 결정한다. 관리자는 시스템 연결을 인수·교체하며
  시스템은 관리자 지정 연결을 덮어쓰지 않는다. 정책의 시스템 교체 입력에도 관리자
  연결 보호를 적용하지만 기존 set_system_tags는 계속 추가만 수행한다.
- 내부 삭제: 시스템의 관리자 연결 삭제는 기존 ValueError 문구로 거절한다.
  없는 연결 삭제는 멱등이다.

공통 정책은 세션/ORM/콜백 없이 Command/Info와 UUID tuple만 받고 입력을 변경하지 않는다.
tag/types.py에 새 정책 Command 3개와 InternalTagChangesInfo를 추가했다. 기존 types는
변경하지 않았다. 업무 판단이므로 mapper나 내부 util 대신 공개 service/policy.py에 둔다.
공통 repository 프레임워크, 도메인 테이블 통합, router/mapper 추상화는 추가하지 않았다.

각 콘텐츠 서비스의 관리자 재검증·소유권/공개 접근·부모 FOR UPDATE·잠금 아래 기존 연결
조회·resolve·제거·설정·응답 재조회와 use_case_transaction 순서는 같다. 비활성 유지/신규
거절은 U25의 resolve_tags가 담당하며 이름 정규화·배치 SQL·이름순 잠금·입력 순서 반환은
수정하지 않았다. 도메인 간 접근 차이는 유지한다.

## 검증

프로젝트 .venv/Scripts/python.exe를 사용했다.

1. tools/check_backend_quality.py: 통과. 시그니처 진단 0건, Ruff format/check 통과,
   mypy 370 source files 통과, 아키텍처/패턴 검사 13 passed.
2. test_tag_policy.py, test_tag_management.py, test_tag_resolve_batch_contracts.py,
   test_tag_schema.py, test_tag_management_db.py: 72 passed / 11 skipped.
3. test_product_http.py, test_character_http.py, test_lorebook_http.py,
   test_product_studio_contracts.py, test_studio_publication.py, test_studio_draft_guard.py:
   63 passed.

신규 순수 정책 16건은 공개 추가/교체/비우기, 내부 선택/보호/인수/전체 해제,
삭제 보호·없는 연결 멱등·입력 비변경을 확인한다. 기존 3개 도메인 fixture에 2개 계약을
추가하여 6건으로 추가 시 기존 메타데이터/비활성 연결 보존, 빈 추가, 비활성 연결의
관리자 인수와 시스템 보호, 전체 해제 후 비활성 재연결 거절을 확인했다.

검증 명령(저장소 루트):

```powershell
$env:PYTEST_ADDOPTS='--basetemp=tmp/u16-quality-verified'
.venv/Scripts/python.exe tools/check_backend_quality.py
Remove-Item Env:PYTEST_ADDOPTS
$env:PYTHONPATH='apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.venv/Scripts/python.exe -u -m pytest -p pytest_asyncio.plugin -p no:cacheprovider --basetemp=tmp/u16-tags-unrestricted apps/api/tests/test_tag_policy.py apps/api/tests/test_tag_management.py apps/api/tests/test_tag_resolve_batch_contracts.py apps/api/tests/test_tag_schema.py apps/api/tests/test_tag_management_db.py -q --tb=short
.venv/Scripts/python.exe -u -m pytest -p pytest_asyncio.plugin -p no:cacheprovider --basetemp=tmp/u16-content-regression apps/api/tests/test_product_http.py apps/api/tests/test_character_http.py apps/api/tests/test_lorebook_http.py apps/api/tests/test_product_studio_contracts.py apps/api/tests/test_studio_publication.py apps/api/tests/test_studio_draft_guard.py -q --tb=short
```

로그는 tmp/u16-backend-quality-verified.txt, tmp/u16-tag-tests-final.txt,
tmp/u16-content-regression.txt에 있다. 최초 품질 검사는 기본 임시 폴더 생성 권한으로
2건 오류가 나서 workspace의 basetemp로 재실행했다. 샌드박스 비동기 테스트는
Windows asyncio의 socketpair accept 초기화에서 정지한 스택을 확인해 중단했으며,
같은 로컬 테스트를 제한 밖에서 실행한 결과를 위에 기록했다. 검사 설정·기준선·
예외를 늘리지 않았다.

TEST_DATABASE_URL 미설정으로 PostgreSQL 11건은 skip했다. 실제 PG 잠금/경합/격리·
FK·원자성을 검증한 결과가 아니다. 전체 API/브라우저 E2E는 이번 범위에서 실행하지 않았다.
기존 staged/unstaged 변경과 U25 구현을 보존했고 commit/push는 수행하지 않았다.
