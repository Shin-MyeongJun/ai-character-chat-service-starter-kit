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
- `service/authentication.py`: 가입 DB 확정·메일 증명 발급/소모·비밀번호·세션 유스케이스, 트랜잭션과 사용자 잠금. 같은 잠금·폐기 정책을 공유하여 한 서비스에 둔다.
- `service/google.py`: OIDC state 생성/선소모 및 provider/sub 계정 식별/연결의 상태 조건. 외부 검증 순서는 workflow/google.py가 맡는다.
- `service/query.py`: 기존 `require_admin(GetUserCommand)` 계약 유지. 활성 admin 외에는 같은 LookupError. admin/moderator HTTP 훅의 별도 권한 정책은 확장하지 않는다.
- `repository.py`: 자기 테이블 SQL·잠금, ORM 반환. `mapper/persistence.py`: Entity→Info/스칼라 변환. 서비스는 Entity 필드를 해석하지 않는다.
- `security.py`: Argon2id, JWT 고정 알고리즘/claim 검증, 이메일·비밀번호·redirect 정책. 자체 암호 알고리즘은 없다.
- `adapters.py`: 교체 가능한 `MailSender`, `GoogleVerifier` 프로토콜과 SMTP/Google 구현. 자격증명과 원본 토큰은 로그에 남기지 않는다.
- `settings.py`: 환경변수 로드·운영 보안 설정 검증. `app/auth_cleanup.py`: 만료 레코드 정리 CLI.

타 모듈 JOIN 예외는 없다. 기존 관리자 조회를 포함한 타 모듈 접근은 공개 service/types만 사용한다. main은 조립 코드로 HTTP 의존성과 어댑터를 연결한다.

## 공개 서비스 계약

### 핵심 저장소·조회 타입 계약

- `repository.py`와 `service/query.py`의 실행 세션은 `AsyncSession`이다. 사용자·세션·토큰 ID는 `UUID`, 저장 시각은 `datetime`으로 표현하며 기존 시각 생성·만료 비교 위치를 유지한다.
- 단건 조회와 이메일 충돌 시 `create_user`는 Entity 또는 `None`을 반환한다. `verify_user_email`은 기존 `scalar_one()` 계약에 따라 반드시 User를 반환하며 미존재 예외를 숨기지 않는다.
- persistence mapper의 overload는 존재하는 `User`/`AuthSession`/`AuthActionToken` 입력에는 해당 Info, `None` 입력에는 `None`을 보장한다. Entity 내부의 nullable 비밀번호·대기 기한·폐기/사용 시각은 그대로 보존하며 Entity 미존재와 합치지 않는다. role/status/purpose는 기존 저장 문자열과 공개 `str` 호출 계약을 유지한다.
- `scalar_row_to_used`는 토큰 UUID·OAuth state 해시·요청 제한 카운터의 **존재 여부**만 변환한다. `0`·빈 문자열도 존재하는 값이다. `CleanupRow`는 repository 내부의 기존 5개 정수 tuple 계약(사용자, 토큰, 세션, OAuth 시도, 요청 제한 순)이며 공개 결과는 `CleanupInfo`다. 공개 types에는 ORM을 노출하지 않는다.
- SQL 조회 조건·`populate_existing`·사용자/세션 잠금과 토큰 선조회·조건부 소모·폐기 조건·SQL 실행/flush 순서는 유지한다. 단건 SELECT 결과는 동일 SQL의 `scalars(...).first()`로 받아 Entity 타입을 보존한다. 정리 DELETE의 `CursorResult` cast는 `RETURNING` 없는 DML의 라이브러리 반환 타입 한계에만 적용한다.
- 인증·인가 정책을 재설계하지 않고 기존 파일 책임을 유지한다. 핵심 타입·nullable 매핑·최신 인가 조회·SQL 저장 계약의 DB 없는 회귀 검증은 `tests/test_identity_persistence_contracts.py`가 담당한다. 이 대역 검증은 실제 PostgreSQL 잠금·경쟁 조건 검증을 대체하지 않는다.

인증 서비스의 기존 `sessions` 인자/속성은 호환을 유지한다. 실행 의존성 타입은
`app.db.types.SessionFactory`, 설정은 `AuthSettings`로 명시한다. 인증 잠금·쿠키·폐기
정책은 타입 정리의 변경 범위가 아니다.

`AuthenticationService(sessions, settings)`는 실행 의존성을 생성자로 받는다. 모든 요청 값은 `types.py`의 Command로 받으며 HTTP 예외를 사용하지 않는다.

