from dataclasses import asdict
from uuid import UUID

from app.http.contracts import answers as Schemas
from app.use_cases.answers import AnswerInfo, GenerateAnswerCommand


def answer_request_to_command(
    value: Schemas.GenerateAnswerRequestDto, conversation_id: UUID, owner_id: UUID
) -> GenerateAnswerCommand:
    return GenerateAnswerCommand(
        conversation_id=conversation_id, user_id=owner_id, **value.model_dump()
    )


def answer_info_to_response(value: AnswerInfo) -> Schemas.GenerateAnswerResponseDto:
    return Schemas.GenerateAnswerResponseDto(**asdict(value))
