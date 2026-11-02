# 관리자·검수 HTTP 권한 (U24)

2026-11-02 기준. `create_app()`은 기존 쿠키 인증과 최신 DB 관리자 인가를 연결한다.
DB 역할은 `user`, `admin`이며 검수 권한도 `status=active`인 `admin`에게만 부여한다.
별도 `moderator` 계정 역할·역할 부여 API·환경변수 관리자 ID 목록은 제공하지 않는다.

## 제공 범위

| 경로 | 활성 관리자 권한 | 일반 사용자 |
| --- | --- | --- |
| GET `/characters`, `/characters/{id}` | 소유자와 무관한 원본 목록·상세(비공개 포함) | 403 |
| GET `/lorebooks`, `/lorebooks/{id}` | 소유자와 무관한 원본 목록·상세(비공개 포함) | 403 |
| GET `/lorebooks/{id}/entries`, `/lorebooks/{id}/entries/{entry_id}` | 원본 항목 목록·상세 | 403 |
| PATCH `/characters/status`, `/lorebooks/status` | 기존 `draft/approved/rejected` 변경. **본인 소유 원본만** | 403 |
| 기존 `/admin/products/*`, `/admin/models/*`, `/admin/tags*`, `/admin/*/internal-tags*` | 기존 상품 정책·모델 종료·태그 관리 서비스의 관리자 검사 유지 | 기존 서비스 거절 유지 |
| 기존 `/admin/reporting/generation-prompts*` | 기존 운영 조회의 관리자 검사 유지 | 기존 403 유지 |

상태 변경의 `owner_id`는 검증된 요청자 UUID다. 본문에 임의의 owner_id를 보내도 인가
또는 저장 대상 소유자로 사용하지 않는다. 다른 소유자·미존재 원본은 기존 404이며,
관리자에게 타인 원본 변경 권한을 새로 부여하지 않는다. `/characters/me`, `/lorebooks/me`
등 일반 사용자 소유자 경로는 기존 정책을 유지한다.

내부 신고·평가·조치 서비스에 신규 HTTP를 노출하지 않는다. `require_product_admin`도
연결하지만 현재 상품·모델·태그 관리 라우트는 기존 공개 서비스의 DB 인가를 사용하므로
이를 새 공통 HTTP 가드로 교체하거나 기존 404/403 오류 계약을 통일하지 않는다.

## 신뢰 경계와 세션

1. 기존 owner 훅이 서명·만료·issuer/audience·서버 세션·현재 사용자 상태를 검증한
   내부 UUID를 제공한다. 상태 변경에는 기존 Origin/CSRF 검증이 적용된다.
2. `app/http/authorization.py`의 의존성은 identity 공개 `require_admin(GetUserCommand)`을
   호출한다. `refresh=True`로 현재 DB의 역할·상태를 다시 읽으며 토큰/헤더/본문의 역할을
   신뢰하지 않는다. 사용자 미존재·일반 사용자·비활성 관리자 모두 HTTP 403 `forbidden`이다.
3. 인가 조회는 `app.state.session_factory`의 별도 세션에서 끝낸 뒤 업무를 호출한다.
   인가 SELECT의 autobegin이 상태 변경의 `use_case_transaction`과 충돌하지 않는다.
4. 소유자 없는 콘텐츠 조회와 기존 상태 변경 공개 서비스는 신뢰된 내부 호출자가
   사용하는 경계다. 직접 Python 호출의 토큰 인증·관리자 인가는 호출자가 책임진다.
   일반 소유자용 상태 변경 서비스 자체의 소유자 검사는 그대로 남는다.

`create_app(authenticate=...)`의 기존 주입 계약은 **검증된 UUID 제공**이다. 이 주입도
DB 관리자 검사를 통과해야 한다. 외부 authenticate의 토큰·세션·CSRF 검증은 주입자
책임이다. 각 원본 owner 훅과 가드의 함수 정체성을 유지하므로
기존 `dependency_overrides`는 계속 동작한다. 명시적으로 가드 자체를 override하는
조립 코드는 인증·인가를 구현할 책임이 있다.

인가 조회 이후 진행 중인 요청의 역할 변경/정지는 소급 취소하지 않는다. 다음 요청은
최신 DB로 다시 검사한다. 별도 인가 세션의 격리 수준은 배포의 DB 설정을 따른다.

## 미설정과 거절

- 기본 앱의 인증 서비스 미설정: 기존 503 `auth_not_configured`.
- 외부 인증 주입 후 인가 세션 팩토리 미설정: 503. 관리자라고 가정하지 않는다.
- 조립되지 않은 독립 라우터: 기존 훅이 503으로 거절한다.
- 기본 쿠키 인증에서 누락/위조/만료 토큰, 폐기 세션, 정지 사용자는 기존 401이다.
  검증된 외부 UUID라도 DB 사용자가 정지 관리자이면 403이다.
- Origin/CSRF 실패는 기존 403이다. DB 장애 등 저장소 오류를 권한 부족이나 성공으로
  숨기지 않는다. 거절된 요청은 콘텐츠 조회·상태 변경 서비스를 호출하지 않는다.

검증 기록: [U24 작업 기록](audits/2026-10-26-pattern-standardization/U24-WORKLOG.md).
