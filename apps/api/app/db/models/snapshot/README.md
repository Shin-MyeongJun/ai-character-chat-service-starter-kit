# Publication snapshots

`ProductSnapshot` is the published product version. Its JSON payload contains
product data and resolved runtime settings (provider/model identifier, prompts,
and generation settings), not copies of character or lorebook payloads.
`CharacterSnapshot` contains character data; images and assets are frozen in
`character_snapshot_images` and `character_snapshot_assets` child tables.
`LorebookSnapshot` contains lorebook data and its
complete entries, including activation/retrieval settings.

The two product association tables preserve character order/primary role and
lorebook role/priority/required settings. Unchanged component snapshots can be
shared across product versions. Payloads must be self-contained: source IDs are
for provenance, never for resolving current editable content at runtime.

Create snapshots and their associations in one publication transaction. Treat
payloads and associations as immutable after publication; this schema does not
install update-blocking triggers. Allocate positive versions per source; do not
use a naive concurrent max(version) + 1 without locking/retry. The unique
constraints reject duplicate versions while the source exists.

Deleting a source sets its reference to NULL and preserves snapshots. Referenced
component snapshots cannot be deleted; deleting a product snapshot deletes only
its association rows. Asset files require separate retention management.
Publication and conversation pinning services now exist; see
`docs/reference/product-implementation-plan.md` for verification status and
remaining integration work. Managed character media has explicit ID-scoped cleanup in `app.media_cleanup`;
referenced snapshot media is retained. Legacy URL files are not managed by that cleanup. Expiry columns are mutable operational metadata; content payloads
and associations remain immutable through the service API.

`infra/postgres/init/003_snapshots.sql` creates the matching PostgreSQL tables.
It runs automatically for a fresh Docker database; apply it explicitly to an
existing database. Existing databases are not changed by importing the models.

## 현재 구조를 읽을 때 (2026-09-17)

위 003 SQL은 초기 스냅샷 구조다. 현재 ORM까지의 변경은 뒤따르는 초기 SQL 또는 Alembic revision 체인에 포함되어 있다. 기존 DB에 003만 적용하면 현재 구조 전체가 되는 것은 아니다. 두 초기화 경로와 제약 검증 범위는 [DB 읽기 안내](../../ARCHITECTURE.md)를 본다.

payload와 연결을 서비스에서 새 버전으로 보존하는 정책과 DB UPDATE 차단은 다르다. 관리 미디어는 참조된 스냅샷이 있으면 명시 ID 정리에서도 유지한다. 현재 버전과 최초 시작 항목 ID 연결의 점검 사항은 [F01](../../../../../../references_document/backend_review/findings.md)에 기록했다.
