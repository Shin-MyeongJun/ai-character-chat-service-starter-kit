# HTTP 경로의 대화 ID와 인증 owner를 요청 DTO에 합쳐 답변 Command로 전달한다.
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
