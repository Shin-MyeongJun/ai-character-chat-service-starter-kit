# 회원가입·로그인 실행 및 연동

인증 전용 API이며 UI와 상품·채팅 가입 후 흐름은 포함하지 않는다. 기본 배포는 프런트와 API를 같은 origin에서 제공한다. API 자체를 테스트할 때는 `http://localhost:8000`을 사용한다. 개인정보 확장 경계와 잠금 정책은 [Identity 아키텍처](../apps/api/app/modules/identity/ARCHITECTURE.md)에 있다.

## 설정과 로컬 실행

1. `.env.example`을 `.env`로 복사한다. 실제 `.env`와 비밀값은 커밋하지 않는다.
2. 가상환경에서 `python -m pip install -r requirements-dev.txt`를 실행한다.
3. 아래 명령으로 각각 다른 키를 생성하고 `.env`의 빈 값에 넣는다. 모든 API 프로세스가 같은 키를 사용해야 한다.

```sh
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

첫 결과는 `AUTH_JWT_KEY`(base64, 최소 32바이트 난수), 둘째는 `AUTH_FLOW_KEY`(Fernet)에 넣는다. 키 교체는 이전 JWT/CSRF/OIDC 흐름을 무효화하므로 계획된 재로그인이 필요하다. 기본 키나 운영 개발용 대체 동작은 없다.

```sh
docker compose --profile auth-dev up -d postgres mailpit
```

Mailpit SMTP는 `localhost:1025`, 수신함은 `http://localhost:8025`다. 호스트에서 API를 실행한다면 `.env`의 `DATABASE_URL` 호스트를 `postgres`에서 `localhost`로 바꾼다. 컨테이너에서 실행하면 SMTP 호스트는 `mailpit`이다.

DB 초기화는 두 방식 중 하나만 선택한다.

- 새 compose 볼륨은 `infra/postgres/init/*.sql`로 **0020 구조까지** 생성된다. 빈 DB에 Alembic을 다시 실행하지 않는다. 스키마를 확인한 후 기존 방식대로 Alembic `stamp head`를 명시적으로 실행하여 이력을 맞춘다.
- Alembic 관리 DB는 기존 revision을 확인하고 `python -m alembic -c apps/api/alembic.ini upgrade head`를 실행한다. 빈 독립 DB는 `upgrade head`로 생성한다. 마이그레이션 실행 프로세스에도 `DATABASE_URL`과 `PYTHONPATH=apps/api`를 설정해야 한다. `.env` 자동 로드는 Uvicorn 옵션에만 적용된다.

0020은 기존 이메일을 앞뒤 ASCII 공백 제거·소문자로 정규화하기 전에 충돌을 검사한다. 충돌 또는 기존 국제화 이메일이 있으면 중단한다. 계정을 자동 삭제/병합하지 않는다. 운영자는 백업 후 IDNA 변환·계정 충돌을 별도 해소해야 한다. 기존 `id/password_hash/display_name/role/status`는 보존한다. 기존 계정의 인증 상태를 추정하지 않아 `email_verified=false`, `pending_expires_at=NULL`이며 자동 정리 대상이 아니다. 기존 자격증명을 실제 인증에 이관할 경우 이메일 소유 증거 확인과 Argon2id 전환을 별도 계획해야 한다. 인증 데이터가 있으면 downgrade를 거절한다.

PowerShell 실행 예:

```powershell
$env:PYTHONPATH='apps/api'
python -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000 --no-access-log
```

기존 앱의 asset storage 설정도 유효해야 한다. `ENVIRONMENT=local`, `AUTH_SECURE_COOKIES=false`는 로컬 HTTP용이다. 운영은 `ENVIRONMENT=production`, HTTPS `AUTH_PUBLIC_ORIGIN`, `AUTH_SECURE_COOKIES=true`, 인증 가능한 SMTP(`SMTP_TLS=starttls` 또는 `ssl`, `SMTP_USER`, `SMTP_PASSWORD`)가 필요하다. SMTP 오류를 로그 메일로 대체하지 않는다. 메일 전송 실패는 503이며 재발송으로 복구한다.

운영 스케줄러에서 환경변수를 주입하고 매시간 `python -m app.auth_cleanup`을 실행한다. 신규 미인증 계정은 7일 후, 세션·토큰·OIDC·요청 제한 행은 각 만료 후 삭제한다. 출력은 건수뿐이다. 자동 스케줄러 자체는 이 저장소에서 등록하지 않는다.

