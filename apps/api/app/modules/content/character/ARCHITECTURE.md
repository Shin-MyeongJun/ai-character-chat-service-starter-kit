# Character 모듈

캐릭터 원본과 이미지·에셋 및 이들의 발행 스냅샷을 소유한다.

- 소유 테이블: `characters`, `character_images`, `character_assets`, `character_snapshots`, `character_snapshot_images`, `character_snapshot_assets`, `character_media`.
- `service/query.py`: 소유자별 조회, 프롬프트·프로모션 조회, 발행 소스 잠금, 스냅샷·미디어 참조 조회. 조회 요청은 Command, 결과는 Info 또는 명시적인 Info 페이지/목록이다.
- `service/command.py`: 생성·수정·상태 변경·삭제·기본 이미지 선택·`freeze_character`. 쓰기는 `use_case_transaction`으로 조합하며 삭제 성공 시 None을 반환한다. 반복 삭제의 미존재는 기존 LookupError 계약을 유지한다.
- `service/media.py`: `CharacterMediaService.upload_character_media`, `read_character_media`, `read_snapshot_media`, `cleanup_character_media`. DB 예약과 외부 저장소 수명이 필요한 별도 책임이므로 분리했다. `AssetStorageService`와 공개 types만 사용하고 adapter는 참조하지 않는다. `mapper/media.py`는 저장소 예약 Entity를 불변 Info로 변환한다. 기존 JSON 이미지·에셋 추가는 command에서 이 모듈 내부 미디어 연결 함수를 호출한다.
- `repository.py`: 인가 조건을 포함한 원본 조회, 변경 저장, 미디어 및 스냅샷 저장. `CharacterPageRow`, `CharacterPromotionRow`, `SnapshotMediaRow`는 이 계층에만 정의한다.
- `mapper/persistence.py`: 미존재를 포함한 Entity/Row → Info 변환. 서비스는 원본 필드를 읽지 않는다. 스냅샷 JSON은 원본과 공유되지 않도록 복사한다.
- `mapper/schema.py`, `router.py`: 일반 소유자 HTTP 요청·응답. 관리자 조회는 governance/admin, 상태 변경 라우팅은 governance/moderation에서 공개 서비스를 호출한다.

## 경계와 특이 계약

타 모듈은 `service`와 `types`만 사용한다. product는 잠긴 CharacterInfo와 freeze 결과를 받아 자기 스냅샷에 연결한다. 스냅샷의 이미지·에셋 이력은 이 모듈만 조회한다. 인가 JOIN 예외는 없다.

`schemas.py`와 `dependencies.py`는 기존 import 및 FastAPI dependency override 호환성을 위한 재노출이다. 여러 접근 주체가 공유하는 HTTP 표현은 `app/http/contracts/character.py`, 실행 의존성 훅은 `app/http/character_dependencies.py`에 있다. 기존 클래스명·응답 필드와 미설정 인증의 503 동작을 유지한다. 기존 이미지/에셋 추가의 501 스텁은 실제 DB 참조 추가로 구현했다. 기존 URL 요청은 복사·다운로드 없이 보관하고, 신규 업로드의 앱 내부 URL은 소유 캐릭터의 준비된 미디어만 연결한다.

원본 및 미디어 참조 저장은 기존 repository에 유지했다. `character_media`는 캐릭터/계정 삭제 시에도 복구·정리 기록을 보존하도록 cascade FK를 두지 않는다. 영구 객체의 `(storage_kind, storage_id, object_key)`와 콘텐츠 타입·크기·원본 파일명·용도·SHA-256을 보관한다. 원본 이미지/에셋과 각각의 스냅샷에 nullable `media_id` RESTRICT FK를 추가했다. 기존 URL 컬럼은 그대로 남으며 게시 시 FK를 복사한다.

업로드는 소유자 확인 → 요청 UUID 예약 커밋 → 캐릭터/예약 잠금 → 저장 → ready 커밋이다. 같은 요청 키의 내용/메타데이터 변경은 422, 완료 재전송은 기존 결과다. 저장 후 DB 실패는 pending 예약을 유지하고 같은 요청으로 재개하며, 모호한 커밋 직후 보상 삭제를 하지 않는다. 프로세스 취소는 공급자 작업이 끝날 때까지 잠금을 유지한다. 준비된 객체의 재저장·수정은 없고 교체는 새 업로드다. 연결 재전송은 같은 결과를 반환하지만 삭제된 연결을 재생성하지 않는다.

온라인 삭제는 DB 참조만 제거한다. `app.media_cleanup`은 명시적 미디어 ID만 받아 마지막 미디어 갱신 시점이 최소 24시간 이전이고 원본/모든 스냅샷 참조가 없을 때 deleting을 먼저 커밋한 후 파일 삭제 → deleted를 커밋한다. 오류는 전파되고 재실행은 deleting부터 계속한다. 보존된 스냅샷은 만료 여부와 관계없이 정리를 막는다. 기존 URL만 있는 파일은 정리 대상이 아니다.

`app/http/media.py`는 기존 인증 훅을 사용하는 추가 바이너리 업로드/스트리밍 HTTP 조립이다. 소유자 경로는 현재 캐릭터 소유권을 검사한다. 상품 스냅샷 읽기는 신뢰된 product 공개 서비스가 접근 검증한 스냅샷 ID만 받으며 직접 HTTP에 공개하지 않는다. 파일 제공은 `read_asset` reader를 스트리밍하고 연결 종료·오류 시 닫는다. 절대 경로·버킷 URL·서명 URL은 반환하지 않는다. `app.main`이 실제 DB 세션과 저장소를 조립하고 기본 소유자 인증을 identity의 쿠키·CSRF·세션 검증에 연결한다.

운영/이전/롤백 절차는 `references_document/reference/character-product-asset-storage.md`에 있다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: router → command/query → repository → persistence/schema mapper. 업로드는 `http/media.py` → `CharacterMediaService` → asset_storage, 발행은 product → freeze_character → 스냅샷 본문/미디어 저장을 따라 읽는다.

조회마다 소유자 조건이 같지는 않다. owner 없는 관리자/내부 query의 인가는 호출자가 맡으며 공개 캐릭터 목록 쿼리는 visibility 조건을 사용한다. 기본 이미지 최대 하나는 DB 부분 UNIQUE다. 두 번째 기본 이미지 추가의 실패 전달은 별도 점검 F03에 기록했다.

관련 테스트: `test_character_command`, `test_character_query`, `test_character_media`, `test_media_http`, `test_media_migrations`. 파일 저장과 DB 전체의 원자성, 저장소 간 이전을 보장한다고 해석하지 않는다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.
