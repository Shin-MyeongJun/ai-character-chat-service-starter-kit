# U22 작업 기록 — 인증 메일 접수·Outbox·재시도

작성일: 2026-11-02 (Asia/Seoul). 구현 시작: 2026-11-01.

상태: **구현·PostgreSQL/로컬 SMTP 검증·문서화 완료. 운영 배포는 수행하지 않음.**

## 문제와 보존 범위

기존 가입·인증 재발송·비밀번호 재설정 workflow는 대상이 없으면 즉시 반환하고, 대상이 있으면 증명 commit 뒤 SMTP 완료를 기다렸다. SMTP 장애는 `mail_unavailable`/503이 되어 계정 상태가 응답 상태와 전송 대기 시간에 드러났다.

AGENTS.md, 모듈 아키텍처·명명 규칙, 백엔드 코드 작성 규칙, identity/DB ARCHITECTURE, 원본 U22와 후속 통합 검토를 적용했다. 기존 U10 인증 읽기/암호 작업 잠금 및 다른 작업의 staged/unstaged 변경을 보존했다. HTTP 경로·DTO·일반 202 본문·보안 헤더·쿠키·CSRF·요청 제한·계정 적격성·비밀번호·증명 만료/소모 계약을 유지했다. 이 작업의 의도적인 변경은 메일 요청의 응답 의미를 접수 성공으로 정하고 SMTP 결과/지연을 요청 처리에서 분리하는 것이다.

## 최종 구현

- `AuthenticationService._create_mail_token`이 증명과 암호화 토큰을 포함한 Outbox를 같은 트랜잭션에 저장한다. 저장 실패 시 신규 계정·증명·기존 증명 무효화가 함께 rollback된다. 기존 ActionMailInfo 반환 계약은 유지한다.
- `AuthenticationMailWorkflow`의 세 HTTP 유스케이스는 DB 확정만 기다린다. SMTP 예외 무시, 고정 sleep, 비영속 BackgroundTask는 사용하지 않는다. 계정이 미존재/부적격이어도 기존 일반 202이고, DB 실패는 성공으로 바꾸지 않는다.
- 신규 `service/mail_delivery.py`가 발송 상태 전이와 재시도를 소유하고, 기존 `workflow/mail.py`가 claim commit → SMTP → 결과 commit을 조율한다. 모듈 소유 SQL은 기존 repository에, 변환은 persistence mapper에 둔다. 인증 계정 정책과 외부 메일 실행 책임을 분리한 것이며 타 모듈 경계/인가 JOIN을 추가하지 않는다.
- 워커는 한 번에 한 건씩 `FOR UPDATE SKIP LOCKED`로 가져와 새 claim UUID/120초 lease를 저장한다. SMTP 중 세션·사용자/Outbox 잠금을 보유하지 않는다. 늦은 워커의 결과는 UUID와 유효 lease를 재검증하여 거절한다.
- 연결 오류/SMTP 4xx는 최대 5회 시도하며 30/60/120/240초 + 최대 25% jitter로 재예약한다. 5xx/영구 수신 거절/기능 미지원은 failed, 소모·무효화·만료·부적격 증명은 cancelled다. 워커 종료도 시도 횟수에 포함하여 무한 재선점을 막는다. 다음 시각이 증명 만료 이후면 재시도하지 않는다.
- 재시도는 같은 일회용 링크를 사용한다. SMTP 수락 뒤 DB 확정이 실패하면 같은 메일이 다시 갈 수 있으며, 토큰 소모는 기존대로 한 번만 성공한다. exactly-once는 보장하지 않는다.
- Outbox 토큰은 기존 `AUTH_FLOW_KEY`의 Fernet과 인증된 용도 접두사로 보호하고 증명 해시와 결합 검증한다. terminal 상태에서는 암호문을 지운다. 기존 증명 정리에 FK CASCADE되어 장기 개인정보/토큰 저장소로 남지 않는다. 키 교체 시 대기 작업 처리/만료가 필요하다.
- 로그는 작업 UUID·상태·시도 횟수·고정 오류 종류만 포함한다. 워커 CLI도 예외 종류만 출력하고 SMTP 원문/예외 체인을 출력하지 않는다. `sent`는 SMTP 호출 성공이지 수신함 도착 증명이 아니다.
- Alembic `0034`와 초기 SQL `024`를 추가했다. 기존 계정·증명은 보존하며 예전 증명을 소급 큐잉하지 않는다. pending/processing이 있으면 downgrade를 거절한다. online asyncpg 실행을 위해 고정 DDL을 문장별로 실행한다.
- 별도 진입점 `python -m app.auth_mail_worker`와 현재 due 작업만 처리하는 `--once`를 제공한다. 배포/키 보존/정리/관측/복구 절차는 [Outbox 운영 문서](../../auth-mail-outbox.md)에 정리했다.

