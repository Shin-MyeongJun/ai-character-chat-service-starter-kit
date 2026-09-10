from uuid import UUID

from app.modules.content.lorebook import types as LorebookTypes
from app.modules.governance.moderation.schemas import lorebook as schemas


class LorebookSchemaMapper:
    @classmethod
    def lorebook_info_to_status_response(
        cls,
        value: LorebookTypes.LorebookInfo,
    ) -> schemas.ChangeLorebookStatusResponseDto:
        return schemas.ChangeLorebookStatusResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @staticmethod
    def change_lorebook_status_request_to_command(
        request: schemas.ChangeLorebookStatusRequestDto,
        owner_id: UUID,
    ) -> LorebookTypes.ChangeLorebookStatusCommand:
        return LorebookTypes.ChangeLorebookStatusCommand(
            lorebook_id=request.lorebook_id,
            owner_id=owner_id,
            status=request.status,
        )

    @staticmethod
    def lorebook_info_to_response(
        value: LorebookTypes.LorebookInfo,
    ) -> schemas.LorebookResponseDto:
        return schemas.LorebookResponseDto(
            id=value.id,
            owner_id=value.owner_id,
            title=value.title,
            description=value.description,
            visibility=value.visibility,
            status=value.status,
            created_at=value.created_at,
            updated_at=value.updated_at,
        )
