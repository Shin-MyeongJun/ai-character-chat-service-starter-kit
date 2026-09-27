"""Explicit synthetic prices and grants, confined to test schemas."""

from decimal import Decimal

from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import policies as PolicyService
from app.modules.commerce.billing.service.pricing import BillingPricingConfiguration


def answer_pricing(model_id, *, price=10):
    return BillingPricingConfiguration(
        price_book=BillingTypes.PriceBookInfo(
            version="answer-test-v1",
            currency="TEST",
            credits_per_currency_unit=Decimal("1"),
            safety_factor=Decimal("1"),
            models=(
                BillingTypes.ModelPriceInfo(
                    execution=BillingTypes.BillingExecutionInfo(
                        model_id=model_id,
                        provider="openai",
                        model="gpt-test",
                        reasoning_effort="low",
                    ),
                    input_cost_per_token=Decimal("0.00001"),
                    output_cost_per_token=Decimal("0.00002"),
                    tiers=(
                        BillingTypes.ContextPriceTierInfo(
                            tier_id="fixture",
                            min_context_tokens=0,
                            max_context_tokens_exclusive=100000,
                            normal_price_credit=Decimal(price),
                        ),
                    ),
                ),
            ),
        ),
        policies=PolicyService.create_default_policy_registry(),
        quote_ttl_seconds=60,
    )
