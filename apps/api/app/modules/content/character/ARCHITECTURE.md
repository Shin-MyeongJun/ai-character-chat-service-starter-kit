# Character 모듈

캐릭터 원본과 이미지·에셋 및 이들의 발행 스냅샷을 소유한다.

- 태그 연결 소유 테이블: `character_tags`, `character_internal_tags`. 사전 `tags`는 content/tag 영역 소유이며 ORM은 `app/db/models/tag.py`에 분리한다. 공개 연결은 sort_order·assigned_by, 내부 연결은 source(admin/system)·assigned_by·갱신 시각을 기록한다. 같은 태그 ID를 양쪽에서 사용할 수 있다. 대상 삭제는 연결만 CASCADE, 연결된 사전 삭제는 RESTRICT, 부여 사용자 삭제는 SET NULL이다. 개수 제한·태그 snapshot은 없고 기존 API 응답/발행 snapshot 구조를 유지하며 태그 전용 서비스가 인가·활성 상태·관리자 지정 보호 정책을 검사한다.
- 소유 테이블: `characters`, `character_images`, `character_assets`, `character_snapshots`, `character_snapshot_images`, `character_snapshot_assets`, `character_media`.
- `service/query.py`: 소유자별 조회, 프롬프트·프로모션 조회, 발행 소스 잠금, 스냅샷·미디어 참조 조회. 조회 요청은 Command, 결과는 Info 또는 명시적인 Info 페이지/목록이다.
- `service/command.py`: 생성·수정·상태 변경·삭제·기본 이미지 선택·`freeze_character`. 쓰기는 `use_case_transaction`으로 조합하며 삭제 성공 시 None을 반환한다. 반복 삭제의 미존재는 기존 LookupError 계약을 유지한다.
- `service/media.py`: `CharacterMediaService`의 읽기·업로드 예약·잠금/상태 검증·정리 조건·첨부 기능. DB 예약과 외부 저장소 수명이 필요한 별도 책임이므로 분리했다. `AssetStorageService`와 공개 types만 사용하고 adapter는 참조하지 않는다. `mapper/media.py`는 저장소 예약 Entity를 불변 Info로 변환한다. 기존 JSON 이미지·에셋 추가는 command에서 이 모듈 내부 미디어 연결 함수를 호출한다.
- `repository.py`: 인가 조건을 포함한 원본 조회, 변경 저장, 미디어 및 스냅샷 저장. `CharacterPageRow`, `CharacterPromotionRow`, `SnapshotMediaRow`는 이 계층에만 정의한다.
- `mapper/persistence.py`: 미존재를 포함한 Entity/Row → Info 변환. 서비스는 원본 필드를 읽지 않는다. 스냅샷 JSON은 원본과 공유되지 않도록 복사한다.
- `mapper/schema.py`, `router.py`: 일반 소유자 HTTP 요청·응답. 관리자 조회는 governance/admin, 상태 변경 라우팅은 governance/moderation에서 공개 서비스를 호출한다.

## 경계와 특이 계약

미디어 서비스 생성자의 `sessions`는 공통 `app.db.types.SessionFactory`로 타입을 명시한다.
기존 인자명과 `self.sessions`는 호환을 위해 유지하며 저장소/스트림 수명이나 잠금은 바꾸지 않는다.

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


## 선택적 미디어 workflow (2026-09-27)

`service/workflow/media.py`의 CharacterMediaWorkflow는 하위 CharacterMediaService의 읽기 계약을 유지하며 업로드/정리 실행만 추가한다. 예약 commit → 캐릭터/예약 잠금 → 외부 저장 종료 대기 → ready commit, deleting commit → 잠금 → 외부 삭제 종료 대기 → deleted commit 순서다. workflow는 repository를 호출하지 않는다. 준비/완료 조건은 하위 service/media.py에 있으며 `_attach_character_media`도 그 위치를 유지하여 command가 workflow를 역호출하지 않는다.

