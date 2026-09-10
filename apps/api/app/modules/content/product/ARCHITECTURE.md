# Product 모듈

## 소유 데이터

`products`, `product_characters`, `product_lorebooks`, `product_lorebook_characters`, `product_start_sets`; `product_snapshots`, `product_snapshot_characters`, `product_snapshot_lorebooks`, `product_snapshot_lorebook_characters`, `product_snapshot_start_sets`, `product_snapshot_policy_changes`; `product_release_notes`, `product_release_note_revisions`; `product_daily_stats`, `product_version_daily_stats`, `product_user_daily_activity`, `product_version_user_daily_activity`, `product_stats_dirty_days`.

이름이 product로 시작해도 `product_generations`는 conversation, `product_payment_events`는 billing 소유다. 해당 사실 데이터는 공개 service를 통해 받는다. 타 모듈 인가 JOIN 예외는 없다.

## 파일별 책임

- `service/command/__init__.py`: draft 생성·수정·삭제, identity 인가를 거친 관리자 정책 변경.
- `service/command/composition.py`: 구성 검증·변경. 캐릭터·로어북 소유권과 잠금을 각 공개 서비스로 확인한다.
- `service/command/settings.py`: 모델·시작 항목·대체 정책 설정. `_validate_*`는 같은 모듈의 발행에서 쓰는 내부 검증이다.
- `service/command/publication.py`: 잠긴 소스의 발행 스냅샷 조합 및 digest. 상위 publish 유스케이스가 트랜잭션을 소유하며 character/lorebook freeze도 같은 범위에 참여한다.
- `service/command/releases.py`: `publish_product`, `correct_note`; 내용·미디어 비교에 따른 업데이트 정책과 릴리스 노트 이력.
- `service/command/statistics.py`: 날짜별 통계 재구축, 대기 작업 처리, 최근 날짜 재요청. 배치는 날짜 하나를 원자적 작업 단위로 삼는다.
- `service/command/statistics_queue.py`: 다른 모듈이 통계 갱신을 요청하는 Command 경계. queue SQL은 product repository 소유다.
- `service/query/`: 자기 데이터의 소유자/공개 접근 조회, 구성 및 통계 조회. `service/views/`: 공개 snapshot·LLM·conversation 결과를 조합한 SnapshotRuntimeView, PublishedProductView, PendingUpdatesView, VersionAvailabilityView, MediaReferenceView.
- `repository/`: core, composition, publication, releases, statistics로 저장 책임을 분리했다. `__init__.py`는 같은 모듈의 저장소 진입점을 재노출한다.
- `mapper/persistence.py`: Row/Entity와 공개 Info의 순수 변환. `mapper/statistics.py`: 전달받은 사실 데이터의 집계·표현 변환. DB, 시계, 공급자 호출은 하지 않는다.
- `router.py`, `mapper/schema.py`, `schemas.py`: HTTP 계약. `statistics_job.py`: 배치 실행 조립 코드.

## 트랜잭션과 반환 계약

Command는 최상위 `use_case_transaction`을 시작하거나 명시적으로 조합된 동일 범위에 참여한다. 내부 commit은 없다. 잠금 순서는 상품 → 캐릭터 → 로어북이며 각 소스 ID를 정렬한다. 발행 중 실패하면 원본 스냅샷·상품 링크·릴리스 노트를 함께 롤백한다.

작성/설정/구성 변경은 Info를, 발행은 ReleaseInfo를 반환한다. 삭제는 None이며 발행 이력이 있으면 삭제를 거절한다. 배치 처리 결과는 ProcessedStatisticsInfo이다. 릴리스 목록의 `(ProductSnapshotInfo, ReleaseNoteInfo | None)`은 명시적인 값 조합 계약이며 ORM Row가 아니다.

statistics 및 일부 command 모듈의 명시적 재노출은 이전 Python import 호출부의 호환 진입점이다. 새 구현은 역할별 파일에 둔다. HTTP DTO 이름은 기존 OpenAPI와 생성 클라이언트 계약을 보존하기 위해 유지했다. 상품 구성, 발행, 통계는 변경 이유와 의존성이 달라 분리했으며 줄 수를 기준으로 자르지 않았다.

공통 HTTP 의존성의 실제 세션/인증 연결과 운영 스케줄러 배포는 기존 미구현·환경 연결 범위다.
