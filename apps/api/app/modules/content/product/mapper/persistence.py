from app.modules.content.product.types import ProductInfo


def to_info(entity):
    return ProductInfo(**{name: getattr(entity, name) for name in ProductInfo.__dataclass_fields__})
