# Moderation 모듈

모더레이터의 콘텐츠 상태 변경 HTTP 경계를 담당한다.

- `character_router.py`, `lorebook_router.py`: 기존 `/characters/status`, `/lorebooks/status` 경로 및 moderation 의존성 가드.
- `mapper/character.py`, `mapper/lorebook.py`: 요청 → 대상 모듈 Command, Info → 공유 HTTP DTO.
- `schemas.py`: app/http/contracts의 동일 콘텐츠 DTO 정의를 참조한다.
- 원본 변경은 character/lorebook 공개 service에 위임하며 직접 저장소를 접근하지 않는다. 인가 JOIN 예외는 없다.

`moderation_flags`, `audit_logs`는 기존 moderation 도메인의 데이터지만 이번 구현이 사용하지 않는 미구현 영역이다. 기존 service/repository 골격을 실제 신고 처리나 감사 기록 구현으로 간주하지 않는다. owner_id 전달과 별도 moderation 가드를 보존하며 인증·권한 정책 자체는 바꾸지 않았다.

관리자 조회와 모더레이터 변경은 접근 주체가 달라 별도 모듈에 두었다. 저장 로직을 복제하거나 빈 업무 계층을 추가하지 않았다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: character/lorebook_router → HTTP moderator dependency → mapper → content change_*_status → content repository. owner_id 이름은 이 경로에서 요청 행위자이며 상태 변경 서비스가 대상 소유자 조회와 동일한 정책을 적용한다고 가정하지 않는다.

현재 두 moderator dependency는 기본 503이며 main의 일반 authenticate 주입과 별도 연결이 필요하다. `test_content_actor_routes`는 거절된 가드가 변경 호출을 막는지 확인하고 실제 운영 인증 제공자는 검증하지 않는다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.