취소가 와도 `_settle_storage`는 실제 공급자 작업 종료까지 기다린 후 취소를 전달한다. 다른 업로드 재시도/GC/첨부가 미완료 외부 작업과 경쟁하도록 잠금을 조기 해제하지 않는다. 명시적 저장소 실패/모호한 DB commit/retention/deleting 재개 계약은 유지한다. main/HTTP/cleanup CLI는 CharacterMediaWorkflow를 사용하고 product 읽기는 하위 서비스의 읽기 계약을 사용한다.


## 현재 태그 관리

생성 Command/DTO의 선택 tags로 공개 태그를 생성 트랜잭션에 함께 연결한다. 미지정/빈 목록은 기존 생성 동작이다. 공개 태그 전용 API는 조회·추가·전체 교체/정렬·해제를 제공한다. 연결을 제거해도 사전 항목은 남는다. 태그 수정은 현재 연결에 즉시 반영하고 발행 snapshot에는 넣지 않는다.

`service/tags.py`는 부모 잠금·인가·트랜잭션 및 사전 공개 service 호출을 소유한다. `mapper/tags.py`는 연결 Entity → 값, 사전 Info와의 조합만 담당한다. `mapper/tag_schema.py`는 HTTP 요청/응답 변환이다. 연결 SQL은 해당 모듈 repository에 있고 tags 테이블을 직접 읽거나 JOIN하지 않는다. 내부 쓰기는 admin/system 출처를 분리하고 관리자 source를 시스템이 덮어쓰거나 제거하지 못한다. 시스템 Command는 신뢰된 애플리케이션 호출 전용이며 HTTP에 노출하지 않는다. 관리자는 identity.require_admin으로 재검증한다. 공개 응답에는 내부 태그가 포함되지 않는다.

공개 태그 HTTP는 기존 /me 콘텐츠 조회와 같은 소유자 정책이다. 일반 소유자 라우터와 관리자 내부 태그 라우터는 분리한다. 기존 생성·상세 응답의 구조는 바꾸지 않는다.

API 경로·예제·검증은 [태그 관리](../../../../../../references_document/reference/content-tags.md)에 정리했다.

## 기본 CRUD 패턴 정리 (2026-10-27)

기본 생성·수정·상태 변경 저장소는 Character, 삭제 저장소는 None을 반환하도록 명시한다.
서비스는 Entity를 persistence mapper로 변환한 Info로 존재·소유권을 판단하며, 기존
use_case_transaction, 소유 캐릭터 FOR UPDATE와 저장소 재조회 순서를 유지한다.
수정의 description/default_model_id=None은 해제이고, 상태 변경은 프로필을 바꾸지 않는다.
생성 시 공개 태그 연결은 같은 트랜잭션에 남고 PublicTagsCommand는 키워드로 구성한다.

query와 persistence/schema mapper 3개 파일을 Ruff/mypy 엄격 검사 범위에 추가했다.
목록 mapper는 Entity의 Iterable을 받아 기존 list를 반환한다. 단건의 None/Info overload와
공개 함수·인자·DTO 이름은 유지한다. 저장소의 기본 CRUD 및 조회 관련 타입도 보완했지만
repository 전체가 엄격 검사를 통과한 것은 아니다.

SnapshotMediaManifestItem은 기존 이미지 4필드/에셋 5필드 tuple을 표현한다. 비교 집합에서
is_default 제외·중복 제거·URL/출처 ID 보존 정책은 그대로다. 스냅샷 JSON은 계속 깊게 복사하며
character_id=None인 보존 스냅샷도 변환한다. JSON 필드별 검증 완료를 뜻하지 않는다.

