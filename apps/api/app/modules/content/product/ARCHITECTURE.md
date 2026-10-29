# Product 모듈

## 소유 데이터

`product_tags`, `product_internal_tags`: 작품의 현재 공개/내부 태그 연결. 공통 사전 `tags`는 content/tag 영역이 소유한다. ORM은 `app/db/models/tag.py`에 분리한다. 공개 연결은 표시 순서·부여 사용자, 내부 연결은 admin/system 출처·부여 사용자·갱신 시각을 기록한다. 양쪽에서 같은 사전 ID를 사용할 수 있고 연결은 작품·태그당 각 테이블에 한 행이다. 관리자 지정값은 시스템 쓰기/삭제에서 보호하며 DB만으로 인가를 보장하지 않는다.

normalized_name·동의어 통합·개수 제한·태그 snapshot은 없다. 작품 삭제는 연결만 CASCADE하고 연결된 사전 항목 삭제는 RESTRICT한다. 부여 사용자 삭제는 assigned_by를 SET NULL하되 연결은 보존한다. 공개 태그는 작품의 현재 분류 정보로 사용하며 내부 태그는 운영/추천에 사용한다. 공개 태그 전용 API가 현재 연결을 조립하며 기존 콘텐츠 응답·목록·발행 snapshot 구조는 유지한다.

`product_studio_drafts`: 상품별 스튜디오 편집 문서(JSONB), revision·digest, 최초 발행 digest·결과. 상품 삭제 시 함께 삭제된다.

`products`, `product_characters`, `product_lorebooks`, `product_lorebook_characters`, `product_start_sets`; `product_snapshots`, `product_snapshot_characters`, `product_snapshot_lorebooks`, `product_snapshot_lorebook_characters`, `product_snapshot_start_sets`, `product_snapshot_policy_changes`; `product_release_notes`, `product_release_note_revisions`; `product_daily_stats`, `product_version_daily_stats`, `product_user_daily_activity`, `product_version_user_daily_activity`, `product_stats_dirty_days`.

이름이 product로 시작해도 `product_generations`는 chat, `product_payment_events`는 billing 소유다. 통계의 도메인 간 사실 수집은 최상위 `app/use_cases/product_statistics.py`가 공개 service로 처리한다. product는 수집된 값만 받아 집계·저장하며 chat에 대한 역방향 의존성이 없다. 타 모듈 인가 JOIN 예외는 없다.

## 파일별 책임

- `service/command/__init__.py`: draft 생성·수정·삭제, identity 인가를 거친 관리자 정책 변경.
- `service/command/composition.py`: 구성 검증·변경. 캐릭터·로어북 소유권과 잠금을 각 공개 서비스로 확인한다.
- `service/command/settings.py`: 모델·시작 항목·대체 정책 설정. `_validate_*`는 같은 모듈의 발행에서 쓰는 내부 검증이다.
- `service/command/studio.py`, `service/query/studio.py`, `repository/studio.py`: 소유권 확인 후 스튜디오 JSON 문서를 비교 갱신하거나 조회한다. revision 충돌은 409, 동일 문서 재전송은 같은 결과다. 최대 2 MiB다. 발행 결과를 문서 digest와 함께 기록해 응답 유실 재호출을 복구한다. 현재 구현은 발행 후 변경 문서도 저장하며 이미 발행된 상품의 프로필/태그는 이 저장에서 변경하지 않는다. 상위 `use_cases/studio_publication.py`는 재발행 경로를 포함한다. 과거의 재발행 거절 문서/테스트와의 계약 불일치는 감사 U06으로 남아 있다. 실제 교차 도메인 조합은 최상위 use case가 소유한다.
- `service/command/publication.py`: 잠긴 소스의 발행 스냅샷 조합 및 digest. 상위 publish 유스케이스가 트랜잭션을 소유하며 character/lorebook freeze도 같은 범위에 참여한다.
- `service/command/releases.py`: `publish_product`, `correct_note`; 내용·미디어 비교에 따른 업데이트 정책과 릴리스 노트 이력.
- `service/command/statistics.py`: 수집된 사실의 집계·저장, 상위 트랜잭션의 작업 잠금·완료, 최근 날짜 재요청을 담당한다. 도메인 간 수집 및 배치 반복은 최상위 product_statistics 유스케이스로 이동했다.
- `service/command/statistics_queue.py`: 다른 모듈이 통계 갱신을 요청하는 Command 경계. queue SQL은 product repository 소유다.
- `service/query/`: 자기 데이터의 소유자/공개 접근 조회, 구성 및 통계 조회. `service/views/`: 공개 snapshot·LLM·conversation 결과를 조합한 SnapshotRuntimeView, PublishedProductView, PendingUpdatesView, VersionAvailabilityView, MediaReferenceView.
- `service/views/media.py`: `ProductMediaService.read_product_media(ReadProductMediaCommand)`는 기존 상품 접근 정책, 상품/버전 소속, 버전 만료를 검사하고 해당 버전의 캐릭터 스냅샷 ID를 character 공개 미디어 서비스에 전달한다. 결과는 공개 `AssetReadInfo`이며 adapter·character repository/ORM을 참조하지 않는다. HTTP 바이너리 경로는 `app/http/media.py`에 추가 조립했다.
- `repository/`: core, composition, publication, releases, statistics로 저장 책임을 분리했다. `__init__.py`는 같은 모듈의 저장소 진입점을 재노출한다.
- `mapper/persistence.py`: Row/Entity와 공개 Info의 순수 변환. `mapper/statistics.py`: 전달받은 사실 데이터의 집계·표현 변환. DB, 시계, 공급자 호출은 하지 않는다.
- `router.py`, `mapper/schema.py`, `schemas.py`: HTTP 계약. `statistics_job.py`: 배치 실행 조립 코드.

