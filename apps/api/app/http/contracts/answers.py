# input_message_id는 이미 저장된 마지막 사용자 메시지, expected_revision은 그 메시지의 수정 버전이다.
# product_character_id는 원본 character_id가 아니라 상품 구성 안의 참여 캐릭터 식별자다.
# retryable은 새 시도 가능성 표기이며 같은 request_key 재전송은 기존 생성 상태를 돌려준다.
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GenerateAnswerRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=128)
    input_message_id: UUID
    expected_revision: int = Field(ge=1)
    product_character_id: UUID


class GenerateAnswerResponseDto(BaseModel):
    generation_id: UUID
    status: str
    content: str | None
    model: str
    error_code: str | None
    retryable: bool
    uncertain: bool