기본 CRUD 단계 종료 당시 command.py에는 미디어 첨부 함수의 반환 타입 누락에서 오는 기존 mypy 오류 2개가 남아
전체 파일을 strict scope에 넣지 않았다. repository의 버전 계산·미디어/태그 함수,
types의 snapshot_data 구조, media/tags service와 HTTP 라우터도 후속 범위다.
미디어 예약·외부 저장 종료 대기·잠금 수명·정리/재시도 정책은 이번 변경 대상이 아니다.
기존 파일 구성을 유지하고 타입 검사 편의를 위한 인위적인 파일 분리는 하지 않았다.

검증은 기존 character CRUD/SQLite 조회 테스트와 test_character_mapping의 JSON 격리·발행
비교 계약 테스트를 사용한다. 실제 PostgreSQL 잠금·동시성·외부 저장소 검증은 포함하지 않는다.

## 미디어·저장소 타입 정리 (2026-10-27)

위 기본 CRUD 단계의 후속으로 command.py, repository.py, mapper/media.py,
service/media.py, service/workflow/media.py를 엄격 검사 범위에 추가했다.
command의 미디어 반환 오류 2개와 repository의 남은 타입 오류를 해결했다.
세션은 AsyncSession, 조회의 미존재는 None, 미디어 참조 범위는 Sequence[UUID]로 표현한다.
정리 작업의 snapshot_ids=None은 원본과 모든 스냅샷을 검사하고, 지정된 목록은 해당
스냅샷만 검사한다. 빈 목록을 전체 참조 조회로 바꾸지 않는다.

미디어 첨부와 저장소의 image/asset overload는 종류와 Command·Entity·Info의 대응을
표현한다. 구현의 isinstance assertion은 공개 command가 전달하는 이 대응 관계를
명시한다. 미디어 Entity/Info는 getattr 일괄 복사 대신 명시적 필드 대응으로 변환한다.
업로드 완료 시 잠근 예약 행이 상태 갱신 후에도 존재한다는 불변 조건을 assertion으로
표현한다. 외부 저장 종료 대기 함수는 제네릭으로 공급자 작업의 반환 타입을 보존한다.
예약·커밋 순서, 잠금 수명, 취소 후 종료 대기, 재전송·삭제된 연결의 정책은 유지한다.

test_character_media_contracts는 이미지/에셋의 신규 첨부·재전송·삭제된 연결과 SQLite의
원본/허가된 스냅샷 참조 범위를 확인한다. 실제 PostgreSQL 잠금이나 외부 저장 검증은 아니다.
types의 snapshot_data, 태그 service/mapper, HTTP 라우터 등은 후속 정리 범위로 남는다.
follow_imports=silent이므로 이번 파일의 검사 통과가 의존 모듈 전체의 통과를 의미하지 않는다.

## 태그·스냅샷 JSON 타입 정리 (2026-10-27)

service/tags.py, mapper/tags.py, mapper/tag_schema.py, types.py를 엄격 검사 범위에
추가했다. 태그 서비스는 AsyncSession과 업무 Command를 받고 기존 Info tuple 또는
None을 반환한다. mapper는 Entity/Info의 Iterable을 받아 기존 tuple/list를 유지한다.
관리자 Command와 source="admin", 시스템 Command와 source="system"의 대응을 overload로
표현한다. 관리자 분기의 isinstance assertion은 이 내부 호출 불변 조건을 명시한다.
시스템 쓰기는 기존 공개 함수와 같이 추가만 허용하는 타입 계약이다. 관리자 재검증,
부모 잠금, 관리자 지정 보호, 공개 태그 순서, 비활성 태그 유지 및 트랜잭션 정책은 유지한다.

새 스냅샷의 본문은 CharacterSnapshotV2Data로 name/description/persona_prompt를
명시하고 repository에서 해당 필드를 직접 저장한다. 읽기 결과의 snapshot_data는
dict[str, CharacterSnapshotJsonValue]다. 이는 문자열·숫자·불리언·null·배열·객체의
재귀 JSON 값 범위이며, 기존 스냅샷의 확장 필드와 중첩 구조를 그대로 보존한다.
읽기 데이터에 v2의 필수 키가 있다고 단정하거나 과거 버전을 변환하지 않는다.
DB JSONB 디코딩을 경계로 사용하며 공유 SnapshotMixin의 기존 Any 선언이나 저장 데이터의
버전별 실행 검증을 이번에 정리한 것은 아니다. 기존 deepcopy 격리를 유지한다.

