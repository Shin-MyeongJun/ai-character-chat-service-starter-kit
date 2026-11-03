# U05 현재 구현과 통합 재검증 기록

작성: 2026-11-02 (Asia/Seoul). 최초 구현자의 기록이 누락돼 이번 통합 점검에서 현재
코드·기존 테스트·실제 실행 근거를 연결했다. 과거 작업 과정이나 운영 성능을 복원한 기록은 아니다.

## 현재 계약

- 답변 준비/예약 직전 검증은 conversation·참여자·runtime·모델·현재 입력과 DB history
  version을 비교한다. 원문 전체의 반복 직렬화 대신 변경 번호로 과거 메시지 변경을 감지한다.
- 로어는 최근 최대 100개, 답변 및 memory 원문은 position/토큰 예산으로 범위를 읽는다.
  기존 전체 목록 API의 10,000개 반환 계약을 바꾸지 않고 긴 대화의 답변/요약 진행을 분리한다.
- 메시지 INSERT/UPDATE/DELETE/TRUNCATE, metadata 변경·FK SET NULL·대화 이동에
  history version trigger를 연결하고 같은 트랜잭션 rollback을 보존한다.
- memory는 보호 suffix와 축약 prefix를 읽고 여러 배치의 후속 claim으로 목표를 처리한다.
  U01 축약 목표, U03 claim fencing, U29 전체 기한과 기존 원문 보존 정책을 유지한다.

구현 설명은 [chat 아키텍처](../../../apps/api/app/modules/chatting/chat/ARCHITECTURE.md)를 따른다.
이 기록에서는 업무 코드·공개 API·migration·처리량 정책을 변경하지 않았다.

## 확인한 테스트

`test_answer_history_windows.py`는 1,000/10,050개 이력의 실제 조회량 상한,
10,500개 미요약 이력의 여러 배치와 같은 입력의 후속 답변 성공, 준비 중 원문·모델·참여자·
runtime·스냅샷 변경 거절, 전체 이력 참조 결과와 범위 문맥의 동등성, 로어 최대 깊이를 검사한다.
`test_chat_history_migrations.py`는 0033의 기존 메시지 보존·변경 감지·rollback·
FK NULL 변경과 pending 중 downgrade 거절을 검사한다.

2026-11-02 전체 PostgreSQL 실행에 위 테스트를 포함했다. 과거
[U02·U05 검토](U02-U05-INTEGRATION-REVIEW.md)의 DB 접속 거부는 당시 결과로 보존한다.
최신 최종 집계·로그·작업 트리 기준은 [통합 점검](../../deployment-readiness-2026-11-02.md)을 따른다.
이번에 별도 성능 개선율·운영 처리량을 측정하지 않았다.

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_answer_history_windows.py apps/api/tests/test_chat_history_migrations.py apps/api/tests/test_context_compaction.py apps/api/tests/test_memory_claim_fencing.py
```

## 배포

Alembic 0033 / 초기 SQL 023의 trigger가 필요하다. 현재 전체 head는 **0036**이다.
API/worker를 멈추고 기존 DB에는 Alembic, 빈 DB에는 선택한 한 경로만 적용한 뒤
새 코드를 함께 시작한다. 이번 검증은 전용 로컬 테스트 DB의 UUID 스키마에서 실행했고
운영 DB/외부 공급자/실제 네트워크 장애/브라우저 긴 대화 E2E는 검증하지 않았다.