## 검증 결과

| 검증 | 결과 |
| --- | --- |
| 신규 U22 전용 3개 파일 | 90건. 아래 최종 305건에 포함 |
| identity 전체 + product migration + first answer integration + runtime entrypoints | **305 passed, 0 failed, 0 skipped** |
| 실제 로컬 PostgreSQL | 원자적 rollback, 재시도/복구, 선점 경합/SKIP LOCKED, 만료 선점 fencing, 기존 인증/증명/세션 회귀 |
| 실제 로컬 Mailpit SMTP | Outbox 워커에서 인증·재설정 링크 송신/수신 후 실제 HTTP 증명 사용 성공 |
| 마이그레이션 | 0034 SQLAlchemy/asyncpg online 실행, 생성 DDL 실행/초기 SQL/ORM 일치, 대기 작업 downgrade 차단·기존 증명 보존 |
| 필수 `tools/check_backend_quality.py` | 신규 시그니처 위반 0, Ruff format/lint 통과, mypy 375 source files 통과, 아키텍처/검사기 테스트 13 passed |
| U22 변경 파일의 `git diff --check` | 통과 |

HTTP 대역 검사는 3개 경로 × 6개 계정 상태 × 3개 SMTP 상태의 54가지 조합을 실행한다. SMTP 대기 대역은 호출되면 종료하지 않도록 구성했고, HTTP 요청이 완료되며 SMTP가 한 번도 호출되지 않음을 확인했다. 실제 벽시계 응답 시간의 통계적 동일성을 측정한 것은 아니다.

PostgreSQL 검사는 실패한 Outbox INSERT 뒤 신규 계정/증명/Outbox 전체 rollback, 실패한 재발송의 기존 증명 보존, transient 복구, 영구 실패, 최대 5회 및 crash 소진, 토큰 만료 전 재시도 종료, superseded/사용/정지/Google/대기 만료/삭제/잘못된 암호문 차단, 두 워커의 한 번 선점, 잠긴 작업을 건너뛰는 처리, 이전 워커의 늦은 결과 거절, SMTP 대기 중 재발송/잠금 진행을 검증한다. SMTP 수락 후 ack 트랜잭션을 실패시켜 같은 링크의 재전송과 한 번만 가능한 증명 소모도 확인했다.

최종 실행은 프로젝트 가상환경과 `tools/run_postgres_audit_tests.py`를 사용했다. 두 전용 테스트 DB에 UUID 스키마를 만들고 정리했으며 운영/앱 DB에 migration을 실행하지 않았다. 테스트 Mailpit은 localhost에서만 메일을 수신하며 외부로 전달하지 않는다. [최종 출력](../../../tmp/u22-final-regression.txt).

초기 검증은 298 passed / Mailpit 미설정 1 skipped였다. 추가 테스트 중 Windows sandbox의 asyncio socketpair 초기화 차단을 진단하고, 허용된 범위에서 동일 검사를 실행했다. 작업 재개 시 Docker가 꺼져 DB 연결이 거절되어 환경 오류가 발생했다. 기존 Docker Desktop/컨테이너를 시작한 뒤 최종 305건을 통과했다. 볼륨/컨테이너 재생성·앱 DB 초기화는 하지 않았다. 품질 검사의 임시 디렉터리 권한 문제는 새 workspace basetemp로 해결했고 기준선 예외를 늘리지 않았다. 전체 작업공간 diff 검사에는 기존 `tmp/u05-windows-pg.txt`의 공백 진단이 있어 U22 변경 범위를 별도로 확인했다.

## 적용과 남은 한계

운영 적용 시 **0034 migration을 먼저 실행하고 새 API와 별도 메일 워커를 배포**해야 한다. API/워커의 DB·AUTH_FLOW_KEY·public origin·SMTP 설정을 같게 주입하고 워커 재시작/지연/실패 알림을 운영 환경에서 연결한다. 기존 매시간 auth_cleanup은 유지한다. 이 작업에서 운영 서비스/스케줄러를 등록하거나 commit/push하지 않았다.

DB 작업량·락 경합·암호 비용의 시간 차이를 없애는 constant-time 설계, SMTP exactly-once, 실 운영 SMTP/TLS/수신함 도착, Google/JWKS 실서버, 장시간 부하·다중 호스트 시계 차이·실제 프로세스 강제 종료는 검증 범위 밖이다. PG에서 별도 서비스/연결과 제어된 취소·lease/ack 장애를 검증했으며 모든 프로세스 장애의 재현을 주장하지 않는다. SMTP 소켓별 timeout은 유지하고 전체 전송 deadline/lease heartbeat는 추가하지 않았다. 선점 이후 무효화된 구 링크가 도착할 수 있으나 사용 시 현재 증명/계정 상태를 재검증한다.
