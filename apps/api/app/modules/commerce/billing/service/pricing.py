"""Explicit price configuration and deterministic final pricing; no live lookups."""

import re
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, ROUND_HALF_UP, Context, Decimal, localcontext
from uuid import UUID

from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.service import policies as PolicyService

CALCULATION_VERSION = "context-budget-cost-floor-v1"
_MAX_TOKENS = 2**31 - 1
_USER_OPERATIONS = frozenset(
    (
        Types.BillingOperationKind.USER_GENERATION,
        Types.BillingOperationKind.USER_REGENERATION,
        Types.BillingOperationKind.USER_CONTINUATION,
    )
)


def _validate_text(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise Types.BillingPricingError(
            "Expected nonempty text of at most 500 characters."
        )


def _validate_decimal(value: Decimal) -> None:
    # Bounded inputs keep multiplication exact at the fixed calculation precision.
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or value >= Decimal("1e18")
        or value.as_tuple().exponent not in range(-12, 19)
    ):
        raise Types.BillingPricingError(
            "Expected finite nonnegative Decimal < 1e18, scale <= 12."
        )


def _validate_execution(execution: Types.BillingExecutionInfo) -> None:
    if not isinstance(execution.model_id, UUID):
        raise Types.BillingPricingError("model_id must be UUID.")
    for value in (execution.provider, execution.model, execution.reasoning_effort):
        _validate_text(value)
    if not isinstance(execution.pricing_settings, tuple):
        raise Types.BillingPricingError("Pricing settings must be an immutable tuple.")
    names = []
    for setting in execution.pricing_settings:
        _validate_text(setting.name)
        _validate_text(setting.value)
        names.append(setting.name)
    if names != sorted(set(names)):
        raise Types.BillingPricingError(
            "Pricing settings must be unique and sorted by name."
        )


def _validate_request(request: Types.BillingRequestInfo) -> None:
    if not all(
        isinstance(value, UUID) for value in (request.user_id, request.request_key)
    ):
        raise Types.BillingPricingError("User and request keys must be UUIDs.")
    if (
        not isinstance(request.operation_kind, Types.BillingOperationKind)
        or request.operation_kind not in _USER_OPERATIONS
    ):
        raise Types.BillingPricingError(
            "Only authorized user paid generation can be quoted."
        )
    if not isinstance(request.operation_fingerprint, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", request.operation_fingerprint
    ):
        raise Types.BillingPricingError(
            "Expected canonical sha256 operation fingerprint."
        )
    if request.product is not None and not all(
        isinstance(value, UUID)
        for value in (request.product.product_id, request.product.product_snapshot_id)
    ):
        raise Types.BillingPricingError("Product identifiers must be UUIDs.")
    _validate_execution(request.execution)
    for tokens in (request.input_tokens, request.max_output_tokens):
        if type(tokens) is not int or not 0 <= tokens <= _MAX_TOKENS:
            raise Types.BillingPricingError(
                "Token budgets must be nonnegative bounded integers."
            )


def _validate_price_book(book: Types.PriceBookInfo) -> None:
    _validate_text(book.version)
    _validate_text(book.currency)
    for value in (book.credits_per_currency_unit, book.safety_factor):
        _validate_decimal(value)
    if book.credits_per_currency_unit <= 0 or book.safety_factor < 1:
        raise Types.BillingPricingError(
            "Conversion must be positive and safety factor >= 1."
        )
    if not isinstance(book.models, tuple) or not book.models:
        raise Types.BillingPricingError(
            "Price book must contain explicit model prices."
        )
    executions = set()
    for model in book.models:
        _validate_execution(model.execution)
        if model.execution in executions:
            raise Types.BillingPricingError("Duplicate execution price configuration.")
        executions.add(model.execution)
        _validate_decimal(model.input_cost_per_token)
        _validate_decimal(model.output_cost_per_token)
        if not isinstance(model.tiers, tuple) or not model.tiers:
            raise Types.BillingPricingError("Model requires explicit context tiers.")
        tier_ids: set[str] = set()
        for tier in model.tiers:
            _validate_text(tier.tier_id)
            _validate_decimal(tier.normal_price_credit)
            if (
                type(tier.min_context_tokens) is not int
                or type(tier.max_context_tokens_exclusive) is not int
                or not 0
                <= tier.min_context_tokens
                < tier.max_context_tokens_exclusive
                <= 2 * _MAX_TOKENS + 1
                or tier.tier_id in tier_ids
            ):
                raise Types.BillingPricingError("Invalid or duplicate context tier.")
            tier_ids.add(tier.tier_id)
        ordered = sorted(model.tiers, key=lambda tier: tier.min_context_tokens)
        if any(
            left.max_context_tokens_exclusive > right.min_context_tokens
            for left, right in zip(ordered, ordered[1:])
        ):
            raise Types.BillingPricingError("Overlapping context tiers.")


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingPricingConfiguration:
    """Server-owned dependency. No production prices or fallback book are supplied."""

    price_book: Types.PriceBookInfo | None
    policies: PolicyService.PricingPolicyRegistry
    quote_ttl_seconds: int

    def __post_init__(self) -> None:
        if (
            type(self.quote_ttl_seconds) is not int
            or not 0 < self.quote_ttl_seconds <= 86400
        ):
            raise Types.BillingPricingError("Quote TTL must be 1..86400 seconds.")
        if self.price_book is not None:
            _validate_price_book(self.price_book)
        for registration in self.policies.registrations:
            _validate_text(registration.adapter.policy.policy_id)
            _validate_text(registration.adapter.policy.version)


