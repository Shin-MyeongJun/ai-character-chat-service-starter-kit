from app.modules.chatting.conversation import schemas, types


class ConversationSchemaMapper:
    """Convert HTTP DTOs and application types at the router boundary."""

    @staticmethod
    def to_start(request: schemas.StartRequest) -> types.ConversationStart:
        return types.ConversationStart(
            product_id=request.product_id, start_set_id=request.start_set_id
        )

    @staticmethod
    def to_switch(request: schemas.SwitchRequest) -> types.VersionSwitch:
        return types.VersionSwitch(target_snapshot_id=request.target_snapshot_id)

    @staticmethod
    def started_response(
        result: types.ConversationStarted,
    ) -> schemas.ConversationStartedResponseDto:
        return schemas.ConversationStartedResponseDto.model_validate(result)

    @staticmethod
    def switched_response(
        result: types.VersionSwitched,
    ) -> schemas.VersionSwitchedResponseDto:
        return schemas.VersionSwitchedResponseDto.model_validate(result)
