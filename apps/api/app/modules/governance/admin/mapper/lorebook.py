from app.modules.content.lorebook import types as LorebookTypes
from app.modules.governance.admin.schemas import lorebook as schemas


class LorebookSchemaMapper:
    @classmethod
    def entry_info_to_get_response(
        cls,
        value: LorebookTypes.LorebookEntryInfo,
    ) -> schemas.GetLorebookEntryResponseDto:
        return schemas.GetLorebookEntryResponseDto(
            entry=cls.entry_info_to_response(value)
        )

    @classmethod
    def entry_page_to_response(
        cls,
        page: LorebookTypes.LorebookEntryPage[LorebookTypes.LorebookEntryInfo],
    ) -> schemas.ListLorebookEntriesResponseDto:
        return schemas.ListLorebookEntriesResponseDto(
            entries=[cls.entry_info_to_response(item) for item in page.items],
            next_cursor=cls._cursor_to_response(page.next_cursor),
        )

    @classmethod
    def lorebook_info_to_get_response(
        cls,
        value: LorebookTypes.LorebookInfo,
    ) -> schemas.GetLorebookByIdResponseDto:
        return schemas.GetLorebookByIdResponseDto(
            lorebook=cls.lorebook_info_to_response(value)
        )

    @classmethod
    def lorebook_page_to_response(
        cls,
        page: LorebookTypes.LorebookPage[LorebookTypes.LorebookInfo],
    ) -> schemas.ListLorebooksResponseDto:
        return schemas.ListLorebooksResponseDto(
            lorebooks=[cls.lorebook_info_to_response(item) for item in page.items],
            next_cursor=cls._cursor_to_response(page.next_cursor),
        )

    @staticmethod
    def cursor_request_to_value(
        request: schemas.CursorRequestDto,
    ) -> LorebookTypes.LorebookCursor | None:
        if request.cursor_created_at is None and request.cursor_id is None:
            return None
        if request.cursor_created_at is None or request.cursor_id is None:
            raise ValueError(
                "cursor_created_at and cursor_id must be provided together."
            )
        return LorebookTypes.LorebookCursor(
            created_at=request.cursor_created_at,
            id=request.cursor_id,
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

    @staticmethod
    def entry_info_to_response(
        value: LorebookTypes.LorebookEntryInfo,
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
        value: LorebookTypes.LorebookCursor | None,
    ) -> schemas.LorebookCursorResponseDto | None:
        if value is None:
            return None
        return schemas.LorebookCursorResponseDto(
            created_at=value.created_at,
            id=value.id,
        )