검증은 태그 소유권·관리자/시스템 보호·롤백·HTTP 경계의 기존 테스트, 스냅샷의 중첩 변경
격리 및 신규 v2 본문 테스트를 사용한다. None/빈 문자열·원문 공백을 보존하고 소유자·상태·
모델 선택 정보가 스냅샷 본문에 추가되지 않음을 확인한다. HTTP 라우터 및 공유 DB/HTTP
의존 파일 전체는 아직 엄격 검사 완료 범위가 아니다.

## HTTP 경계 타입 정리 (2026-10-27)

character 모듈 디렉터리 전체를 Ruff/mypy 검사 범위에 포함했다. HTTP 계약의 재노출인
schemas.py와 dependency override 호환 파일인 dependencies.py도 포함한다. 공유 파일인
http/character_dependencies.py, http/contracts/character.py, http/contracts/tags.py,
http/dependencies.py도 직접 검사한다. 다른 HTTP/DB 의존 파일 전체가 검증됐다는 의미는 아니다.

태그 조회·추가·교체는 list[PublicTagResponseDto], 삭제는 None을 반환한다고 명시한다.
일반 라우터의 업무 요청 지역 변수는 command로 표현한다. 기존 경로·인자명·의존성 함수와
DTO 재노출, 응답 모델, 204 빈 본문 및 미설정 의존성의 503 동작을 유지한다.
태그의 공유 errors는 Iterator[None]인 contextmanager이며 LookupError→404,
ValueError→422 변환을 유지한다. 일반 character 라우터의 별도 오류 응답 표현도 유지한다.

test_character_http는 실제 FastAPI 요청으로 태그 4개 경로의 응답과 신뢰된 owner/session
전달, 삭제의 OpenAPI 204 응답 본문 없음, 404/422 변환과 미설정 의존성의 503 거절을 확인한다.
서비스는 mock이므로 DB·외부 저장소 실행 검증을 대신하지 않는다.

## 공유 바이너리 HTTP 전송 타입 정리 (2026-10-28)

app/http/media.py의 contextmanager·ASGI scope/receive/send·비동기 byte iterator와
MediaStreamingResponse 반환을 명시했다. main의 미디어 서비스 주입 두 곳과 기본
w+b SpooledTemporaryFile의 BinaryIO 계약만 cast로 연결한다. 새 isinstance 제한·
BinaryIO wrapper·파일 복사나 의존성 실패 기본값은 추가하지 않았다.

32 MiB 수신 한도·1 MiB spool 임계값·다운스트림의 fingerprint rewind·64 KiB 읽기,
업로드 context 종료 시 파일 닫기와 전송 finally의 reader 종료, 소유자/상품 버전 전달·
비공개 캐시/길이/MIME/nosniff/inline 헤더를 유지한다. 읽기 시작 전의 HTTP 오류
변환과 전송 시작 후 예외 전파를 분리하는 기존 경계도 같다. 공용 http 디렉터리 전체를
직접 Ruff/mypy로 검사한 뒤 엄격 범위에 편입했다. asset_storage 어댑터 전체 완료를
뜻하지 않는다.

test_media_transport_contracts는 바이너리 spool의 정상·검증 실패·예외와 수신 한도
초과에서 파일 종료, ASGI 정상·읽기 오류·취소에서 reader 종료, 캐릭터/상품 소유자
전달·응답 헤더/빈 OpenAPI 스키마를 오프라인으로 확인한다. 실제 DB 인가·S3·네트워크
단절·공급자 스레드 정리는 이 HTTP 전송 테스트의 검증 범위가 아니다.
