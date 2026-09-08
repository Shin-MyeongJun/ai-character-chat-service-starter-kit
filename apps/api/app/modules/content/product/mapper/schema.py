from app.modules.content.product.types import ProductWrite


def to_write(request):
    return ProductWrite(**request.model_dump())
