"""Owner-only studio publication endpoint."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.http.dependencies import Owner, Session, errors
from app.modules.content.product import schemas as ProductSchemas
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.mapper.schema import ProductSchemaMapper
from app.use_cases.studio_publication import PublishStudioCommand, publish_studio

router = APIRouter(prefix="/products", tags=["products"])


class PublishStudioRequestDto(BaseModel):
    expected_revision: int = Field(ge=1)
    model_id: UUID
    reasoning_effort: str = Field(min_length=1, max_length=50)
    summary: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


@router.post("/{product_id}/studio-publication", response_model=ProductSchemas.ReleaseInfoResponseDto)
async def publish_studio_draft(product_id: UUID, body: PublishStudioRequestDto, session: Session, owner: Owner):
    with errors():
        try:
            release = await publish_studio(session, PublishStudioCommand(
                product_id=product_id, owner_id=owner,
                expected_revision=body.expected_revision, model_id=body.model_id,
                reasoning_effort=body.reasoning_effort, summary=body.summary, body=body.body,
            ))
        except ProductTypes.StudioDraftConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        return ProductSchemaMapper.release_info_to_response(release)
