# Admin 모듈

## U27 빈 파일 정리 (2026-11-02)

0바이트 `router.py`는 import·문자열 로딩·실행/배포 진입점 참조가 없어 제거했다.
HTTP 등록은 계속 `app/http/routes.py`의 기능별 `*_router.py`가 담당한다. 기존 인가
훅·의존성 정체성과 경로는 유지한다. 조사·검증 범위는
[U27 작업 기록](../../../../../../docs/audits/2026-10-26-pattern-standardization/U27-WORKLOG.md)을 따른다.

관리자라는 접근 주체의 HTTP 어댑터와 유스케이스 조율을 담당한다. 직접 소유·접근하는 저장 테이블은 없다. 상품 정책 이력은 product, 모델 대체 이력은 llm이 소유한다.

- `product_router.py`, `model_router.py`: 기존 상품 정책·모델 종료 API.
- `character_router.py`, `lorebook_router.py`: 기존 URL을 유지한 관리자 전역/단건 콘텐츠 조회. 기존 admin 의존성 가드를 유지한다.
- `service/command.py`: 상품 만료/상태 변경을 product 공개 Command로 조율한다. ExpiryChangedInfo, ModeratedProductInfo로 반환한다.
- `mapper/schema.py`, `mapper/character.py`, `mapper/lorebook.py`: 각 관리자 HTTP 표현의 순수 변환.
- `schemas.py`: 관리자 고유 DTO와 app/http/contracts의 공유 콘텐츠 표현.

콘텐츠의 repository/mapper/schemas를 직접 가져오지 않는다. 공개 service/types만 사용한다. HTTP 오류 변환은 HTTP 계층에 두며 product/llm 내부 service에서는 identity 공개 service로 관리자 DB 인가도 수행한다. 인가 JOIN 예외는 없다.

일반 사용자 라우팅과 관리자 라우팅을 분리하되, 공유 DTO 정의와 의존성 함수의 정체성을 유지해 OpenAPI 이름 및 dependency_overrides가 달라지지 않게 했다. U24 이후 기본 앱은 관리자 훅을 쿠키 인증 및 최신 DB의 활성 admin 검사에 연결한다. 독립 라우터의 미설정 훅은 계속 503으로 거절한다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: app/http/routes의 등록 순서 → 각 router → mapper → 공개 product/llm 서비스 또는 content query. character/lorebook 전역 조회는 HTTP 역할 가드에 의존하고, 상품/모델 변경은 도메인 서비스의 identity DB 검사로 이어진다.

U24 이후 authenticate 주입도 검증된 UUID만 제공하며 character/lorebook 관리자는 별도 세션의 DB 인가를 통과해야 한다. 관련 테스트: `test_admin_authorization_http`, `test_content_actor_routes`, `test_product_boundaries`, `test_product_expiry`, `test_architecture_contracts`.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.


## 태그 관리

`tag_router.py`는 /admin/tags 사전 생성·단건 조회·수정·비활성화와 /admin/{products|characters|lorebooks}/{id}/internal-tags 조회·추가·전체 교체·해제를 제공한다. 공통 세션과 검증된 owner 인증 훅을 재사용하며 콘텐츠/tag 공개 서비스가 identity.require_admin으로 최신 DB 역할·활성 상태를 재검증한다. 기존 미연결 character/lorebook 관리자 훅을 우회해 관리자라고 가정하지 않는다. source와 assigned_by는 요청 본문에서 받지 않는다. mapper/tags.py는 공개 Info만 DTO로 변환한다. SQL/콘텐츠 repository/ORM은 참조하지 않는다.

API 및 예제: [태그 관리](../../../../../../references_document/reference/content-tags.md).

## 타입 정리 (2026-10-28)

모듈 전체를 공용 엄격 검사에 편입했다. 태그 router는 목록/단건 DTO와 본문 없는
None 반환을, 상품 정책·모델 종료 router는 기존 DTO/204 반환을 명시했다.
mapper/tags는 공개 TagInfo/InternalTagInfo를 받아 기존 Pydantic from_attributes 변환을
수행한다. 목록 입력은 Iterable로 표현해 기존 tuple/list/generator 소비를 유지한다.
상품 정책 command의 실행 세션은 AsyncSession이다.

여러 ID/행위자/이름을 갖는 Command 생성은 키워드로 구분한다. 기존 target_id·actor_id,
tag_id·names, 만료 시각·reason·status의 값과 source/assigned_by의 서비스 결정 책임은
같다. 반환 DTO·경로·상태 코드·의존성 함수 정체성·오류 변환·관리자 재검증 순서는
유지한다. 새로운 인증 연결·타 모듈 접근·SQL·JSON 검증이나 Any/cast/ignore는 추가하지
않았다. 별도 서비스/mapper 클래스 통합이나 파일 분리도 하지 않았다.

## U24 HTTP 관리자 인가 연결 (2026-11-02)

main이 기존 character/lorebook 관리자 훅과 product 관리자 훅을
`app/http/authorization.py::create_admin_dependency`에 연결한다. 이 HTTP 의존성은
identity 공개 service/types만 사용하며 현재 active admin을 확인한다. 실패는 403이고
콘텐츠 query 호출 전에 끝난다. 별도 인가 세션으로 업무 세션의 트랜잭션을 시작하지 않는다.
공유 함수 정체성·URL·DTO·기존 상품/모델/태그 서비스의 DB 재검증은 유지한다.

소유자 없는 character/lorebook 조회는 이 인증된 내부 호출 경계를 신뢰한다. 역할은
user/admin만 지원하고 검수 권한도 admin에게만 제공한다. 제공 범위·외부 인증 주입·
미설정 거절 계약은 [권한 문서](../../../../../../docs/admin-authorization.md)에 있다.
