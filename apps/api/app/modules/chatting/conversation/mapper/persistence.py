from app.db.models.product_usage import ProductGeneration
from app.modules.chatting.conversation.types import GenerationInfo


def generation_to_info(
    run: ProductGeneration, *, created: bool = False
) -> GenerationInfo:
    return GenerationInfo(
        id=run.id,
        created=created,
        status=run.status,
        product_snapshot_id=run.product_snapshot_id,
        model_id=run.model_id,
        model_name=run.model_name,
        reasoning_effort=run.reasoning_effort,
        message_count=run.message_count,
    )