## 트랜잭션과 반환 계약

`ProductMediaService`의 기존 `sessions` 생성자 인자/속성은 호환을 유지하며 타입은
`app.db.types.SessionFactory`로 표현한다. 읽기 범위·인가·세션 종료 시점은 동일하다.

Command는 최상위 `use_case_transaction`을 시작하거나 명시적으로 조합된 동일 범위에 참여한다. 내부 commit은 없다. 잠금 순서는 상품 → 캐릭터 → 로어북이며 각 소스 ID를 정렬한다. 발행 중 실패하면 원본 스냅샷·상품 링크·릴리스 노트를 함께 롤백한다.

작성/설정/구성 변경은 Info를, 발행은 ReleaseInfo를 반환한다. 삭제는 None이며 발행 이력이 있으면 삭제를 거절한다. 배치 처리 결과는 ProcessedStatisticsInfo이다. 릴리스 목록의 `(ProductSnapshotInfo, ReleaseNoteInfo | None)`은 명시적인 값 조합 계약이며 ORM Row가 아니다.

statistics의 조회와 일부 command 모듈의 명시적 재노출은 이전 Python import 호출부의 호환 진입점이다. 통계 rebuild_day/process_pending 호출부는 `app/use_cases/product_statistics.py`로 이동해 도메인 간 순환 호출을 추가하지 않았다. HTTP DTO 이름은 기존 OpenAPI와 생성 클라이언트 계약을 보존하기 위해 유지했다. 상품 구성, 발행, 통계는 변경 이유와 의존성이 달라 분리했으며 줄 수를 기준으로 자르지 않았다.

상품에 독립적인 파일 테이블/업로드 기능은 없다. 상품 미디어는 캐릭터 스냅샷을 통해 참조하므로 product 테이블에는 추가 컬럼이 필요하지 않다. character의 스냅샷 미디어 FK가 불변 저장소 객체를 보존하며, 초안 수정·삭제·다음 게시·버전 만료는 이전 파일을 삭제하지 않는다. 상품 미디어 접근은 인증된 소유자 또는 기존 approved + public/unlisted 접근 정책을 그대로 따른다. 공개 버킷/ACL, 서명 URL, 익명 파일 접근은 추가하지 않았다.

`app.main`이 세션/미디어 저장소와 일반 소유자의 실제 쿠키 인증을 연결한다. 운영 스케줄러 배포는 환경 연결 범위다. 운영/이전/롤백 절차는 `references_document/reference/character-product-asset-storage.md`에 있다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: 초안 command → composition → settings → releases/publication → views/snapshots → conversation 시작/전환. 저장 동작은 repository의 같은 책임 파일로 내려가고, 공개 응답은 mapper/schema와 schemas에서 확인한다.

발행은 요청 키 기반 멱등 API가 아니다. 같은 내용을 다시 발행하는 것과 구성요소 스냅샷을 재사용하는 것을 구분한다. 접근 가능한 상품(owner 또는 approved 비private) 조회와 버전 만료 검사는 별도 경계다. 시작 옵션의 원본 entry ID와 발행 start ID도 다르다.

통계는 `use_cases/product_statistics` → 각 도메인 facts → mapper/statistics → repository/statistics 순서로 읽는다. 환불은 원매출 귀속일, 활성 사용자는 기간 중복 제거, 금액은 통화별로 확인한다. 관련 테스트는 `test_product_*` 전반이며 파일별 계약은 전체 점검 안내에 연결했다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.

