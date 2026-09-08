from pydantic import BaseModel, ConfigDict, Field

from app.modules.content.product.types import Visibility


class ProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    opening_message: str | None = Field(default=None, max_length=20000)
    visibility: Visibility = "private"
