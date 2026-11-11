from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.content.product import types as ProductTypes


class TextContentBlockResponseDto(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageContentBlockResponseDto(BaseModel):
    type: Literal["image"] = "image"
    image_item_id: UUID
    file_version_id: UUID
    alt: str
    content_url: str


ContentBlockResponseDto = Annotated[
    TextContentBlockResponseDto | ImageContentBlockResponseDto,
    Field(discriminator="type"),
]


def content_blocks_to_response(
    blocks: tuple[ProductTypes.ContentBlockInfo, ...], occurrence_url: str
) -> list[ContentBlockResponseDto]:
    return [
        TextContentBlockResponseDto(type="text", text=block.text)
        if isinstance(block, ProductTypes.TextContentBlockInfo)
        else ImageContentBlockResponseDto(
            type="image",
            image_item_id=block.image_item_id,
            file_version_id=block.file_version_id,
            alt=block.alt,
            content_url=f"{occurrence_url}/blocks/{index}/content",
        )
        for index, block in enumerate(blocks)
    ]
