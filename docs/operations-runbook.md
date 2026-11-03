# API·worker 배포 및 복구 절차

기준: 2026-11-02, Alembic head **0036**. 이 문서는 실행 절차이며 실제 운영 배포 기록이 아니다.
현재 Compose는 PostgreSQL·Redis·선택적 Mailpit만 제공한다. API, 웹, worker 서비스와
스케줄러·재시작·알림은 배포 환경에서 별도로 등록해야 한다.

## 배포 전 환경

- Python 3.12(.python-version), Node.js 22와 루트 packageManager에 지정한 pnpm을 사용한다.
- 아래 Python 명령은 저장소 루트에서 실행한다. `PYTHONPATH=apps/api`를 설정하고
  서비스 관리자가 환경변수를 주입한다. CLI와 기본 ASGI 진입점은 `.env`를 자동 로드하지 않는다.
- API와 모든 worker는 같은 DB를 사용한다. API와 mail worker는 같은 AUTH_JWT_KEY,
  AUTH_FLOW_KEY, 인증 origin/SMTP 설정을 사용한다. 키를 명령행·실행 로그에 출력하지 않는다.
- 운영은 HTTPS/Secure 쿠키와 올바른 proxy origin, 활성 관리자 권한, S3 저장소를 준비한다.
  `test_local`은 production에서 거절된다. mock 모델·가격을 운영 설정으로 가져가지 않는다.
- 승인한 BILLING_PRICING_CONFIG_PATH와 모델/provider 연결·사용자 크레딧이 필요하다.
  가격표가 없으면 신규 답변은 503이며 기존 답변 재생/복구와 구분한다.
- memory worker는 API와 일치하는 요약 모델·임베딩 모델/차원 및 공급자 키가 필요하다.
  기본 임베딩 저장 차원은 1536이다. timeout 240초 < lease 300초를 유지한다.

설정의 실제 계약은 [.env.example](../.env.example), [인증](authentication.md),
[가격 연결](billing-generation-integration.md), [메일 outbox](auth-mail-outbox.md)를 따른다.

## 중지·migration·기동

1. 대상 DB·백업·복원 경로와 배포 버전을 확인한다. 요청 유입을 멈추고 진행 중 작업을 drain한다.
2. 모든 API(내장 답변 복구 포함), memory/mail worker, 통계·정리 스케줄러를 중지한다.
   구/신 memory claim writer, 신고 writer, 답변 복구 admission 코드를 혼용하지 않는다.
3. **기존 DB는 Alembic**, 빈 DB는 Alembic 또는 초기 SQL 중 검증된 한 경로만 사용한다.
   초기화 SQL을 기존 DB에 재적용하지 않는다. 테이블이 있다는 이유만으로 stamp하지 않는다.

```powershell
$env:PYTHONPATH='apps/api'
.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini current
.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini heads
.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini current
```

4. 단일 head **0036**을 확인한다. 0031 claim token, 0032 축약 목표, 0033 메시지 변경
   trigger, 0034 mail outbox, 0035 pending 부분 인덱스, 0036 영속 복구 감사가 연결돼야 한다.
   신규 초기 SQL의 대응 끝은 **026**이다. 0035는 일반 인덱스 생성/삭제로 테이블 잠금을
   사용하므로 API/worker가 중지된 창에서 적용한다.
5. 같은 버전의 API·worker를 시작하고 아래 스케줄러와 프로세스 재시작 정책을 등록한다.
   프로세스별 stdout/stderr와 비정상 종료를 수집한다. 명령을 한 번 실행하는 것으로
   상시 서비스/예약 실행이 등록되지는 않는다.

```powershell
# 각각 독립 서비스로 등록한다. 같은 터미널에 순차 입력하는 실행 스크립트가 아니다.
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.venv/Scripts/python.exe -m app.memory_worker --concurrency 2 --poll-seconds 2
.venv/Scripts/python.exe -m app.auth_mail_worker
```

| 실행 | 운영 방식 | 확인할 의미 |
| --- | --- | --- |
| API 내장 answer recovery | lifespan 동안 15초 간격 | 별도 recovery daemon이 아니다. DB 장애 경고와 격리 잔량 관측 |
| memory_worker | 상시, 프로세스 감독/재시작 | claim UUID/lease, timeout < lease, 늦은 결과 거절 |
| auth_mail_worker | 상시, 프로세스 감독/재시작 | due claim → SMTP → ack, 최대 5회·120초 lease |
| auth_cleanup | 외부 스케줄러로 매시간 | 만료 계정/증명/세션·outbox 정리; 장기 메일 감사는 별도 보존 |
| product.statistics_job | 매시간, 야간 repair | 기본 최대 100개 날짜 처리; 잔량에 따라 후속 실행·용량 조정 |
| media_cleanup | 조사한 ID와 cutoff로 명시 실행 | 자동 bucket 순회·무조건 삭제가 아니다 |