공개 목록 `GET /products/catalog`은 승인된 public 발행본만 생성 시각·ID 내림차순으로 조회한다. 커서는 두 값을 함께 전달한다. 초안·비공개·링크 공개·최신 버전 만료 상품은 목록에 포함하지 않는다. 제목·설명·snapshot_id는 목록 조회 당시 최신 발행본에서 읽는다.


## 사용자 영역별 reporting 조회 연결 (2026-10-15)

기존 통계 저장·worker·get_statistics 계약은 유지한다.
service/query/reporting.py에 get_owner_reporting_statistics,
get_admin_reporting_statistics, get_recorded_service_statistics, get_statistics_queue를
추가했다. repository/reporting.py는 product 소유 통계 테이블만 읽고
mapper/reporting.py는 revenue를 제외한 집계·누락 날짜·dirty·갱신 범위를 변환한다.
역방향으로 reporting 모듈을 import하지 않는다. 데이터 소유권/마이그레이션 변경은 없다.

소유자 조회는 최신 활성 상태와 소유권, 관리자 조회는 최신 active admin과 작품 존재,
공통 읽기는 snapshot의 작품 소속을 확인한다. 날짜는 서울 기준 포함 최대 731일이다.
일별 active_users를 더하지 않고 activity에서 기간 DISTINCT를 조회한다. 전체 서비스
조회도 작품 간 DISTINCT를 사용한다. parent 일별 집계 없는 날을 0으로 만들지 않고,
parent 집계가 있는 무활동 버전만 0으로 표현한다. 누락/dirty가 있으면 확정 totals는 None이다.
recorded_totals는 기록된 부분 합계이고 oldest/newest_updated_at은 포함한 행의 갱신 범위다.
전체 registry의 과거 집계 완전성은 증명하지 않는다. 집계 없는 생성/발행 이전 날짜도
보수적으로 missing 처리한다. 금액/신고/내부 태그/개인정보는 이 경계에서 반환하지 않는다.

새 공개 조회는 no_autoflush에서 read만 수행한다. 기존 source 사실별 시간 기준은
완료 생성 finished_at, 방 생성/버전 전환 created_at, usage.created_at이다. payments의
attributed_at 매출은 새 reporting 반환에서 제외한다. 조회 간 일관된 스냅샷이 필요하면
호출자가 읽기 전용 REPEATABLE READ를 제공한다. 큐 요청 시각은 재요청으로 갱신되므로
min(requested_at)은 최초 적체 시각이 아니다.


## 현재 태그 관리

생성 Command/DTO의 선택 tags로 공개 태그를 생성 트랜잭션에 함께 연결한다. 미지정/빈 목록은 기존 생성 동작이다. 공개 태그 전용 API는 조회·추가·전체 교체/정렬·해제를 제공한다. 연결을 제거해도 사전 항목은 남는다. 태그 수정은 현재 연결에 즉시 반영하고 발행 snapshot에는 넣지 않는다.

`service/tags.py`는 부모 잠금·인가·트랜잭션 및 사전 공개 service 호출을 소유한다. `mapper/tags.py`는 연결 Entity → 값, 사전 Info와의 조합만 담당한다. `mapper/tag_schema.py`는 HTTP 요청/응답 변환이다. 연결 SQL은 해당 모듈 repository에 있고 tags 테이블을 직접 읽거나 JOIN하지 않는다. 내부 쓰기는 admin/system 출처를 분리하고 관리자 source를 시스템이 덮어쓰거나 제거하지 못한다. 시스템 Command는 신뢰된 애플리케이션 호출 전용이며 HTTP에 노출하지 않는다. 관리자는 identity.require_admin으로 재검증한다. 공개 응답에는 내부 태그가 포함되지 않는다.

공개 조회는 기존 get_accessible_product와 같은 소유자 또는 approved + 비private 정책을 따른다. 기존 ProductWriteRequestDto의 tags 생략/NULL은 수정 시 유지, []는 모두 해제다. 스튜디오 저장의 work.tags도 현재 연결에 반영하고 필드 생략 시 유지한다. 기존 생성·상세 응답의 구조는 바꾸지 않는다.

API 경로·예제·검증은 [태그 관리](../../../../../../references_document/reference/content-tags.md)에 정리했다.

## 기본 CRUD·조회 타입 정리 (2026-10-27)

repository/core.py, service/command/__init__.py, service/query/__init__.py의 3개 파일을
엄격 검사 범위에 추가했다. 기존 패키지 구성과 __init__ 공개 함수 위치를 유지한다.
원본의 단건 조회/수정은 Product 또는 None, 생성/저장은 Product, 삭제는 None이다.
목록은 list, 카탈로그는 기존 SQL Row 쌍을 유지하고 CatalogRow 별칭으로 표현한다.
단건의 기존 scalar 호출과 SQL·잠금·populate_existing을 유지하며, SELECT가 투영하는
Entity 타입을 저장소 경계의 지역 변수에 명시한다. COUNT는 GROUP BY가 없으므로
non-null 한 행을 반환한다는 불변 조건을 assertion으로 표현한다.

