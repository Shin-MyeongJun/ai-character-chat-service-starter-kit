"""Versioned persistence conversion. Decimal values never pass through floats."""

import json
from dataclasses import asdict
from decimal import Decimal
from typing import Any, overload
from uuid import UUID

from app.db.models.billing_quote import BillingQuote
from app.modules.commerce.billing import types as Types


def _scalar_to_json(value: object) -> str:
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    raise TypeError(f"Unsupported quote value: {type(value).__name__}")


def quote_info_to_snapshots(
    info: Types.BillingQuoteInfo,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "schema_version": 1,
            "value": json.loads(
                json.dumps(asdict(info.request), default=_scalar_to_json)
            ),
        },
        {
            "schema_version": 1,
            "value": json.loads(
                json.dumps(asdict(info.price), default=_scalar_to_json)
            ),
        },
    )


@overload
def quote_entity_to_info(entity: BillingQuote) -> Types.BillingQuoteInfo: ...


@overload
def quote_entity_to_info(entity: None) -> None: ...


def quote_entity_to_info(entity: BillingQuote | None) -> Types.BillingQuoteInfo | None:
    if entity is None:
        return None
    if (
        entity.request_snapshot["schema_version"] != 1
        or entity.price_snapshot["schema_version"] != 1
    ):
        raise ValueError("Unsupported persisted billing quote schema.")
    request = entity.request_snapshot["value"]
    execution = request["execution"]
    product = request["product"]
    price = entity.price_snapshot["value"]
    basis = price["basis"]
    return Types.BillingQuoteInfo(
        id=entity.id,
        request=Types.BillingRequestInfo(
            user_id=entity.user_id,
            request_key=entity.request_key,
            operation_kind=Types.BillingOperationKind(request["operation_kind"]),
            operation_fingerprint=request["operation_fingerprint"],
            product=None
            if product is None
            else Types.BillingProductInfo(
                product_id=UUID(product["product_id"]),
                product_snapshot_id=UUID(product["product_snapshot_id"]),
            ),
            execution=Types.BillingExecutionInfo(
                model_id=UUID(execution["model_id"]),
                provider=execution["provider"],
                model=execution["model"],
                reasoning_effort=execution["reasoning_effort"],
                pricing_settings=tuple(
                    Types.PricingSettingInfo(**item)
                    for item in execution["pricing_settings"]
                ),
            ),
            input_tokens=request["input_tokens"],
            max_output_tokens=request["max_output_tokens"],
        ),
        price=Types.BillingPriceInfo(
            price_book_version=price["price_book_version"],
            context_tier_id=price["context_tier_id"],
            calculation_version=price["calculation_version"],
            normal_price_credit=Decimal(price["normal_price_credit"]),
            cost_floor_credit=Decimal(price["cost_floor_credit"]),
            final_price_credit=price["final_price_credit"],
            display_discount_percent=Decimal(price["display_discount_percent"]),
            cost_floor_exceeds_normal=price["cost_floor_exceeds_normal"],
            policy_results=tuple(
                Types.PricingPolicyResultInfo(
                    policy=Types.PricingPolicyInfo(**item["policy"]),
                    status=Types.PricingPolicyStatus(item["status"]),
                    input_price_credit=Decimal(item["input_price_credit"]),
                    output_price_credit=Decimal(item["output_price_credit"]),
                    reason=item["reason"],
                )
                for item in price["policy_results"]
            ),
            basis=None
            if basis is None
            else Types.BillingPriceBasisInfo(
                context_tokens=basis["context_tokens"],
                min_context_tokens=basis["min_context_tokens"],
                max_context_tokens_exclusive=basis["max_context_tokens_exclusive"],
                currency=basis["currency"],
                input_cost_per_token=Decimal(basis["input_cost_per_token"]),
                output_cost_per_token=Decimal(basis["output_cost_per_token"]),
                credits_per_currency_unit=Decimal(basis["credits_per_currency_unit"]),
                safety_factor=Decimal(basis["safety_factor"]),
            ),
        ),
        status=Types.BillingQuoteStatus.QUOTED,
        expires_at=entity.expires_at,
    )
