"""All prices below are synthetic test fixtures, never operational defaults."""

from dataclasses import dataclass, replace
from decimal import Decimal, Inexact, localcontext
from uuid import uuid4

import pytest
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.service import policies as PolicyService
from app.modules.commerce.billing.service import pricing as PricingService


@pytest.fixture(name="request_info")
def _request_info():
    return Types.BillingRequestInfo(
        user_id=uuid4(),
        request_key=uuid4(),
        operation_kind=Types.BillingOperationKind.USER_GENERATION,
        operation_fingerprint="sha256:" + "a" * 64,
        product=Types.BillingProductInfo(
            product_id=uuid4(), product_snapshot_id=uuid4()
        ),
        execution=Types.BillingExecutionInfo(
            model_id=uuid4(),
            provider="fixture",
            model="fixture-model",
            reasoning_effort="low",
        ),
        input_tokens=60,
        max_output_tokens=30,
    )


@pytest.fixture(name="configuration")
def _configuration(request_info):
    return PricingService.BillingPricingConfiguration(
        price_book=Types.PriceBookInfo(
            version="test-only-v1",
            currency="TEST",
            credits_per_currency_unit=Decimal("2"),
            safety_factor=Decimal("1.25"),
            models=(
                Types.ModelPriceInfo(
                    execution=request_info.execution,
                    input_cost_per_token=Decimal("0.01"),
                    output_cost_per_token=Decimal("0.02"),
                    tiers=(
                        Types.ContextPriceTierInfo(
                            tier_id="small",
                            min_context_tokens=0,
                            max_context_tokens_exclusive=100,
                            normal_price_credit=Decimal("10"),
                        ),
                        Types.ContextPriceTierInfo(
                            tier_id="large",
                            min_context_tokens=100,
                            max_context_tokens_exclusive=200,
                            normal_price_credit=Decimal("20"),
                        ),
                    ),
                ),
            ),
        ),
        policies=PolicyService.create_default_policy_registry(),
        quote_ttl_seconds=60,
    )


def calculate(request_info, configuration):
    return PricingService.calculate_billing_price(
        Types.CalculateBillingPriceCommand(request=request_info),
        configuration=configuration,
    )


@dataclass(frozen=True)
class AdjustmentAdapter:
    policy_id: str
    multiplier: Decimal = Decimal("1")
    adjustment: Decimal = Decimal("0")

    @property
    def policy(self) -> Types.PricingPolicyInfo:
        return Types.PricingPolicyInfo(
            policy_id=self.policy_id, version="test-policy-v1"
        )

    def apply_policy(
        self, command: Types.ApplyPricingPolicyCommand
    ) -> Types.PricingPolicyResultInfo:
        return Types.PricingPolicyResultInfo(
            policy=self.policy,
            status=Types.PricingPolicyStatus.APPLIED,
            input_price_credit=command.current_price_credit,
            output_price_credit=command.current_price_credit * self.multiplier
            + self.adjustment,
            reason="Synthetic test adjustment",
        )


def registry(*adapters):
    return PolicyService.PricingPolicyRegistry(
        tuple(
            PolicyService.PricingPolicyRegistration(order=index, adapter=adapter)
            for index, adapter in enumerate(adapters)
        )
    )


@pytest.mark.parametrize(
    ("tokens", "tier", "price"),
    [(0, "small", 10), (99, "small", 10), (100, "large", 20), (199, "large", 20)],
)
def test_context_boundaries_and_noop_prices(
    request_info, configuration, tokens, tier, price
):
    result = calculate(
        replace(request_info, input_tokens=tokens, max_output_tokens=0), configuration
    )
    assert result.context_tier_id == tier
    assert result.final_price_credit == result.normal_price_credit == price
    assert result.display_discount_percent == 0
    assert len(result.policy_results) == 3
    assert all(
        item.status is Types.PricingPolicyStatus.UNIMPLEMENTED
        for item in result.policy_results
    )
    assert result.basis.context_tokens == tokens


