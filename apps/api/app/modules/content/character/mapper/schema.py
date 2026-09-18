# 인증 owner를 Command에 명시적으로 합치고 결과를 기존 DTO로 변환한다. 삭제 응답 true는 서비스 정상 종료를 뜻한다.
from uuid import UUID

from app.modules.content.character import schemas as Schemas
from app.modules.content.character import types as Types


class CharacterSchemaMapper:
    """Convert HTTP schemas and application types at the router boundary."""

    # Request schema -> command/query type

    @staticmethod
    def create_character_request_to_command(
        request: Schemas.CreateCharacterRequestDto,
        owner_id: UUID,
    ) -> Types.CreateCharacterCommand:
        return Types.CreateCharacterCommand(
            owner_id=owner_id,
            name=request.name,
            persona_prompt=request.persona_prompt,
            description=request.description,
            visibility=request.visibility,
            default_model_id=request.default_model_id,
        )

    @staticmethod
    def update_character_request_to_command(
        request: Schemas.UpdateCharacterRequestDto,
        owner_id: UUID,
    ) -> Types.UpdateCharacterCommand:
        return Types.UpdateCharacterCommand(
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
        request: Schemas.ChangeCharacterStatusRequestDto,
        owner_id: UUID,
    ) -> Types.ChangeCharacterStatusCommand:
        return Types.ChangeCharacterStatusCommand(
            character_id=request.character_id,
            owner_id=owner_id,
            status=request.status,
        )

    @staticmethod
    def delete_character_request_to_command(
        request: Schemas.DeleteCharacterRequestDto,
        owner_id: UUID,
    ) -> Types.DeleteCharacterCommand:
        return Types.DeleteCharacterCommand(
            character_id=request.character_id,
            owner_id=owner_id,
        )

    @staticmethod
    def add_character_image_request_to_command(
        request: Schemas.AddCharacterImageRequestDto,
        owner_id: UUID,
    ) -> Types.CreateCharacterImageCommand:
        return Types.CreateCharacterImageCommand(
            character_id=request.character_id,
            owner_id=owner_id,
            emotion_tag=request.emotion_tag,
            image_url=request.image_url,
            is_default=request.is_default,
        )

    @staticmethod
    def set_default_character_image_request_to_command(
        request: Schemas.SetDefaultCharacterImageRequestDto,
        owner_id: UUID,
    ) -> Types.SetDefaultCharacterImageCommand:
        return Types.SetDefaultCharacterImageCommand(
            character_id=request.character_id,
            image_id=request.image_id,
            owner_id=owner_id,
        )

    @staticmethod
    def delete_character_image_request_to_command(
        request: Schemas.DeleteCharacterImageRequestDto,
        owner_id: UUID,
    ) -> Types.DeleteCharacterImageCommand:
        return Types.DeleteCharacterImageCommand(
            character_id=request.character_id,
            image_id=request.image_id,
            owner_id=owner_id,
        )

    @staticmethod
    def add_character_asset_request_to_command(
        request: Schemas.AddCharacterAssetRequestDto,
        owner_id: UUID,
    ) -> Types.CreateCharacterAssetCommand:
        return Types.CreateCharacterAssetCommand(
            character_id=request.character_id,
            owner_id=owner_id,
            asset_type=request.asset_type,
            purpose=request.purpose,
            file_url=request.file_url,
        )

    @staticmethod
    def delete_character_asset_request_to_command(
        request: Schemas.DeleteCharacterAssetRequestDto,
        owner_id: UUID,
    ) -> Types.DeleteCharacterAssetCommand:
        return Types.DeleteCharacterAssetCommand(
            character_id=request.character_id,
            asset_id=request.asset_id,
            owner_id=owner_id,
        )

    @staticmethod
    def list_characters_request_to_cursor(
        request: Schemas.ListCharactersRequestDto,
    ) -> Types.CharacterCursor | None:
        if request.cursor_created_at is None and request.cursor_id is None:
            return None
        if request.cursor_created_at is None or request.cursor_id is None:
            # Defensive check for callers that bypass Pydantic validation.
            # TODO: Map cursor validation failures to unified API error codes.
            raise ValueError(
                "cursor_created_at and cursor_id must be provided together."
            )

        return Types.CharacterCursor(
            created_at=request.cursor_created_at,
            id=request.cursor_id,
        )

    @staticmethod
    def search_characters_request_to_cursor(
        request: Schemas.SearchCharactersByNameRequestDto,
    ) -> Types.CharacterCursor | None:
        return CharacterSchemaMapper.list_characters_request_to_cursor(request)

    # Result type -> response schema

    @staticmethod
    def character_info_to_response(
        character: Types.CharacterInfo,
    ) -> Schemas.CharacterResponseDto:
        return Schemas.CharacterResponseDto(
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
        image: Types.CharacterImageInfo,
    ) -> Schemas.CharacterImageResponseDto:
        return Schemas.CharacterImageResponseDto(
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
        asset: Types.CharacterAssetInfo,
    ) -> Schemas.CharacterAssetResponseDto:
        return Schemas.CharacterAssetResponseDto(
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
        cursor: Types.CharacterCursor,
    ) -> Schemas.CharacterCursorResponseDto:
        return Schemas.CharacterCursorResponseDto(
            created_at=cursor.created_at,
            id=cursor.id,
        )

    @staticmethod
    def character_page_to_list_response(
        page: Types.CharacterPage[Types.CharacterInfo],
    ) -> Schemas.ListCharactersResponseDto:
        next_cursor = None
        if page.next_cursor is not None:
            next_cursor = CharacterSchemaMapper.character_cursor_to_response(
                page.next_cursor
            )

        return Schemas.ListCharactersResponseDto(
            characters=[
                CharacterSchemaMapper.character_info_to_response(item)
                for item in page.items
            ],
            next_cursor=next_cursor,
        )

    @staticmethod
    def character_page_to_search_response(
        page: Types.CharacterPage[Types.CharacterInfo],
    ) -> Schemas.SearchCharactersByNameResponseDto:
        next_cursor = None
        if page.next_cursor is not None:
            next_cursor = CharacterSchemaMapper.character_cursor_to_response(
                page.next_cursor
            )

        return Schemas.SearchCharactersByNameResponseDto(
            characters=[
                CharacterSchemaMapper.character_info_to_response(item)
                for item in page.items
            ],
            next_cursor=next_cursor,
        )

    @staticmethod
    def image_list_to_response(
        images: list[Types.CharacterImageInfo],
    ) -> Schemas.ListCharacterImagesResponseDto:
        return Schemas.ListCharacterImagesResponseDto(
            images=[
                CharacterSchemaMapper.character_image_info_to_response(image)
                for image in images
            ],
        )

    @staticmethod
    def asset_list_to_response(
        assets: list[Types.CharacterAssetInfo],
    ) -> Schemas.ListCharacterAssetsResponseDto:
        return Schemas.ListCharacterAssetsResponseDto(
            assets=[
                CharacterSchemaMapper.character_asset_info_to_response(asset)
                for asset in assets
            ],
        )

    @staticmethod
    def character_info_to_create_response(
        character: Types.CharacterInfo,
    ) -> Schemas.CreateCharacterResponseDto:
        return Schemas.CreateCharacterResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_info_to_update_response(
        character: Types.CharacterInfo,
    ) -> Schemas.UpdateCharacterResponseDto:
        return Schemas.UpdateCharacterResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_info_to_status_change_response(
        character: Types.CharacterInfo,
    ) -> Schemas.ChangeCharacterStatusResponseDto:
        return Schemas.ChangeCharacterStatusResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_info_to_get_response(
        character: Types.CharacterInfo,
    ) -> Schemas.GetCharacterByIdResponseDto:
        return Schemas.GetCharacterByIdResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_image_info_to_add_response(
        image: Types.CharacterImageInfo,
    ) -> Schemas.AddCharacterImageResponseDto:
        return Schemas.AddCharacterImageResponseDto(
            image=CharacterSchemaMapper.character_image_info_to_response(image),
        )

    @staticmethod
    def character_image_info_to_default_response(
        image: Types.CharacterImageInfo,
    ) -> Schemas.SetDefaultCharacterImageResponseDto:
        return Schemas.SetDefaultCharacterImageResponseDto(
            image=CharacterSchemaMapper.character_image_info_to_response(image),
        )

    @staticmethod
    def character_asset_info_to_add_response(
        asset: Types.CharacterAssetInfo,
    ) -> Schemas.AddCharacterAssetResponseDto:
        return Schemas.AddCharacterAssetResponseDto(
            asset=CharacterSchemaMapper.character_asset_info_to_response(asset),
        )

    @staticmethod
    def delete_character_result_to_response(
        result: None,
    ) -> Schemas.DeleteCharacterResponseDto:
        return Schemas.DeleteCharacterResponseDto(deleted=True)

    @staticmethod
    def delete_character_image_result_to_response(
        result: None,
    ) -> Schemas.DeleteCharacterImageResponseDto:
        return Schemas.DeleteCharacterImageResponseDto(deleted=True)

    @staticmethod
    def delete_character_asset_result_to_response(
        result: None,
    ) -> Schemas.DeleteCharacterAssetResponseDto:
        return Schemas.DeleteCharacterAssetResponseDto(deleted=True)