def calculate_billing_price(
    command: Types.CalculateBillingPriceCommand,
    *,
    configuration: BillingPricingConfiguration,
) -> Types.BillingPriceInfo:
    request = command.request
    _validate_request(request)
    book = configuration.price_book
    if book is None:
        raise Types.BillingPricingError("Price book is not configured.")
    model = next(
        (item for item in book.models if item.execution == request.execution), None
    )
    if model is None:
        raise Types.BillingPricingError("Unsupported model or execution settings.")
    context_tokens = request.input_tokens + request.max_output_tokens
    tier = next(
        (
            item
            for item in model.tiers
            if item.min_context_tokens
            <= context_tokens
            < item.max_context_tokens_exclusive
        ),
        None,
    )
    if tier is None:
        raise Types.BillingPricingError("Context budget outside configured tiers.")
    with localcontext(Context(prec=160, rounding=ROUND_HALF_UP)):
        current = tier.normal_price_credit
        results = []
        for registration in configuration.policies.registrations:
            result = registration.adapter.apply_policy(
                Types.ApplyPricingPolicyCommand(
                    request=request,
                    normal_price_credit=tier.normal_price_credit,
                    current_price_credit=current,
                )
            )
            if not isinstance(result, Types.PricingPolicyResultInfo):
                raise Types.BillingPricingError("Invalid policy result.")
            _validate_decimal(result.input_price_credit)
            _validate_decimal(result.output_price_credit)
            if (
                result.policy != registration.adapter.policy
                or result.input_price_credit != current
                or not isinstance(result.status, Types.PricingPolicyStatus)
                or (
                    result.status != Types.PricingPolicyStatus.APPLIED
                    and result.output_price_credit != current
                )
            ):
                raise Types.BillingPricingError("Inconsistent policy result.")
            if not result.reason:
                if result.status is Types.PricingPolicyStatus.APPLIED:
                    raise Types.BillingPricingError("Applied policy requires a reason.")
                result = replace(
                    result, reason=f"Policy reported {result.status.value}."
                )
            _validate_text(result.reason)
            results.append(result)
            current = result.output_price_credit
        # These are fixed finalization steps, never replaceable policy adapters.
        cost_floor = (
            (
                request.input_tokens * model.input_cost_per_token
                + request.max_output_tokens * model.output_cost_per_token
            )
            * book.credits_per_currency_unit
            * book.safety_factor
        )
        final = int(max(current, cost_floor).to_integral_value(rounding=ROUND_CEILING))
        if final > 2**63 - 1:
            raise Types.BillingPricingError(
                "Final price exceeds supported credit range."
            )
        normal = tier.normal_price_credit
        discount = Decimal(0)
        if normal > 0 and final < normal:
            discount = ((normal - final) * 100 / normal).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return Types.BillingPriceInfo(
            price_book_version=book.version,
            context_tier_id=tier.tier_id,
            calculation_version=CALCULATION_VERSION,
            normal_price_credit=normal,
            cost_floor_credit=cost_floor,
            final_price_credit=final,
            display_discount_percent=discount,
            policy_results=tuple(results),
            cost_floor_exceeds_normal=cost_floor > normal,
            basis=Types.BillingPriceBasisInfo(
                context_tokens=context_tokens,
                min_context_tokens=tier.min_context_tokens,
                max_context_tokens_exclusive=tier.max_context_tokens_exclusive,
                currency=book.currency,
                input_cost_per_token=model.input_cost_per_token,
                output_cost_per_token=model.output_cost_per_token,
                credits_per_currency_unit=book.credits_per_currency_unit,
                safety_factor=book.safety_factor,
            ),
        )
