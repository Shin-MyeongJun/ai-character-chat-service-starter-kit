# admin_web 구현 계획 및 현재 결과

2026-10-22 갱신. 디자인 선행 이후 프런트 구현까지 진행했다. backend 확장은 후속 제안이며 이번 작업에 포함하지 않는다.

## 완료한 구현

1. **독립 앱**: `apps/admin_web`, Next 16.3.3 / React 19.2.8 / 기존 TypeScript·pnpm workspace 버전, 독립 package/Next/TS·환경변수·실행 문서. 루트 `admin:dev`, `admin:build`, `admin:typecheck`, `admin:test` 제공.
2. **화면**: 로그인·생성 프롬프트 목록/상세·접근 권한 없음과 필수 상태. 실제 제공하는 메뉴만 표시하고 사용자 웹을 import/리팩터링하지 않는다.
3. **디자인**: [Figma](https://www.figma.com/design/yVzKbeu9mNhbXrZhGBkuqO)의 목록 5:230·상세 5:921·로그인 5:175에 대응하는 최종 PNG와 [기록](admin-web-figma-design.md)을 사용했다. API 한도 응답 후 반복 호출하지 않았고 Figma/Studio 원본을 수정하지 않았다.
4. **인증**: 기존 HttpOnly 쿠키·CSRF·Origin·회전형 refresh·로그아웃 계약 사용. Web Locks로 origin 내 탭 간 회전을 직렬화하고 불확실한 회전 응답 뒤 자동 재전송하지 않는다. 원본 토큰은 저장하지 않는다.
5. **인가**: 없는 `/admin/session`을 호출하지 않는다. `/auth/me` 후 기존 관리자 목록 GET(`page_size=1`) 성공으로 접근을 확인한다. 본문 조회도 각각 서버 인가를 받는다. 401/403/Origin 오류를 구분한다.
6. **목록**: 계약상 날짜/대화 UUID/상태/page/page_size만 사용한다. 서울 최근 7일·50개 기본, URL 조건/페이지·복귀 보존, 요청 취소/응답 유효성 확인, 로딩·빈 결과·오류/재시도. 긴 ID/모델과 표 내부 스크롤 처리.
7. **상세**: 당시 메타데이터, 생성 상태/원문 저장 사실 분리, 역할별/원본 전환·wrap·스크롤·전체 복사. 미기록 200/생성 404/파싱·복사 실패 구분. 원문을 재직렬화하거나 storage·콘솔/분석에 남기지 않는다.
8. **검증**: typecheck/production build, 계약 테스트 9개, Edge 개발 fixture 검사 26개, 1440px·1280px 실제 렌더링. [검증 기록](admin-web-validation.md)에서 실제 API 검증과 구분한다.

## 디자인 결정과 차이

- Light 고정, Noto Sans KR, Studio 중성색·1px 경계·8px/12px 모서리·224px 탐색을 유지한다. 공통 UI 패키지를 새로 만들지 않는다.
- native date/select로 키보드 조작·달력 입력을 제공한다. OS별 달력/화살표는 Figma와 다를 수 있다.
- 역할별 보기에도 줄바꿈 체크를 제공해 긴 참조 메시지를 바로 읽게 한다.
- `stale`는 디자인의 ‘만료’를 유지하고 생성 버전/실행 유효성 만료를 설명한다. 저장 사실은 전송/생성 성공 증거가 아니다.
- 관리자 표시명 API가 없어 ‘운영 관리자’는 문맥 라벨이며 이메일은 실제 식별 응답이다.
- 가상 고정 날짜/계정은 실제 서울 날짜·응답으로 대체하고 실제 page_size만큼 표 안에서 스크롤한다.
- Windows clipboard LF→CRLF 정규화를 관찰했다. 원문 그대로 API에 전달하는 것과 OS 붙여넣기 바이트 표현을 구분한다.

## 실행·배포

`pnpm admin:dev` → <http://127.0.0.1:3100/login>. 관리자 `ADMIN_API_URL` 기본값은 <http://127.0.0.1:8000>이며 `/backend` rewrite에서 사용한다. [README](../apps/admin_web/README.md)에 독립 실행/배포·fixture 재현을 기록했다.

사용자 웹 `localhost`, 관리자 `127.0.0.1`로 호스트를 구분한다. 포트만 다르면 쿠키는 공유되고 Web Locks는 origin별이어서 refresh 격리가 되지 않는다. 운영은 별도 HTTPS 관리자 호스트·기존 Domain 없는 Secure 쿠키·같은 origin `/backend` 프록시를 사용한다. 기존 `CORS_ORIGINS`에 정확한 관리자 origin을 추가하고 public origin/사용자 웹 설정은 대체하지 않는다.

## 남은 실환경 완료 기준

프런트/fixture 검증 완료를 실제 API 연동 완료로 해석하지 않는다. 현재 API 8000 포트에 서버가 없고 실제 검증용 관리자 세션/DB가 없다.

1. API 실행 환경, migration 0030 적용 DB, 활성 관리자 계정을 기존 운영 절차로 준비한다. 이번 작업은 backend·DB·권한을 변경하지 않았다.
2. 실제 Origin 허용·host-only/HttpOnly/Secure 쿠키·CSRF·refresh 회전/응답 유실·서버 로그아웃을 검증한다.
3. 실제 데이터 검색→페이지→상세→복귀와 일반 사용자/moderator/비활성 관리자/권한 회수 차단을 검증한다.
4. 여러 탭과 사용자 웹 동시 사용을 분리한 호스트에서 확인한다. 합성 쿠키 검사를 실제 인증 검사로 대신하지 않는다.

## 후속 제안

`GET /admin/session`은 향후 별도 서비스 계약으로 논의할 수 있지만 현재 구현/필수 전제가 아니다. 관리자 표시명·계정 부여 운영 절차도 소유 책임 영역에서 확정한다.

작품/사용자/결제/통계 메뉴는 미노출이다. 콘텐츠 관리자 인가 연결, 운영 통계 HTTP, 민감 조회 감사(원문 제외), MFA·네트워크 정책은 후속 범위다. backend 확장 시 모듈 아키텍처·명명 규칙과 해당 ARCHITECTURE를 읽고 기존 API를 보존한다.
