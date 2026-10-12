"""Owner tag endpoints. Internal tags have a separate administrative router."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.contracts import tags as Schemas
from app.http.dependencies import errors
from app.modules.content.character import types as Types
from app.modules.content.character.dependencies import (
    get_character_session,
    get_current_owner_id,
)
from app.modules.content.character.mapper import tag_schema as SchemaMapper
from app.modules.content.character.service import tags as TagsService

Session = Annotated[AsyncSession, Depends(get_character_session)]
Owner = Annotated[UUID, Depends(get_current_owner_id)]
router = APIRouter(prefix="/me", tags=["character tags"])


@router.get("/{target_id}/tags", response_model=list[Schemas.PublicTagResponseDto])
async def list_public_tags(target_id: UUID, session: Session, owner: Owner):
    with errors():
        return SchemaMapper.public_tag_infos_to_response(
            await TagsService.list_public_tags(
                session, Types.PublicTagsCommand(target_id, owner)
            )
        )


@router.post("/{target_id}/tags", response_model=list[Schemas.PublicTagResponseDto])
async def add_public_tags(
    target_id: UUID, body: Schemas.TagsRequestDto, session: Session, owner: Owner
):
    with errors():
        return SchemaMapper.public_tag_infos_to_response(
            await TagsService.add_public_tags(
                session,
                SchemaMapper.public_tags_request_to_command(target_id, owner, body),
            )
        )


@router.put("/{target_id}/tags", response_model=list[Schemas.PublicTagResponseDto])
async def replace_public_tags(
    target_id: UUID, body: Schemas.TagsRequestDto, session: Session, owner: Owner
):
    with errors():
        return SchemaMapper.public_tag_infos_to_response(
            await TagsService.replace_public_tags(
                session,
                SchemaMapper.public_tags_request_to_command(target_id, owner, body),
            )
        )


@router.delete("/{target_id}/tags/{tag_id}", status_code=204)
async def remove_public_tag(
    target_id: UUID, tag_id: UUID, session: Session, owner: Owner
):
    with errors():
        await TagsService.remove_public_tag(
            session, Types.PublicTagsCommand(target_id, owner, tag_id=tag_id)
        )