## API 계약

모든 본문은 JSON이고 알 수 없는 필드는 거절한다. `User`는 `{id: UUID, email: string, email_verified: boolean}`이다. 원본 Access/Refresh는 응답 JSON에 포함하지 않는다.

| 메서드·경로 | 요청 | 성공 |
|---|---|---|
| GET `/auth/csrf` | 없음 | 200 `{csrf_token}` 및 HttpOnly CSRF 쿠키 |
| POST `/auth/register` | `{email,password}` | 202 일반 메시지, 세션 없음 |
| POST `/auth/email/resend` | `{email}` | 202 동일 일반 메시지 |
| POST `/auth/email/verify` | `{token}` | 200 User, 세션 없음; 이후 로그인 |
| POST `/auth/login` | `{email,password}` | 200 User 및 Access/Refresh 쿠키 |
| POST `/auth/refresh` | 없음, refresh 쿠키 | 200 User 및 교체 쿠키 |
| POST `/auth/logout` | 없음 | 204 현재 세션 폐기·모든 인증 쿠키 삭제 |
| POST `/auth/logout-all` | 없음, access 쿠키 | 204 모든 세션 폐기·쿠키 삭제 |
| GET `/auth/me` | access 쿠키 | 200 User |
| POST `/auth/password/reset/request` | `{email}` | 202 동일 일반 메시지 |
| POST `/auth/password/reset` | `{token,password}` | 204 비밀번호 변경·모든 세션 폐기·쿠키 삭제 |
| POST `/auth/google/start` | `{redirect:"/"}` | 200 `{authorization_url}` 및 OIDC 흐름 쿠키 |
| GET `/auth/google/callback` | Google의 `code`, `state` | 303 안전한 상대 경로로 이동·세션 쿠키 |

정상 가입·재발송·재설정 요청은 계정 존재/종류를 응답에서 구분하지 않는다. 로그인은 미존재·미인증·비밀번호 오류·정지·Google 전용 계정 모두 같은 `invalid_credentials`다. 비밀번호 12~128 Unicode 문자, 최대 UTF-8 512바이트를 허용한다. 공백/유니코드를 변환하거나 조용히 잘라내지 않는다. Argon2id 비용은 메모리 64MiB, 반복 3, 병렬도 4이며 검증 시 필요하면 재해시한다. 불명 계정도 더미 Argon2 검증을 수행한다.

이메일은 `email-validator`로 구문 검증하고 ASCII local-part, IDNA domain으로 변환한 뒤 앞뒤 공백 제거·전체 소문자를 적용한다. DNS로 수신 가능 여부를 추측하지 않고 인증 메일로 확인한다. Gmail의 점/플러스는 그대로 유지한다. 같은 정규화 규칙과 DB UNIQUE/CHECK를 적용한다.

메일 링크는 `${AUTH_PUBLIC_ORIGIN}/verify-email#token=...`, `/reset-password#token=...`이다. 토큰은 query가 아닌 fragment여서 일반 서버 로그/Referer로 전송되지 않는다. 이 프런트 경로는 이번 작업에서 화면을 만들지 않았다. Mailpit에서 링크의 토큰을 복사해 위 POST API로 검증할 수 있다. 이메일 인증 링크는 30분, 재설정 링크는 15분 유효하고 한 번만 사용할 수 있다. 재발송하면 이전 토큰은 무효다. 인증 대기 7일은 연장하지 않는다.

## 쿠키·CSRF·CORS

운영 쿠키는 `__Host-chatkit_access`, `__Host-chatkit_refresh`, `__Host-chatkit_csrf`, `__Host-chatkit_flow`다. 모두 Secure, HttpOnly, SameSite=Lax, Path=/이며 Domain을 설정하지 않는다. 로컬 HTTP는 `__Host-` 접두사만 제외한다. Access는 15분, refresh·서버 세션은 최초 로그인부터 14일 절대 만료다. CSRF는 1시간, OIDC flow는 10분이다.

