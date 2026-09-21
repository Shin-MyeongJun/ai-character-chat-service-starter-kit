"""순수 가격 정책 확장점과 구성용 등록부. 가격 계산기/견적 서비스가 아니다."""

from dataclasses import dataclass
from typing import Protocol

from app.modules.commerce.billing import types as Types


class PricingPolicyAdapter(Protocol):
    @property
    def policy(self) -> Types.PricingPolicyInfo: ...

    def apply_policy(
        self, command: Types.ApplyPricingPolicyCommand
    ) -> Types.PricingPolicyResultInfo: ...


def _apply_unimplemented_policy(
    command: Types.ApplyPricingPolicyCommand,
    policy: Types.PricingPolicyInfo,
    enabled: bool,
) -> Types.PricingPolicyResultInfo:
    return Types.PricingPolicyResultInfo(
        policy=policy,
        status=(
            Types.PricingPolicyStatus.UNIMPLEMENTED
            if enabled
            else Types.PricingPolicyStatus.DISABLED
        ),
        input_price_credit=command.current_price_credit,
        output_price_credit=command.current_price_credit,
        reason="Policy is not implemented." if enabled else "Policy is disabled.",
    )


@dataclass(frozen=True, slots=True)
class ProductAuthorPolicyAdapter:
    enabled: bool = True

    @property
    def policy(self) -> Types.PricingPolicyInfo:
        return Types.PricingPolicyInfo(policy_id="product_author", version="noop-v1")

    def apply_policy(
        self, command: Types.ApplyPricingPolicyCommand
    ) -> Types.PricingPolicyResultInfo:
        # 후속: 조율 계층이 product 공개 service에서 상품 상태·작가 정책·버전을
        # 받아 billing의 공개 값 계약으로 변환해 입력한다. 여기서 조회하지 않는다.
        return _apply_unimplemented_policy(command, self.policy, self.enabled)


@dataclass(frozen=True, slots=True)
class PromotionPolicyAdapter:
    enabled: bool = True

    @property
    def policy(self) -> Types.PricingPolicyInfo:
        return Types.PricingPolicyInfo(policy_id="promotion", version="noop-v1")

    def apply_policy(
        self, command: Types.ApplyPricingPolicyCommand
    ) -> Types.PricingPolicyResultInfo:
        # 후속: 프로모션 소유 모듈의 공개 service가 판정한 적용 자격·기간·정책
        # 버전을 조율 계층이 값으로 전달한다. 현재 할인/자격 데이터는 만들지 않는다.
        return _apply_unimplemented_policy(command, self.policy, self.enabled)


@dataclass(frozen=True, slots=True)
class UnpopularProductPolicyAdapter:
    enabled: bool = True

    @property
    def policy(self) -> Types.PricingPolicyInfo:
        return Types.PricingPolicyInfo(policy_id="unpopular_product", version="noop-v1")

    def apply_policy(
        self, command: Types.ApplyPricingPolicyCommand
    ) -> Types.PricingPolicyResultInfo:
        # 후속: 통계 소유 모듈의 공개 service에서 받은 인기도 판정·집계 기준 시각·
        # 버전을 조율 계층이 값으로 전달한다. 순위/조회수 추정이나 ORM 접근은 금지한다.
        return _apply_unimplemented_policy(command, self.policy, self.enabled)


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingPolicyRegistration:
    """업무 값이 아닌 구성 메타데이터. order는 중복 없는 오름차순 실행 순서다."""

    order: int
    adapter: PricingPolicyAdapter


@dataclass(frozen=True, slots=True)
class PricingPolicyRegistry:
    """등록 목록을 교체해 추가/제거/재정렬한다. 실행 중인 등록부는 변경하지 않는다."""

    registrations: tuple[PricingPolicyRegistration, ...]

    def __post_init__(self) -> None:
        registrations = tuple(sorted(self.registrations, key=lambda item: item.order))
        orders = [item.order for item in registrations]
        policy_ids = [item.adapter.policy.policy_id for item in registrations]
        if len(set(orders)) != len(orders):
            raise ValueError("Pricing policy order must be unique.")
        if len(set(policy_ids)) != len(policy_ids):
            raise ValueError("Pricing policy ID must be unique.")
        object.__setattr__(self, "registrations", registrations)


def create_default_policy_registry() -> PricingPolicyRegistry:
    """명시적인 기본 구성. 전역 등록/자동 탐색/가격 계산은 수행하지 않는다."""

    return PricingPolicyRegistry(
        (
            PricingPolicyRegistration(order=10, adapter=ProductAuthorPolicyAdapter()),
            PricingPolicyRegistration(order=20, adapter=PromotionPolicyAdapter()),
            PricingPolicyRegistration(
                order=30, adapter=UnpopularProductPolicyAdapter()
            ),
        )
    )
