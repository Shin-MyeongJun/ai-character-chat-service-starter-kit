from uuid import UUID

from app.modules.lorebook import schemas, types


class LorebookSchemaMapper:
    @staticmethod
    def create_lorebook_request_to_command(
        request: schemas.CreateLorebookRequestDto,
        owner_id: UUID,
    ) -> types.LorebookCreate:
        return types.LorebookCreate(
            owner_id=owner_id,
            title=request.title,
            description=request.description,
            visibility=request.visibility,
        )

    @staticmethod
    def update_lorebook_request_to_command(
        request: schemas.UpdateLorebookRequestDto,
        owner_id: UUID,
    ) -> types.LorebookUpdate:
        return types.LorebookUpdate(
            lorebook_id=request.lorebook_id,
            owner_id=owner_id,
            title=request.title,
            description=request.description,
            visibility=request.visibility,
        )

    @staticmethod
    def change_lorebook_status_request_to_command(
        request: schemas.ChangeLorebookStatusRequestDto,
        owner_id: UUID,
    ) -> types.LorebookStatusChange:
        return types.LorebookStatusChange(
            lorebook_id=request.lorebook_id,
            owner_id=owner_id,
            status=request.status,
        )

    @staticmethod
    def delete_lorebook_request_to_command(
        request: schemas.DeleteLorebookRequestDto,
        owner_id: UUID,
    ) -> types.LorebookDelete:
        return types.LorebookDelete(
            lorebook_id=request.lorebook_id,
            owner_id=owner_id,
        )

    @staticmethod
    def create_entry_request_to_command(
        request: schemas.CreateLorebookEntryRequestDto,
        owner_id: UUID,
    ) -> types.LorebookEntryCreate:
        return types.LorebookEntryCreate(
            lorebook_id=request.lorebook_id,
            owner_id=owner_id,
            title=request.title,
            content=request.content,
            entry_type=request.entry_type,
            activation_type=request.activation_type,
            key_triggers=request.key_triggers,
            match_mode=request.match_mode,
            priority=request.priority,
            token_budget=request.token_budget,
            placement=request.placement,
            is_enabled=request.is_enabled,
            metadata=request.metadata,
        )

    @staticmethod
    def update_entry_request_to_command(
        request: schemas.UpdateLorebookEntryRequestDto,
        owner_id: UUID,
    ) -> types.LorebookEntryUpdate:
        return types.LorebookEntryUpdate(
            lorebook_id=request.lorebook_id,
            entry_id=request.entry_id,
            owner_id=owner_id,
            title=request.title,
            content=request.content,
            entry_type=request.entry_type,
            activation_type=request.activation_type,
            key_triggers=request.key_triggers,
            match_mode=request.match_mode,
            priority=request.priority,
            token_budget=request.token_budget,
            placement=request.placement,
            is_enabled=request.is_enabled,
            metadata=request.metadata,
        )

    @staticmethod
    def delete_entry_request_to_command(
        request: schemas.DeleteLorebookEntryRequestDto,
        owner_id: UUID,
    ) -> types.LorebookEntryDelete:
        return types.LorebookEntryDelete(
            lorebook_id=request.lorebook_id,
            entry_id=request.entry_id,
            owner_id=owner_id,
        )

    @staticmethod
    def cursor_request_to_value(
        request: schemas.CursorRequestDto,
    ) -> types.LorebookCursor | None:
        if request.cursor_created_at is None and request.cursor_id is None:
            return None
        if request.cursor_created_at is None or request.cursor_id is None:
            raise ValueError(
                "cursor_created_at and cursor_id must be provided together."
            )
        return types.LorebookCursor(
            created_at=request.cursor_created_at,
            id=request.cursor_id,
        )

    @staticmethod
    def lorebook_info_to_response(
        value: types.LorebookInfo,
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

    @staticmethod
    def entry_info_to_response(
        value: types.LorebookEntryInfo,
    ) -> schemas.LorebookEntryResponseDto:
        return schemas.LorebookEntryResponseDto(
            id=value.id,
            lorebook_id=value.lorebook_id,
            title=value.title,
            content=value.content,
            entry_type=value.entry_type,
            activation_type=value.activation_type,
            key_triggers=value.key_triggers,
            match_mode=value.match_mode,
            priority=value.priority,
            token_budget=value.token_budget,
            placement=value.placement,
            is_enabled=value.is_enabled,
            metadata=value.metadata,
            created_at=value.created_at,
            updated_at=value.updated_at,
        )

    @staticmethod
    def _cursor_to_response(
        value: types.LorebookCursor | None,
    ) -> schemas.LorebookCursorResponseDto | None:
        if value is None:
            return None
        return schemas.LorebookCursorResponseDto(
            created_at=value.created_at,
            id=value.id,
        )

    @classmethod
    def lorebook_page_to_response(
        cls,
        page: types.LorebookPage[types.LorebookInfo],
    ) -> schemas.ListLorebooksResponseDto:
        return schemas.ListLorebooksResponseDto(
            lorebooks=[cls.lorebook_info_to_response(item) for item in page.items],
            next_cursor=cls._cursor_to_response(page.next_cursor),
        )

    @classmethod
    def entry_page_to_response(
        cls,
        page: types.LorebookEntryPage[types.LorebookEntryInfo],
    ) -> schemas.ListLorebookEntriesResponseDto:
        return schemas.ListLorebookEntriesResponseDto(
            entries=[cls.entry_info_to_response(item) for item in page.items],
            next_cursor=cls._cursor_to_response(page.next_cursor),
        )

    @classmethod
    def lorebook_info_to_create_response(
        cls,
        value: types.LorebookInfo,
    ) -> schemas.CreateLorebookResponseDto:
        return schemas.CreateLorebookResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def lorebook_info_to_update_response(
        cls,
        value: types.LorebookInfo,
    ) -> schemas.UpdateLorebookResponseDto:
        return schemas.UpdateLorebookResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def lorebook_info_to_status_response(
        cls,
        value: types.LorebookInfo,
    ) -> schemas.ChangeLorebookStatusResponseDto:
        return schemas.ChangeLorebookStatusResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def lorebook_info_to_get_response(
        cls,
        value: types.LorebookInfo,
    ) -> schemas.GetLorebookByIdResponseDto:
        return schemas.GetLorebookByIdResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def entry_info_to_create_response(
        cls,
        value: types.LorebookEntryInfo,
    ) -> schemas.CreateLorebookEntryResponseDto:
        return schemas.CreateLorebookEntryResponseDto(
            entry=cls.entry_info_to_response(value)
        )

    @classmethod
    def entry_info_to_update_response(
        cls,
        value: types.LorebookEntryInfo,
    ) -> schemas.UpdateLorebookEntryResponseDto:
        return schemas.UpdateLorebookEntryResponseDto(
            entry=cls.entry_info_to_response(value)
        )

    @classmethod
    def entry_info_to_get_response(
        cls,
        value: types.LorebookEntryInfo,
    ) -> schemas.GetLorebookEntryResponseDto:
        return schemas.GetLorebookEntryResponseDto(
            entry=cls.entry_info_to_response(value)
        )

    @staticmethod
    def delete_lorebook_result_to_response(
        result: None,
    ) -> schemas.DeleteLorebookResponseDto:
        return schemas.DeleteLorebookResponseDto(deleted=True)

    @staticmethod
    def delete_entry_result_to_response(
        result: None,
    ) -> schemas.DeleteLorebookEntryResponseDto:
        return schemas.DeleteLorebookEntryResponseDto(deleted=True)
