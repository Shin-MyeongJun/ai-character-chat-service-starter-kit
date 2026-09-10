# Moderation 모듈

모더레이터의 콘텐츠 상태 변경 HTTP 경계를 담당한다.

- `character_router.py`, `lorebook_router.py`: 기존 `/characters/status`, `/lorebooks/status` 경로 및 moderation 의존성 가드.
- `mapper/character.py`, `mapper/lorebook.py`: 요청 → 대상 모듈 Command, Info → 공유 HTTP DTO.
- `schemas.py`: app/http/contracts의 동일 콘텐츠 DTO 정의를 참조한다.
- 원본 변경은 character/lorebook 공개 service에 위임하며 직접 저장소를 접근하지 않는다. 인가 JOIN 예외는 없다.

`moderation_flags`, `audit_logs`는 기존 moderation 도메인의 데이터지만 이번 구현이 사용하지 않는 미구현 영역이다. 기존 service/repository 골격을 실제 신고 처리나 감사 기록 구현으로 간주하지 않는다. owner_id 전달과 별도 moderation 가드를 보존하며 인증·권한 정책 자체는 바꾸지 않았다.

관리자 조회와 모더레이터 변경은 접근 주체가 달라 별도 모듈에 두었다. 저장 로직을 복제하거나 빈 업무 계층을 추가하지 않았다.