프런트는 먼저 `GET /auth/csrf`의 JSON에서 CSRF 값을 읽어 메모리에 보관한다. 가입·로그인·Google 시작을 포함한 모든 POST는 `Origin: 정확한 프런트 origin`, `X-CSRF-Token: 받은 값`, 쿠키를 함께 보내야 한다. signed double-submit을 사용하므로 cookie/header 일치와 서명·용도를 모두 확인한다. Origin 누락/불일치도 403이다. OAuth callback은 GET의 state·암호화 브라우저 쿠키·nonce·PKCE로 보호한다. 로그인 쿠키를 동반한 다른 API의 상태 변경도 같은 CSRF 검사를 받는다.

```javascript
const {csrf_token} = await fetch('/auth/csrf', {credentials:'same-origin'}).then(r => r.json());
await fetch('/auth/login', {
  method:'POST', credentials:'same-origin',
  headers:{'Content-Type':'application/json', 'X-CSRF-Token':csrf_token},
  body:JSON.stringify({email, password})
});
```

브라우저가 Origin을 설정한다. curl/스크립트는 Origin을 직접 설정하고 쿠키 저장소를 유지한다. 로그아웃·재설정·세션 오류는 CSRF 쿠키도 지우므로 다시 가져온다. `/auth/google/start`의 URL로 top-level navigation하면 된다.

`CORS_ORIGINS`는 쉼표로 구분한 정확한 허용 origin만 받는다. 기본값은 추가 허용 없음이고 public origin은 항상 포함한다. `*`는 설정 오류다. 다른 origin의 개발 프런트를 쓰면 명시적으로 추가하고 `credentials:'include'`를 사용한다. SameSite=Lax는 서로 다른 site 간 쿠키 인증을 지원하지 않는다. 운영 기본은 같은 origin reverse proxy다. 프록시 뒤에서는 Uvicorn의 trusted proxy IP를 정확히 제한하고 전달 IP 헤더를 모든 인터넷 클라이언트에 신뢰하지 않는다.

**갱신은 탭 간에도 하나씩 수행해야 한다.** 같은 refresh로 두 요청이 오면 하나가 새 토큰을 받은 뒤 다른 요청이 그 세션 전체를 폐기한다. 네트워크 응답 유실 후 이전 refresh를 자동 재시도해도 폐기된다. 401 또는 불확실한 갱신 결과는 재로그인으로 복구한다. refresh를 재시도 큐에 넣거나 Access와 바꿔 사용하지 않는다. JWT에는 내부 ID·세션 ID와 검증용 claim만 포함하고 이메일/프로필은 포함하지 않는다. 모든 Access 검증에서 서버 세션 폐기/만료와 사용자 active·인증 상태를 조회한다.

## 오류와 요청 제한

오류는 `{ "error": { "code": "..." } }`이며 민감한 입력/외부 공급자 원문을 포함하지 않는다. 인증 응답은 Cache-Control: no-store, Referrer-Policy: no-referrer다.

| 상태 | 코드 |
|---|---|
| 400 | invalid_action_token, invalid_google_login, invalid_redirect |
| 401 | invalid_credentials, invalid_token, invalid_session, refresh_reused |
| 403 | csrf_failed, origin_forbidden |
| 409 | account_conflict: 기존 가입 방법으로 로그인, 계정 연결 미지원 |
| 422 | invalid_input: JSON·필드·이메일·비밀번호 정책 위반 |
| 429 | rate_limited, Retry-After: 900(보수적 재시도 시간) |
| 503 | mail_unavailable, google_not_configured, auth_not_configured |

DB의 고정 시간 버킷으로 전체 인증 IP 120회/분, 상태 변경 경로와 Google callback별 IP 20회/5분, 로그인 이메일 10회/5분, 가입 이메일 5회/15분, 인증 메일(가입+재발송 공유) 및 재설정 메일 이메일별 5회/15분을 제한한다. 경계 시점에는 인접 버킷의 한도를 연속 소비할 수 있다. IP/이메일 원문 대신 키 기반 HMAC를 저장하고 만료 버킷은 정리한다. PostgreSQL 장애 때 프로세스 메모리 제한으로 우회하지 않는다. 운영에서 body 크기 제한 및 엣지 제한도 적용한다.

SMTP 통신은 커밋 후 실행하므로 정상 응답 문구는 같아도 전송 시간과 장애 여부에 따른 차이는 있을 수 있다. 완전한 시간 동일성은 보장하지 않는다. 실서비스에서 SMTP 상태 관측과 요청 제한을 함께 운영한다.