프로필 생성·수정은 title/description/opening_message/visibility를 명시적으로 전달한다.
상태·모델·발행 링크는 프로필 수정으로 덮어쓰지 않는다. 기본 상품/상태/스냅샷 mapper도
명시적 필드 매핑을 사용하며 JSON의 깊은 복사는 유지한다. 단건 product mapper의 None은
None으로 변환한다. 쓰기 서비스는 앞에서 잠근 원본이 갱신 뒤에도 존재한다는 불변 조건을
Info의 assertion으로 표현한다. 기존 has_publication은 심사 상태와 독립적인 발행 링크 존재다.

조회 서비스의 세션·현재 시각·반환 타입과 필요한 mapper 계약을 보완했다. snapshot 조회
저장소의 단일 함수도 타입을 명시했다. mapper/persistence.py 전체, repository/publication.py
전체 및 types.py 전체는 아직 엄격 검사 범위가 아니다. 스튜디오·통계·구성·발행 JSON 등
후속 타입 진단을 숨기거나 타입 검사 편의를 위해 파일을 분리하지 않았다.

test_product_core_contracts는 최소 SQLite 스키마로 소유자 검색·COUNT·offset과 동률 ID 정렬,
잠금 옵션을 사용하는 조회의 캐시 갱신·미존재, 프로필 쓰기와 정책 JSON 격리, 실제 카탈로그
SQL Row·발행 제목·커서·스냅샷 복사를 확인한다. FK·PostgreSQL 잠금 경쟁 검증은 아니다.

## persistence mapper·공개 types 정리 (2026-10-27)

types.py와 mapper/persistence.py 전체를 엄격 검사 범위에 추가했다. 스튜디오 Entity,
구성/발행 Row와 Entity 목록, 공개 component Info 및 notice의 입력을 명시한다.
생성·시작 옵션·일별 통계·원본/발행 구성의 동적 필드 복사를 명시적 매핑으로 바꿨다.
원본 ID·구성 링크 ID·발행 슬롯 ID의 의미, 목록/tuple 순서, 노트 없는 업데이트 제외,
JSON 깊은 복사 및 None 표현은 유지한다. scope/role Literal cast는 DB CHECK 제약에
근거를 둔다. 스냅샷 JSON cast는 기존 create/finish 저장 필드를 표현하며 런타임 검증을
추가하거나 과거 확장 데이터를 삭제하지 않는다.

금액 문자열·매출/환불 건수와 통계 카운터는 RevenueValues/StatisticsMetricsValues로
표현한다. 통화별 dict와 금액 문자열의 정확한 표기, 통계 사실 tuple의 순서·UUID·정수·
Decimal·payment ID 목록을 보존한다. 통계 집계 로직과 통화 연산 정책은 이번 범위가 아니다.
StatisticsBuildInfo와 ReplaceStatisticsDayCommand의 bare dict/tuple도 이 계약으로 표현한다.

편집 문서·컴포넌트 매핑·발행 영수증·대체 정책은 재귀 JSON 객체 범위로 표현한다.
문서 버전별 검증은 기존 workflow/service의 책임이다. ProductSnapshotData는 발행 profile의
키를 표현하고 기존 선택 필드·확장 필드를 보존한다. 공유 ORM의 동적 JSON 선언과 다른
mapper/repository/service의 타입 진단까지 완료한 것은 아니다.