```powershell
# 스케줄러에 각 명령을 등록한다.
.venv/Scripts/python.exe -m app.auth_cleanup
.venv/Scripts/python.exe -m app.modules.content.product.statistics_job --limit 100
# 야간 재집계 요청 + 처리
.venv/Scripts/python.exe -m app.modules.content.product.statistics_job --limit 100 --repair-recent
# 수동 GC 예시: 조사한 UUID와 시간대를 포함한 cutoff를 지정
.venv/Scripts/python.exe -m app.media_cleanup --media-id <UUID> --older-than <ISO8601-with-offset>
```

`memory_worker --once`와 `auth_mail_worker --once`는 현재 실행 가능한 작업을 소진하고
종료한다. 미래 backoff와 아직 유효한 lease는 남으므로 정기 재시도를 대체하지 않는다.
서비스 관리자는 종료 시 정리 시간을 주고 강제 종료 시 lease 만료/재선점을 관측한다.
SMTP 수락과 DB ack는 원자화되지 않으므로 동일 링크가 중복 발송될 수 있다.

6. 로그인/CSRF, 일반 사용자·비활성 관리자 차단, 작품 조회·대화·답변과 동일 키 재생,
   메일 도착·인증, memory/통계 큐 소진을 스테이징에서 확인하고 트래픽을 연다.
   API에는 전용 readiness endpoint가 없으므로 프로세스 기동이나 OpenAPI 응답만으로
   DB·키·가격표·worker 준비 완료를 판정하지 않는다.

## 관측과 장애 대응

원문·토큰·메일 주소 대신 작업/생성 UUID·상태·시도·고정 오류 분류를 수집한다.
메일의 due/만료 lease/failed 잔량과 안전한 SQL은 [메일 운영](auth-mail-outbox.md),
복구 격리 SQL과 수동 절차는 [답변 복구 정책](../references_document/reference/answer-recovery-policy.md)을 따른다.

```sql
SELECT status, count(*) AS jobs,
       count(*) FILTER (WHERE status = 'pending' AND next_attempt_at <= now()) AS due_jobs,
       count(*) FILTER (WHERE status = 'running' AND leased_until <= now()) AS expired_leases,
       min(updated_at) AS oldest_updated_at
FROM memory_jobs GROUP BY status;

SELECT count(*) AS dirty_days, min(requested_at) AS oldest_request
FROM product_stats_dirty_days;
```

- memory failed 증가, 만료된 running, due 적체는 공급자 설정/DB/claim/timeout을 조사한다.
  실패·claim 필드를 직접 고쳐 실행 예산을 초기화하지 않는다.
- 메일 failed/cancelled는 임의로 reopen하지 않는다. 사용자 재발송/재설정으로 새 증명을 접수한다.
  키 교체는 신규 접수 중지→기존 outbox 처리/만료→키 교체 순서다. key ring은 없다.
- 답변 격리는 pending·예약·staging을 보존한다. terminal 상태를 새 세션에서 확인하고
  원인 해결 후 operator/reason을 지정한 수동 retry만 사용한다. 새 request_key로 공급자를
  재호출하거나 강제 환불·격리 해제로 해결하지 않는다.
- 프로세스 반복 종료, 큐 대기 증가, lease 만료, failed/quarantine/claim_lost 증가를
  외부 모니터링에 연결한다. 저장소는 알림 전송과 운영 서비스 자동 등록을 제공하지 않는다.

## 롤백

API/worker/스케줄러를 다시 중지한다. 구버전과 새 writer를 섞지 않는다. 0031/0032는
진행 중 작업·목표, 0033은 pending 생성, 0034는 pending/processing 메일, 0036은 복구
감사/제어 이력에 따른 downgrade 거절 조건이 있다. 거절을 우회하거나 감사 기록을
삭제하지 않는다. 데이터 보존 조건을 확인해 수정 배포 또는 검증된 백업 복원으로 결정한다.
전체 migration을 무조건 downgrade하는 롤백 명령은 제공하지 않는다.

최신 실행 근거와 미검증 경계는 [통합 점검 기록](deployment-readiness-2026-11-02.md)을 따른다.
