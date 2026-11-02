# 인증 메일 Outbox와 운영

U22는 가입·인증 재발송·비밀번호 재설정 요청에서 SMTP 호출을 제거한다. 정상 입력과 요청 제한을 통과한 요청의 **202는 접수 성공**이다. 대상 계정 유무·자체/Google 계정·인증/정지 상태·SMTP 지연/장애는 응답 상태, 본문, 쿠키 또는 보안 헤더로 알리지 않는다. DB 저장 오류는 전파하며, 전송 성공으로 위장하지 않는다. DB 작업량과 잠금 경합 등에 따른 시간 차이까지 같게 만드는 설계는 아니다.

## 저장과 실행

1. 기존 계정/증명 정책에 따라 필요한 경우만 `auth_action_tokens`와 `auth_mail_outbox`를 같은 트랜잭션에 저장한다. Outbox 저장 또는 commit 실패는 신규 계정·증명·기존 증명 무효화까지 함께 rollback한다. 이메일/IP 요청 제한은 기존 별도 트랜잭션으로 유지된다.
2. 요청 처리 중 SMTP나 메모리 BackgroundTask를 실행하지 않는다. commit 뒤 API 프로세스가 종료돼도 작업은 DB에 남는다. 기존 내부 `register_pending_user`/`prepare_action_mail`의 ActionMailInfo 반환은 유지하지만 HTTP 경로에서는 사용하지 않는다.
3. 별도 워커는 `FOR UPDATE SKIP LOCKED`로 실행 시각이 지난 pending 또는 lease가 만료된 processing 한 건을 가져온다. 시도 횟수를 증가시키고 새 claim UUID와 120초 lease를 commit한다. 프로세스당 SMTP 동시성은 1이며 여러 워커가 함께 실행할 수 있다.
4. 선점 트랜잭션에서 증명의 미사용·미만료, 계정의 active·자체 비밀번호·용도별 인증/대기 상태를 재확인한다. 재발송으로 무효화된 이전 증명, 사용된/만료된 증명, 삭제·정지·부적격 계정은 발송하지 않는다. 사용자·토큰을 읽을 때는 쓰기 잠금을 요청하지 않아 기존 사용자→토큰 쓰기 순서와 역순 교착을 만들지 않는다.
5. DB 세션과 잠금을 닫은 뒤 SMTP를 호출한다. 결과 저장은 processing·claim UUID·유효 lease를 다시 잠가 검증한 뒤 수행한다. 만료된 워커의 늦은 성공/실패는 새 워커 상태를 덮어쓰지 않으며 `claim_lost`로 기록한다.

HTTP 접수 workflow와 발송 workflow는 같은 파일에서 조율하고, DB 상태 전이·재시도 정책은 `MailDeliveryService`로 분리한다. repository는 SQL만, persistence mapper는 이미 읽은 값을 Info로 바꾸는 일만 맡는다. 신규 공개 실행은 `claim_mail() → MailDeliveryInfo | None`, `complete_mail(CompleteMailDeliveryCommand) → bool`, `deliver_next_mail() → bool`이다. bool은 각각 유효 선점 결과 반영/현재 작업 처리 여부이며 SMTP 수신함 도착 보장이 아니다.

## 재시도와 중복

| 상황 | 동작 |
| --- | --- |
| 연결 오류·SMTP 4xx | pending으로 되돌려 30/60/120/240초 지연 + 최대 25% jitter |
| SMTP 5xx·영구 수신 거절·TLS 기능 미지원 | failed, 자동 재시도 없음 |
| 최대 5회 시도 소진 | failed. SMTP 호출 전 워커가 종료된 선점도 시도에 포함 |
| 다음 실행 시각이 증명 만료 이후 | cancelled, 더 이상 시도하지 않음 |
| 잘못된/다른 키의 암호문 | failed / payload_invalid, 내용은 출력하지 않음 |
| 워커 취소·예상하지 못한 오류·결과 commit 실패 | processing 유지, lease 만료 뒤 회수. 예상하지 못한 오류는 CLI 오류 종료 후 운영 감독자가 재시작 |

`sent`는 SMTP 호출이 성공했다는 의미다. 수신 서버의 최종 배달이나 사용자의 수신함 도착은 확인하지 않는다. SMTP 수락과 결과 commit을 원자화할 수 없으므로 **중복 전송이 가능**하다. 같은 증명 해시의 Outbox는 하나이며 재시도는 같은 링크를 보낸다. 재시도 때문에 새 토큰을 만들거나 만료를 늘리지 않는다. 실제 토큰 소모는 기존 조건부 UPDATE로 한 번만 성공한다.

