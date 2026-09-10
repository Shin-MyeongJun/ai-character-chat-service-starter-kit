from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import query as CharacterQueryService
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import query as LorebookQueryService
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper


async def get_snapshot_runtime(
    session, command: Types.ProductSnapshotCommand
) -> Types.SnapshotRuntimeView:
    row = await Repository.get_snapshot_composition(session, command.snapshot_id)
    composition = PersistenceMapper.snapshot_composition_row_to_info(row)
    characters = await CharacterQueryService.get_character_snapshots(
        session,
        CharacterTypes.GetCharacterSnapshotsCommand(
            tuple(c.character_snapshot_id for c in composition.characters)
        ),
    )
    books = await LorebookQueryService.get_lorebook_snapshots(
        session,
        LorebookTypes.GetLorebookSnapshotsCommand(
            tuple(b.lorebook_snapshot_id for b in composition.books)
        ),
    )
    return PersistenceMapper.snapshot_components_infos_to_view(
        composition, characters, books
    )
