from app.modules.chatting.conversation import schemas as Schemas
from app.modules.chatting.conversation import types as Types


class ConversationSchemaMapper:
    """Convert HTTP DTOs and application types at the router boundary."""

    @staticmethod
    def conversation_start_request_to_command(
        request: Schemas.StartRequest,
    ) -> Types.ConversationStart:
        return Types.ConversationStart(
            product_id=request.product_id, start_set_id=request.start_set_id
        )

    @staticmethod
    def conversation_switch_request_to_command(
        request: Schemas.SwitchRequest,
    ) -> Types.VersionSwitch:
        return Types.VersionSwitch(target_snapshot_id=request.target_snapshot_id)

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


def pending_updates_view_to_response(result) -> Schemas.PendingUpdatesInfoResponseDto:
    return Schemas.PendingUpdatesInfoResponseDto.model_validate(result)
