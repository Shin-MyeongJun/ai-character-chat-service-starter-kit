# U20 신고 그래프 잠금 범위와 순환·평가 충돌 방지

작성일: 2026-11-01 (Asia/Seoul)

## 변경

접수 상태 변경과 평가가 공유하던 `moderation.intake/graph` 전역 잠금을 기존
`moderation.target/{target_type}:{target_id}`로 통합했다. 같은 대상은 직렬화하고
다른 ID 또는 종류의 대상은 독립 진행한다. 기존 재평가/조치 잠금과도 일치한다.

- 접수 변경은 대상 식별용 비잠금 조회 후 대상 잠금, 신고 행 잠금 순으로 진행한다.
  다시 읽은 대상·접수 상태·평가 연결로 판단한다. 최초 조회는 잠금 키 선택에만 쓴다.
  대상 변경은 state_conflict, 삭제는 not_found로 거절한다.
- 평가는 정규화된 최대 100건의 근거 신고를 같은 대상 조건으로 일괄 잠금 조회한다.
  ID 순서와 populate_existing을 유지하며 mapper 이후 Info로 업무 판단한다.
  누락 ID는 타 대상 행만 추가로 비잠금 조회해 기존 not_found/invalid_link 구분과
  정규화된 신고 순서의 오류 우선순위를 유지한다.
- 잠금을 대상별로 나누면서 잘못된 요청이 타 대상 행까지 잠그면 중복 FK 갱신과
  교착할 수 있다. 해당 경로를 실제 DB에서 재현한 뒤 대상 조건을 추가했다.
  정상 평가의 조회는 1회이며 잘못된/누락 ID가 있는 경우 최대 2회다.
- 중복 체인은 다음 연결을 따라가며 순환·동일 대상·거절 여부를 검사한다.
  재평가 체인, 멱등 지문, legacy 확인, 기간 [start,end), 감사 로그 원자성은 유지했다.
  접수 대상 키 조회가 1회 늘어나는 대신 관련 없는 대상의 전역 대기가 사라진다.

저장소 연산은 기존 repository/review.py에, 업무 흐름은 기존 reports/assessments에
유지했다. 새 workflow나 범용 잠금 계층은 추가하지 않았다. 모든 쓰기는 기존
use_case_transaction에 참여하고 잠금은 최외곽 트랜잭션 종료 시 해제된다.

## 불변 조건과 적용 범위

신고 대상은 생성 후 서비스에서 변경하지 않는다. 대상 변경용 공개 함수/저장소 쓰기를
추가하지 않았으며 DB 불변 트리거를 새로 설치한 것은 아니다. 직접 SQL 유지보수는
업무 쓰기를 중단해야 한다. PostgreSQL 기본 READ COMMITTED에서 검증했다.

submit_report는 연결 없는 received 신고만 생성한다. 그래프 writer는 접수 변경과
평가 생성이고 둘 다 동일 대상 잠금을 획득한다. 조치는 기존 평가 대상 잠금을 유지한다.
목록/상세 조회는 표시용 읽기이고 자동 평가는 비활성이다. API/DB 스키마 변경은 없다.

구버전 접수 변경은 새 대상 잠금을 사용하지 않으므로 배포 시 기존 접수/평가 요청을
drain하고 모든 writer를 함께 교체한다. 구버전과 신버전을 혼용하는 실행은 지원하지
않는다. 이번 작업에서는 배포나 앱 DB migration을 실행하지 않았다.

## 검증

프로젝트 `.venv/Scripts/python.exe`와 준비된 전용 감사 테스트 DB를 사용했다.
Docker가 정지되어 최초 DB 회귀는 연결 거절(52 passed / 6 errors)이었다.
Docker Desktop을 시작한 뒤 기존 컨테이너가 healthy인 것을 확인했다. 컨테이너나
볼륨을 재생성하지 않았고 테스트는 UUID 스키마에 격리했다.