SMTP 호출에는 기존 소켓 작업별 10초 timeout이 있다. 전체 메시지 전송 시간 제한이나 lease heartbeat는 없으므로 느린 연결 또는 프로세스 정지로 lease를 초과하면 다른 워커가 같은 링크를 보낼 수 있다. 워커 취소가 실행 중인 SMTP 스레드/외부 수락을 취소하는 것은 아니다. 재발송·비밀번호 변경·계정 상태 변경이 선점 후 일어나면 이미 전송 중인 구 링크가 도착할 수 있으나, 증명 사용 시점의 검증에서 거절된다. exactly-once나 지연 없는 도착을 주장하지 않는다.

## 비밀값과 보존

증명 저장소는 계속 SHA-256 해시만 저장한다. Outbox는 재전송용 토큰을 `AUTH_FLOW_KEY`의 Fernet 인증 암호화로 단기 보관한다. 인증된 `auth-mail-v1:` 접두사로 OAuth 쿠키와 구분하고, 복호화 후 증명 해시를 비교해 다른 행의 암호문 치환을 거절한다. 수신 주소·비밀번호·메일 본문·전체 링크는 Outbox에 별도로 저장하지 않는다.

sent/cancelled/failed 전환 시 암호문을 NULL로 지운다. 만료 증명을 삭제하는 기존 매시간 `app.auth_cleanup`에서 Outbox도 FK CASCADE로 삭제된다. 따라서 결과 행 자체는 장기 감사 기록이 아니며, 운영 지표는 별도로 보관해야 한다. DB 백업 암호문과 암호키는 별도로 접근 통제한다. API와 워커는 동일한 `AUTH_FLOW_KEY`를 사용해야 한다. 키 교체 전 신규 접수를 중단하고 기존 작업을 처리하거나 증명 만료·정리를 기다린다. 이전 키를 읽는 key ring은 구현하지 않았으며, 교체 후 남은 작업은 payload_invalid가 될 수 있다. 로그에는 작업 UUID·상태·시도 횟수·고정 오류 분류만 기록한다. SMTP 원문 예외/예외 체인·토큰·수신 주소를 출력하지 않는다.

## 배포와 복구

1. 기존 DB는 API/워커 배포 전에 `PYTHONPATH=apps/api`와 DB 환경변수를 주입하여 `python -m alembic -c apps/api/alembic.ini upgrade head`를 실행한다. 신규 `0034`는 테이블/인덱스만 추가하며 기존 계정·세션·증명은 보존한다. 이전에 발급된 증명에는 평문이 없으므로 메일을 소급 큐잉하지 않는다. 새 DB 초기 SQL은 `024_auth_mail_outbox.sql`이다.
2. API와 별도로 **상시 워커**를 실행한다. 동일한 DB·인증 키·public origin·SMTP 환경변수가 필요하다. 아래 명령 자체는 `.env`를 자동 로드하지 않는다. 서비스 관리자에서 환경을 주입해야 한다.

```powershell
$env:PYTHONPATH='apps/api'
.venv/Scripts/python.exe -m app.auth_mail_worker
```

3. `--once`는 현재 실행 가능한 작업을 처리하고 종료한다. 미래 backoff/아직 유효한 lease 작업은 남기므로 재시도 운영에 이 명령을 한 번만 실행해서는 안 된다. 상시 실행을 권장한다. 서비스 관리자의 재시작 정책을 설정하고 기존 정리 CLI는 매시간 실행한다. 이 저장소가 운영 스케줄러나 서비스를 자동 등록하지는 않는다.
4. SMTP 복구 후 pending은 자동 재시도한다. failed/cancelled는 기존 작업을 임의로 다시 열지 않는다. 사용자가 기존 인증 재발송/재설정 요청으로 새 증명을 발급받도록 한다. 계정별 배달 상태를 공개 조회하는 API는 없다.
5. 롤백하려면 API/워커를 모두 중지하고 pending/processing을 처리 또는 만료·정리한 뒤 `0034:0033` downgrade를 수행한다. 대기 작업이 있으면 downgrade를 거절한다. terminal 작업은 테이블 제거로 삭제되지만 기존 계정·증명은 보존된다.

운영에서는 pending 최대 대기 시간(예: 60초 초과), due 건수, 만료 processing 건수, failed/payload_invalid/smtp_permanent/claim_lost 로그 증가, 워커 비정상 종료를 알린다. 이메일 인증 30분·재설정 15분 안에 도착하도록 워커 용량과 장애 알림을 설정한다. 상태별 잔량은 개인정보 없이 조회할 수 있다.

```sql
SELECT status, count(*) AS jobs,
       min(created_at) AS oldest_created_at,
       count(*) FILTER (WHERE status = 'pending' AND available_at <= now()) AS due_jobs,
       count(*) FILTER (WHERE status = 'processing' AND lease_until <= now()) AS expired_leases
FROM auth_mail_outbox
GROUP BY status;
```

현재는 SQL과 안전한 상태 로그를 제공한다. 외부 알림 시스템 연결·대시보드·처리량 자동 확장은 별도 운영 구성이다. 검증 범위와 실행 결과는 [U22 작업 기록](audits/2026-10-26-pattern-standardization/U22-WORKLOG.md)에 기록한다.
