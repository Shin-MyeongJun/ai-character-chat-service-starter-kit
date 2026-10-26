# Studio Admin

별도 Next.js 관리자 앱. Next 16.3.3 / React 19.2.8 / 저장소 lockfile의 TypeScript 5.9.3을 사용한다. 사용자 웹의 컴포넌트·CSS·업무 코드를 import하지 않는다.

## 실행

저장소 루트의 PowerShell:

```powershell
pnpm install --frozen-lockfile
Copy-Item apps/admin_web/.env.example apps/admin_web/.env.local
pnpm admin:dev
```

접속: <http://127.0.0.1:3100/login>. `ADMIN_API_URL`은 관리자 전용 서버 환경변수이며 기본값은 `http://127.0.0.1:8000`이다. `.env.local` 또는 실행 셸에 설정한다. 개발 서버 재시작/운영 재빌드 후 `/backend/*` rewrite에 반영된다. 사용자 웹의 `CHAT_KIT_API_URL`과 독립적이다.

```powershell
pnpm admin:typecheck
pnpm admin:test
pnpm admin:build
pnpm --dir apps/admin_web start
```

dev와 production start는 3100 포트를 사용하므로 하나씩 실행한다. 독립 배포 시 앱 작업 디렉터리에서 build/start하고 설치에는 루트 pnpm lockfile을 포함한다.

## 실제 API 연결

- 기존 `/auth/csrf`, `/auth/login`, `/auth/me`, `/auth/refresh`, `/auth/logout`과 `/admin/reporting/generation-prompts` 목록·상세를 사용한다.
- **`/admin/session`은 없다.** `/auth/me`는 식별 정보만 제공하므로, 기존 관리자 목록 GET을 최근 7일·`page_size=1`로 호출해 서버 인가 성공 후 본문을 연다. 본문 데이터 요청도 각각 서버 인가를 받는다. 확인용 조회가 실패하면 콘텐츠를 숨기고 재시도를 제공한다. 이 관리자 조회 기능에 한정한 접근 확인이다.
- 관리자 표시명 계약이 없어서 ‘운영 관리자’는 고정 문맥 라벨, 아래 이메일은 `/auth/me` 응답이다. 클라이언트 role로 인가하지 않는다.
- 실제 DB에는 migration **0030 이상**과 검증된 활성 관리자 계정이 필요하다. 이번 작업은 backend·DB·계정 권한을 변경하지 않는다. 계정 부여는 기존 운영 절차로 수행하며 관리자 가입 UI는 없다.
- backend `CORS_ORIGINS`에 **`http://127.0.0.1:3100`**을 기존 origin들과 함께 추가한다. `AUTH_PUBLIC_ORIGIN`이나 기존 사용자 origin을 대체하지 않는다. 브라우저 Origin을 프록시에서 임의로 변경하지 않는다.
- 사용자 웹은 `http://localhost:3000`, 관리자는 **`http://127.0.0.1:3100`**을 사용한다. `localhost:3100`은 `localhost:3000`과 쿠키를 공유한다. 포트만 분리하면 쿠키는 같고 refresh Web Locks는 origin별이라 안전한 격리가 되지 않는다.
- 기존 쿠키는 Domain 없는 host-only, HttpOnly, SameSite=Lax, Path=/다. 로컬 HTTP만 기존 backend의 `ENVIRONMENT=local`, `AUTH_SECURE_COOKIES=false` 설정을 사용한다. 운영은 별도 관리자 HTTPS 호스트, Secure `__Host-` 쿠키, 각 호스트의 같은 origin `/backend` 프록시를 사용한다.
- 프록시는 Cookie/여러 Set-Cookie/Origin/X-CSRF-Token을 보존해야 한다. 프록시·APM도 인증 본문/쿠키/원문을 수집하지 않도록 기존 정책을 적용한다.

## 화면과 민감 데이터

`/login`, `/generation-prompts`, `/generation-prompts/[generationId]`, `/forbidden`을 제공한다. 서울 최근 7일·50개가 기본이고 검색 조건과 페이지는 URL에 남는다. 크기는 20·50·100 선택이며 계약상 1–100의 URL 값도 받는다. `401`은 로그인, `403 forbidden`은 접근 거절, `origin_forbidden`은 설정 오류다. `stale`는 디자인의 ‘만료’를 유지하고 생성 버전/실행 유효성 만료 의미를 설명한다.