StartOptionInfo.title은 기존 DB/SnapshotStartInfo에서 실제 전달되는 str | None을
표현한다. None을 빈 문자열로 보정하지 않는다. HTTP DTO의 문자열 제약과 충돌하는 기존
[F02](../../../../../../references_document/backend_review/findings.md#f02-제목-없는-시작-항목의-응답-검증-실패)는 별도 동작 수정 과제로 남아 있다.

test_product_mapping은 구성 ID/순서·역할, 편집 문서와 발행 영수증의 중첩 변경 격리,
통화별 금액 문자열과 일별 수치, nullable 시작 제목과 발행 프로필 표시를 확인한다.

## 구성 저장소·구성/설정 서비스 타입 정리 (2026-10-27)

repository/composition.py, service/command/composition.py, service/command/settings.py,
service/query/composition.py를 엄격 검사 범위에 추가했다. 세션·UUID·구성/설정 값과
로어북 시작 항목 Info 목록, 모델 검증 Info 반환, 발행 전 검증의 기존 tuple 반환을 명시한다.
업무 요청 Command는 ID와 잠금 옵션을 키워드로 구성하고 기존 공개 인자명은 유지한다.

저장소의 characters_by_source_id/lorebooks_by_source_id는 원본별 기존 Entity,
character_link_ids_by_source_id는 원본 캐릭터와 상품 구성 링크 ID의 대응이다.
character_link/lorebook_link와 selection을 구별해 같은 row 변수가 다른 Entity를 가리키지
않게 했다. 유지되는 원본의 링크 ID 재사용, 대상 링크 삭제 후 재생성, 대표 플래그 해제 후
flush, 신규 대표 설정 후 flush의 기존 순서를 유지한다. SQL·조회 정렬·FK 정책은 유지한다.

설정 저장은 상품 잠금 아래 기존 상품이 존재한다는 assertion을 명시한다. 정책 JSON의
scope/model_ids/unavailable 키와 문자열 UUID, 요청 시작 항목의 sort_order를 유지한다.
상품 → 캐릭터 → 로어북의 소유권/잠금 확인과 모델·구성 범위의 시작 항목 검증은 기존과 같다.

test_product_composition_contracts는 SQLite의 대표 캐릭터 부분 유일 인덱스로 전환 순서,
기존 링크 재사용·제거·대상 재구성, 설정 JSON/시작 순서를 확인한다. 서비스 대역을 사용해
각 소유권 확인 실패 시 저장 미호출, 시작 항목 범위 검증 및 트랜잭션 종료를 확인한다.
최소 SQLite 스키마이므로 PostgreSQL FK cascade·잠금 경쟁을 검증한 것은 아니다.

## 발행·릴리스 타입 정리 (2026-10-27)

repository/publication.py, repository/releases.py, service/command/publication.py,
service/command/releases.py를 엄격 검사 범위에 추가했다. 세션·UUID·스냅샷 본문·구성 Info·
시작 항목 Info·노트 입력과 Entity/ID/미디어 manifest/릴리스 결과를 명시한다.
ReleaseRow는 기존 SQL Row이며 OUTER JOIN의 노트 부재 None을 표현한다. 해당 cast는
SQLAlchemy의 외부 JOIN 엔티티 nullability 표현 한계에 근거하고 실제 SQL은 유지한다.

발행 builder는 구성 Row와 생성/완료 스냅샷 Row를 구분한다. 원본 링크→스냅샷 슬롯 ID
사전과 원본 ID 사전을 역할별로 명명한다. digest 입력 구조는 내부 TypedDict로 표현하고
필드명·정렬·json.dumps(sort_keys=True, ensure_ascii=False) 및 SHA-256 입력을 유지한다.
최종 본문은 기존과 같이 profile을 얕게 복사하고 선택 scene 옵션, digest를 순서대로 넣는다.
저장소는 TypedDict 본문을 dict로 전달하며 반환 Info의 깊은 복사 정책은 그대로다.

모델·reasoning 설정/시작 항목의 검증과 원본 잠금, 생성/정정 대상의 존재는 근거를 붙인
assertion으로 표현한다. scene 옵션 cast는 기존 JSONB metadata의 개방형 JSON 값 경계다.
실행 시 검증을 대신하지 않는다. 발행 버전 증가·소스 잠금·flush/트랜잭션 소유권,
내용/미디어 제거 비교, automatic/choice 정책 및 정정 전 노트 이력 저장은 유지한다.

test_product_publication_contracts는 SQLite에서 실제 발행 슬롯과 digest 본문, latest 링크,
OUTER JOIN의 노트 부재·버전 범위·정정 이력을 확인한다. 정책 테스트는 초기/미디어/내용
변경과 미디어 제거의 결과를 서비스 대역으로 확인한다. 외부 character/lorebook freeze와
모델 조회는 대역이며 PostgreSQL 발행 동시성·FK·잠금 경쟁 검증은 아니다.

## 스튜디오 저장·조회 타입 정리 (2026-10-27)

repository/studio.py, service/command/studio.py, service/query/studio.py를 엄격 검사에
추가했다. 저장소의 Entity/None과 생성·갱신 Entity 반환, nullable publication_digest,
JSON 문서·영수증 입력과 세션/UUID/버전 타입을 명시했다. scalar 조회와 잠금·refresh·
flush 순서, digest 직렬화/크기 제한, 동일 문서 우선 재전송과 revision 비교는 유지한다.
단건 draft mapper의 None/Info overload로 결과 타입을 연결한다.

스튜디오 JSON 태그는 배열/문자열 요소 형태를 좁혀 tuple Command로 전달한다. 잘못된
형태는 기존 태그 서비스와 같은 ValueError로 거절하며 공백/trim/중복 정책은 태그 서비스에
남는다. 공개 범위 라벨 조회는 기존 raw JSON의 미등록/잘못된 값 처리도 유지한다.
원본 존재 확인과 메타데이터 저장 뒤 행 존재는 검증·잠금에 근거한 assertion으로 표현한다.

기존 test_studio_draft_guard의 불완전한 SimpleNamespace를 실제 Product/StudioDraft로
보완했다. 기대 예외·저장 미호출 검증은 유지한다. 이 테스트는 이제 필드 누락 대신
거절 예외 미발생으로 실패하며, 감사 U06의 문서/테스트와 현재 재발행 구현 충돌을 드러낸다.
운영 재발행 장애로 단정하거나 타입 정리 중 거절 정책을 복원하지 않는다.

test_product_studio_contracts는 revision/digest·재전송·소유권/삭제 충돌, profile/태그 투영,
영수증/컴포넌트 매핑의 버전 보존과 조회 잠금 요청을 확인한다. SQLite 저장소 검사는 생성·
갱신·publication_digest=None·캐시 갱신을 확인하며 PostgreSQL advisory/row lock 경쟁을
검증하지 않는다. 외부 발행 조합/재시도 전체의 검증 완료를 의미하지 않는다.

## 스냅샷·안내·미디어 views 타입 정리 (2026-10-27)

service/views/ 전체 4파일을 엄격 검사 범위에 포함했다. runtime/안내/미디어 참조 함수의
세션을 AsyncSession으로 명시하고 snapshot ID Command의 입력과 lorebooks 지역 이름을
정리했다. 이미 타입이 충분한 ProductMediaService도 직접 검사한다. 기존 sessions
생성자/속성, 공개 함수와 입력·반환 형태는 유지한다.

get_pending_updates는 조회된 대화의 필수 RESTRICT 상품 FK에 따른 기존 부모 존재 가정을
assertion으로 드러낸다. 원본이 없으면 기존처럼 안내 조합을 성공시키지 않는다. 대화 삭제와
상품 삭제가 읽기 사이에 경합하는 정책/동시성 보장은 별도 설계 과제이며 새 잠금은 추가하지
않았다. 새 404/빈 업데이트 정책으로 바꾸거나 부모 누락을 숨기지 않는다.

runtime은 이미 접근·만료를 확인한 호출자가 지정한 snapshot 링크로만 character/lorebook
공개 조회 결과를 조합한다. 공개/버전 안내는 기존 만료 정보도 표시하고 실행용 미디어는
접근·만료·버전 소속을 확인한다. 미디어는 DB 세션 종료 후 character 스냅샷 읽기로 넘기며
반환 reader를 닫는 책임은 호출자에게 있다. 기존 소유자·대화 소유권·상품 소속 조건은 유지한다.

test_product_views는 source 삭제 후 snapshot ID 조합, 미발행 조회 거절, 만료 버전 안내,
legacy 대화/부모 누락의 실패, 노트 없는 업데이트 제외, 소유자·버전 소속 검증과 미디어
접근/만료/소속 실패 시 읽기 미호출, 세션 종료 뒤 읽기·reader 소유권을 확인한다.
서비스 대역과 실제 AsyncSession 수명 검증이며 DB·외부 모델/저장소 연동 검증은 아니다.

## 태그 저장소·서비스·mapper 타입 정리 (2026-10-27)

repository/tags.py, service/tags.py, mapper/tags.py, mapper/tag_schema.py를 엄격 검사에
추가했다. 저장소의 세션·UUID·순서/제거용 Sequence·nullable 시스템 actor, Entity/목록/
None 반환을 명시한다. scalar와 SQL·잠금·populate_existing·upsert 조건은 유지한다.
서비스는 ProductStateInfo로 대상 존재/소유권을 판단하며 사전 데이터는 tag 공개 서비스로
읽는다. mapper는 Entity/Info의 Iterable을 받아 기존 tuple/list로 변환한다.

관리자/시스템 Command와 source의 대응을 overload로 표현한다. 관리자 분기의
isinstance assertion은 내부 호출 불변 조건이며 공개 entry point가 이를 보장한다.
retained_tag_ids/requested_tag_ids/protected_tag_ids/actor_id/tags_by_id/sort_order로
역할을 명확히 하고 Command는 키워드로 구성한다. 새로운 추상 계층은 추가하지 않는다.

공개 조회는 소유자 또는 approved + 비private인 기존 조건을 유지한다. public뿐 아니라
unlisted도 이 조회에 포함되며 공개 catalog 목록의 조건과 혼동하지 않는다. 공개 쓰기는
소유자만 허용하고 내부 쓰기에는 관리자 재검증·시스템의 관리자 지정 보호를 유지한다.
재정렬 시 기존 assigned_by/created_at 보존, 비활성 유지/신규 연결 제한, 원본 연결만
변경하는 태그/스냅샷 분리 정책도 유지한다.

추가 회귀는 소유자/승인/공개·링크 공개·비공개 조합 7건과 비소유자 쓰기 거절을 확인한다.
SQLite 부모 조회 검사는 캐시 갱신/미존재를 확인한다. 기존 태그 테스트가 재정렬·정확한
이름·비활성 유지·관리자/시스템 보호·롤백·HTTP 변환을 확인한다. 실제 PostgreSQL upsert
경합·부모 잠금 경쟁·FK 검증은 기존 DB 통합 테스트 범위이며 이번 오프라인 실행에선 미검증이다.

## 통계 집계·저장·큐 타입 정리 (2026-10-27)

mapper/statistics.py, repository/statistics.py와 command/statistics.py,
command/statistics_queue.py, query/statistics.py를 엄격 검사에 추가했다.
세션·상품/버전 UUID·날짜·재생성 입력·작업 Entity/Info·None 반환을 명시한다.
repository의 StatisticsReportRow는 일별 Entity 목록·기간 순사용자 수·대기 날짜의
내부 전달 타입이다. mapper가 이를 StatisticsInfo로 바꾸며 service는 ORM을 읽지 않는다.

집계 누적값은 StatisticsMetricsValues와 내부 결제/기간 매출 TypedDict로 표현한다.
금액은 통화별 Decimal, 출력은 기존 문자열이며 판매 건수는 결제 ID 중복 제거,
환불 건수는 기존 합산이다. 버전별 사용자 수와 상품/기간 순사용자 수를 구별한다.
완료 상태별 기존 카운터만 집계하며 pending/알 수 없는 상태는 기존처럼 KeyError다.
이를 SQL 조건만으로 배제할 수 있다는 추가 보장은 하지 않는다.

재생성은 상품/날짜의 기존 결과·활동 행을 삭제한 뒤 교체하며 commit은 상위 책임이다.
큐의 requested_at/product_id/day 순서와 FOR UPDATE SKIP LOCKED, upsert 및 삭제 범위는
유지한다. claim/complete도 상위 트랜잭션 범위에 참여한다. enqueue_recent(days)는
서울의 오늘을 포함해 days+1개 날짜를 예약한다. 조회는 소유권·버전 소속·최대 731일을
검사하고 빈 날짜를 합성하지 않는다. 버전 조건은 버전 Entity의 열로 명시한다.

test_product_statistics_contracts의 6건은 정확한 금액·카운터·사용자 중복 제거,
빈 입력/예상 밖 상태, 재생성 반복·기간/버전 필터·대기 날짜, 호출자 롤백,
큐 선택/삭제 및 서울 날짜 예약을 확인한다. SQLite 검사는 FK를 복제하지 않은 최소
테이블을 사용한다. 롤백 검사의 savepoint는 테스트 호출자 소유이며 운영 코드에 도입한
것이 아니다. PostgreSQL 잠금·경합·FK 보장은 이 오프라인 검사로 검증하지 않는다.

## Reporting 조회 타입 정리 (2026-10-27)

repository/reporting.py, mapper/reporting.py, service/query/reporting.py를 엄격 검사에
추가했다. ProductReportingRow는 상품별 또는 버전별 일별 Entity 목록과 부모 집계,
기간 DISTINCT 사용자 수, 대기 날짜를 전달한다. ServiceReportingRow의 object 필드는
집계 14개 열과 큐 2개 열의 내부 tuple 별칭으로 구체화했다. SQLAlchemy Result.tuples()는
실제 Row를 유지하면서 위치별 타입을 표현하며 기존 SQLAlchemy >= 2.0 범위를 지원한다.
공개 types에는 ORM을 추가하지 않았고 service는 raw 결과를 mapper에 전달하기만 한다.

전체 집계의 COUNT는 정수, MIN/MAX 시각은 빈 결과에서 None, bigint SUM은 int/Decimal로
표현한다. mapper는 기존처럼 int로 반환하며 금액/revenue는 결과에서 제외한다.
일별 필드 변환·합산은 명시적 접근으로 바꿨다. GROUP BY 없는 사용자 COUNT의 non-null
반환은 assertion으로 명시했다. 버전 사용자 필터는 버전 활동 Entity의 열로 표현한다.

활성 소유자/관리자 확인, 상품 존재·소유권과 버전 소속 검증, no_autoflush 범위는 유지한다.
pending 우선 상태, 부모 집계가 있는 무활동 버전의 0, 부모 집계 없는 날의 None,
미집계/dirty가 있을 때 확정 totals 미제공, 기간·작품 간 사용자 DISTINCT와 기록된
부분 합계의 범위도 유지한다. 서비스 전체 수집 완료나 조회 간 동일 DB 스냅샷은 보장하지 않는다.

test_product_reporting_contracts의 14건은 SQLite SQL 필터·집계·큐 현황과 빈 집계의
NULL 시각, Decimal 큰 정수의 정확한 변환, 소유자/관리자·버전 소속 거절 및 성공,
잘못된 기간의 조회 차단, no_autoflush 복원을 확인한다. SQLite는 기존 통계 테스트의
최소 테이블을 재사용하며 FK를 복제하지 않는다. 서비스 인가는 공개 경계 대역을 사용하므로
실제 사용자 상태 갱신·PostgreSQL READ ONLY/동시성 검증은 기존 DB 통합 테스트 범위다.

## HTTP 경계 타입 정리 (2026-10-28)

router.py, tag_router.py, mapper/schema.py와 schemas.py를 엄격 검사에 추가했다.
일반/태그 반환을 기존 ResponseDto·목록·None으로 명시한다. catalog-tags와 mine/count의
기존 raw list/dict 응답은 구체적 요소 타입과 response_model=None으로 표현해 자동 응답
검증을 새로 추가하지 않는다. 단독 상품 router의 OpenAPI는 전후 동일하다(16경로·27스키마).
삭제 204의 빈 본문, 인증 의존성·오류 변환·HTTP 필드/인자 이름은 유지한다.

요청으로부터 만든 지역 값은 command로 맞추고 여러 ID/옵션을 받는 Command는 키워드로
구성한다. schema mapper의 캐릭터/로어북 순회 이름을 구체화했다. 스튜디오 DTO document는
dict[str, object]로 자유로운 JSON 본문을 표현한다. 업무용 재귀 JSON 타입으로의 변환은
studio_draft_request_to_command가 맡으며 app/http/studio_publication.py의 저장 경로가
이를 사용한다. HTTP JSON 파싱이 제공하는 값이라는 근거로 이 경계에 cast 1곳을 둔다.
중첩 문자열 trim이나 구조 검증을 새로 도입하지 않으며 구조·크기·digest 검증은 기존
스튜디오 service 책임이다. 직접 Python DTO 생성이 JSON 검증을 대신한다고 보장하지 않는다.

test_product_http의 20건은 태그 4경로, 카탈로그 커서/필터와 raw 응답, 소유자 목록/개수,
태그 생략·null 유지와 빈 배열 해제, 삭제 204, 노트 정책 변경 거절, 스튜디오 JSON 읽기/저장,
통계 날짜/버전·정확한 금액 문자열, 오류 번역과 미설정 의존성의 서비스 미호출을 확인한다.
서비스 대역으로 실제 FastAPI 처리를 확인한 범위이며 DB 인가·외부 연동을 대체하지 않는다.
U06 및 nullable 시작 제목의 F02는 별도 과제로 유지한다. 실행 스크립트와 모듈 전체
검사 편입은 아래 완료 범위를 따른다.

## 모듈 전체 엄격 검사·통계 실행 타입 완료 (2026-10-28)

statistics_job.run(limit: int, repair: bool) -> None을 명시하고 처리 결과 이름은
ProcessedStatisticsInfo에 맞춰 processed_info로 구분했다. 기존 인자명·위치/키워드 호출,
CLI 기본 limit=100·--repair-recent, DATABASE_URL 읽기, 출력 문구를 유지한다.
repair이면 최근 재집계 요청을 먼저 넣고 같은 세션으로 process_pending을 실행한다.
세션의 expire_on_commit=False와 async context 종료 후 finally에서 엔진 dispose 순서도
유지한다. 스케줄러 등록이나 유스케이스 트랜잭션·재시도 정책을 변경하지 않았다.

tools/backend-quality-scope.json은 개별 상품 파일 목록을 product 디렉터리로 묶는다.
전체 43 source files의 mypy와 44 Python 파일의 Ruff 검사가 통과하며 product의
시그니처 기준선 항목은 0개다. 타 디렉터리의 ORM 모델·최상위 use case·공유 HTTP 파일까지
모두 엄격 검사를 끝냈다는 뜻은 아니다. mypy의 follow_imports=silent 정책은 유지한다.

test_product_statistics_job의 5건은 정상 실행의 repair 유무, 재집계 요청/처리 실패,
CancelledError 전달에서 세션 종료 후 엔진 dispose와 원래 예외 전달을 확인한다.
실제 AsyncSession의 연결 없는 트랜잭션·종료를 사용하고 엔진/업무 서비스는 대역이다.
성공 시 기존 처리 건수 문구만 출력하고 실패 시 성공 문구가 없음을 확인한다.
실제 PostgreSQL 연결·큐 경합·반복 취소·운영 스케줄러 실행은 검증하지 않았다.
