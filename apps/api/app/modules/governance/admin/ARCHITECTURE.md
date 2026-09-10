# Admin 모듈

관리자라는 접근 주체의 HTTP 어댑터와 유스케이스 조율을 담당한다. 직접 소유·접근하는 저장 테이블은 없다. 상품 정책 이력은 product, 모델 대체 이력은 llm이 소유한다.

- `product_router.py`, `model_router.py`: 기존 상품 정책·모델 종료 API.
- `character_router.py`, `lorebook_router.py`: 기존 URL을 유지한 관리자 전역/단건 콘텐츠 조회. 기존 admin 의존성 가드를 유지한다.
- `service/command.py`: 상품 만료/상태 변경을 product 공개 Command로 조율한다. ExpiryChangedInfo, ModeratedProductInfo로 반환한다.
- `mapper/schema.py`, `mapper/character.py`, `mapper/lorebook.py`: 각 관리자 HTTP 표현의 순수 변환.
- `schemas.py`: 관리자 고유 DTO와 app/http/contracts의 공유 콘텐츠 표현.

콘텐츠의 repository/mapper/schemas를 직접 가져오지 않는다. 공개 service/types만 사용한다. HTTP 오류 변환은 HTTP 계층에 두며 product/llm 내부 service에서는 identity 공개 service로 관리자 DB 인가도 수행한다. 인가 JOIN 예외는 없다.

일반 사용자 라우팅과 관리자 라우팅을 분리하되, 공유 DTO 정의와 의존성 함수의 정체성을 유지해 OpenAPI 이름 및 dependency_overrides가 달라지지 않게 했다. 실제 인증 훅은 기존과 같이 미연결 상태에서 503으로 거절한다.
