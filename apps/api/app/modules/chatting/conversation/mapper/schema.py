from uuid import UUID

from app.modules.chatting.conversation import schemas as Schemas
from app.modules.chatting.conversation import types as Types
from app.modules.content.product import types as ProductTypes


class ConversationSchemaMapper:
    """Convert HTTP DTOs and application types at the router boundary."""

    @staticmethod
    def conversation_start_request_to_command(
        request: Schemas.StartRequest,
        user_id: UUID,
    ) -> Types.StartConversationCommand:
        return Types.StartConversationCommand(
            product_id=request.product_id,
            user_id=user_id,
            start_set_id=request.start_set_id,
        )

    @staticmethod
    def conversation_switch_request_to_command(
        request: Schemas.SwitchRequest,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Types.SwitchVersionCommand:
        return Types.SwitchVersionCommand(
            conversation_id=conversation_id,
            user_id=user_id,
            target_snapshot_id=request.target_snapshot_id,
        )

    @staticmethod
    def conversation_started_info_to_response(
        result: Types.ConversationStartedInfo,
    ) -> Schemas.ConversationStartedResponseDto:
        return Schemas.ConversationStartedResponseDto.model_validate(result)

    @staticmethod
    def conversation_switched_info_to_response(
        result: Types.VersionSwitchedInfo,
    ) -> Schemas.VersionSwitchedResponseDto:
        return Schemas.VersionSwitchedResponseDto.model_validate(result)

    @staticmethod
    def pending_updates_view_to_response(
        result: ProductTypes.PendingUpdatesView,
    ) -> Schemas.PendingUpdatesInfoResponseDto:
        return Schemas.PendingUpdatesInfoResponseDto.model_validate(result)
