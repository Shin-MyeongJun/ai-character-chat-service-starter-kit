# Publication snapshots

`ProductSnapshot` is the published product version. Its JSON payload contains
product data and resolved runtime settings (provider/model identifier, prompts,
and generation settings), not copies of character or lorebook payloads.
`CharacterSnapshot` contains character data, image/asset references and any
character runtime overrides. `LorebookSnapshot` contains lorebook data and its
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
Conversation pinning, publication APIs and garbage collection are not implemented
by these model definitions. Add conversation references before enabling cleanup.

`infra/postgres/init/003_snapshots.sql` creates the matching PostgreSQL tables.
It runs automatically for a fresh Docker database; apply it explicitly to an
existing database. Existing databases are not changed by importing the models.
