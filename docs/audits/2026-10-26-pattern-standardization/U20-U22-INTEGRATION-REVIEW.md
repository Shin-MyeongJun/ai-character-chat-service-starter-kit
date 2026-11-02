# U20·U22 통합 재검토

검토일: 2026-11-02 (Asia/Seoul)

두 전용 WORKLOG와 현재 코드를 대조하고 검증을 독립 실행했다. 검토 범위에서 추가
수정이 필요한 코드 결함은 발견하지 못했다. 앱 전체 전수 감사는 아니다.

- U20은 최초 비잠금 조회를 대상 잠금 선택에만 사용하고 잠금 후 대상/상태를 다시
  확인한다. 평가의 근거 신고 조회는 동일 대상에 한정하여 타 대상 행 잠금을 피한다.
- U22는 HTTP에서 DB 접수만 확정하고 별도 실행이 claim commit → SMTP → ack를 수행한다.
  claim UUID/lease, 최대 횟수·만료 이전 재시도, terminal 암호문 제거를 확인했다.
  SMTP 중 DB 세션을 보유하지 않으며 외부 전송 exactly-once나 constant-time 보장은 아니다.

## 이번 독립 실행

| 검사 | 결과 |
|---|---|
| moderation_graph_db + identity_mail_outbox/worker/migrations | 118 passed / 0 failed / 0 skipped |
| 전체 API 오프라인 | 1554 passed / 0 failed / 417 skipped |
| 필수 품질 | Ruff 396파일·mypy 375소스·13 passed·기준선 0개 |

실제 PG는 준비된 감사 DB/UUID 스키마를 사용했다. 이번에는 로컬 SMTP Mailpit 통합을
재실행하지 않았으며 U22 작업자의 기존 305건/SMTP 실행을 이번 독립 실행으로 합산하지 않는다.
전체 오프라인 실행에는 기존 Starlette 경고 2개가 있다. skipped를 passed로 세지 않는다.

로그: [DB](../../../tmp/u20-u22-review-db.txt),
[전체 API](../../../tmp/u20-u22-review-api.txt),
[품질](../../../tmp/u20-u22-review-quality.txt).

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_moderation_graph_db.py apps/api/tests/test_identity_mail_outbox.py apps/api/tests/test_identity_mail_worker.py apps/api/tests/test_identity_mail_migrations.py
```

운영 적용은 별도다. U20 구/신 writer는 혼용하지 않고 요청을 drain한 뒤 함께 교체한다.
U22는 0034 적용과 별도 auth_mail_worker 배포, 동일 AUTH_FLOW_KEY/DB/SMTP 설정이 필요하다.
이번 검토에서 앱 DB migration·배포·외부 메일·commit/push는 실행하지 않았다.

## 다음 병렬 후보

- U17: chat 답변 복구의 pending/만료 조회를 데이터 분포별 EXPLAIN ANALYZE로 측정하고
  partial index와 종료 lease 정책을 검토한다. 이력 의미/재생/불확실 commit 복구를
  보존하며 근거 없이 lease를 지우지 않는다. 추천: GPT-6.1 Sol / High.
- U26: reporting 매퍼·타입 중복의 현재 잔여 범위를 먼저 재확인한다. 타입 정리 과정에서
  scalar deepcopy 일부는 이미 사라졌으므로 과거 감사대로 일괄 변경하지 않는다.
  JSON 가변값 격리를 유지하고 의미 없는 공통 계층/타 모듈 mapper 호출을 만들지 않는다.
  실익이 확인된 중복만 정리하고 보고 DTO·인가·금액/날짜 계약을 검증한다.
  추천: GPT-6.1 Sol / High.

두 작업은 chat 복구와 reporting 변환 경로로 나누고 각 전용 WORKLOG를 사용한다.
공통 REPORT/검사 설정은 동시 편집하지 않는다. U19는 전반 이미지 구조 개편 과제로 유지한다.
이 검토는 기존 변경과 앱 코드를 보존하고 이 기록만 추가했다.
