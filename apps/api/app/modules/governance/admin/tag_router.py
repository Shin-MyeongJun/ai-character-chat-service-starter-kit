"""Administrative tag adapters; content services recheck active DB admin roles."""

from uuid import UUID

from fastapi import APIRouter

from app.http.contracts import tags as Schemas
from app.http.dependencies import Owner, Session, errors
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import tags as CharacterTagsService
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import tags as LorebookTagsService
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import tags as ProductTagsService
from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import command as TagCommandService
from app.modules.content.tag.service import query as TagQueryService
from app.modules.governance.admin.mapper import tags as SchemaMapper

router = APIRouter(prefix="/admin", tags=["tag administration"])


@router.get(
    "/products/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def list_product_internal_tags(
    target_id: UUID, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await ProductTagsService.list_internal_tags(
                session,
                ProductTypes.InternalTagsCommand(target_id=target_id, actor_id=owner),
            )
        )


@router.post(
    "/products/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def add_product_internal_tags(
    target_id: UUID, body: Schemas.TagsRequestDto, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await ProductTagsService.add_internal_tags(
                session,
                ProductTypes.InternalTagsCommand(
                    target_id=target_id, actor_id=owner, names=tuple(body.tags)
                ),
            )
        )


@router.put(
    "/products/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def replace_product_internal_tags(
    target_id: UUID, body: Schemas.TagsRequestDto, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await ProductTagsService.replace_internal_tags(
                session,
                ProductTypes.InternalTagsCommand(
                    target_id=target_id, actor_id=owner, names=tuple(body.tags)
                ),
            )
        )


@router.delete("/products/{target_id}/internal-tags/{tag_id}", status_code=204)
async def remove_product_internal_tag(
    target_id: UUID, tag_id: UUID, session: Session, owner: Owner
) -> None:
    with errors():
        await ProductTagsService.remove_internal_tag(
            session,
            ProductTypes.InternalTagsCommand(
                target_id=target_id, actor_id=owner, tag_id=tag_id
            ),
        )


@router.get(
    "/characters/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def list_character_internal_tags(
    target_id: UUID, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await CharacterTagsService.list_internal_tags(
                session,
                CharacterTypes.InternalTagsCommand(target_id=target_id, actor_id=owner),
            )
        )


@router.post(
    "/characters/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def add_character_internal_tags(
    target_id: UUID, body: Schemas.TagsRequestDto, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await CharacterTagsService.add_internal_tags(
                session,
                CharacterTypes.InternalTagsCommand(
                    target_id=target_id, actor_id=owner, names=tuple(body.tags)
                ),
            )
        )


@router.put(
    "/characters/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def replace_character_internal_tags(
    target_id: UUID, body: Schemas.TagsRequestDto, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await CharacterTagsService.replace_internal_tags(
                session,
                CharacterTypes.InternalTagsCommand(
                    target_id=target_id, actor_id=owner, names=tuple(body.tags)
                ),
            )
        )


@router.delete("/characters/{target_id}/internal-tags/{tag_id}", status_code=204)
async def remove_character_internal_tag(
    target_id: UUID, tag_id: UUID, session: Session, owner: Owner
) -> None:
    with errors():
        await CharacterTagsService.remove_internal_tag(
            session,
            CharacterTypes.InternalTagsCommand(
                target_id=target_id, actor_id=owner, tag_id=tag_id
            ),
        )


@router.get(
    "/lorebooks/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def list_lorebook_internal_tags(
    target_id: UUID, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await LorebookTagsService.list_internal_tags(
                session,
                LorebookTypes.InternalTagsCommand(target_id=target_id, actor_id=owner),
            )
        )


@router.post(
    "/lorebooks/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def add_lorebook_internal_tags(
    target_id: UUID, body: Schemas.TagsRequestDto, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await LorebookTagsService.add_internal_tags(
                session,
                LorebookTypes.InternalTagsCommand(
                    target_id=target_id, actor_id=owner, names=tuple(body.tags)
                ),
            )
        )


@router.put(
    "/lorebooks/{target_id}/internal-tags",
    response_model=list[Schemas.InternalTagResponseDto],
)
async def replace_lorebook_internal_tags(
    target_id: UUID, body: Schemas.TagsRequestDto, session: Session, owner: Owner
) -> list[Schemas.InternalTagResponseDto]:
    with errors():
        return SchemaMapper.internal_tag_infos_to_response(
            await LorebookTagsService.replace_internal_tags(
                session,
                LorebookTypes.InternalTagsCommand(
                    target_id=target_id, actor_id=owner, names=tuple(body.tags)
                ),
            )
        )


@router.delete("/lorebooks/{target_id}/internal-tags/{tag_id}", status_code=204)
async def remove_lorebook_internal_tag(
    target_id: UUID, tag_id: UUID, session: Session, owner: Owner
) -> None:
    with errors():
        await LorebookTagsService.remove_internal_tag(
            session,
            LorebookTypes.InternalTagsCommand(
                target_id=target_id, actor_id=owner, tag_id=tag_id
            ),
        )


@router.get("/tags/{tag_id}", response_model=Schemas.TagResponseDto)
async def get_tag(
    tag_id: UUID, session: Session, owner: Owner
) -> Schemas.TagResponseDto:
    with errors():
        return SchemaMapper.tag_info_to_response(
            await TagQueryService.get_admin_tag(
                session, TagTypes.AdminGetTagCommand(tag_id=tag_id, actor_id=owner)
            )
        )


@router.post("/tags", response_model=Schemas.TagResponseDto, status_code=201)
async def create_tag(
    body: Schemas.TagWriteRequestDto, session: Session, owner: Owner
) -> Schemas.TagResponseDto:
    with errors():
        return SchemaMapper.tag_info_to_response(
            await TagCommandService.create_tag(
                session,
                TagTypes.CreateTagCommand(
                    actor_id=owner, name=body.name, description=body.description
                ),
            )
        )


@router.put("/tags/{tag_id}", response_model=Schemas.TagResponseDto)
async def update_tag(
    tag_id: UUID, body: Schemas.TagWriteRequestDto, session: Session, owner: Owner
) -> Schemas.TagResponseDto:
    with errors():
        return SchemaMapper.tag_info_to_response(
            await TagCommandService.update_tag(
                session,
                TagTypes.UpdateTagCommand(
                    tag_id=tag_id,
                    actor_id=owner,
                    name=body.name,
                    description=body.description,
                ),
            )
        )


@router.delete("/tags/{tag_id}", status_code=204)
async def deactivate_tag(tag_id: UUID, session: Session, owner: Owner) -> None:
    with errors():
        await TagCommandService.deactivate_tag(
            session, TagTypes.DeactivateTagCommand(tag_id=tag_id, actor_id=owner)
        )
