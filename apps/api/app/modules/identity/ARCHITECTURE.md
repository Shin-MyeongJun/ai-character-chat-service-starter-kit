# Identity 모듈

인증은 내부 사용자 ID, 이메일·인증 상태, 자격증명, 공급자 식별자와 로그인 세션만 담당한다. 상품·채팅 업무 흐름이나 프런트 화면을 추가하지 않는다. 기존 `display_name` 컬럼은 호환성을 위해 보존하며 새 인증 API에서는 수집·출력하지 않는다.

## 소유 테이블과 파일 책임

- `users`: 정규화된 이메일 UNIQUE, Argon2id 비밀번호(자체 계정만), 이메일 인증 상태, 신규 자체 가입의 인증 대기 기한. 기존 role/status 계약 유지.
- `user_oauth_accounts`: `(provider, provider_user_id)` UNIQUE. Google의 `sub`가 식별 기준이며 이메일로 연결하지 않는다.
- `auth_sessions`: 로그인별 refresh 검증 해시, 최초 로그인/절대 만료 시각, 폐기 시각. 한 행이 하나의 토큰 계열이다.
- `auth_action_tokens`: 인증/재설정 일회용 토큰의 SHA-256 해시, 용도, 만료/사용 시각.
- `auth_oauth_attempts`: state 해시와 10분 만료/사용 시각. 원본 state·nonce·PKCE verifier는 Fernet 암호화 HttpOnly 쿠키로 전달한다.
- `auth_rate_limits`: HMAC 식별키·시간 버킷별 카운터. 여러 API 프로세스가 PostgreSQL UPSERT로 같은 한도를 공유한다.
- `router.py`, `schemas.py`, `mapper/schema.py`: HTTP 계약, DTO와 Command/Info 순수 변환.
- `http_security.py`: 쿠키/CSRF/Origin, 공통 오류와 민감 입력의 반사 방지, 요청 제한 연결, access log 쿼리 제거.
- `dependencies.py`: 검증된 내부 UUID를 기존 owner 의존성에 연결. 업무 조회는 공개 서비스에 위임한다.
- `service/authentication.py`: 가입·메일 증명·비밀번호·세션 유스케이스, 최상위 트랜잭션과 사용자 잠금. 같은 잠금·폐기 정책을 공유하여 한 서비스에 둔다.
- `service/google.py`: OIDC 상태 소모, 외부 검증, provider/sub 계정 식별. 네트워크와 콜백 복구 정책이 달라 별도 분리했다.
- `service/query.py`: 기존 `require_admin(GetUserCommand)` 계약 유지. 활성 admin 외에는 같은 LookupError. admin/moderator HTTP 훅의 별도 권한 정책은 확장하지 않는다.
- `repository.py`: 자기 테이블 SQL·잠금, ORM 반환. `mapper/persistence.py`: Entity→Info/스칼라 변환. 서비스는 Entity 필드를 해석하지 않는다.
- `security.py`: Argon2id, JWT 고정 알고리즘/claim 검증, 이메일·비밀번호·redirect 정책. 자체 암호 알고리즘은 없다.
- `adapters.py`: 교체 가능한 `MailSender`, `GoogleVerifier` 프로토콜과 SMTP/Google 구현. 자격증명과 원본 토큰은 로그에 남기지 않는다.
- `settings.py`: 환경변수 로드·운영 보안 설정 검증. `app/auth_cleanup.py`: 만료 레코드 정리 CLI.

타 모듈 JOIN 예외는 없다. 기존 관리자 조회를 포함한 타 모듈 접근은 공개 service/types만 사용한다. main은 조립 코드로 HTTP 의존성과 어댑터를 연결한다.

## 공개 서비스 계약

`AuthenticationService(sessions, settings, mailer)`는 실행 의존성을 생성자로 받는다. 모든 요청 값은 `types.py`의 Command로 받으며 HTTP 예외를 사용하지 않는다.

| 메서드 | Command | 결과 |
|---|---|---|
| register_user / login_user | CredentialsCommand | None / LoginInfo |
| resend_verification / request_password_reset | EmailCommand | None |
| verify_email | TokenCommand | UserInfo |
| reset_password | ResetPasswordCommand | None |
| refresh_session | TokenCommand | LoginInfo |
| get_authenticated_user | TokenCommand | UserInfo |
| logout_session | LogoutCommand | None, 이미 종료된 세션도 성공 |
| logout_all_sessions | TokenCommand(Access) | None |
| check_rate_limit | RateLimitCommand | None 또는 rate_limited |
| cleanup_expired_auth | 요청 값 없음 | CleanupInfo(실제 삭제 건수) |

`GoogleLoginService(authentication, verifier)`의 `start_google_login(GoogleStartCommand) → GoogleStartInfo`, `complete_google_login(GoogleCallbackCommand) → GoogleLoginInfo`는 HTTP 표현과 독립적이다. `LoginInfo`의 원본 토큰은 HTTP 쿠키 설정에만 사용하며 응답 JSON/로그로 내보내지 않는다. 일반 업무 모듈은 `get_authenticated_user` 결과의 내부 ID만 사용한다.

