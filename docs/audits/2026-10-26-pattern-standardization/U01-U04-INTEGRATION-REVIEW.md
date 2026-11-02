# U01·U04 완료 작업 통합 재검토

검토일: 2026-10-30 (Asia/Seoul)

현재 작업 트리와 두 WORKLOG, 실제 구현을 대조하고 관련 검증을 독립적으로 실행했다.
검토 범위에서 새 수정이 필요한 코드 결함을 발견하지 못했다. 전체 코드 전수 감사나
운영 공급자/브라우저/처리량 검증을 완료했다는 의미는 아니다.

## 확인한 구현

- U01: 답변 예산으로 필요한 prefix를 계산하고 summary_through_position을 실패 결과,
  예약·claim·worker 계획까지 전달한다. 일반 임계치 미만도 필요한 배치를 처리하고
  여러 배치·새 목표 병합·후속 세대 보존을 지원한다. 보호 원문 때문에 불가능한 경우는
  무진행 재시도로 남기지 않는다. U03 claim 토큰/저장 잠금과 U29 전체 기한을 유지한다.
- U04: 스튜디오 공개 잠금 조회와 직접 쓰기가 advisory → product → draft 순서를 사용한다.
  동일 digest 재시도·CAS 충돌·legacy 매핑/영수증·rollback을 유지한다. 매핑/영수증 쓰기는
  refresh 후 mapper에 전달하여 updated_at의 암묵적 비동기 조회도 방지한다.
- 앱 DB에 migration은 적용하지 않았다. U01의 새 Alembic head는 0032이며 배포 시 API와
  worker를 중지하고 필요한 migration을 적용한 후 함께 새 코드로 시작해야 한다.

## 이번에 직접 실행한 검증

| 검증 | 결과 |
|---|---|
| context_compaction, memory_compaction_migrations, studio_locking_db, memory_claim_fencing, memory_deadlines 5파일 | 66 passed / 0 failed / 0 skipped |
| 전체 API 오프라인 | 1483 passed / 0 failed / 346 skipped |
| check_backend_quality.py | Ruff 393파일 / mypy 372소스 / 13 passed / 기준선 0개 |
| 관련 staged/unstaged diff 공백 검사 | 통과 |

관련 실행에는 실제 PG 요약→저장→색인/검색→같은 입력의 새 답변 성공, 교착 대조 경로와
수정 경로, CAS·동일 문서 재시도, U03 fencing, 기존 deadline 회귀가 포함된다. 공급자만
대역이며 DB 테스트는 준비된 전용 감사 DB와 UUID 스키마를 사용한다. 66건 전체가 PG
경합 테스트인 것은 아니다. 오프라인 346 skipped는 passed에 포함하지 않는다.
실행 간 중복되는 테스트 건수는 합산하지 않는다.

기존 Alembic 설정 경고 4개와 전체 API의 Starlette 경고 2개가 있다.
로그: [DB/업무](../../../tmp/u01-u04-review-db.txt),
[전체 API](../../../tmp/u01-u04-review-api.txt),
[품질 검사](../../../tmp/u01-u04-review-quality.txt).

실행 명령:

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_context_compaction.py apps/api/tests/test_memory_compaction_migrations.py apps/api/tests/test_studio_locking_db.py apps/api/tests/test_memory_claim_fencing.py apps/api/tests/test_memory_deadlines.py
```

오프라인 전체 API와 품질 검사는 DB URL을 제거하고 새 workspace basetemp를 사용했다.
전체 API는 pytest_asyncio만 명시적으로 로드하고 공급자 키도 제거했다. Windows asyncio/DB
접근이 필요한 명령은 승인된 실행 권한을 사용했다. 앱 코드·공통 REPORT·검사 설정·기존
staged/unstaged 변경은 수정하지 않았다. 이 검토 기록만 추가했으며 commit/push는 없다.

## 다음 병렬 작업: U02 + U05

### U02 계정 전환 중 추가 페이지 응답 혼입

현재 recent-conversations.tsx의 첫 페이지 조회는 active/sequence를 확인하지만 loadMore는
계정 변경·새 조회·unmount 뒤에도 rows/cursor/error/loading을 갱신할 수 있다.

- 책임: apps/web/components/recent-conversations.tsx와 관련 프런트 테스트/문서.
- 동일 요청 세대/수명 검사를 추가 페이지의 성공·실패·finally 전체에 적용한다.
- 이전 계정의 지연 성공/실패, 새 계정의 첫 조회와 교차 완료, 로그아웃/unmount,
  연속 더 보기와 중복 요청을 제어된 응답 순서로 검증한다.
- 백엔드/공통 API 클라이언트의 계약·대화 DTO/페이지 정렬은 유지한다.
- 추천: GPT-6.1 Sol / High. 작업 범위에 따른 판단이며 모델별 실측 비교는 아니다.

### U05 답변 준비의 반복 전체 이력 조회·10,000개 상한

현재 답변 준비의 list_memory_source와 truncated 거절 경로가 남아 있다. U01은 필요한
요약 목표를 처리하지만 전체 이력 10,000개 초과의 최초 조회 거절을 해결하지 않는다.

- 책임: chatting/chat의 답변 준비·조회·repository와 필요한 memory 공개 인터페이스,
  해당 API 테스트/아키텍처/전용 WORKLOG. 프런트 변경은 분리한다.
- 단계별 실제 SQL·반환 행 수를 먼저 측정하고 미요약 범위·로어 검색에 필요한 범위·
  요약 이전 꼬리를 명시한다. 상한 숫자만 올리거나 전체 이력을 무제한 수집하지 않는다.
- preparation digest가 보호하는 runtime·모델 설정·참여자·snapshot·원문 변경 검증을
  보존한다. 단순 revision/current_message/snapshot 조합으로 임의 축소하지 않는다.
- 실제 PG에서 10,000개 초과 이력, 수정/되돌리기/append 교차, 같은 입력 재생과 U01
  요약 요청→진행, U03 fencing·U29 기한·과금 원자성을 검증한다.
- 추천: GPT-6 Astra / xHigh. 여러 단계의 조회와 변경 감지 계약을 함께 재설계해야 한다.

두 작업은 프런트 목록 수명과 백엔드 답변 이력 경로로 분리된다. 공통 REPORT/검사 설정을
동시에 편집하지 말고 전용 WORKLOG를 사용한다. migration이 필요하면 U05 한 작업에서
번호를 관리하고 실행마다 고유 basetemp를 사용한다. 두 결과가 모이면 전체 API·웹 검사와
품질 검사를 한 곳에서 통합 실행한다. U19는 기존의 전반 이미지 구조 개편 범위를 유지한다.