def test_context_includes_output_budget_and_rejects_gaps(request_info, configuration):
    assert (
        calculate(
            replace(request_info, max_output_tokens=40), configuration
        ).context_tier_id
        == "large"
    )
    with pytest.raises(Types.BillingPricingError, match="outside"):
        calculate(
            replace(request_info, input_tokens=199, max_output_tokens=1), configuration
        )
    book = configuration.price_book
    model = book.models[0]
    changed = replace(
        model,
        tiers=(
            replace(model.tiers[0], max_context_tokens_exclusive=80),
            model.tiers[1],
        ),
    )
    with pytest.raises(Types.BillingPricingError, match="outside"):
        calculate(
            request_info,
            replace(configuration, price_book=replace(book, models=(changed,))),
        )


def test_missing_price_book_and_unknown_execution_fail(request_info, configuration):
    with pytest.raises(Types.BillingPricingError, match="not configured"):
        calculate(request_info, replace(configuration, price_book=None))
    for execution in (
        replace(request_info.execution, model_id=uuid4()),
        replace(request_info.execution, provider="other"),
        replace(request_info.execution, model="other"),
        replace(request_info.execution, reasoning_effort="high"),
        replace(
            request_info.execution,
            pricing_settings=(Types.PricingSettingInfo(name="x", value="1"),),
        ),
    ):
        with pytest.raises(Types.BillingPricingError, match="Unsupported"):
            calculate(replace(request_info, execution=execution), configuration)


@pytest.mark.parametrize(
    "change",
    [
        {"version": ""},
        {"models": ()},
        {"credits_per_currency_unit": Decimal("0")},
        {"safety_factor": Decimal("0.9")},
        {"safety_factor": Decimal("NaN")},
        {"safety_factor": Decimal("Infinity")},
        {"credits_per_currency_unit": 1.2},
    ],
)
def test_invalid_book_configuration(configuration, change):
    with pytest.raises(Types.BillingPricingError):
        replace(configuration, price_book=replace(configuration.price_book, **change))


@pytest.mark.parametrize(
    "change",
    [
        {"min_context_tokens": -1},
        {"min_context_tokens": 100},
        {"max_context_tokens_exclusive": 101},
        {"normal_price_credit": Decimal("-1")},
        {"normal_price_credit": Decimal("0.0000000000001")},
        {"tier_id": "large"},
        {"min_context_tokens": False},
    ],
)
def test_invalid_tiers(configuration, change):
    book = configuration.price_book
    model = book.models[0]
    changed = replace(model, tiers=(replace(model.tiers[0], **change), model.tiers[1]))
    with pytest.raises(Types.BillingPricingError):
        replace(configuration, price_book=replace(book, models=(changed,)))


def test_duplicate_models_and_invalid_costs(configuration):
    book = configuration.price_book
    with pytest.raises(Types.BillingPricingError, match="Duplicate"):
        replace(configuration, price_book=replace(book, models=book.models * 2))
    with pytest.raises(Types.BillingPricingError):
        replace(
            configuration,
            price_book=replace(
                book,
                models=(replace(book.models[0], input_cost_per_token=Decimal("-1")),),
            ),
        )
    for ttl in (0, -1, True, 86401):
        with pytest.raises(Types.BillingPricingError):
            replace(configuration, quote_ttl_seconds=ttl)


@pytest.mark.parametrize(
    "change",
    [
        {"input_tokens": -1},
        {"max_output_tokens": True},
        {"input_tokens": 1.1},
        {"input_tokens": 2**31},
        {"request_key": "not-uuid"},
        {"operation_fingerprint": "not-a-digest"},
        {"operation_kind": Types.BillingOperationKind.INTERNAL_EMBEDDING},
        {"operation_kind": Types.BillingOperationKind.INTERNAL_SUMMARY},
    ],
)
def test_invalid_requests_and_internal_work_rejected(
    request_info, configuration, change
):
    with pytest.raises(Types.BillingPricingError):
        calculate(replace(request_info, **change), configuration)


def test_settings_must_be_normalized(request_info, configuration):
    setting = Types.PricingSettingInfo(name="x", value="1")
    for settings in (
        (setting, setting),
        [setting],
        (setting, replace(setting, name="a")),
    ):
        with pytest.raises(Types.BillingPricingError, match="settings"):
            calculate(
                replace(
                    request_info,
                    execution=replace(
                        request_info.execution, pricing_settings=settings
                    ),
                ),
                configuration,
            )