Light 고정, 로컬 Noto Sans KR와 OFL 라이선스, Studio의 중성색·테두리·모서리를 사용한다. 미구현 메뉴는 없다. UUID는 축약+전체 title, 모델은 2줄, 표와 원문은 내부 스크롤을 제공한다.

CSRF는 메모리 보관·단회 재발급한다. refresh는 Web Locks로 탭 간 직렬화하고 잠금 후 `/auth/me` 재확인, 한 번 회전한다. 응답 유실/5xx는 재로그인하며 자동 재전송하지 않는다. 재전송 방지용 **불리언 하나**만 localStorage에 남긴다. 토큰·권한·원문·API 응답은 저장하지 않는다. 명시적 로그인/로그아웃으로 표식을 해제한다. BroadcastChannel로 다른 탭의 로그인은 재검증하고 로그아웃은 본문을 숨긴다. Web Locks를 지원하는 HTTPS 또는 loopback 보안 컨텍스트가 필요하다.

`request_json`은 React 텍스트로 표시하고 원문 그대로 `clipboard.writeText`에 전달한다. 역할 파싱 실패/미지원 버전에도 원본 표시·복사를 유지한다. 복사 성공은 실제 promise 완료 후 표시한다. **Windows 네이티브 클립보드의 LF→CRLF 정규화**를 관찰했으므로, 앱 전달 원문 보존과 OS 붙여넣기의 바이트 동일성은 구분한다. digest는 서버 원문 기준이다. 원문을 재직렬화·HTML 실행·콘솔/분석 전송하지 않는다.

## 명시적 개발 fixture

앱에 가짜 인증 분기는 없다. 별도 `tests/fixture-api.cjs`는 `ADMIN_FIXTURE=1`에서만 실행하며 `NODE_ENV=production`이면 거절한다. 아래는 실제 API 연동이 아닌 합성 데이터 검사다.

첫 번째 PowerShell:

```powershell
$env:ADMIN_FIXTURE='1'
pnpm --dir apps/admin_web fixture
```

두 번째 PowerShell:

```powershell
$env:ADMIN_API_URL='http://127.0.0.1:8100'
pnpm admin:dev
```

합성 관리자 `admin@example.test` / `fixture-password`, 비관리자 `user@example.test` / 같은 비밀번호. fixture 상태 제어 `/__fixture/control`은 테스트 서버에만 존재한다. 운영 API로 사용하지 않는다. 실제 API 복귀 시 dev 종료 후 `Remove-Item Env:ADMIN_API_URL`하고 재시작한다.

Playwright와 Edge가 설치된 세 번째 셸에서 **한 번에 한 검사만** 실행한다:

```powershell
$env:ADMIN_FIXTURE='1'
node apps/admin_web/tests/browser.test.cjs
```

기본 Edge(`msedge`), `ADMIN_BROWSER_CHANNEL=chrome`으로 변경할 수 있다. Playwright는 앱 의존성이 아니다. 이번 환경은 Codex 번들을 사용했고 모듈 탐색에 다음을 설정했다:

```powershell
$env:NODE_PATH='C:/Users/smj/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
```

다른 환경은 설치된 Playwright 위치에 맞게 설정한다. 결과/스크린샷은 `docs/assets/admin-web-implementation`에 저장한다.

## 검증과 남은 환경

2026-10-22: typecheck·production build 통과, 계약 테스트 9개, 실제 Edge의 fixture 브라우저 검사 26개 통과. 1440px·1280px 화면·로그인→목록→상세→복귀와 필수 상태를 확인했다. refresh 동시성·응답 유실은 fetch 대역 테스트이며 fixture 서버는 실제 rotation을 구현하지 않는다.

**실제 API/DB 통합은 미검증**이다. 현재 API 8000 포트가 열려 있지 않고 검증용 실제 활성 관리자 세션이 없다. 실제 Origin/CSRF/Secure 쿠키/refresh 회전·로그아웃, 0030 DB 조회, 역할별 차단과 사용자 웹 동시 사용은 환경 준비 후 확인해야 한다. [검증 기록](../../docs/admin-web-validation.md)을 따른다.