## Google 실제 연동 확인

Google Cloud에서 Web application OAuth client와 동의 화면을 설정한다. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, **정확히** `${AUTH_PUBLIC_ORIGIN}/auth/google/callback`인 `GOOGLE_CALLBACK_URL`을 등록한다. 개발 동의 화면이면 테스트 사용자를 추가한다. 요청 scope는 `openid email`뿐이며 profile·offline access를 요청하거나 Google access/refresh token을 저장하지 않는다.

1. 실제 브라우저로 CSRF를 받고 `/auth/google/start`를 호출한 후 반환 URL로 이동한다.
2. Google 동의 화면의 권한이 이메일과 기본 OIDC 식별 범위인지 확인한다.
3. callback 후 `/auth/me`와 Secure/HttpOnly 쿠키, DB의 provider=google 및 sub를 확인한다. 실명/사진 컬럼은 추가하지 않는다.
4. 같은 Google 계정 재로그인이 같은 내부 ID인지, 자체 계정과 같은 이메일이면 409인지 확인한다.
5. Google 전용 이메일의 재설정 요청이 일반 202이며 메일/비밀번호를 생성하지 않는지 확인한다.
6. 잘못된 state·다른 브라우저·callback 재사용·허용되지 않은 redirect가 거절되는지 확인한다.

서버가 고정 token endpoint로 code+PKCE verifier를 교환하고 고정 Google JWKS에서 RS256 서명, issuer, audience/azp, exp/iat, nonce, sub, email_verified를 검증한다. 응답이나 키 조회 실패를 성공으로 처리하지 않는다. 자동 테스트는 임시 RSA 키와 모의 code 교환으로 이 경계를 검사한다. 실제 Google 자격증명과 사용자 동의는 별도 확인이 필요하다. 구현 기준: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect), [PyJWT 검증 옵션](https://pyjwt.readthedocs.io/en/stable/api.html).

## 프런트 구현 시 XSS·민감정보 처리

React의 기본 이스케이프를 유지하고 사용자 HTML은 검증된 sanitizer로 정화한다. CSP, 가능한 Trusted Types, 인라인 스크립트 제한을 적용한다. 쿠키의 HttpOnly는 XSS가 사용자를 대신해 요청하는 것을 막지 못한다. 원본 토큰·비밀번호는 localStorage/sessionStorage/분석 이벤트/오류 추적에 넣지 않는다. 메일 fragment는 메모리로 읽고 `history.replaceState`로 즉시 제거한다. 인증/재설정 화면에 제3자 분석 스크립트를 넣지 않는다. 서버·프록시·APM에서도 Cookie/Set-Cookie/X-CSRF-Token/요청 본문과 OAuth code/state 쿼리를 수집하지 않는다. 앱은 Uvicorn 인증 경로의 쿼리를 필터링하며 실행 예는 access log 자체를 끈다.

## 검증 실행

```powershell
$env:PYTHONPATH='apps/api'
$env:TEST_AUTH_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@localhost:5432/chatkit_auth_test'
python -m pytest apps/api/tests/test_identity_security.py apps/api/tests/test_identity_auth.py apps/api/tests/test_identity_migrations.py -q
```

테스트는 실행마다 별도 스키마를 만들고 삭제한다. DB명은 test를 포함해야 한다. 인증 테스트는 pgvector가 필요 없고 기존 전체 DB 테스트는 pgvector를 설치한 `TEST_DATABASE_URL`이 필요하다. 외부 Google·운영 SMTP 비밀값을 테스트에 넣지 않는다. 실제 실행 결과와 외부 설정에 따른 미검증 범위는 [검증 기록](authentication-validation.md)에 기록한다.

실제 로컬 SMTP 검사도 실행하려면 Mailpit을 켜고 `TEST_MAILPIT_HTTP_URL=http://localhost:8025`, `TEST_MAILPIT_SMTP_PORT=1025`를 설정한 뒤 `test_identity_mailpit.py`를 실행한다. 이 테스트는 고유한 테스트 수신 주소만 검색하며 기존 수신함을 삭제하지 않는다. 독립 프로세스 요청 제한 검사는 `test_rate_limit_across_real_processes`에서 실행한다.
