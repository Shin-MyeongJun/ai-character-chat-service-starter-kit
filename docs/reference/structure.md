# Backend Module Structure

This project keeps each domain module small at first, then splits files only when a boundary becomes useful.

## Module Groups

Related domain modules are grouped one level below `app.modules`:

```text
apps/api/app/
    modules/
        content/
            character/
            lorebook/
            product/
        chatting/
            chat/
            conversation/
            memory/
        commerce/
            billing/
            credit/
        governance/
            admin/
            moderation/
        identity/
        llm/
    db/
        models/
```

Each group has an empty `__init__.py` and is a regular Python package. Import
modules through their grouped paths, for example
`from app.modules.content.character.service import query`. Groups organize
domains without merging their services or changing their internal boundaries.
Database models remain under `app.db.models`.

## Character Module

```text
apps/api/app/modules/content/character/
    schemas.py
    types.py
    repository.py
    mapper/
        schema.py
        persistence.py
    service/
        command.py
        query.py
```

## Service Split

`service/command.py` handles state-changing use cases.

Examples:

- create character
- update character
- delete character
- add/delete image
- set default image
- add/delete asset

Command service functions own transaction boundaries for write operations. They use command/result types, not HTTP schemas. Profile and enum-value validation lives in the service; separate domain objects are not currently needed.

Pass an `AsyncSession` with no active transaction to each command service function. The service uses `session.begin()` to commit on success and roll back on failure. If authentication has already queried through a session, use a separate session for the write use case. Results are mapped inside the transaction so that ORM expiration after commit does not affect the returned value.

The caller supplies a trusted, authenticated `owner_id`. Existing-character writes check ownership and lock the character row before changing it or its media. Missing and non-owned resources both raise `LookupError`; invalid input values raise `ValueError`. The router is responsible for HTTP error mapping and any moderation-specific authorization for status changes.

`add_character_image` and `add_character_asset` are storage placeholders that raise `NotImplementedError` without writing to the database. Delete operations currently remove DB records only; physical file cleanup must be integrated with storage later. Deleting a default image does not automatically select a replacement.

`service/query.py` handles read-only use cases.

Query service functions are reusable by routers and other modules. They take explicit keyword arguments and return Result dataclasses, not ORM entities or HTTP schemas. For now, comments divide the file into router-oriented and other-module queries; split files when the use cases grow.

| Use case | Functions / result |
| --- | --- |
| All characters / owner collection | `list_characters`, `list_characters_by_owner_id` -> `CharacterPage[CharacterInfo]` |
| Detail / owner-scoped detail | `get_character_by_id`, `get_character_by_id_and_owner_id` -> `CharacterInfo` or `None` |
| Image by ID / emotion / default | `get_character_image`, `get_character_image_by_emotion_tag`, `get_default_character_image` -> `CharacterImageInfo` or `None` |
| All emotion images | `list_character_images` -> `list[CharacterImageInfo]` |
| Asset by ID / collection | `get_character_asset` -> `CharacterAssetInfo` or `None`; `list_character_assets` -> `list[CharacterAssetInfo]`, optionally filtered by `asset_type` |
| Chat prompt | `get_character_prompt` -> `CharacterPromptInfo` or `None`, including the default model ID |
| Character presentation | `get_character_promotion` -> `CharacterPromotionInfo` or `None`, containing character ID, name, description, all images, and all assets |

Collection pagination reuses the repository cursor `(created_at, id)` in descending order, with a default limit of 50 and limits clamped to 1–100. Media lists are unpaginated; images place the default first, then newest first, and both media lists use ID to break timestamp ties.

These are reads for callers that have already authorized access. The all-character collection intentionally includes private, unlisted, draft, and rejected records. `CharacterInfo` includes `persona_prompt`; it is not a public catalog response. Owner filtering is not authentication: the caller must supply a trusted owner ID. Public catalog rules, response fields, and router search/filter inputs are marked as future work beneath the router-oriented queries.

Individual image/asset lookups require both the character ID and media ID. Emotion tags use exact matching; absent tags return `None`, and callers may explicitly query a default image. Missing individual resources return `None`. Media lists return `[]` for both a missing character and a character with no media; a detail lookup distinguishes those cases. Invalid asset type filters raise `ValueError` even when the caller bypasses HTTP validation.

Promotion results omit the persona prompt but include every asset purpose. Callers must decide which media can be publicly shown. A missing character returns `None`; an existing character without media still returns its presentation data with empty lists. This helper makes three sequential reads on one session. It is intended for one character; future list previews should batch media loading to avoid per-character queries. Snapshot consistency across these reads depends on the caller's transaction isolation.

Queries do not explicitly begin, commit, or roll back transactions. They can participate in an existing caller transaction; SELECT may autobegin a transaction and honors session autoflush for pending changes. Close/end the read transaction or use a separate session before calling the command service, which requires no active transaction.

## Mapper Split

`mapper/schema.py` maps between the HTTP adapter layer and application types.

Examples:

- request schema -> command type
- cursor request fields -> cursor type
- result type -> response schema

`mapper/persistence.py` maps between SQLAlchemy entities and application types.

Examples:

- command type -> SQLAlchemy entity
- update command -> existing SQLAlchemy entity
- SQLAlchemy entity -> result type

This keeps `schemas.py` and `types.py` from importing each other. The intended dependency direction is:

```text
router -> mapper.schema -> schemas/types
service -> mapper.persistence -> types/db.models
repository -> db.models
```

Avoid these dependencies:

```text
service -> schemas
repository -> schemas
db.models -> types
types -> schemas
```

## Lorebook Module

Lorebook follows the same application boundaries as character:

```text
apps/api/app/modules/content/lorebook/
    schemas.py
    types.py
    repository.py
    dependencies.py
    mapper/
        schema.py
        persistence.py
    service/
        command.py
        query.py
```

The parent resource supports owner-scoped CRUD and separate moderation status
changes. Entries are the lorebook's child resource and also support CRUD. Every
entry write first locks the owned lorebook, and entry IDs are always scoped by
their lorebook ID. Lorebook and entry management lists use descending
`(created_at, id)` cursor pagination.

`service/query.py` additionally exposes the initial chat-facing contract:
`get_always_entries` returns enabled `always` entries, and
`activate_keyword_entries` evaluates enabled `keyword` entries using the stored
`exact`, `contains`, or `regex` match mode. Both accept lorebook IDs supplied by
the product/chat composition layer and return `ActiveLorebookEntry`, not ORM or
HTTP objects. Higher-priority active entries are returned first. Semantic search,
manual activation, token-budget truncation, and prompt placement are separate
follow-up responsibilities.

Regex triggers use pydantic-core's Rust regex engine so creator-supplied patterns
cannot cause catastrophic backtracking in the chat event loop. Entry input also
has explicit text, trigger-count, metadata-size, and PostgreSQL integer limits.
An enabled keyword entry must contain at least one trigger.

Entry embeddings are persistence data and are intentionally absent from the HTTP
CRUD contract. A later embedding workflow should update them when semantic
activation is implemented.

The current moderation transition matches character: the status command is
moderator-gated at HTTP level and owner-scoped in the service. Cross-owner review,
audit records, and whether edits reset an approved lorebook to draft must be
defined together before enabling a production moderation workflow.
