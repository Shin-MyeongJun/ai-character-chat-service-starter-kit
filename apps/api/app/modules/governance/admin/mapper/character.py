from app.modules.content.character import types as CharacterTypes
from app.modules.governance.admin.schemas import character as schemas


class CharacterSchemaMapper:
    @staticmethod
    def character_info_to_get_response(
        character: CharacterTypes.CharacterInfo,
    ) -> schemas.GetCharacterByIdResponseDto:
        return schemas.GetCharacterByIdResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )

    @staticmethod
    def character_cursor_to_response(
        cursor: CharacterTypes.CharacterCursor,
    ) -> schemas.CharacterCursorResponseDto:
        return schemas.CharacterCursorResponseDto(
            created_at=cursor.created_at,
            id=cursor.id,
        )

    @staticmethod
    def character_info_to_response(
        character: CharacterTypes.CharacterInfo,
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
    def list_characters_request_to_cursor(
        request: schemas.ListCharactersRequestDto,
    ) -> CharacterTypes.CharacterCursor | None:
        if request.cursor_created_at is None and request.cursor_id is None:
            return None
        if request.cursor_created_at is None or request.cursor_id is None:
            # Defensive check for callers that bypass Pydantic validation.
            # TODO: Map cursor validation failures to unified API error codes.
            raise ValueError(
                "cursor_created_at and cursor_id must be provided together."
            )

        return CharacterTypes.CharacterCursor(
            created_at=request.cursor_created_at,
            id=request.cursor_id,
        )

    @staticmethod
    def character_page_to_list_response(
        page: CharacterTypes.CharacterPage[CharacterTypes.CharacterInfo],
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