def test_policy_execution_order_and_empty_configuration(request_info, configuration):
    half = AdjustmentAdapter("half", multiplier=Decimal("0.5"))
    minus = AdjustmentAdapter("minus", adjustment=Decimal("-1"))
    result = calculate(
        request_info, replace(configuration, policies=registry(half, minus))
    )
    reverse = calculate(
        request_info, replace(configuration, policies=registry(minus, half))
    )
    assert result.final_price_credit == 4
    assert reverse.final_price_credit == 5
    assert [item.input_price_credit for item in result.policy_results] == [10, 5]
    assert [item.output_price_credit for item in result.policy_results] == [5, 4]
    assert result.display_discount_percent == 60
    assert reverse.display_discount_percent == 50
    assert (
        calculate(
            request_info, replace(configuration, policies=registry())
        ).final_price_credit
        == 10
    )


def test_cost_floor_includes_input_output_conversion_and_safety(
    request_info, configuration
):
    free = registry(AdjustmentAdapter("free", multiplier=Decimal("0")))
    config = replace(configuration, policies=free)
    result = calculate(replace(request_info, max_output_tokens=31), config)
    assert result.cost_floor_credit == Decimal("3.05")  # (.60 + .62) * 2 * 1.25
    assert result.final_price_credit == 4
    assert result.display_discount_percent == 60
    assert not result.cost_floor_exceeds_normal
    raised = replace(
        config, price_book=replace(config.price_book, safety_factor=Decimal("10"))
    )
    expensive = calculate(request_info, raised)
    assert expensive.cost_floor_credit == 24
    assert expensive.final_price_credit == 24
    assert expensive.cost_floor_exceeds_normal
    assert expensive.display_discount_percent == 0


def test_rounding_discount_and_ambient_decimal_context(request_info, configuration):
    config = replace(
        configuration,
        policies=registry(AdjustmentAdapter("almost", multiplier=Decimal("0.999"))),
    )
    assert calculate(request_info, config).display_discount_percent == 0
    book = configuration.price_book
    model = book.models[0]
    config = replace(
        configuration,
        price_book=replace(
            book,
            models=(
                replace(
                    model,
                    tiers=(replace(model.tiers[0], normal_price_credit=Decimal("13")),),
                ),
            ),
        ),
        policies=registry(
            AdjustmentAdapter(
                "fixed", multiplier=Decimal("0"), adjustment=Decimal("7.01")
            )
        ),
    )
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        result = calculate(request_info, config)
    assert result.final_price_credit == 8
    assert result.display_discount_percent == Decimal("38.46")


def test_explicit_zero_price_and_fractional_normal_price(request_info, configuration):
    book = configuration.price_book
    model = book.models[0]
    for normal, final in (("0", 0), ("10.01", 11)):
        configured = replace(
            model,
            input_cost_per_token=Decimal("0"),
            output_cost_per_token=Decimal("0"),
            tiers=(replace(model.tiers[0], normal_price_credit=Decimal(normal)),),
        )
        result = calculate(
            request_info,
            replace(configuration, price_book=replace(book, models=(configured,))),
        )
        assert result.final_price_credit == final
        assert result.display_discount_percent == 0


@pytest.mark.parametrize(
    "corruption",
    [
        {"output_price_credit": Decimal("NaN")},
        {"output_price_credit": Decimal("-1")},
        {"input_price_credit": Decimal("0")},
        {
            "status": Types.PricingPolicyStatus.DISABLED,
            "output_price_credit": Decimal("1"),
        },
        {"reason": ""},
        {"policy": Types.PricingPolicyInfo(policy_id="wrong", version="1")},
    ],
)
def test_invalid_adapter_results_fail_closed(request_info, configuration, corruption):
    class InvalidAdapter(AdjustmentAdapter):
        def apply_policy(self, command):
            return replace(super().apply_policy(command), **corruption)

    with pytest.raises(Types.BillingPricingError):
        calculate(
            request_info,
            replace(configuration, policies=registry(InvalidAdapter("bad"))),
        )
