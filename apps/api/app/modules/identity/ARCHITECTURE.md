# Identity 모듈

- 소유 테이블: `users`, `user_oauth_accounts`. 현재 구현은 관리자 인가에 필요한 users 조회만 사용한다.
- `repository.py`: 사용자 Entity 조회.
- `mapper/persistence.py`: UserAccessInfo로 변환.
- `service/query.py`: GetUserCommand를 받는 `require_admin`; 활성 admin인지 판단하며 실패는 동일 LookupError로 처리한다. HTTP 상태 코드는 알지 못한다.
- `service/__init__.py`: 공개 함수 재노출.

Row 필드 해석은 mapper에, 상태·역할 판단은 service에 둔다. 작은 단일 책임이라 추가 파일 분리는 하지 않았다. 타 모듈 JOIN 예외는 없다. 로그인, 토큰 검증, OAuth 및 HTTP 인증 훅 연결은 기존 미구현 범위이며 관리자 DB 검사 구현과 구분한다.
