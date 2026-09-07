from uuid import UUID

from app.modules.character import schemas, types


class CharacterSchemaMapper:
    """Convert HTTP schemas and application types at the router boundary."""

    # Request schema -> command/query type

    @staticmethod
    def create_character_request_to_command(
        request: schemas.CreateCharacterRequestDto,
        owner_id: UUID,
    ) -> types.CharacterCreate:
        return types.CharacterCreate(
            owner_id=owner_id,
            name=request.name,
            persona_prompt=request.persona_prompt,
            description=request.description,
            visibility=request.visibility,
            default_model_id=request.default_model_id,
        )

    @staticmethod
    def update_character_request_to_command(
        request: schemas.UpdateCharacterRequestDto,
        owner_id: UUID,
    ) -> types.CharacterUpdate:
        return types.CharacterUpdate(
            character_id=request.character_id,
            owner_id=owner_id,
            name=request.name,
            persona_prompt=request.persona_prompt,
            description=request.description,
            visibility=request.visibility,
            default_model_id=request.default_model_id,
        )

    @staticmethod
    def change_character_status_request_to_command(
        request: schemas.ChangeCharacterStatusRequestDto,
        owner_id: UUID,
    ) -> types.CharacterStatusChange:
        return types.CharacterStatusChange(
            character_id=request.character_id,
            owner_id=owner_id,
            status=request.status,
        )

    @staticmethod
    def delete_character_request_to_command(
        request: schemas.DeleteCharacterRequestDto,
        owner_id: UUID,
    ) -> types.CharacterDelete:
        return types.CharacterDelete(
            character_id=request.character_id,
            owner_id=owner_id,
        )

    @staticmethod
    def add_character_image_request_to_command(
        request: schemas.AddCharacterImageRequestDto,
        owner_id: UUID,
    ) -> types.CharacterImageCreate:
        return types.CharacterImageCreate(
            character_id=request.character_id,
            owner_id=owner_id,
            emotion_tag=request.emotion_tag,
            image_url=request.image_url,
            is_default=request.is_default,
        )

    @staticmethod
    def set_default_character_image_request_to_command(
        request: schemas.SetDefaultCharacterImageRequestDto,
        owner_id: UUID,
    ) -> types.CharacterImageDefaultSet:
        return types.CharacterImageDefaultSet(
            character_id=request.character_id,
            image_id=request.image_id,
            owner_id=owner_id,
        )

    @staticmethod
    def delete_character_image_request_to_command(
        request: schemas.DeleteCharacterImageRequestDto,
        owner_id: UUID,
    ) -> types.CharacterImageDelete:
        return types.CharacterImageDelete(
            character_id=request.character_id,
            image_id=request.image_id,
            owner_id=owner_id,
        )

    @staticmethod
    def add_character_asset_request_to_command(
        request: schemas.AddCharacterAssetRequestDto,
        owner_id: UUID,
    ) -> types.CharacterAssetCreate:
        return types.CharacterAssetCreate(
            character_id=request.character_id,
            owner_id=owner_id,
            asset_type=request.asset_type,
            purpose=request.purpose,
            file_url=request.file_url,
        )

    @staticmethod
    def delete_character_asset_request_to_command(
        request: schemas.DeleteCharacterAssetRequestDto,
        owner_id: UUID,
    ) -> types.CharacterAssetDelete:
        return types.CharacterAssetDelete(
            character_id=request.character_id,
            asset_id=request.asset_id,
            owner_id=owner_id,
        )

    @staticmethod
    def list_characters_request_to_cursor(
        request: schemas.ListCharactersRequestDto,
    ) -> types.CharacterCursor | None:
        if request.cursor_created_at is None and request.cursor_id is None:
            return None
        if request.cursor_created_at is None or request.cursor_id is None:
            # Defensive check for callers that bypass Pydantic validation.
            # TODO: Map cursor validation failures to unified API error codes.
            raise ValueError(
                "cursor_created_at and cursor_id must be provided together."
            )

        return types.CharacterCursor(
            created_at=request.cursor_created_at,
            id=request.cursor_id,
        )

    @staticmethod
    def search_characters_request_to_cursor(
        request: schemas.SearchCharactersByNameRequestDto,
    ) -> types.CharacterCursor | None:
        return CharacterSchemaMapper.list_characters_request_to_cursor(request)

    # Result type -> response schema

    @staticmethod
    def character_info_to_response(
        character: types.CharacterInfo,
    ) -> schemas.CharacterResponseDto:
        return schemas.CharacterResponseDto(
            id=character.id,
            owner_id=character.owner_id,
            name=character.name,
            description=character.description,
            persona_prompt=character.persona_prompt,
            visibility=character.visibility,
            status=character.status,
            default_model_id=character.default_model_id,
            created_at=character.created_at,
            updated_at=character.updated_at,
        )

    @staticmethod
    def character_image_info_to_response(
        image: types.CharacterImageInfo,
    ) -> schemas.CharacterImageResponseDto:
        return schemas.CharacterImageResponseDto(
            id=image.id,
            character_id=image.character_id,
            emotion_tag=image.emotion_tag,
            image_url=image.image_url,
            is_default=image.is_default,
            created_at=image.created_at,
            updated_at=image.updated_at,
        )

    @staticmethod
    def character_asset_info_to_response(
        asset: types.CharacterAssetInfo,
    ) -> schemas.CharacterAssetResponseDto:
        return schemas.CharacterAssetResponseDto(
            id=asset.id,
            character_id=asset.character_id,
            asset_type=asset.asset_type,
            purpose=asset.purpose,
            file_url=asset.file_url,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    @staticmethod
    def character_cursor_to_response(
        cursor: types.CharacterCursor,
    ) -> schemas.CharacterCursorResponseDto:
        return schemas.CharacterCursorResponseDto(
            created_at=cursor.created_at,
            id=cursor.id,
        )

    @staticmethod
    def character_page_to_list_response(
        page: types.CharacterPage[types.CharacterInfo],
    ) -> schemas.ListCharactersResponseDto:
        next_cursor = None
        if page.next_cursor is not None:
            next_cursor = CharacterSchemaMapper.character_cursor_to_response(
                page.next_cursor
            )

        return schemas.ListCharactersResponseDto(
            characters=[
                CharacterSchemaMapper.character_info_to_response(item)
                for item in page.items
            ],
            next_cursor=next_cursor,
        )

    @staticmethod
    def character_page_to_search_response(
        page: types.CharacterPage[types.CharacterInfo],
    ) -> schemas.SearchCharactersByNameResponseDto:
        next_cursor = None
        if page.next_cursor is not None:
            next_cursor = CharacterSchemaMapper.character_cursor_to_response(
                page.next_cursor
            )

        return schemas.SearchCharactersByNameResponseDto(
            characters=[
                CharacterSchemaMapper.character_info_to_response(item)
                for item in page.items
            ],
            next_cursor=next_cursor,
        )

    @staticmethod
    def image_list_to_response(
        images: list[types.CharacterImageInfo],
    ) -> schemas.ListCharacterImagesResponseDto:
        return schemas.ListCharacterImagesResponseDto(
            images=[
                CharacterSchemaMapper.character_image_info_to_response(image)
                for image in images
            ],
        )

    @staticmethod
    def asset_list_to_response(
        assets: list[types.CharacterAssetInfo],
    ) -> schemas.ListCharacterAssetsResponseDto:
        return schemas.ListCharacterAssetsResponseDto(
            assets=[
                CharacterSchemaMapper.character_asset_info_to_response(asset)
                for asset in assets
            ],
        )

    @staticmethod
    def character_info_to_create_response(
        character: types.CharacterInfo,
    ) -> schemas.CreateCharacterResponseDto:
        return schemas.CreateCharacterResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_info_to_update_response(
        character: types.CharacterInfo,
    ) -> schemas.UpdateCharacterResponseDto:
        return schemas.UpdateCharacterResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_info_to_status_change_response(
        character: types.CharacterInfo,
    ) -> schemas.ChangeCharacterStatusResponseDto:
        return schemas.ChangeCharacterStatusResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_info_to_get_response(
        character: types.CharacterInfo,
    ) -> schemas.GetCharacterByIdResponseDto:
        return schemas.GetCharacterByIdResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_image_info_to_add_response(
        image: types.CharacterImageInfo,
    ) -> schemas.AddCharacterImageResponseDto:
        return schemas.AddCharacterImageResponseDto(
            image=CharacterSchemaMapper.character_image_info_to_response(image),
        )

    @staticmethod
    def character_image_info_to_default_response(
        image: types.CharacterImageInfo,
    ) -> schemas.SetDefaultCharacterImageResponseDto:
        return schemas.SetDefaultCharacterImageResponseDto(
            image=CharacterSchemaMapper.character_image_info_to_response(image),
        )

    @staticmethod
    def character_asset_info_to_add_response(
        asset: types.CharacterAssetInfo,
    ) -> schemas.AddCharacterAssetResponseDto:
        return schemas.AddCharacterAssetResponseDto(
            asset=CharacterSchemaMapper.character_asset_info_to_response(asset),
        )

    @staticmethod
    def delete_character_result_to_response(
        result: None,
    ) -> schemas.DeleteCharacterResponseDto:
        return schemas.DeleteCharacterResponseDto(deleted=True)

    @staticmethod
    def delete_character_image_result_to_response(
        result: None,
    ) -> schemas.DeleteCharacterImageResponseDto:
        return schemas.DeleteCharacterImageResponseDto(deleted=True)

    @staticmethod
    def delete_character_asset_result_to_response(
        result: None,
    ) -> schemas.DeleteCharacterAssetResponseDto:
        return schemas.DeleteCharacterAssetResponseDto(deleted=True)
