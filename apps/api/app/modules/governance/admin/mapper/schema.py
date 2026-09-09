from app.modules.governance.admin import schemas, types


class AdminSchemaMapper:
    """Convert HTTP DTOs and application types at the router boundary."""

    @staticmethod
    def to_expiry(request: schemas.ExpiryRequest) -> types.ExpiryChange:
        return types.ExpiryChange(expires_at=request.expires_at, reason=request.reason)

    @staticmethod
    def to_status(request: schemas.StatusRequest) -> types.ProductStatusChange:
        return types.ProductStatusChange(status=request.status)

    @staticmethod
    def to_retirement(request: schemas.RetirementRequest) -> types.ModelRetirement:
        return types.ModelRetirement(
            announced_at=request.announced_at, shutdown_at=request.shutdown_at
        )

    @staticmethod
    def expiry_response(
        result: types.ExpiryChanged,
    ) -> schemas.ExpiryChangedResponseDto:
        return schemas.ExpiryChangedResponseDto.model_validate(result)