| 메서드 | Command | 결과 |
|---|---|---|
| register_pending_user / login_user | CredentialsCommand | ActionMailInfo 또는 None / LoginInfo |
| prepare_action_mail | PrepareActionMailCommand | ActionMailInfo 또는 None |
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

Access 검증의 `invalid_token` 401은 쿠키를 변경하지 않는다. 클라이언트가 유효한 Refresh로 복구할 수 있어야 하고, 늦게 도착한 401이 동시에 갱신된 쿠키를 지우면 안 된다. `/auth/refresh`의 `invalid_token`, 폐기된 세션의 `invalid_session`, `refresh_reused`는 전체 인증 쿠키를 정리한다. 인증 실패의 상태 코드와 JSON 계약은 유지한다.

일회용 토큰은 사용자 잠금 아래 조건부 UPDATE로 만료·미사용 상태를 검사하고 변경과 함께 커밋한다. 재발송은 이전 같은 용도의 증명을 무효화한다. 이메일 인증 30분, 재설정 15분, 신규 미인증 계정 7일이며 재발송은 7일 기한을 연장하지 않는다. 정리 CLI를 매시간 실행한다. 기한을 지난 미인증 계정은 같은 이메일의 새 자체 가입 시에도 정리된다. 마이그레이션 이전 계정은 pending 기한을 부여하지 않아 자동 삭제하지 않는다.

메일은 증명 저장 커밋 후 전송한다. SMTP 실패는 `mail_unavailable`이며 저장된 계정은 유지한다. 재발송/재설정 재요청으로 복구하고 새 증명이 이전 증명을 무효화한다. 외부 SMTP 전송과 DB의 분산 원자성은 보장하지 않는다. 정상 응답의 계정 존재 여부를 통일하지만 전송 지연/일시적 SMTP 장애까지 동일하게 만드는 타이밍 보장은 없다.

Google state는 공급자 통신 전에 원자적으로 사용 처리한다. 통신 실패·콜백 응답 유실은 새 로그인 시작으로 복구한다. 서버 검증 후에도 같은 이메일의 자체/다른 sub 계정을 자동 병합하지 않고 `account_conflict`로 기존 로그인 방법을 안내한다. Google 전용 계정에는 재설정 메일을 보내거나 비밀번호를 생성하지 않는다.

## 향후 프로필·본인확인 확장 위치

### Moderation 내부 조회 연결 (2026-10-14)

service/query.py에 require_active_user(GetUserCommand)와
get_reportable_user(GetUserCommand)를 추가했다. 전자는 활성 상태를 재검증해
UserAccessInfo를, 후자는 신고 대상의 존재만 확인해 UUID를 반환한다. 이메일·프로필을
노출하지 않으며 토큰 인증은 호출 경계 책임이다. require_admin의 기존 LookupError
계약은 유지하고 repository.get_user(refresh=True)로 DB 최신 상태를 읽어 오래 열린
세션 캐시의 이전 역할·상태로 인가하지 않는다. 기본 get_user 호출 계약은 유지한다.

현재 성별·전화번호·생년월일·실명·사진을 수집/저장/활용하지 않는다. 향후 별도 profile 모듈을 내부 `user_id`로 연결한다. 사이트별 미수집/선택/필수 정책과 가입 후 추가정보 입력 단계는 profile의 정책 서비스 및 이를 호출하는 가입 후 조율 유스케이스에 둔다. Google/SMTP/휴대폰 확인 어댑터에 수집 정책을 넣지 않는다. 인증 성공은 추가정보 입력 완료와 구분하고 서비스별 필요 조건은 해당 업무의 인가 정책에서 확인한다.

자기기입 프로필, 외부 제공자의 검증 결과(검증 종류·시각·최소 증명), 목적별 동의 이력(정책 버전·동의/철회 시각)은 별도 책임으로 구분한다. 향후 휴대폰·연령 확인은 별도 외부 확인 서비스와 교체 가능한 provider 어댑터에서 증명을 검증하고 공개 Info로 전달한다. 인증은 내부 ID 연결만 담당한다. 추가 프로필/검증/동의 정보는 JWT claim에 넣지 않는다. 사용하지 않는 개인정보 컬럼, 동적 필드 엔진, 빈 어댑터는 만들지 않았다.

