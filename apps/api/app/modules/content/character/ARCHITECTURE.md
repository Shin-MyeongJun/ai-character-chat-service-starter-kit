# Character 모듈

캐릭터 원본과 이미지·에셋 및 이들의 발행 스냅샷을 소유한다.

- 소유 테이블: `characters`, `character_images`, `character_assets`, `character_snapshots`, `character_snapshot_images`, `character_snapshot_assets`.
- `service/query.py`: 소유자별 조회, 프롬프트·프로모션 조회, 발행 소스 잠금, 스냅샷·미디어 참조 조회. 조회 요청은 Command, 결과는 Info 또는 명시적인 Info 페이지/목록이다.
- `service/command.py`: 생성·수정·상태 변경·삭제·기본 이미지 선택·`freeze_character`. 쓰기는 `use_case_transaction`으로 조합하며 삭제 성공 시 None을 반환한다. 반복 삭제의 미존재는 기존 LookupError 계약을 유지한다.
- `repository.py`: 인가 조건을 포함한 원본 조회, 변경 저장, 미디어 및 스냅샷 저장. `CharacterPageRow`, `CharacterPromotionRow`, `SnapshotMediaRow`는 이 계층에만 정의한다.
- `mapper/persistence.py`: 미존재를 포함한 Entity/Row → Info 변환. 서비스는 원본 필드를 읽지 않는다. 스냅샷 JSON은 원본과 공유되지 않도록 복사한다.
- `mapper/schema.py`, `router.py`: 일반 소유자 HTTP 요청·응답. 관리자 조회는 governance/admin, 상태 변경 라우팅은 governance/moderation에서 공개 서비스를 호출한다.

## 경계와 특이 계약

타 모듈은 `service`와 `types`만 사용한다. product는 잠긴 CharacterInfo와 freeze 결과를 받아 자기 스냅샷에 연결한다. 스냅샷의 이미지·에셋 이력은 이 모듈만 조회한다. 인가 JOIN 예외는 없다.

`schemas.py`와 `dependencies.py`는 기존 import 및 FastAPI dependency override 호환성을 위한 재노출이다. 여러 접근 주체가 공유하는 HTTP 표현은 `app/http/contracts/character.py`, 실행 의존성 훅은 `app/http/character_dependencies.py`에 있다. 기존 클래스명·응답 필드·503 동작을 유지한다.

원본과 미디어는 캐릭터 수명 주기를 함께 따르므로 현재 command/repository 파일을 유지했다. 관리자 접근 주체만 별도 모듈로 분리했다. 실제 DB/auth 의존성 연결은 기존 미구현 범위다.
