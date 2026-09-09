from app.modules.content.product import schemas, types


class ProductSchemaMapper:
    """Convert HTTP DTOs and application types at the router boundary."""

    @staticmethod
    def to_list_query(
        request: schemas.ListProductsRequestDto,
    ) -> types.ProductListQuery:
        return types.ProductListQuery(offset=request.offset, limit=request.limit)

    @staticmethod
    def to_statistics_query(
        request: schemas.ProductStatisticsRequestDto,
    ) -> types.ProductStatisticsQuery:
        return types.ProductStatisticsQuery(
            date_from=request.date_from,
            date_to=request.date_to,
            snapshot_id=request.snapshot_id,
        )

    @staticmethod
    def to_write(request: schemas.ProductWriteRequestDto) -> types.ProductWrite:
        return types.ProductWrite(
            title=request.title,
            description=request.description,
            opening_message=request.opening_message,
            visibility=request.visibility,
        )

    @staticmethod
    def to_composition(request: schemas.CompositionRequestDto) -> types.Composition:
        return types.Composition(
            characters=tuple(
                types.CharacterSelection(
                    character_id=c.character_id,
                    is_primary=c.is_primary,
                    role_name=c.role_name,
                )
                for c in request.characters
            ),
            lorebooks=tuple(
                types.LorebookSelection(
                    lorebook_id=b.lorebook_id,
                    scope=b.scope,
                    character_ids=b.character_ids,
                    role=b.role,
                    priority=b.priority,
                    is_required=b.is_required,
                )
                for b in request.lorebooks
            ),
        )

    @staticmethod
    def to_settings(request: schemas.SettingsRequestDto) -> types.Settings:
        return types.Settings(
            model_id=request.model_id,
            reasoning_effort=request.reasoning_effort,
            start_entry_ids=request.start_entry_ids,
            replacement_scope=request.replacement_scope,
            replacement_model_ids=request.replacement_model_ids,
            unavailable_policy=request.unavailable_policy,
        )

    @staticmethod
    def to_release(request: schemas.ReleaseRequestDto) -> types.ReleasePublish:
        return types.ReleasePublish(
            summary=request.summary,
            body=request.body,
            auto_apply_media=request.auto_apply_media,
        )

    @staticmethod
    def product_response(result: types.ProductInfo) -> schemas.ProductInfoResponseDto:
        return schemas.ProductInfoResponseDto.model_validate(result)

    @staticmethod
    def composition_response(
        result: types.Composition,
    ) -> schemas.CompositionResponseDto:
        return schemas.CompositionResponseDto.model_validate(result)

    @staticmethod
    def settings_response(result: types.Settings) -> schemas.SettingsResponseDto:
        return schemas.SettingsResponseDto.model_validate(result)

    @staticmethod
    def release_response(result: types.ReleaseInfo) -> schemas.ReleaseInfoResponseDto:
        return schemas.ReleaseInfoResponseDto.model_validate(result)

    @staticmethod
    def published_response(
        result: types.PublishedProductInfo,
    ) -> schemas.PublishedProductInfoResponseDto:
        return schemas.PublishedProductInfoResponseDto.model_validate(result)

    @staticmethod
    def updates_response(
        result: types.PendingUpdatesInfo,
    ) -> schemas.PendingUpdatesInfoResponseDto:
        return schemas.PendingUpdatesInfoResponseDto.model_validate(result)

    @staticmethod
    def availability_response(
        result: types.VersionAvailabilityInfo,
    ) -> schemas.VersionAvailabilityInfoResponseDto:
        return schemas.VersionAvailabilityInfoResponseDto.model_validate(result)

    @staticmethod
    def statistics_response(
        result: types.StatisticsInfo,
    ) -> schemas.StatisticsInfoResponseDto:
        return schemas.StatisticsInfoResponseDto.model_validate(result)
