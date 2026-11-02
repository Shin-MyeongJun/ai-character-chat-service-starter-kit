# U01 답변 예산과 요약 진행 보장

작업일: 2026-10-30 (Asia/Seoul)

## 원인과 변경

답변은 최종 문맥의 원문 UTF-8 바이트+32를 예약하지만 일반 요약은 role 포함
UTF-8 /4의 4,000 임계치로 실행한다. 이 때문에 ASCII 800자 11개처럼 답변 예산은
초과하면서 일반 요약 임계치는 넘지 않는 이력이 무진행 상태가 된다.

답변의 실제 가용 예산과 최근 원문 보호를 함께 평가해 필요한 축약 범위를
`summary_through_position`으로 계산한다. 오류 → 실패 답변 metadata → DB 큐 →
claim → 배치 계획까지 목표를 전달하며 임계치 미만에서도 목표를 처리한다.
한 배치로 부족하면 완료 후 다음 claim을 남겨 목표에 도달한다. 일반 예약의
임계치·배치 크기와 원문 보존 정책은 유지한다.

실행 중 새 목표는 최댓값으로 병합하고 세대/claim fencing을 유지한다. 일반
예약이나 더 작은 목표가 기존 목표를 지우지 않으며, 실패/재claim/후속 배치에서도
보존한다. 보호 원문만으로 예산이 넘으면 비재시도 오류로 명시하고 요약 작업을
예약하지 않는다. 워커에서 목표가 보호 범위와 충돌하면 idle 대신 failed다.
U03 저장 잠금·claim 토큰·원문 revision/digest와 U29 전체 처리 기한을 유지한다.

## 검증 범위

- 실제 PostgreSQL의 API 업무 서비스 → 영속 큐 → 요약 생성 → 요약 저장 →
  pgvector 색인/검색 → 동일 입력의 새 답변 요청 성공을 연결한다.
- ASCII, 한글, 작은 이력 예산/여러 배치, 큰 고정 프롬프트 네 경우 모두 검사한다.
- 최종 prompt가 응답 예약과 함께 한도 안에 있고, 요약 본문을 포함하며, 최근 원문과
  현재 입력을 보존하고, 사용자 메시지를 중복 저장하지 않는지 확인한다.
- 외부 텍스트/임베딩 호출만 대역이다. 실 공급자·브라우저 E2E 검증은 포함하지 않는다.
- 기존 실패 답변 키는 저장된 결과를 재생한다. 재시도는 같은 입력 ID/revision과
  새 답변 키를 사용하며, 실제 답변 텍스트 호출은 한 번이다.

## 최종 실행 결과

| 검사 | 결과 |
| --- | --- |
| 실제 PG 10파일: U01, migration, 기억, U03 fencing, U29 deadline, 답변·과금·prompt, 전체 스키마 비교 | 118 passed / 0 failed / 0 skipped |
| 전체 API 오프라인 | 1483 passed / 0 failed / 346 skipped |
| 필수 backend quality | Ruff 393파일 / mypy 372소스 / 13 passed / 타입 기준선 0개 |

요청한 완료 조건:

- [x] ASCII·한글·작은 문맥·큰 고정 문맥에서 `summary_required` 실제 발생
- [x] 영속 목표 claim 후 실제 요약 저장·색인, 필요한 여러 배치 수행, 최종 idle
- [x] 같은 사용자 입력으로 새 답변 요청 성공, 최종 프롬프트 한도·요약 포함·원문 보존 확인
- [x] 보호 원문으로 불가능한 답변은 비재시도 결과, 워커의 불가능 목표는 failed
- [x] 더 큰/작은/일반 예약 병합, 재claim, 실패 재시도, 오래된 완료, 후속 세대 목표 보존

로그: [PostgreSQL 회귀](../../../tmp/u01-db-regression.txt),
[전체 API](../../../tmp/u01-api-regression.txt),
[필수 품질 검사](../../../tmp/u01-quality.txt).
PG 검증의 기존 Alembic 설정 경고 7개와 전체 API의 기존 Starlette 경고 2개가 있다.
서로 중복되는 테스트를 포함하므로 실행 건수는 합산하지 않는다.

프로젝트 `.venv/Scripts/python.exe`와 기존 `tools/run_postgres_audit_tests.py`를
사용했다. 이 도구는 전용 localhost 감사 DB만 허용하고 테스트별 UUID 스키마를
생성·제거한다. 오프라인 실행에서는 두 DB URL과 공급자 키를 비웠다. Windows
비동기 이벤트 루프/DB의 로컬 소켓 접근 때문에 테스트 실행은 샌드박스 밖에서
수행했고, 품질 검사는 고유한 workspace basetemp로 실행했다.

프런트의 기존 재시도 경로도 확인했다. `apps/web/app/chats/[id]/page.tsx`는 재시도
가능 실패에서 저장된 `message`를 유지하고 `answerKey`만 새 UUID로 바꾼다. 이번
업무 서비스 통합 검증은 같은 계약을 사용하며 프런트 코드는 변경하지 않았다.

## 스키마와 적용

Alembic `0032`와 신규 DB 초기 SQL `022_memory_summary_target.sql`을 추가했다.
기존 작업은 NULL 목표로 보존한다. API/worker를 중지하고 migration 후 새 버전으로
함께 시작해야 한다. 실행 중 작업 또는 목표가 남은 경우 downgrade는 거절한다.
이번 작업은 격리된 감사 DB에서만 검증하며 앱 DB migration은 수행하지 않는다.

공통 감사 REPORT와 품질 기준선/검사 범위 설정은 수정하지 않는다.
