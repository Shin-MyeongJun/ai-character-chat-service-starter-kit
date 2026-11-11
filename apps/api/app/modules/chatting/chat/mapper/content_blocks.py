"""Lossless persisted blocks; URLs belong only to the HTTP read projection."""

from uuid import UUID

from app.modules.chatting.chat import types as Types
from app.modules.content.product import types as ProductTypes


def content_blocks_to_json(
    blocks: tuple[ProductTypes.ContentBlockInfo, ...] | None,
) -> list[Types.AnswerJsonValue] | None:
    if blocks is None:
        return None
    return [
        {"type": "text", "text": block.text}
        if isinstance(block, ProductTypes.TextContentBlockInfo)
        else {
            "type": "image",
            "image_item_id": str(block.image_item_id),
            "file_version_id": str(block.file_version_id),
            "alt": block.alt,
        }
        for block in blocks
    ]


def content_blocks_json_to_info(
    value: object,
) -> tuple[ProductTypes.ContentBlockInfo, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("Invalid stored content blocks.")
    blocks: list[ProductTypes.ContentBlockInfo] = []
    for block in value:
        if not isinstance(block, dict):
            raise ValueError("Invalid stored content block.")
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            blocks.append(ProductTypes.TextContentBlockInfo(text=block["text"]))
        elif block.get("type") == "image" and all(
            isinstance(block.get(key), str)
            for key in ("image_item_id", "file_version_id", "alt")
        ):
            blocks.append(
                ProductTypes.ImageContentBlockInfo(
                    image_item_id=UUID(block["image_item_id"]),
                    file_version_id=UUID(block["file_version_id"]),
                    alt=block["alt"],
                )
            )
        else:
            raise ValueError("Invalid stored content block.")
    return tuple(blocks)
