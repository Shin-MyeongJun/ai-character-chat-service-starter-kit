# Product 모듈

## 소유 데이터

`products`, `product_characters`, `product_lorebooks`, `product_lorebook_characters`, `product_start_sets`; `product_snapshots`, `product_snapshot_characters`, `product_snapshot_lorebooks`, `product_snapshot_lorebook_characters`, `product_snapshot_start_sets`, `product_snapshot_policy_changes`; `product_release_notes`, `product_release_note_revisions`; `product_daily_stats`, `product_version_daily_stats`, `product_user_daily_activity`, `product_version_user_daily_activity`, `product_stats_dirty_days`.

이름이 product로 시작해도 `product_generations`는 chat, `product_payment_events`는 billing 소유다. 통계의 도메인 간 사실 수집은 최상위 `app/use_cases/product_statistics.py`가 공개 service로 처리한다. product는 수집된 값만 받아 집계·저장하며 chat에 대한 역방향 의존성이 없다. 타 모듈 인가 JOIN 예외는 없다.

## 파일별 책임

- `service/command/__init__.py`: draft 생성·수정·삭제, identity 인가를 거친 관리자 정책 변경.
- `service/command/composition.py`: 구성 검증·변경. 캐릭터·로어북 소유권과 잠금을 각 공개 서비스로 확인한다.
- `service/command/settings.py`: 모델·시작 항목·대체 정책 설정. `_validate_*`는 같은 모듈의 발행에서 쓰는 내부 검증이다.
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

`app.main`이 세션/미디어 저장소를 연결하며 실제 인증 검증기와 운영 스케줄러 배포는 환경 연결 범위다. 운영/이전/롤백 절차는 `references_document/reference/character-product-asset-storage.md`에 있다.
