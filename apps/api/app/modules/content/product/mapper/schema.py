# DTO와 신뢰된 경로/owner 값을 Command로 변환하고 from_attributes로 응답을 만든다.
from typing import cast
from uuid import UUID

from app.modules.content.product import schemas as Schemas
from app.modules.content.product import types as Types


class ProductSchemaMapper:
    """Convert HTTP DTOs and application types at the router boundary."""

    @staticmethod
    def studio_draft_request_to_command(
        product_id: UUID, owner_id: UUID, request: Schemas.SaveStudioDraftRequestDto
    ) -> Types.SaveStudioDraftCommand:
        # HTTP JSON parsing supplies JSON-compatible values. The DTO deliberately
        # keeps nested values opaque so inherited string stripping does not edit
        # authored content. This cast preserves that existing boundary; the studio
        # service still owns document structure/size/digest validation.
        document = cast(Types.ProductJsonObject, request.document)
        return Types.SaveStudioDraftCommand(
            product_id=product_id,
            owner_id=owner_id,
            expected_revision=request.expected_revision,
            document=document,
        )

    @staticmethod
    def catalog_page_info_to_response(
        result: Types.CatalogPageInfo,
    ) -> Schemas.CatalogPageResponseDto:
        return Schemas.CatalogPageResponseDto.model_validate(result)

    @staticmethod
    def studio_draft_info_to_response(
        result: Types.StudioDraftInfo,
    ) -> Schemas.StudioDraftResponseDto:
        return Schemas.StudioDraftResponseDto.model_validate(result)

    @staticmethod
    def product_list_request_to_command(
        request: Schemas.ListProductsRequestDto,
    ) -> Types.ProductPaginationCommand:
        return Types.ProductPaginationCommand(
            offset=request.offset, limit=request.limit
        )

    @staticmethod
    def statistics_request_to_command(
        request: Schemas.ProductStatisticsRequestDto,
    ) -> Types.ProductStatisticsRangeCommand:
        return Types.ProductStatisticsRangeCommand(
            date_from=request.date_from,
            date_to=request.date_to,
            snapshot_id=request.snapshot_id,
        )

    @staticmethod
    def product_request_to_command(
        request: Schemas.ProductWriteRequestDto,
    ) -> Types.ProductProfileCommand:
        return Types.ProductProfileCommand(
            title=request.title,
            description=request.description,
            opening_message=request.opening_message,
            visibility=request.visibility,
        )

    @staticmethod
    def composition_request_to_info(
        request: Schemas.CompositionRequestDto,
    ) -> Types.ProductCompositionInfo:
        return Types.ProductCompositionInfo(
            characters=tuple(
                Types.CharacterSelection(
                    character_id=character.character_id,
                    is_primary=character.is_primary,
                    role_name=character.role_name,
                )
                for character in request.characters
            ),
            lorebooks=tuple(
                Types.LorebookSelection(
                    lorebook_id=lorebook.lorebook_id,
                    scope=lorebook.scope,
                    character_ids=lorebook.character_ids,
                    role=lorebook.role,
                    priority=lorebook.priority,
                    is_required=lorebook.is_required,
                )
                for lorebook in request.lorebooks
            ),
        )

    @staticmethod
    def settings_request_to_info(
        request: Schemas.SettingsRequestDto,
    ) -> Types.ProductSettingsInfo:
        return Types.ProductSettingsInfo(
            model_id=request.model_id,
            reasoning_effort=request.reasoning_effort,
            start_entry_ids=request.start_entry_ids,
            replacement_scope=request.replacement_scope,
            replacement_model_ids=request.replacement_model_ids,
            unavailable_policy=request.unavailable_policy,
        )

    @staticmethod
    def release_request_to_command(
        request: Schemas.ReleaseRequestDto,
    ) -> Types.ReleaseNoteCommand:
        return Types.ReleaseNoteCommand(
            summary=request.summary,
            body=request.body,
            auto_apply_media=request.auto_apply_media,
        )

    @staticmethod
    def product_info_to_response(
        result: Types.ProductInfo,
    ) -> Schemas.ProductInfoResponseDto:
        return Schemas.ProductInfoResponseDto.model_validate(result)

    @staticmethod
    def composition_info_to_response(
        result: Types.ProductCompositionInfo,
    ) -> Schemas.CompositionResponseDto:
        return Schemas.CompositionResponseDto.model_validate(result)

    @staticmethod
    def settings_info_to_response(
        result: Types.ProductSettingsInfo,
    ) -> Schemas.SettingsResponseDto:
        return Schemas.SettingsResponseDto.model_validate(result)

    @staticmethod
    def release_info_to_response(
        result: Types.ReleaseInfo,
    ) -> Schemas.ReleaseInfoResponseDto:
        return Schemas.ReleaseInfoResponseDto.model_validate(result)

    @staticmethod
    def published_view_to_response(
        result: Types.PublishedProductView,
    ) -> Schemas.PublishedProductInfoResponseDto:
        return Schemas.PublishedProductInfoResponseDto.model_validate(result)

    @staticmethod
    def availability_view_to_response(
        result: Types.VersionAvailabilityView,
    ) -> Schemas.VersionAvailabilityInfoResponseDto:
        return Schemas.VersionAvailabilityInfoResponseDto.model_validate(result)

    @staticmethod
    def statistics_info_to_response(
        result: Types.StatisticsInfo,
    ) -> Schemas.StatisticsInfoResponseDto:
        return Schemas.StatisticsInfoResponseDto.model_validate(result)
