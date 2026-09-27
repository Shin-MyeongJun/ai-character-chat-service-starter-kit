"""Load an operator-supplied price book; never synthesize operational prices."""

import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.service import policies as PolicyService
from app.modules.commerce.billing.service.pricing import BillingPricingConfiguration


def _parse_decimal(value: str) -> Decimal:
    if not isinstance(value, str):
        raise Types.BillingPricingError(
            "Billing monetary values must be decimal strings."
        )
    return Decimal(value)


def load_billing_pricing_configuration() -> BillingPricingConfiguration | None:
    """Missing configuration disables new answers but leaves recovery available."""
    path = os.getenv("BILLING_PRICING_CONFIG_PATH", "").strip()
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        book = data["price_book"]
        models = []
        for model in book["models"]:
            execution = model["execution"]
            models.append(
                Types.ModelPriceInfo(
                    execution=Types.BillingExecutionInfo(
                        model_id=UUID(execution["model_id"]),
                        provider=execution["provider"],
                        model=execution["model"],
                        reasoning_effort=execution["reasoning_effort"],
                        pricing_settings=tuple(
                            Types.PricingSettingInfo(**setting)
                            for setting in execution.get("pricing_settings", [])
                        ),
                    ),
                    tiers=tuple(
                        Types.ContextPriceTierInfo(
                            **{
                                **tier,
                                "normal_price_credit": _parse_decimal(
                                    tier["normal_price_credit"]
                                ),
                            }
                        )
                        for tier in model["tiers"]
                    ),
                    input_cost_per_token=_parse_decimal(model["input_cost_per_token"]),
                    output_cost_per_token=_parse_decimal(
                        model["output_cost_per_token"]
                    ),
                )
            )
        return BillingPricingConfiguration(
            price_book=Types.PriceBookInfo(
                version=book["version"],
                currency=book["currency"],
                credits_per_currency_unit=_parse_decimal(
                    book["credits_per_currency_unit"]
                ),
                safety_factor=_parse_decimal(book["safety_factor"]),
                models=tuple(models),
            ),
            policies=PolicyService.create_default_policy_registry(),
            quote_ttl_seconds=data["quote_ttl_seconds"],
        )
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as exc:
        raise Types.BillingPricingError(
            "Invalid billing pricing configuration."
        ) from exc
