"""Models currently eligible for owner publication settings."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.http.dependencies import Session
from app.modules.llm.service import query as ModelQuery

router = APIRouter(prefix="/models", tags=["models"])


class AvailableModelDto(BaseModel):
    id: UUID
    name: str
    reasoning_efforts: list[str]


@router.get("/available", response_model=list[AvailableModelDto])
async def available_models(session: Session):
    now = datetime.now(UTC)
    models = await ModelQuery.list_candidate_models(session)
    return [
        AvailableModelDto(
            id=model.id,
            name=model.model_name,
            reasoning_efforts=[value for value in model.capabilities.get("reasoning_efforts", []) if isinstance(value, str)],
        )
        for model in models
        if model.is_enabled and (model.shutdown_at is None or model.shutdown_at > now)
    ]
