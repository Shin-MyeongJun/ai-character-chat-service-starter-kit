# 초안 → 구성 → 설정 → 발행 → 공개 안내 흐름의 HTTP 경계. 발행과 안내는 인증 owner 훅을 사용한다.
# 노트 수정으로 자동 적용 정책을 바꿀 수 없으며 상품 삭제 성공은 204다.
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.http.dependencies import Owner, Session, errors
from app.modules.content.product import schemas as Schemas
from app.modules.content.product import types as Types
from app.modules.content.product.mapper.schema import (
    ProductSchemaMapper as SchemaMapper,
)
from app.modules.content.product.service import command as CommandService
from app.modules.content.product.service import query as QueryService
from app.modules.content.product.service.command import (
    composition as CompositionCommandService,
)
from app.modules.content.product.service.command import (
    releases as ReleasesCommandService,
)
from app.modules.content.product.service.command import (
    settings as SettingsCommandService,
)
from app.modules.content.product.service.views import notices as NoticesViewsService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/mine", response_model=list[Schemas.ProductInfoResponseDto])
async def list_mine(
    session: Session,
    owner: Owner,
    request: Annotated[Schemas.ListProductsRequestDto, Query()],
):
    value = SchemaMapper.product_list_request_to_command(request)
    return [
        SchemaMapper.product_info_to_response(result)
        for result in await QueryService.list_products(
            session,
            Types.ListProductsCommand(
                owner_id=owner, offset=value.offset, limit=value.limit
            ),
        )
    ]


@router.post("", response_model=Schemas.ProductInfoResponseDto, status_code=201)
async def create(body: Schemas.ProductWriteRequestDto, session: Session, owner: Owner):
    with errors():
        return SchemaMapper.product_info_to_response(
            await CommandService.create_product(
                session,
                Types.CreateProductCommand(
                    owner_id=owner, value=SchemaMapper.product_request_to_command(body)
                ),
            )
        )


@router.get("/{product_id}/draft", response_model=Schemas.ProductInfoResponseDto)
async def get_draft(product_id: UUID, session: Session, owner: Owner):
    with errors():
        return SchemaMapper.product_info_to_response(
            await QueryService.get_product(
                session,
                Types.GetProductCommand(product_id=product_id, owner_id=owner),
            )
        )


@router.put("/{product_id}/draft", response_model=Schemas.ProductInfoResponseDto)
async def update(
    product_id: UUID,
    body: Schemas.ProductWriteRequestDto,
    session: Session,
    owner: Owner,
):
    with errors():
        return SchemaMapper.product_info_to_response(
            await CommandService.update_product(
                session,
                Types.UpdateProductCommand(
                    product_id=product_id,
                    owner_id=owner,
                    value=SchemaMapper.product_request_to_command(body),
                ),
            )
        )


@router.delete("/{product_id}/draft", status_code=204)
async def delete(product_id: UUID, session: Session, owner: Owner):
    with errors():
        await CommandService.delete_product(
            session,
            Types.DeleteProductCommand(product_id=product_id, owner_id=owner),
        )


@router.put("/{product_id}/composition", response_model=Schemas.CompositionResponseDto)
async def put_composition(
    product_id: UUID,
    body: Schemas.CompositionRequestDto,
    session: Session,
    owner: Owner,
):
    with errors():
        return SchemaMapper.composition_info_to_response(
            await CompositionCommandService.replace_composition(
                session,
                Types.ReplaceCompositionCommand(
                    product_id=product_id,
                    owner_id=owner,
                    value=SchemaMapper.composition_request_to_info(body),
                ),
            )
        )


@router.get("/{product_id}/composition", response_model=Schemas.CompositionResponseDto)
async def read_composition(product_id: UUID, session: Session, owner: Owner):
    with errors():
        return SchemaMapper.composition_info_to_response(
            await CompositionCommandService.get_composition(
                session,
                Types.GetCompositionCommand(product_id=product_id, owner_id=owner),
            )
        )


@router.put("/{product_id}/settings", response_model=Schemas.SettingsResponseDto)
async def put_settings(
    product_id: UUID, body: Schemas.SettingsRequestDto, session: Session, owner: Owner
):
    with errors():
        return SchemaMapper.settings_info_to_response(
            await SettingsCommandService.set_settings(
                session,
                Types.SetSettingsCommand(
                    product_id=product_id,
                    owner_id=owner,
                    value=SchemaMapper.settings_request_to_info(body),
                ),
            )
        )


@router.post(
    "/{product_id}/releases",
    response_model=Schemas.ReleaseInfoResponseDto,
    status_code=201,
)
async def publish(
    product_id: UUID, body: Schemas.ReleaseRequestDto, session: Session, owner: Owner
):
    with errors():
        return SchemaMapper.release_info_to_response(
            await ReleasesCommandService.publish_product(
                session,
                Types.PublishCommand(
                    product_id=product_id,
                    owner_id=owner,
                    value=SchemaMapper.release_request_to_command(body),
                ),
            )
        )


@router.patch(
    "/{product_id}/releases/{snapshot_id}/note",
    response_model=Schemas.ReleaseInfoResponseDto,
)
async def correct_note(
    product_id: UUID,
    snapshot_id: UUID,
    body: Schemas.ReleaseRequestDto,
    session: Session,
    owner: Owner,
):
    value = SchemaMapper.release_request_to_command(body)
    with errors():
        if value.auto_apply_media:
            raise HTTPException(422, "Patch corrections cannot change update policy.")
        return SchemaMapper.release_info_to_response(
            await ReleasesCommandService.correct_note(
                session,
                Types.CorrectNoteCommand(
                    product_id=product_id,
                    snapshot_id=snapshot_id,
                    owner_id=owner,
                    summary=value.summary,
                    body=value.body,
                ),
            )
        )


@router.get("/{product_id}", response_model=Schemas.PublishedProductInfoResponseDto)
async def published(product_id: UUID, session: Session, owner: Owner):
    with errors():
        return SchemaMapper.published_view_to_response(
            await NoticesViewsService.get_published_product(
                session,
                Types.PublishedProductCommand(product_id=product_id, user_id=owner),
            )
        )


@router.get(
    "/{product_id}/statistics", response_model=Schemas.StatisticsInfoResponseDto
)
async def statistics(
    product_id: UUID,
    request: Annotated[Schemas.ProductStatisticsRequestDto, Query()],
    session: Session,
    owner: Owner,
):
    from app.modules.content.product.service.statistics import get_statistics

    value = SchemaMapper.statistics_request_to_command(request)
    with errors():
        return SchemaMapper.statistics_info_to_response(
            await get_statistics(
                session,
                Types.GetStatisticsCommand(
                    product_id=product_id,
                    owner_id=owner,
                    date_from=value.date_from,
                    date_to=value.date_to,
                    snapshot_id=value.snapshot_id,
                ),
            )
        )


@router.get(
    "/{product_id}/releases/{snapshot_id}/availability",
    response_model=Schemas.VersionAvailabilityInfoResponseDto,
)
async def version_availability(
    product_id: UUID, snapshot_id: UUID, session: Session, owner: Owner
):
    with errors():
        return SchemaMapper.availability_view_to_response(
            await NoticesViewsService.get_version_availability(
                session,
                Types.VersionAvailabilityCommand(
                    product_id=product_id, snapshot_id=snapshot_id, owner_id=owner
                ),
            )
        )