실행 명령:

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_moderation_services.py apps/api/tests/test_moderation_services_db.py apps/api/tests/test_moderation_graph_db.py apps/api/tests/test_moderation_review_schema.py apps/api/tests/test_content_actor_routes.py -s
.venv/Scripts/python.exe tools/check_backend_quality.py
```

검증 내용:

- 접수/평가의 네 조합 × 같은 대상/다른 ID/다른 종류. 같은 대상은 pg_stat_activity의
  실제 advisory 대기 및 pg_blocking_pids로 확인한다. 다른 대상은 holder commit 전에
  완료돼야 한다. 잠금 지속 시간을 임의 sleep으로 추측하지 않는다.
- 두 노드 상호 연결과 세 노드 간접 순환. 먼저 commit한 연결만 남고 후속 연결은
  invalid_link이며 실패 요청의 감사 기록도 남지 않는다.
- 평가→접수/접수→평가 두 순서에서 rejected/duplicate 모두 확인한다.
  평가가 먼저면 state_conflict, 접수가 먼저면 invalid_link다.
- 같은 접수의 재호출은 대기 후 최신 상태로 멱등 재사용/사유 충돌을 구별한다.
- 외곽 실패 및 실행 취소는 접수와 감사를 롤백하고, 대기 평가는 received를 읽는다.
- 교차 대상의 잘못된 근거 목록과 중복 부모 FK 경합을 거절하며 타 대상 행을 잠그지 않는다.
- 세션에 이미 적재한 신고 상태 갱신, 잠금 대기 중 대상 변경/삭제, 누락 근거 오류,
  기존 권한·멱등·재평가·조치·이관/제약·HTTP 가드 회귀를 확인한다.

최종 결과는 **89 passed / 0 failed / 0 skipped**다. 신규 그래프 DB 검증 28건,
대역 대상 재확인 3건, 기존 업무/DB/스키마/HTTP 가드 58건이다.
필수 백엔드 품질 검사는 종료 코드 0: 새 패턴 위반/기존 예외 0건,
Ruff format 394파일/check 통과, mypy 373소스 통과, 아키텍처/패턴 테스트 13 passed다.

## SQL 수와 기존 구현 비교

현재 작업 파일을 바꾸지 않고 테스트 프로세스에서 HEAD의 기존 command 함수를
로딩해 동일 fixture와 SQL 이벤트 계수로 비교했다. 집계는 초기 수동 평가 1회이며
BEGIN/COMMIT은 제외하고 executemany는 SQLAlchemy 실행 이벤트 1회로 센다.

| 근거 신고 수 | 기존 신고 SELECT | 변경 후 신고 SELECT | 기존 전체 SQL | 변경 후 전체 SQL |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 9 | 8 |
| 10 | 10 | 1 | 18 | 8 |
| 100 | 100 | 1 | 108 | 8 |

수정 전 구현은 다른 대상 접수가 holder commit 전에 완료되지 않아 5초 제한으로
실패했고, 새 일괄 조회 조건도 실패했다. 이 4건은 비교용 의도된 실패다.
중간 구현의 타 대상 행 잠금은 별도 FK 경합 테스트에서 대기 실패로 재현했고 보완했다.
운영 부하에서의 평균/상위 지연이나 처리량은 측정하지 않았다. 체인 길이에 비례하는
순차 탐색 비용도 그대로이며 이번 결과를 그 비용의 제거로 해석하지 않는다.

- [기존 구현 비교 로그](../../../tmp/u20-original-comparison.txt)
- [타 대상 잠금 회귀 재현](../../../tmp/u20-foreign-lock-before.txt)
- [최종 업무/실제 PG 검사](../../../tmp/u20-postgres-final.txt)
- [최종 백엔드 품질 검사](../../../tmp/u20-quality-final.txt)

기존 다른 작업의 staged/unstaged 변경과 품질 기준선/범위는 수정하지 않았다.
commit/push는 실행하지 않았다.