## 원자성·경쟁 조건·실패 계약

최상위 서비스가 `use_case_transaction`으로 commit/rollback을 소유하고 repository는 종료하지 않는다. 신규 이메일 및 Google sub는 advisory lock으로 행 생성 이전부터 직렬화하고 DB UNIQUE가 최종 방어한다. 사용자 행 → 세션/일회용 토큰 순으로 잠근다. 로그인·갱신·전체 로그아웃·재설정은 사용자 잠금을 공유하므로 재설정 이전 자격증명으로 생성한 세션이 폐기에서 빠지지 않는다.

Refresh는 매번 새 JWT로 교체하고 현재 해시만 보관한다. 서명은 유효하지만 해시가 다르면 세션을 폐기하고 **폐기를 커밋한 뒤** `refresh_reused`를 반환한다. 동시 요청은 하나만 회전에 성공하며 뒤 요청이 계열을 폐기하므로 먼저 받은 새 Access도 더 이상 사용할 수 없다. 유예/이전 토큰 재발급은 없다. 응답 유실 후 예전 refresh 재전송도 동일하게 폐기한다. 클라이언트는 탭 사이에서도 갱신을 직렬화하고 불확실한 응답 뒤 자동 재시도하지 말고 재로그인한다.

Access도 매 요청 서명·issuer/audience/필수 claim/type 및 현재 사용자·세션 상태를 확인한다. Access는 15분, refresh와 서버 세션은 최초 로그인부터 14일 절대 만료이며 회전으로 연장하지 않는다. 인증 검사 이후 이미 실행 중인 업무 요청을 소급 취소하지는 않는다.

일회용 토큰은 사용자 잠금 아래 조건부 UPDATE로 만료·미사용 상태를 검사하고 변경과 함께 커밋한다. 재발송은 이전 같은 용도의 증명을 무효화한다. 이메일 인증 30분, 재설정 15분, 신규 미인증 계정 7일이며 재발송은 7일 기한을 연장하지 않는다. 정리 CLI를 매시간 실행한다. 기한을 지난 미인증 계정은 같은 이메일의 새 자체 가입 시에도 정리된다. 마이그레이션 이전 계정은 pending 기한을 부여하지 않아 자동 삭제하지 않는다.

메일은 증명 저장 커밋 후 전송한다. SMTP 실패는 `mail_unavailable`이며 저장된 계정은 유지한다. 재발송/재설정 재요청으로 복구하고 새 증명이 이전 증명을 무효화한다. 외부 SMTP 전송과 DB의 분산 원자성은 보장하지 않는다. 정상 응답의 계정 존재 여부를 통일하지만 전송 지연/일시적 SMTP 장애까지 동일하게 만드는 타이밍 보장은 없다.

Google state는 공급자 통신 전에 원자적으로 사용 처리한다. 통신 실패·콜백 응답 유실은 새 로그인 시작으로 복구한다. 서버 검증 후에도 같은 이메일의 자체/다른 sub 계정을 자동 병합하지 않고 `account_conflict`로 기존 로그인 방법을 안내한다. Google 전용 계정에는 재설정 메일을 보내거나 비밀번호를 생성하지 않는다.

## 향후 프로필·본인확인 확장 위치

현재 성별·전화번호·생년월일·실명·사진을 수집/저장/활용하지 않는다. 향후 별도 profile 모듈을 내부 `user_id`로 연결한다. 사이트별 미수집/선택/필수 정책과 가입 후 추가정보 입력 단계는 profile의 정책 서비스 및 이를 호출하는 가입 후 조율 유스케이스에 둔다. Google/SMTP/휴대폰 확인 어댑터에 수집 정책을 넣지 않는다. 인증 성공은 추가정보 입력 완료와 구분하고 서비스별 필요 조건은 해당 업무의 인가 정책에서 확인한다.

자기기입 프로필, 외부 제공자의 검증 결과(검증 종류·시각·최소 증명), 목적별 동의 이력(정책 버전·동의/철회 시각)은 별도 책임으로 구분한다. 향후 휴대폰·연령 확인은 별도 외부 확인 서비스와 교체 가능한 provider 어댑터에서 증명을 검증하고 공개 Info로 전달한다. 인증은 내부 ID 연결만 담당한다. 추가 프로필/검증/동의 정보는 JWT claim에 넣지 않는다. 사용하지 않는 개인정보 컬럼, 동적 필드 엔진, 빈 어댑터는 만들지 않았다.

API·쿠키·실행·외부 검증 절차는 [인증 실행 및 연동 문서](../../../../../docs/authentication.md)를 참고한다. 테스트는 `test_identity_security.py`, `test_identity_auth.py`, `test_identity_migrations.py`, 기존 `test_architecture_contracts.py`에 있다.
