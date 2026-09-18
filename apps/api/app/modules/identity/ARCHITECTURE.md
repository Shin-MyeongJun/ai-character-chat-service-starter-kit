# Identity 모듈

- 소유 테이블: `users`, `user_oauth_accounts`. 현재 구현은 관리자 인가에 필요한 users 조회만 사용한다.
- `repository.py`: 사용자 Entity 조회.
- `mapper/persistence.py`: UserAccessInfo로 변환.
- `service/query.py`: GetUserCommand를 받는 `require_admin`; 활성 admin인지 판단하며 실패는 동일 LookupError로 처리한다. HTTP 상태 코드는 알지 못한다.
- `service/__init__.py`: 공개 함수 재노출.

Row 필드 해석은 mapper에, 상태·역할 판단은 service에 둔다. 작은 단일 책임이라 추가 파일 분리는 하지 않았다. 타 모듈 JOIN 예외는 없다. 로그인, 토큰 검증, OAuth 및 HTTP 인증 훅 연결은 기존 미구현 범위이며 관리자 DB 검사 구현과 구분한다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: `service/query.require_admin` → repository.get_user → mapper.user_entity_to_access_info → types. 활성 admin 외에는 같은 LookupError이므로 HTTP에서는 공통 오류 변환에 따라 404로 보일 수 있다.

상품/모델 관리 서비스가 이 검사를 호출한다. character/lorebook의 별도 admin/moderator HTTP 훅은 현재 main에서 구현으로 교체되지 않는다. 관련 테스트: `test_product_expiry`, `test_content_actor_routes`, `test_answer_http`. 사용자 전체 인증·상태 정책을 이 관리자 조회만으로 일반화하지 않는다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../references_document/backend_review/README.md)에 모았다.
