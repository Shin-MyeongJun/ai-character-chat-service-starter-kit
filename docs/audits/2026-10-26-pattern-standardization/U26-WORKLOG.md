# U26 보고 매퍼·타입 중복 재점검 (2026-11-02)

현재 코드에서 유지보수 실익이 확인된 항등 매퍼만 제거했다. 보고 영역 간 공개 타입과
명시적 필드 선택, JSON 깊은 복사, HTTP/Python/DB 계약은 유지한다.

## 현재 잔여 범위와 판단

| 대상 | 현재 상태 | 조치와 이유 |
| --- | --- | --- |
| creator/operations 지표·일별·작품 View와 매퍼 | 11개 지표와 작품 변환 구조가 비슷함 | 유지. 영역별 공개 타입과 노출 허용 목록을 독립적으로 소유한다. 공통 기반 타입·범용 매퍼는 현재 변경 이유에 비해 결합과 탐색 비용이 크다. |
| account 생성/usage 매퍼 | 예약 시각 코호트와 별도 usage 기록을 조합 | 유지. 작품 보고와 입력·지표·empty 의미가 다르다. |
| operations 프롬프트 View/DTO | 관리자 전용 목록·상세의 허용 필드를 선택 | 유지. 목록의 원문 제외와 상세 prompt=None, HTTP DTO 경계가 실제 역할이다. |
| core/reporting.py | 순수 기간·최신성 값과 날짜 검증 공유 | 유지. 도메인·영역별 변환을 core로 끌어올리지 않는다. |
| product/moderation scalar deepcopy | 과거 감사 이후 타입 정리에서 이미 제거됨 | 추가 수정 없음. 현재 남은 복사는 초안·발행 JSON, replacement_policy, 증거·첨부·signals·권고 등 가변값 격리다. |
| moderation.scalar_row_to_value | UUID 또는 None을 그대로 반환 | 제거. 호출 4곳에서 이미 값인 UUID를 직접 판단한다. |

원본 감사의 “reporting은 fields/getattr 방식” 설명도 현재는 과거 스냅샷이다.
지금은 creator/operations/account 매퍼 모두 구체적인 입력 타입과 명시적 필드 선택을
사용한다. 같은 필드를 가진다는 이유만으로 타입을 alias/상속으로 합치거나 다른 영역의
매퍼를 직접 호출하지 않았다. 새로운 공통 계층·파일 분리는 필요하지 않다.

## 변경과 보존한 계약

- `moderation/mapper/persistence.py`의 항등 함수와 전용 TypeVar/UUID import를 제거했다.
- `service/command/reports.py`, `assessments.py`, `actions.py`의 호출 4곳을
  `assessment_id`, `superseding_id`, `reversal_id`의 `is not None` 판단으로 바꿨다.
  해당 저장소 함수의 반환은 Row/Entity가 아닌 `UUID | None`이다.
- 조회 호출·순서, 대상 잠금·트랜잭션·SQL, 권한·멱등성·state_conflict 의미는 유지했다.
  Row/Entity 변환은 계속 mapper가 소유한다. 기존 U20 변경을 보존했다.
- 모듈 ARCHITECTURE.md에 scalar 값 처리 경계를 기록했다. 보고 타입·서비스·DTO,
  금액·날짜·상태·None/0, 기간 DISTINCT, 최신성·coverage는 변경하지 않았다.
- 기존 JSON 격리·업무 회귀로 검증 가능한 작은 정리여서 구현 배치를 검사하는 신규
  테스트는 추가하지 않았다. 타입/검사 예외와 기준선·공용 검사 설정도 추가하지 않았다.

## 검증

프로젝트 `.venv/Scripts/python.exe`(Python 3.12.14)를 사용했다.

```powershell
$env:PYTEST_ADDOPTS = '--basetemp=tmp/u26-quality-' + [guid]::NewGuid().ToString('N').Substring(0,8)
.venv/Scripts/python.exe tools/check_backend_quality.py
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_moderation_services.py apps/api/tests/test_moderation_services_db.py apps/api/tests/test_moderation_graph_db.py apps/api/tests/test_moderation_review_schema.py apps/api/tests/test_content_actor_routes.py apps/api/tests/test_reporting.py apps/api/tests/test_reporting_contracts.py apps/api/tests/test_reporting_db.py apps/api/tests/test_product_reporting_contracts.py apps/api/tests/test_generation_prompt_http.py apps/api/tests/test_generation_prompt_commands.py
```

| 검증 | 결과 |
| --- | --- |
| 필수 백엔드 품질 검사 | 종료 코드 0. 패턴 진단/예외 0건, Ruff format 396파일·lint 통과, mypy 375소스 통과, 아키텍처/패턴 13 passed |
| 위 11개 업무·보고·HTTP 테스트 파일 | **177 passed / 0 failed / 0 skipped** (30.71초) |
| 제거한 함수 참조·변경 파일 diff 공백 검사 | 앱 코드 참조 0건, git diff --check 통과 |

업무 검증에는 신고·평가·해제의 상태 충돌과 멱등/권한, JSON 중첩 격리 및 legacy 값,
U20 실제 PostgreSQL 잠금·rollback·취소가 포함된다. 보고 회귀는 영역별 인가와 소유권,
서울 날짜 경계, 비용/토큰 값, 미집계 None과 기록된 0, 기간 DISTINCT·pending/coverage,
읽기 전용 실행과 프롬프트 DTO·원문 노출 계약을 검증한다.

첫 업무 테스트 실행은 샌드박스의 로컬 소켓 접근 제한(10013)으로 출력 없이 대기하여
중단했다. 같은 명령을 승인된 실행으로 다시 실행해 전부 통과했다. runner는 기존
로컬 전용 감사 DB 설정을 확인하고 live 공급자 키를 제거하며 매번 새 basetemp를 쓴다.
DB 테스트는 기존 fixture의 UUID 스키마 생성/정리에 격리된다. 앱 DB migration이나
초기화, 컨테이너/볼륨 재생성, 실제 외부 공급자 호출은 수행하지 않았다.

이는 현재 미커밋 작업 트리의 관련 회귀 결과이며 전체 API 실행 결과는 아니다.
성능 부하 측정은 하지 않았으므로 처리량/지연 개선율을 주장하지 않는다. 실익은
변환 없는 함수·타입 변수·호출 4곳의 제거와 값 역할 명확화다. 기존 staged/unstaged
변경을 보존했고 commit/push는 하지 않았다. U26의 현재 정리는 완료했으며 새로운
필드·노출 정책이나 측정된 hotspot이 생기면 영역별 공통화 여부를 다시 판단한다.
