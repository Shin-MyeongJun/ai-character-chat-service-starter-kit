# U02·U05 코드 확인과 다음 병렬 작업

검토일: 2026-10-31 (Asia/Seoul)

## 판단

U02의 요청 세대/수명 검사와 U05의 이력 범위 조회·변경 번호를 실제 코드에서 확인했다.
이번 코드 검토에서 새로 확정한 기능 결함은 없다. 다만 **U05의 실제 PG 재검증과 전용
작업 기록 확인이 남아 있으므로 두 작업 모두의 최종 통합 완료로 판정하지 않는다.**
다른 작업의 최초 구현/검증 결과를 이번 실행 결과로 인증하지 않는다.

U02-WORKLOG.md는 존재하지만 U05-WORKLOG.md는 검토 시점에 없었다. chat 아키텍처에는
이 파일을 참조하는 설명이 있으므로 구현 담당자의 측정·회귀·한계 기록 보완이 필요하다.
이번 검토 기록은 U05 구현자의 작업 기록을 대신하지 않는다.

## 코드에서 확인한 내용

- U02: 첫 조회/추가 페이지가 active·sequence·busy·cursor ref를 공유한다. 이전 세대의
  성공/실패/finally가 새 계정 상태를 갱신하지 않으며, 같은 렌더의 중복 요청도 차단한다.
  getMe 이후 재검사, effect cleanup, 페이지 병합·오류 재시도도 포함한다.
- U05: preparation의 전체 원문 digest 대신 conversation/participants/runtime/model/current
  값과 DB history version을 검증한다. 로어는 최근 최대 100개, 답변/worker 원문은 토큰
  예산에 따른 position 범위로 읽는다. 기존 전체 목록 API의 10,000개 계약은 유지한다.
- 0033/초기 SQL 023은 message INSERT/UPDATE/DELETE/TRUNCATE에 변경 번호를 갱신한다.
  변경 번호는 같은 트랜잭션에서 관리하고 rollback되며, 원문 revision 의미는 유지한다.
  worker는 prefix와 보호 suffix를 읽고 후속 claim으로 생략 범위를 남긴다. U01 목표,
  U03 claim token과 저장 잠금, U29 deadline 연결을 확인했다.
- 새 PG 회귀에는 10,050개 이력의 조회 행 수 제한, 10,500개 미요약 이력의 여러 배치와
  같은 입력 재시도, 준비 중 원문/모델/참여자/runtime/snapshot 변경, migration이 있다.
  테스트 소스 확인과 실제 DB 실행 성공은 구별한다.

## 이번 실행 결과

| 검사 | 결과 |
|---|---|
| 웹 전체 node 테스트 | 72 passed / 0 failed / 0 skipped |
| pnpm web:typecheck | 통과 |
| 전체 API 오프라인 | 1483 passed / 0 failed / 367 skipped |
| check_backend_quality.py | Ruff 394파일 / mypy 373소스 / 13 passed / 기준선 0개 |
| 관련 unstaged diff 공백 검사 | 통과 |
| U05/U01/U03 관련 DB 도우미 실행 | 3 passed / 0 failed / 46 setup errors / 0 skipped |
| 기존 답변·과금 DB 도우미 실행 | 0 passed / 0 failed / 41 setup errors / 0 skipped |

DB setup 오류는 모두 PostgreSQL 접속 거부였다. Docker Linux engine 파이프가 없었고
`docker desktop start --timeout 45`도 시작 시간 초과로 종료했다. 뒤이은 status/ps에서도
엔진 접근이 되지 않았다. DB 검증 통과 또는 코드 결함 재현으로 계산하지 않는다.
앱 DB migration/컨테이너 재생성/볼륨 삭제는 실행하지 않았다.

로그: [웹](../../../tmp/u02-u05-review-web.txt),
[웹 타입](../../../tmp/u02-u05-review-web-types.txt),
[API](../../../tmp/u02-u05-review-api.txt),
[품질](../../../tmp/u02-u05-review-quality.txt),
[DB 연결 실패](../../../tmp/u02-u05-review-db.txt),
[답변 DB 연결 실패](../../../tmp/u02-u05-review-answer-db.txt).
기존 Starlette 경고 2개가 있다. skipped·setup errors를 passed로 합산하지 않는다.
이번 웹 검증은 제어된 Promise/hook 대역이며 브라우저 E2E나 production build 재실행은 아니다.

## DB 복구 후 남은 검증

기존 Docker 엔진과 테스트 PostgreSQL이 준비되면 다음 명령을 재실행한다. 도우미의
전용 테스트 URL/계정/스키마 격리를 유지하고 앱 DB 계정으로 우회하지 않는다.

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_answer_history_windows.py apps/api/tests/test_chat_history_migrations.py apps/api/tests/test_context_compaction.py apps/api/tests/test_memory_claim_fencing.py
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_nonstream_answers.py apps/api/tests/test_answer_billing_integration.py
```

배포 전 head 0033과 필요한 0031/0032를 확인하고 API/worker 중지→migration→새 버전 함께
시작 순서를 따른다. 이번에는 앱 DB에 migration을 적용하지 않았다.

## 다음 병렬 추천: U20 + U22

1. **U20 신고 그래프 잠금 범위 개선** — governance/moderation 책임.
   현재 접수 변경과 평가가 모두 moderation.intake/graph 전역 잠금을 쓴다. 동일 대상은
   직렬화하고 다른 대상은 병렬 진행하도록 모든 reader/writer의 순서를 조사한다.
   target 불변성과 잠금 후 재검증을 확보하고, 중복 체인 순환·접수/평가 교차 실행을 실제
   PG에서 검증한다. 전역 잠금을 단순 삭제하지 않는다. 알려진 평가 대상의 일괄 조회와
   next_id를 따라가는 체인 조회를 구별한다. 추천 모델: GPT-6 Astra / xHigh.
2. **U22 인증 메일의 외부 응답·전송 경로 분리** — identity와 인증 메일 실행 책임.
   현재 존재하지 않는 대상은 즉시 반환하지만 실제 발송은 SMTP를 기다리고 장애를
   mail_unavailable/503으로 노출한다. 응답의 의미를 접수 성공으로 정하고 durable queue/
   Outbox, commit 뒤 전송, 제한된 재시도·운영 관측을 함께 설계/구현한다. 단순 예외 무시나
   고정 sleep으로 처리하지 않는다. 계정 유무/SMTP 지연·실패가 응답을 바꾸지 않는지,
   토큰 유효성·중복/재시도·rollback·로그의 비밀 제외를 대역과 PG로 검증한다.
   완전한 constant-time이나 메일 exactly-once를 주장하지 않는다.
   추천 모델: GPT-6 Astra / xHigh.

모델 추천은 작업 범위에 따른 판단이며 모델 간 실측 비교는 아니다. 두 도메인은 코드
경로가 분리된다. 공통 REPORT/품질 설정은 동시에 편집하지 않고 각 WORKLOG를 사용한다.
새 migration이나 main/worker 조립부가 필요하면 담당을 미리 나누고, U05의 0033을 보존한다.
DB가 준비되기 전에도 구현/오프라인 검증은 가능하지만 PG 경합 검증 완료로 표시하지 않는다.
U19는 사용자가 지정한 감정·상황·장면별 이미지의 전반 구조 개편 과제로 유지한다.

이 검토에서는 앱 코드와 기존 변경을 수정하지 않았고 이 기록만 추가했다.
공통 REPORT·검사 설정·commit/push·새 대화/서브에이전트 생성은 없다.
