"""가격 정책 구성/무효과 동작과 신규 공개 계약의 모듈 경계를 검증한다."""

import ast
import inspect
from dataclasses import FrozenInstanceError, dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints
from uuid import uuid4

import pytest
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import policies as BillingPolicyService


@pytest.fixture
def command() -> BillingTypes.ApplyPricingPolicyCommand:
    return BillingTypes.ApplyPricingPolicyCommand(
        request=BillingTypes.BillingRequestInfo(
            user_id=uuid4(),
            operation_kind=BillingTypes.BillingOperationKind.USER_GENERATION,
            request_key=uuid4(),
            operation_fingerprint="sha256:" + "a" * 64,
            product=BillingTypes.BillingProductInfo(
                product_id=uuid4(), product_snapshot_id=uuid4()
            ),
            execution=BillingTypes.BillingExecutionInfo(
                model_id=uuid4(),
                provider="test",
                model="test-model",
                reasoning_effort="low",
            ),
            input_tokens=100,
            max_output_tokens=200,
        ),
        normal_price_credit=Decimal("10"),
        current_price_credit=Decimal("7.125"),
    )


@pytest.mark.parametrize(
    "adapter_type",
    [
        BillingPolicyService.ProductAuthorPolicyAdapter,
        BillingPolicyService.PromotionPolicyAdapter,
        BillingPolicyService.UnpopularProductPolicyAdapter,
    ],
)
@pytest.mark.parametrize(
    ("enabled", "status"),
    [
        (True, BillingTypes.PricingPolicyStatus.UNIMPLEMENTED),
        (False, BillingTypes.PricingPolicyStatus.DISABLED),
    ],
)
@pytest.mark.parametrize("price", [Decimal("0"), Decimal("7.125")])
def test_noop_preserves_exact_input_price(
    command, adapter_type, enabled, status, price
):
    adapter = adapter_type(enabled=enabled)
    request = replace(command, current_price_credit=price)
    result = adapter.apply_policy(request)
    assert result.input_price_credit == result.output_price_credit == price
    assert result.status is status
    assert result.policy == adapter.policy
    assert result.policy.version == "noop-v1"
    assert adapter.apply_policy(request) == result
    assert request.normal_price_credit == Decimal("10")


@dataclass(frozen=True)
class ExtraPolicyAdapter:
    """등록 확장을 검증하는 테스트 전용 무효과 정책."""

    @property
    def policy(self) -> BillingTypes.PricingPolicyInfo:
        return BillingTypes.PricingPolicyInfo(policy_id="extra", version="test-v1")

    def apply_policy(
        self, command: BillingTypes.ApplyPricingPolicyCommand
    ) -> BillingTypes.PricingPolicyResultInfo:
        return BillingTypes.PricingPolicyResultInfo(
            policy=self.policy,
            status=BillingTypes.PricingPolicyStatus.NOT_APPLICABLE,
            input_price_credit=command.current_price_credit,
            output_price_credit=command.current_price_credit,
        )


def test_registry_add_remove_reorder_and_empty_configuration(command):
    original = BillingPolicyService.create_default_policy_registry()
    assert [item.order for item in original.registrations] == [10, 20, 30]
    assert [item.adapter.policy.policy_id for item in original.registrations] == [
        "product_author",
        "promotion",
        "unpopular_product",
    ]
    extra = BillingPolicyService.PricingPolicyRegistration(
        order=15, adapter=ExtraPolicyAdapter()
    )
    expanded = BillingPolicyService.PricingPolicyRegistry(
        (*original.registrations, extra)
    )
    assert [item.order for item in expanded.registrations] == [10, 15, 20, 30]
    # 상품 정책 제거 및 프로모션 순서 변경은 새 구성을 만들어 적용한다.
    reconfigured = BillingPolicyService.PricingPolicyRegistry(
        (expanded.registrations[3], extra, replace(expanded.registrations[2], order=5))
    )
    results = tuple(
        item.adapter.apply_policy(command) for item in reconfigured.registrations
    )
    assert [result.policy.policy_id for result in results] == [
        "promotion",
        "extra",
        "unpopular_product",
    ]
    assert all(
        result.output_price_credit == command.current_price_credit for result in results
    )
    assert len(original.registrations) == 3
    assert BillingPolicyService.PricingPolicyRegistry(()).registrations == ()
    with pytest.raises(FrozenInstanceError):
        original.registrations = ()


def test_registry_rejects_ambiguous_order_and_duplicate_policy():
    registration = BillingPolicyService.PricingPolicyRegistration
    product = BillingPolicyService.ProductAuthorPolicyAdapter()
    promotion = BillingPolicyService.PromotionPolicyAdapter()
    with pytest.raises(ValueError, match="order must be unique"):
        BillingPolicyService.PricingPolicyRegistry(
            (
                registration(order=1, adapter=product),
                registration(order=1, adapter=promotion),
            )
        )
    with pytest.raises(ValueError, match="ID must be unique"):
        BillingPolicyService.PricingPolicyRegistry(
            (
                registration(order=1, adapter=product),
                registration(order=2, adapter=product),
            )
        )


def test_request_key_has_no_default_and_request_values_are_immutable(command):
    request = command.request
    fields = {
        name: getattr(request, name)
        for name in request.__dataclass_fields__
        if name != "request_key"
    }
    with pytest.raises(TypeError, match="request_key"):
        BillingTypes.BillingRequestInfo(**fields)
    with pytest.raises(FrozenInstanceError):
        request.input_tokens = 101
    assert replace(request, operation_fingerprint="sha256:" + "b" * 64) != request
    # 기존 문자열 요청 키/사용량/결제 계약은 신규 UUID 계약으로 바꾸지 않는다.
    assert get_type_hints(BillingTypes.RecordSaleCommand)["event_key"] is str
    assert get_type_hints(BillingTypes.RecordUsageCommand)["cost_credit"] is int


def test_public_policy_signatures_use_only_billing_values():
    for adapter in (
        BillingPolicyService.PricingPolicyAdapter,
        BillingPolicyService.ProductAuthorPolicyAdapter,
        BillingPolicyService.PromotionPolicyAdapter,
        BillingPolicyService.UnpopularProductPolicyAdapter,
    ):
        assert get_type_hints(adapter.apply_policy) == {
            "command": BillingTypes.ApplyPricingPolicyCommand,
            "return": BillingTypes.PricingPolicyResultInfo,
        }


@pytest.mark.parametrize("module", [BillingTypes, BillingPolicyService])
def test_contract_and_adapter_imports_cannot_leak_orm_or_external_modules(module):
    # types는 표준 라이브러리만, 정책은 표준 라이브러리와 자기 공개 types만 참조한다.
    allowed = {
        "__future__",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "typing",
        "uuid",
    }
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if (
                node.module == "app.modules.commerce.billing"
                and module is BillingPolicyService
            ):
                assert [alias.name for alias in node.names] == ["types"]
            else:
                assert node.level == 0 and node.module in allowed
