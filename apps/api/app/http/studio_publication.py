"""Owner-only studio publication endpoint."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.http.dependencies import Owner, Session, errors
from app.modules.content.product import schemas as ProductSchemas
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.mapper.schema import ProductSchemaMapper
from app.use_cases.studio_components import prepare_components, save_studio
from app.use_cases.studio_diagnostics import (
    DiagnoseStudioLoreCommand,
    diagnose_studio_lore,
)
from app.use_cases.studio_publication import PublishStudioCommand, publish_studio

router = APIRouter(prefix="/products", tags=["products"])


@router.put("/{product_id}/studio-draft", response_model=ProductSchemas.StudioDraftResponseDto)
async def write_studio_draft(product_id: UUID, body: ProductSchemas.SaveStudioDraftRequestDto, session: Session, owner: Owner):
    """Route composed legacy adoption and CAS-save without reversing a module dependency."""
    with errors():
        try:
            info = await save_studio(session, ProductTypes.SaveStudioDraftCommand(product_id, owner, body.expected_revision, body.document))
        except ProductTypes.StudioDraftConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        return ProductSchemaMapper.studio_draft_info_to_response(info)


class LoreDiagnosticMessageDto(BaseModel):
    role: str = Field(pattern="^(user|character)$")
    text: str = Field(max_length=32000)


class StudioLoreDiagnosticRequestDto(BaseModel):
    entries: list[dict] = Field(max_length=100)
    messages: list[LoreDiagnosticMessageDto] = Field(max_length=100)
    manual_entry_ids: list[str] = Field(default_factory=list, max_length=100)


@router.post("/studio/lore-diagnostics")
async def diagnose_lore(body: StudioLoreDiagnosticRequestDto, owner: Owner):
    """Evaluate unsaved draft values for the signed-in author without publishing or AI."""
    with errors():
        return diagnose_studio_lore(DiagnoseStudioLoreCommand(owner, tuple(body.entries), tuple((row.role, row.text) for row in body.messages), tuple(body.manual_entry_ids)))


class PublishStudioRequestDto(BaseModel):
    expected_revision: int = Field(ge=1)
    model_id: UUID
    reasoning_effort: str = Field(min_length=1, max_length=50)
    summary: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


class PrepareStudioComponentsRequestDto(BaseModel):
    expected_revision: int = Field(ge=1)


@router.post("/{product_id}/studio-components")
async def prepare_studio_components(product_id: UUID, body: PrepareStudioComponentsRequestDto, session: Session, owner: Owner):
    """Prepare stable work-specific upload targets under authenticated ownership."""
    with errors():
        try:
            return await prepare_components(session, ProductTypes.GetStudioDraftCommand(product_id, owner), body.expected_revision)
        except ProductTypes.StudioDraftConflictError as exc:
            raise HTTPException(409, str(exc)) from exc


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
