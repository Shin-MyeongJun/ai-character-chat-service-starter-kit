from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.modules.content.product import schemas
from app.modules.content.product.http import Owner, Session, errors
from app.modules.content.product.mapper.schema import ProductSchemaMapper
from app.modules.content.product.service import (
    command,
    composition,
    notices,
    query,
    releases,
    settings,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/mine", response_model=list[schemas.ProductInfoResponseDto])
async def list_mine(
    session: Session,
    owner: Owner,
    request: Annotated[schemas.ListProductsRequestDto, Query()],
):
    value = ProductSchemaMapper.to_list_query(request)
    return [
        ProductSchemaMapper.product_response(result)
        for result in await query.list_products(
            session, owner_id=owner, offset=value.offset, limit=value.limit
        )
    ]


@router.post("", response_model=schemas.ProductInfoResponseDto, status_code=201)
async def create(body: schemas.ProductWriteRequestDto, session: Session, owner: Owner):
    with errors():
        return ProductSchemaMapper.product_response(
            await command.create_product(
                session, owner_id=owner, value=ProductSchemaMapper.to_write(body)
            )
        )


@router.get("/{product_id}/draft", response_model=schemas.ProductInfoResponseDto)
async def get_draft(product_id: UUID, session: Session, owner: Owner):
    with errors():
        return ProductSchemaMapper.product_response(
            await query.get_product(session, product_id=product_id, owner_id=owner)
        )


@router.put("/{product_id}/draft", response_model=schemas.ProductInfoResponseDto)
async def update(
    product_id: UUID,
    body: schemas.ProductWriteRequestDto,
    session: Session,
    owner: Owner,
):
    with errors():
        return ProductSchemaMapper.product_response(
            await command.update_product(
                session,
                product_id=product_id,
                owner_id=owner,
                value=ProductSchemaMapper.to_write(body),
            )
        )


@router.delete("/{product_id}/draft", status_code=204)
async def delete(product_id: UUID, session: Session, owner: Owner):
    with errors():
        await command.delete_product(session, product_id=product_id, owner_id=owner)


@router.put("/{product_id}/composition", response_model=schemas.CompositionResponseDto)
async def put_composition(
    product_id: UUID,
    body: schemas.CompositionRequestDto,
    session: Session,
    owner: Owner,
):
    with errors():
        return ProductSchemaMapper.composition_response(
            await composition.replace_composition(
                session,
                product_id=product_id,
                owner_id=owner,
                value=ProductSchemaMapper.to_composition(body),
            )
        )


@router.get("/{product_id}/composition", response_model=schemas.CompositionResponseDto)
async def read_composition(product_id: UUID, session: Session, owner: Owner):
    with errors():
        return ProductSchemaMapper.composition_response(
            await composition.get_composition(
                session, product_id=product_id, owner_id=owner
            )
        )


@router.put("/{product_id}/settings", response_model=schemas.SettingsResponseDto)
async def put_settings(
    product_id: UUID, body: schemas.SettingsRequestDto, session: Session, owner: Owner
):
    with errors():
        return ProductSchemaMapper.settings_response(
            await settings.set_settings(
                session,
                product_id=product_id,
                owner_id=owner,
                value=ProductSchemaMapper.to_settings(body),
            )
        )


@router.post(
    "/{product_id}/releases",
    response_model=schemas.ReleaseInfoResponseDto,
    status_code=201,
)
async def publish(
    product_id: UUID, body: schemas.ReleaseRequestDto, session: Session, owner: Owner
):
    with errors():
        return ProductSchemaMapper.release_response(
            await releases.publish(
                session,
                product_id=product_id,
                owner_id=owner,
                value=ProductSchemaMapper.to_release(body),
            )
        )


@router.patch(
    "/{product_id}/releases/{snapshot_id}/note",
    response_model=schemas.ReleaseInfoResponseDto,
)
async def correct_note(
    product_id: UUID,
    snapshot_id: UUID,
    body: schemas.ReleaseRequestDto,
    session: Session,
    owner: Owner,
):
    value = ProductSchemaMapper.to_release(body)
    with errors():
        if value.auto_apply_media:
            raise HTTPException(422, "Patch corrections cannot change update policy.")
        return ProductSchemaMapper.release_response(
            await releases.correct_note(
                session,
                product_id=product_id,
                snapshot_id=snapshot_id,
                owner_id=owner,
                summary=value.summary,
                body=value.body,
            )
        )


@router.get("/{product_id}", response_model=schemas.PublishedProductInfoResponseDto)
async def published(product_id: UUID, session: Session, owner: Owner):
    with errors():
        return ProductSchemaMapper.published_response(
            await notices.published_product(
                session, product_id=product_id, user_id=owner
            )
        )


@router.get(
    "/{product_id}/statistics", response_model=schemas.StatisticsInfoResponseDto
)
async def statistics(
    product_id: UUID,
    request: Annotated[schemas.ProductStatisticsRequestDto, Query()],
    session: Session,
    owner: Owner,
):
    from app.modules.content.product.service.statistics import get_statistics

    value = ProductSchemaMapper.to_statistics_query(request)
    with errors():
        return ProductSchemaMapper.statistics_response(
            await get_statistics(
                session,
                product_id=product_id,
                owner_id=owner,
                date_from=value.date_from,
                date_to=value.date_to,
                snapshot_id=value.snapshot_id,
            )
        )


@router.get(
    "/{product_id}/releases/{snapshot_id}/availability",
    response_model=schemas.VersionAvailabilityInfoResponseDto,
)
async def version_availability(
    product_id: UUID, snapshot_id: UUID, session: Session, owner: Owner
):
    with errors():
        return ProductSchemaMapper.availability_response(
            await notices.version_availability(
                session, product_id=product_id, snapshot_id=snapshot_id, owner_id=owner
            )
        )
