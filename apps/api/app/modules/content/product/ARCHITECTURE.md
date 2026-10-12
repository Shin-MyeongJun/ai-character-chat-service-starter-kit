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
- `service/command/studio.py`, `service/query/studio.py`, `repository/studio.py`: 소유권 확인 후 스튜디오 JSON 문서를 비교 갱신하거나 조회한다. revision 충돌은 409, 동일 문서 재전송은 같은 결과다. 최대 2 MiB다. 최초 발행 결과를 문서 digest와 함께 기록해 응답 유실 재호출을 중복 발행하지 않는다. 후속 발행 경로가 없는 동안 이미 발행한 문서의 변경은 409로 거절해 미발행 편집이 상품 공개 설정을 바꾸지 못하게 한다. 실제 교차 도메인 조합은 최상위 `use_cases/studio_publication.py`가 소유한다.
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
