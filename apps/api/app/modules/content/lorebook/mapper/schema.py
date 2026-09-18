# 인증 owner를 요청과 합쳐 Command로 변환한다. 삭제 응답 deleted=True는 성공 종료이며 반복 삭제 보장이 아니다.
from uuid import UUID

from app.modules.content.lorebook import schemas as Schemas
from app.modules.content.lorebook import types as Types


class LorebookSchemaMapper:
    @staticmethod
    def create_lorebook_request_to_command(
        request: Schemas.CreateLorebookRequestDto,
        owner_id: UUID,
    ) -> Types.CreateLorebookCommand:
        return Types.CreateLorebookCommand(
            owner_id=owner_id,
            title=request.title,
            description=request.description,
            visibility=request.visibility,
        )

    @staticmethod
    def update_lorebook_request_to_command(
        request: Schemas.UpdateLorebookRequestDto,
        owner_id: UUID,
    ) -> Types.UpdateLorebookCommand:
        return Types.UpdateLorebookCommand(
            lorebook_id=request.lorebook_id,
            owner_id=owner_id,
            title=request.title,
            description=request.description,
            visibility=request.visibility,
        )

    @staticmethod
    def change_lorebook_status_request_to_command(
        request: Schemas.ChangeLorebookStatusRequestDto,
        owner_id: UUID,
    ) -> Types.ChangeLorebookStatusCommand:
        return Types.ChangeLorebookStatusCommand(
            lorebook_id=request.lorebook_id,
            owner_id=owner_id,
            status=request.status,
        )

    @staticmethod
    def delete_lorebook_request_to_command(
        request: Schemas.DeleteLorebookRequestDto,
        owner_id: UUID,
    ) -> Types.DeleteLorebookCommand:
        return Types.DeleteLorebookCommand(
            lorebook_id=request.lorebook_id,
            owner_id=owner_id,
        )

    @staticmethod
    def create_entry_request_to_command(
        request: Schemas.CreateLorebookEntryRequestDto,
        owner_id: UUID,
    ) -> Types.CreateLorebookEntryCommand:
        return Types.CreateLorebookEntryCommand(
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
        request: Schemas.UpdateLorebookEntryRequestDto,
        owner_id: UUID,
    ) -> Types.UpdateLorebookEntryCommand:
        return Types.UpdateLorebookEntryCommand(
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
        request: Schemas.DeleteLorebookEntryRequestDto,
        owner_id: UUID,
    ) -> Types.DeleteLorebookEntryCommand:
        return Types.DeleteLorebookEntryCommand(
            lorebook_id=request.lorebook_id,
            entry_id=request.entry_id,
            owner_id=owner_id,
        )

    @staticmethod
    def cursor_request_to_value(
        request: Schemas.CursorRequestDto,
    ) -> Types.LorebookCursor | None:
        if request.cursor_created_at is None and request.cursor_id is None:
            return None
        if request.cursor_created_at is None or request.cursor_id is None:
            raise ValueError(
                "cursor_created_at and cursor_id must be provided together."
            )
        return Types.LorebookCursor(
            created_at=request.cursor_created_at,
            id=request.cursor_id,
        )

    @staticmethod
    def lorebook_info_to_response(
        value: Types.LorebookInfo,
    ) -> Schemas.LorebookResponseDto:
        return Schemas.LorebookResponseDto(
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
        value: Types.LorebookEntryInfo,
    ) -> Schemas.LorebookEntryResponseDto:
        return Schemas.LorebookEntryResponseDto(
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
        value: Types.LorebookCursor | None,
    ) -> Schemas.LorebookCursorResponseDto | None:
        if value is None:
            return None
        return Schemas.LorebookCursorResponseDto(
            created_at=value.created_at,
            id=value.id,
        )

    @classmethod
    def lorebook_page_to_response(
        cls,
        page: Types.LorebookPage[Types.LorebookInfo],
    ) -> Schemas.ListLorebooksResponseDto:
        return Schemas.ListLorebooksResponseDto(
            lorebooks=[cls.lorebook_info_to_response(item) for item in page.items],
            next_cursor=cls._cursor_to_response(page.next_cursor),
        )

    @classmethod
    def entry_page_to_response(
        cls,
        page: Types.LorebookEntryPage[Types.LorebookEntryInfo],
    ) -> Schemas.ListLorebookEntriesResponseDto:
        return Schemas.ListLorebookEntriesResponseDto(
            entries=[cls.entry_info_to_response(item) for item in page.items],
            next_cursor=cls._cursor_to_response(page.next_cursor),
        )

    @classmethod
    def lorebook_info_to_create_response(
        cls,
        value: Types.LorebookInfo,
    ) -> Schemas.CreateLorebookResponseDto:
        return Schemas.CreateLorebookResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def lorebook_info_to_update_response(
        cls,
        value: Types.LorebookInfo,
    ) -> Schemas.UpdateLorebookResponseDto:
        return Schemas.UpdateLorebookResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def lorebook_info_to_status_response(
        cls,
        value: Types.LorebookInfo,
    ) -> Schemas.ChangeLorebookStatusResponseDto:
        return Schemas.ChangeLorebookStatusResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def lorebook_info_to_get_response(
        cls,
        value: Types.LorebookInfo,
    ) -> Schemas.GetLorebookByIdResponseDto:
        return Schemas.GetLorebookByIdResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def entry_info_to_create_response(
        cls,
        value: Types.LorebookEntryInfo,
    ) -> Schemas.CreateLorebookEntryResponseDto:
        return Schemas.CreateLorebookEntryResponseDto(
            entry=cls.entry_info_to_response(value)
        )

    @classmethod
    def entry_info_to_update_response(
        cls,
        value: Types.LorebookEntryInfo,
    ) -> Schemas.UpdateLorebookEntryResponseDto:
        return Schemas.UpdateLorebookEntryResponseDto(
            entry=cls.entry_info_to_response(value)
        )

    @classmethod
    def entry_info_to_get_response(
        cls,
        value: Types.LorebookEntryInfo,
    ) -> Schemas.GetLorebookEntryResponseDto:
        return Schemas.GetLorebookEntryResponseDto(
            entry=cls.entry_info_to_response(value)
        )

    @staticmethod
    def delete_lorebook_result_to_response(
        result: None,
    ) -> Schemas.DeleteLorebookResponseDto:
        return Schemas.DeleteLorebookResponseDto(deleted=True)

    @staticmethod
    def delete_entry_result_to_response(
        result: None,
    ) -> Schemas.DeleteLorebookEntryResponseDto:
        return Schemas.DeleteLorebookEntryResponseDto(deleted=True)
