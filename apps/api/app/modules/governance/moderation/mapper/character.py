from uuid import UUID

from app.modules.content.character import types as CharacterTypes
from app.modules.governance.moderation.schemas import character as schemas


class CharacterSchemaMapper:
    @staticmethod
    def change_character_status_request_to_command(
        request: schemas.ChangeCharacterStatusRequestDto,
        owner_id: UUID,
    ) -> CharacterTypes.ChangeCharacterStatusCommand:
        return CharacterTypes.ChangeCharacterStatusCommand(
            character_id=request.character_id,
            owner_id=owner_id,
            status=request.status,
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
    def character_info_to_status_change_response(
        character: CharacterTypes.CharacterInfo,
    ) -> schemas.ChangeCharacterStatusResponseDto:
        return schemas.ChangeCharacterStatusResponseDto(
            character=CharacterSchemaMapper.character_info_to_response(character),
        )
