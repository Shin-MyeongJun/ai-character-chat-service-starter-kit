from app.modules.governance.admin import schemas as Schemas
from app.modules.governance.admin import types as Types


class AdminSchemaMapper:
    """Convert HTTP DTOs and application types at the router boundary."""

    @staticmethod
    def expiry_request_to_command(request: Schemas.ExpiryRequest) -> Types.ExpiryChange:
        return Types.ExpiryChange(expires_at=request.expires_at, reason=request.reason)

    @staticmethod
    def status_request_to_command(
        request: Schemas.StatusRequest,
    ) -> Types.ProductStatusChange:
        return Types.ProductStatusChange(status=request.status)

    @staticmethod
    def retirement_request_to_command(
        request: Schemas.RetirementRequest,
    ) -> Types.ModelRetirement:
        return Types.ModelRetirement(
            announced_at=request.announced_at, shutdown_at=request.shutdown_at
        )

    @staticmethod
    def expiry_info_to_response(
        result: Types.ExpiryChangedInfo,
    ) -> Schemas.ExpiryChangedResponseDto:
        return Schemas.ExpiryChangedResponseDto.model_validate(result)
