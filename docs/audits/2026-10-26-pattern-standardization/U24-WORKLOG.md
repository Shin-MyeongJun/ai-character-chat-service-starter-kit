# U24 관리자·모더레이터 권한 연결

작업일: 2026-11-02 (Asia/Seoul).

## 확정한 기능과 역할

- DB의 `user/admin` 역할을 유지한다. 검수는 별도 저장 역할 대신 active admin의 권한이다.
- 관리자에게 캐릭터·로어북 원본과 항목의 전역 조회를 제공한다. 비공개 원본도 포함한다.
- 기존 검수 상태 변경 HTTP는 활성 관리자에게 연결하되 **본인 소유 원본만 변경**하는
  공개 서비스 계약을 유지한다. 타인 원본은 404다. 타인 원본 검수 기능은 제공하지 않는다.
- 상품 정책·모델 종료·태그·운영 프롬프트 조회는 기존 공개 서비스의 관리자 검사를
  유지한다. 역할 부여 API·새 moderator DB role·신고/조치 HTTP는 추가하지 않는다.
- 전체 경로와 신뢰 경계는 [권한 문서](../../admin-authorization.md)에 기록했다.

## 구현과 보존한 계약

`app/http/authorization.py`는 HTTP 의존성 연결만 담당한다. 실제 역할·활성 상태 판단은
identity 공개 `require_admin(GetUserCommand)`에 위임한다. main에서 기존 product admin,
character admin/moderator, lorebook admin/moderator 훅 5개를 이 구현에 연결한다.

각 도메인의 원본 owner 의존성을 그대로 참조하므로 기본 쿠키 인증과 기존
`create_app(authenticate=...)`의 검증된 UUID 주입을 재사용한다. 주입된 인증 성공도
관리 권한을 부여하지 않으며 최신 DB 역할·상태 검사를 통과해야 한다. 상태 변경과
가드는 같은 owner 의존성 결과를 요청 내에서 재사용한다. 기존 함수 정체성·URL·DTO·
일반 사용자 owner 경로·본문으로 소유자를 선택하지 않는 정책을 유지한다.

인가 조회는 `app.state.session_factory`의 별도 세션에서 수행하고 끝낸 뒤 업무
서비스를 호출한다. 따라서 인가 SELECT의 autobegin과 쓰기 유스케이스의 begin이
충돌하지 않는다. 인증 미설정 또는 외부 인증 주입 후 인가 세션 팩토리 미설정은 503,
독립 라우터의 미설정 훅도 기존 503이다. LookupError만 HTTP 403 `forbidden`으로
변환하고 DB 장애를 권한 부족이나 성공으로 숨기지 않는다.

공개 콘텐츠 서비스 자체의 인증 계약이나 조회 SQL은 바꾸지 않았다. 소유자 없는
조회 및 소유자 범위 상태 변경을 직접 호출하는 내부 주체는 인증·관리자 인가를
책임진다. 역할 변경/정지 이후의 다음 요청은 재검사하지만 진행 중 요청은 소급 취소하지 않는다.

독립된 HTTP 조립 책임을 authorization.py로 분리했으며 빈 서비스 계층이나 범용
권한 정책 엔진은 만들지 않았다. admin/moderation/identity 아키텍처 및 기존 감사
보고서에 최신 연결과 범위 결정을 반영했다. 다른 작업의 기존 변경은 보존했다.

## 검증 결과

프로젝트 `.venv/Scripts/python.exe`(Python 3.12)로 실행했다.

| 검사 | 결과 |
| --- | --- |
| 신규 `test_admin_authorization_http.py` | **118 passed**, 전체 API 실행에 포함 |
| 전체 `apps/api/tests` | **1,688 passed / 0 failed / 425 skipped**, 31.34초 |
| 필수 `tools/check_backend_quality.py` | 종료 코드 0 |
| 시그니처 검사 | 기존 진단 0, 새 위반 0, 기준선 예외 추가 없음 |
| Ruff format / lint | 애플리케이션 397파일 포맷 및 lint 통과 |
| mypy | 376 source files 통과 |
| 품질 명령의 아키텍처·검사기 테스트 | 13 passed |
| 변경한 추적 파일의 `git diff --check` | 통과 |

신규 검증은 실제 FastAPI 기본 앱·ASGITransport·JWT 서명/쿠키·기존 인증 서비스·
require_admin 정책과 mapper를 사용한다. 저장소 및 콘텐츠 응답은 대역이며 다음을 확인한다.

- 8개 실제 경로의 활성 관리자 성공, private 원본 응답 및 검증된 요청자 ID 전달.
- 일반 사용자·suspended/banned 관리자·지원하지 않는 moderator 역할 및 사용자 미존재 차단.
- 기본 쿠키 인증에서 일반 사용자, 정지 사용자, 폐기 세션, 누락/위조 쿠키 및
  인증 미설정의 거절. 거절 시 콘텐츠 query/command 미호출.
- 외부 인증 주입의 성공/거절, 인가 DB 팩토리 미설정 503, 독립 라우터의 미설정 503.
- 두 PATCH의 Origin/CSRF 누락 차단, 본문 owner_id 위조 무시, 같은 쿠키의 역할 회수 반영.
- 인가 조회의 autobegin과 업무 세션 분리/정리, 저장소 오류 전파, owner 의존성 중복 인증 없음.
- **실제 기존 상태 변경 서비스**를 통해 본인 소유 쓰기 트랜잭션 성공과 타인 원본 404,
  소유자 조건/행 잠금 전달 및 거절 시 저장 미호출. 일반 `/lorebooks/me`도 계속 허용.
- 현재 라우트에서 사용하지 않는 product 관리자 훅도 별도 probe로 동일 정책 확인.

전체 실행에서 TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL/TEST_MAILPIT_URL을 자식 실행
환경에서 제거했다. 425 skip은 실제 DB·외부 환경 등 opt-in 검증이며 통과로 계산하지
않는다. 이번 작업은 DB 마이그레이션이나 실제 운영 설정을 변경하지 않았다.

첫 기본 sandbox 실행은 Windows asyncio 초기화에서 출력 없이 멈춰 중단했다.
로컬 소켓이 허용된 실행으로 동일 신규 테스트 108건을 먼저 통과했고, 외부 인증 성공 및
product 훅 10건을 추가한 뒤 최종 전체 API에서 118건을 모두 통과했다. 품질 명령은
workspace의 별도 basetemp를 사용해 기본 sandbox에서 통과했다.

실제 PostgreSQL의 현재 역할 갱신·격리/동시성, 브라우저/프록시·운영 인증 제공자,
관리자용 화면은 이번 검증 범위가 아니다. 기존 로어북 422 상수의 Starlette 폐기 예정
경고 2건은 전체 회귀에 남아 있으며 테스트 실패는 없다.
