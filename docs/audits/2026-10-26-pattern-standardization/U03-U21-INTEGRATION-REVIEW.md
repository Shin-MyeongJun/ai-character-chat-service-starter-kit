# U03·U21 완료 작업 재검토와 다음 병렬 작업

검토일: 2026-10-30 (Asia/Seoul)

현재 작업 트리의 U03 claim 소유권·결과 저장과 U21 공유 SAVEPOINT·잠금 재사용을
검토하고 독립적으로 통합 회귀를 실행했다. U18 추가 진단 변경도 현재 작업 트리에
포함되며 전체 오프라인 API 회귀 대상이다. 모든 감사 항목의 전수 재감사는 아니다.

## 검토 결과

- 검토 범위에서 새 수정이 필요한 코드 결함은 발견하지 못했다.
- U03의 완료/실패와 결과 저장은 동일한 claim 식별 조건을 사용하고, 결과 쓰기까지
  잠금을 유지한다. 기존 원문 검사·pending 요약 재사용·세대 보존 계약을 확인했다.
- U21은 같은 활성 트랜잭션/저장점/지갑에서만 잠금 근거를 재사용한다. 잔액은 다시
  읽으며 독립 호출과 중첩 실패의 rollback 계약을 관련 PG 회귀로 확인했다.
- 공통 감사 REPORT에는 U03 미완료 및 U25 태그 배치화 미완료라는 이전 기록이 남아
  있다. U03-WORKLOG.md와 U25-TAG-WORKLOG.md가 후속 구현 기록이다. 공통 REPORT를
  수정하지 않는 기존 경계에 따라 이번 검토에서도 직접 갱신하지 않았다.
- 앱 DB의 0031 적용은 별도다. U03 배포 시 구 worker를 중지하고 migration 후 새 worker를
  시작해야 한다. 외부 공급자의 정확히 한 번 호출을 보장하는 변경은 아니다.

## 이번에 직접 실행한 검증

| 실행 | 결과 |
|---|---|
| U03 fencing/migration + U21 scope/lifecycle + 답변 정산, 5파일 실제 PG | 67 passed / 0 failed / 0 skipped |
| 최신 전체 API 오프라인 | 1480 passed / 0 failed / 324 skipped |
| 필수 품질 검사 | Ruff 393파일, mypy 372소스, 13 passed, 타입 기준선 0개 |

신규 PG 테스트가 오프라인에서 skip되므로 이전 실행과 passed/skipped가 다를 수 있다.
위 실행은 서로 중복되는 테스트를 포함하며 합산하지 않는다. 전체 API의 기존 Starlette
경고 2개, PG migration 검사의 기존 Alembic 설정 경고 3개가 있다.

실행 로그: [DB](../../../tmp/u03-u21-review-db.txt),
[전체 API](../../../tmp/u03-u21-review-api.txt),
[품질 검사](../../../tmp/u03-u21-review-quality.txt).

DB 실행에는 기존 tools/run_postgres_audit_tests.py와 격리된 감사 DB를 사용했다.
오프라인 실행은 두 TEST_DATABASE_URL과 공급자 키를 제거하고 고유한 짧은 basetemp를
사용했다. 앱 DB/공통 검사 설정/기존 변경/commit은 수정하지 않았다.

## 다음 병렬 작업 추천

1. **U01 요약 요청 뒤 진행 불능 해결 (P1)**
   - chat의 답변 예산 판단과 memory의 요약 계획·예약·worker 전달을 추적한다.
   - 필요한 축약량과 최근 원문 보호로 축약 불가능한 경우를 구별한다. 단순 임계치 하향만으로
     완료하지 않는다. ASCII/한글/작은 문맥에서 요청→요약→같은 입력 재시도 성공을 검증한다.
   - U03 claim 토큰·잠금·revision 검증과 U29 전체 기한을 유지한다.
   - 수정 책임: chatting/chat, chatting/memory 및 해당 테스트/문서.
2. **U04 스튜디오 저장 잠금 순서 통일 (P2)**
   - use_cases/studio_components.save_studio의 revision 지정 경로와 product의 직접 draft
     저장 경로를 같은 순서로 맞춘다. 현재 product→draft 뒤 advisory를 얻는 경로와
     advisory→product→draft 경로가 공존한다.
   - 두 PostgreSQL 연결과 실행 장벽으로 교차 실행, CAS 충돌, 동일 내용 재시도 및 rollback을
     검증한다. advisory 잠금을 단순 삭제하지 않고 U06 재발행/U14 저장 계약을 유지한다.
   - 수정 책임: use_cases/studio_components, content/product의 studio 공개 서비스와 테스트/문서.

두 작업은 수정할 도메인과 코드 경로가 분리된다. 공통 REPORT·검사 설정을 동시에 편집하지
말고 U01/U04 전용 WORKLOG에 기록한다. migration이 필요하면 U01 담당자가 번호를 소유하고
U04는 불필요한 스키마 변경을 추가하지 않는다. PG fixture는 실행별 UUID 스키마를 사용한다.
완료 후 한 곳에서 전체 API·품질 검사를 통합 실행한다.

U05는 U01의 답변 준비/메모리 조회 경로와 겹쳐 같은 차수의 병렬 작업으로 추천하지 않는다.
U19는 사용자 지시대로 감정·상황·장면별 이미지를 포괄하는 전반 구조 개편 과제로 유지한다.