API·쿠키·실행·외부 검증 절차는 [인증 실행 및 연동 문서](../../../../../docs/authentication.md)를 참고한다. 테스트는 `test_identity_security.py`, `test_identity_auth.py`, `test_identity_migrations.py`, 기존 `test_architecture_contracts.py`에 있다.


## 외부 인증 workflow (2026-09-27)

- `service/workflow/mail.py`: `AuthenticationMailWorkflow(authentication, mailer)`의 register_user/resend_verification/request_password_reset가 DB 확정 서비스 → 메일 전송을 조합한다. SMTP 실패 후 계정/증명은 보존하고 기존 mail_unavailable 응답을 유지한다. 증명 원문은 ActionMailInfo에서 repr 제외다.
- `service/workflow/google.py`: GoogleLoginService가 state 생성·쿠키/PKCE → state 선소모 commit → 외부 검증 → 계정 연결+세션 발급 단일 트랜잭션을 조율한다. 하위 google/authentication 서비스만 호출하며 repository에 접근하지 않는다.
- 공유 `AuthenticationService.issue_session(session, IssueSessionCommand)`는 하위 세션 기능이다. 일반 로그인/Google 모두 사용하며 workflow끼리 비공개 세션 메서드를 호출하지 않는다. refresh 재사용 폐기 후 오류, 사용자→세션 잠금, 요청 제한과 만료 정리는 기존 하위 서비스에 유지한다.
- main은 authentication, authentication_mail, google_login을 조립한다. router는 메일 작업만 workflow에 연결하며 비밀번호 확인/변경·토큰 소모·인증/세션은 하위 서비스에 직접 연결한다. HTTP DTO·쿠키·Google 보안 계약은 변경하지 않았다.

## 인증·메일·JWT 내부 타입 정리 (2026-10-28)

service/authentication.py, service/workflow/mail.py와 연결된 security.py/settings.py를
공용 엄격 검사에 편입했다. sessions 인자/속성은 기존 SessionFactory 호환 이름을
유지하며 현재 세션·UUID·시각·Info/tuple 반환과 내부 rate/mail/session helper를 명시했다.
메일 의존성은 기존 MailSender Protocol이다. HTTP/Google 연결과 외부 어댑터 전체의
엄격 검사 완료를 뜻하지 않는다.

AuthTokenClaims는 기존 PyJWT 검증 및 codec의 type/jti/정수 시각/UUID 검사 뒤의
문자열·정수 claim을 표현한다. 원본 사전과 확장 claim을 그대로 반환하며 JWT를 새로
조립하거나 암호/알고리즘/issuer/audience/시간·세션 정책을 바꾸지 않는다. 기존 키 설정
검증도 반환 None만 명시했다.

cast 3곳은 이메일 validator의 ASCII 필드(기존 AttributeError→invalid_input 유지),
검증된 JWT claim 사전, verify_password가 True일 때 존재하는 저장 hash를 연결한다.
값 변환이나 새 검증은 아니다. refresh의 재사용 분기가 아닌 경로는 LoginInfo를 생성했다는
내부 전제를 assertion으로 명시한다. 전제를 위반하는 잘못된 override의 None 반환만
AssertionError로 드러나며 정상/재사용/실패의 외부 계약은 같다. Any/ignore/예외는 없다.

사용자→세션 잠금, 잠금 뒤 현재 시각 재확인, refresh 재사용 폐기 commit 후 오류,
회전 시 절대 만료 유지, 일회용 조건부 소모와 비밀번호/세션 폐기, 요청 제한과 신규/
중복/Google-only 계정의 기존 분기, 메일 전송 전 DB 확정과 실패 시 상태 보존을 유지한다.
토큰 원문은 기존 repr 제외와 메일 fragment 전달에 한정하며 로그/응답에 추가하지 않는다.

test_identity_auth_contracts는 실제 JWT·mapper와 연결 없는 AsyncSession transaction
event, 저장소/메일 대역으로 위 경계를 확인한다. 테스트 Argon2 비용은 작게 설정하며
운영 보안 파라미터 검증을 대체하지 않는다. 실제 PostgreSQL 잠금/경합·폐기 영속성과
SMTP/Google 통신은 미검증이다. TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거한
기존 인증/암호/쿠키/저장소 회귀도 함께 실행한다.

## Google OIDC·SMTP 내부 타입 정리 (2026-10-28)

service/google.py, service/workflow/google.py, adapters.py를 공용 엄격 검사에 편입했다.
state 생성/소모·계정 연결의 실행 세션은 AsyncSession이며 GoogleLoginService는 기존
AuthenticationService와 GoogleVerifier Protocol을 받는다. SMTP/Google 구현의 설정은
AuthSettings다. 새 실행 계층이나 공급자 wrapper는 추가하지 않았다.

workflow 내부 _GoogleFlow는 자체 생성한 Fernet 인증 쿠키의 state/nonce/verifier/redirect
문자열 형식이다. adapters 내부 _GoogleTokenResponse는 Google token 응답의 id_token
문자열 계약이다. JSON 경계의 두 cast는 실행 시 검증이 아니며 원래 값을 그대로 읽는다.
기존 복호화 TTL·state 비교·redirect 검증과 조회/형식 오류 번역을 유지하고, 손상 값에
새 기본값·문자열 변환·추가 필터를 적용하지 않는다. JWT의 기존 서명/issuer/audience/
azp/nonce/email_verified/sub 검증도 같다.

SMTP는 SSL/일반 생성자를 명시적으로 구분해 SSLContext를 SSL 생성자에만 전달한다.
기존 timeout=10·STARTTLS→선택적 login→send_message·with 종료 순서는 같다. 동기 SMTP와
ID token 검증은 기존 to_thread에서 실행하고, HTTP는 timeout=10/follow_redirects=False로
생성한 client를 닫은 뒤 ID token을 검증한다. 오류 범위·cause·재시도 없음도 유지한다.

Google state 선소모 commit→외부 검증→계정 연결+세션 발급 단일 트랜잭션 순서와
google sub→email 잠금을 유지한다. provider/sub가 기존 계정의 기준이며 공급자 이메일
변경으로 이메일을 변경/병합하지 않는다. 충돌/비활성/미인증 계정은 세션 발급 전에 거절한다.

test_identity_google_contracts의 26건은 실제 암호화 쿠키/PKCE·연결 없는 AsyncSession
transaction event와 저장소/검증기 대역, SMTP 대역 및 httpx.MockTransport로 검증한다.
state 재사용의 SQL 원자성·실제 DB rollback 영속성·Google/JWKS·SMTP/TLS 통신을 증명하지
않는다. TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거하고 기존 인증 회귀도 실행한다.
HTTP 인증 연결과 router는 후속 정리 범위다.

## HTTP 보안·router·의존성 타입 정리 (2026-10-28)

http_security.py, router.py, dependencies.py를 정리하고 DTO/schema mapper를 포함한
identity 전체를 공용 엄격 검사에 편입했다. router는 기존 응답 DTO 또는 명시적
Response/RedirectResponse를 반환한다. CookieCSRFMiddleware는 Starlette의
RequestResponseEndpoint를, AuthRoute는 Request→coroutine→Response 계약을 사용한다.
LogRecord filter의 기존 query 제거 조건도 유지한다.

동적 app.state의 authentication은 AuthenticationService | None으로 연결하며
미설정 시 get_authentication의 auth_not_configured와 오류 renderer/middleware의
선택적 동작을 유지한다. dependencies의 get_authentication_mail/get_google_login은
조립된 기존 workflow를 타입만 연결해 반환한다. cast 5곳은 main의 조립 계약을 표현하며
실행 시 타입 검사·새 fallback을 추가하지 않는다. workflow 속성 미설정의 기존
AttributeError도 그대로다. get_verified_user_id는 검증된 UserInfo.id를 UUID로 반환한다.

Origin/CSRF 검사와 요청 제한 순서, HttpOnly/Secure/SameSite=lax/path=/ 쿠키, access의
최대 900초와 절대 세션 만료까지의 refresh 수명, 204 빈 본문, no-store/no-referrer/
nosniff 헤더를 유지한다. middleware의 조기 거절 헤더를 router 응답과 통일하는 변경은
하지 않았다. access invalid_token의 refresh 복구 허용과 refresh invalid_token/
invalid_session/refresh_reused의 전체 쿠키 정리, Google callback flow 정리도 같다.

test_identity_http_contracts의 신규 31건은 실제 FastAPI/ASGITransport·DTO·JWT와
서비스/workflow 대역으로 HTTP 입력 전달과 공개 사용자 필드 투영, 쿠키·CSRF·Origin·
422 입력 반사 방지·외부 라우트 middleware·callback 303/실패·검증 UUID·429/503 계약을
확인한다. TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거하고 기존 인증 회귀도
실행한다. 실제 PostgreSQL·Google/JWKS·SMTP·브라우저/프록시 동작은 미검증이다.
