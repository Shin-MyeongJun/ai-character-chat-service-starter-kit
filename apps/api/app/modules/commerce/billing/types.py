# amount는 currency 단위의 Decimal 금액이며 cost_credit과 다르다.
# latency_ms의 단위는 밀리초다.
# sale_id는 환불의 원매출 ID이고 매출 이벤트에서는 None이다.
# occurred_at은 실제 발생 시각, attributed_at은 통계 귀속 시각이다.
# 환불도 원매출 날짜에 귀속한다.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RecordUsageCommand:
    user_id: UUID
    conversation_id: UUID
    generation_id: UUID
    product_id: UUID
    product_snapshot_id: UUID
    model_id: UUID
    reasoning_effort: str
    input_tokens: int
    output_tokens: int
    cost_credit: int
    latency_ms: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PaymentInfo:
    id: UUID
    status: str
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class PaymentEventInfo:
    id: UUID
    payment_id: UUID
    product_id: UUID
    product_snapshot_id: UUID
    sale_id: UUID | None
    kind: str
    amount: Decimal
    currency: str
    occurred_at: datetime
    attributed_at: datetime


@dataclass(frozen=True, slots=True)
class GetStatisticsFactsCommand:
    product_id: UUID
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class BillingStatisticsInfo:
    usage: list[tuple]
    payments: list[tuple]


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordSaleCommand:
    payment_id: UUID
    snapshot_id: UUID
    event_key: str
    amount: Decimal
    occurred_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordRefundCommand:
    sale_id: UUID
    event_key: str
    amount: Decimal
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class UsageRecordedInfo:
    id: UUID


# 가격/견적과 크레딧 예약의 값 계약.
class BillingOperationKind(StrEnum):
    USER_GENERATION = "user_generation"
    USER_REGENERATION = "user_regeneration"
    USER_CONTINUATION = "user_continuation"
    INTERNAL_EMBEDDING = "internal_embedding"
    INTERNAL_SUMMARY = "internal_summary"


class PricingPolicyStatus(StrEnum):
    APPLIED = "applied"
    NOT_APPLICABLE = "not_applicable"
    DISABLED = "disabled"
    UNIMPLEMENTED = "unimplemented"


class BillingQuoteStatus(StrEnum):
    QUOTED = "quoted"
    EXPIRED = "expired"


class CreditReservationStatus(StrEnum):
    RESERVED = "reserved"
    COMMITTED = "committed"
    RELEASED = "released"


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingProductInfo:
    product_id: UUID
    product_snapshot_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingSettingInfo:
    """가격에 영향을 주는 추가 설정. 값은 계약별로 정규화한 문자열이다."""

    name: str
    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingExecutionInfo:
    """대체 모델 선택 후 확정한 실행 대상. SDK 요청/ORM 객체는 전달하지 않는다."""

    model_id: UUID
    provider: str
    model: str
    reasoning_effort: str
    pricing_settings: tuple[PricingSettingInfo, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingRequestInfo:
    user_id: UUID
    operation_kind: BillingOperationKind
    request_key: UUID
    # 같은 토큰 수의 다른 입력도 구분할 수 있는 호출자 제공 작업 지문.
    operation_fingerprint: str
    product: BillingProductInfo | None
    execution: BillingExecutionInfo
    input_tokens: int
    max_output_tokens: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingPolicyInfo:
    policy_id: str
    version: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplyPricingPolicyCommand:
    request: BillingRequestInfo
    normal_price_credit: Decimal
    current_price_credit: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingPolicyResultInfo:
    policy: PricingPolicyInfo
    status: PricingPolicyStatus
    input_price_credit: Decimal
    output_price_credit: Decimal
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingPriceInfo:
    """확정 결과. policy_results는 건너뛴 정책도 실행 순서로 포함한다."""

    price_book_version: str
    context_tier_id: str
    calculation_version: str
    normal_price_credit: Decimal
    cost_floor_credit: Decimal
    final_price_credit: int
    display_discount_percent: Decimal
    policy_results: tuple[PricingPolicyResultInfo, ...]
    basis: BillingPriceBasisInfo | None = None
    cost_floor_exceeds_normal: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateBillingQuoteCommand:
    request: BillingRequestInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingQuoteInfo:
    id: UUID
    request: BillingRequestInfo
    price: BillingPriceInfo
    status: BillingQuoteStatus
    expires_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ReserveCreditCommand:
    user_id: UUID
    request_key: UUID
    quote_id: UUID
    # 서버에서 확정한 실행 조건 전체. 견적 스냅샷과 반드시 일치해야 한다.
    request: BillingRequestInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class CommitCreditReservationCommand:
    user_id: UUID
    request_key: UUID
    reservation_id: UUID
    result_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ReleaseCreditReservationCommand:
    user_id: UUID
    request_key: UUID
    reservation_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditReservationInfo:
    id: UUID
    user_id: UUID
    request_key: UUID
    quote_id: UUID
    status: CreditReservationStatus
    reserved_credit: int
    # COMMITTED에서만 결과 ID가 존재한다. 해제는 환불과 다른 상태 전이다.
    result_id: UUID | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextPriceTierInfo:
    tier_id: str
    min_context_tokens: int
    max_context_tokens_exclusive: int
    normal_price_credit: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelPriceInfo:
    execution: BillingExecutionInfo
    tiers: tuple[ContextPriceTierInfo, ...]
    input_cost_per_token: Decimal
    output_cost_per_token: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceBookInfo:
    version: str
    currency: str
    credits_per_currency_unit: Decimal
    safety_factor: Decimal
    models: tuple[ModelPriceInfo, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingPriceBasisInfo:
    context_tokens: int
    min_context_tokens: int
    max_context_tokens_exclusive: int
    currency: str
    input_cost_per_token: Decimal
    output_cost_per_token: Decimal
    credits_per_currency_unit: Decimal
    safety_factor: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class CalculateBillingPriceCommand:
    request: BillingRequestInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class GetBillingQuoteCommand:
    quote_id: UUID
    request: BillingRequestInfo


class BillingPricingError(ValueError):
    """가격 구성 또는 실행 조건을 처리할 수 없음."""


class BillingQuoteConflictError(ValueError):
    """기존 견적과 요청/실행 조건 불일치."""


class BillingQuoteNotFoundError(LookupError):
    """사용자에게 속하는 견적이 없음."""


class BillingQuoteExpiredError(ValueError):
    """조회는 가능하지만 신규 예약에 사용할 수 없는 만료 견적."""


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCreditBalanceCommand:
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditBalanceInfo:
    user_id: UUID
    balance_credit: int
    reserved_credit: int
    available_credit: int


class CreditAccountNotFoundError(LookupError):
    """크레딧 계정이 없다. 조회/예약에서 충전하거나 자동 생성하지 않는다."""


class InsufficientCreditError(ValueError):
    """사용 가능 잔액이 견적의 확정가격보다 부족하다."""


class CreditReservationConflictError(ValueError):
    """요청 키/견적/결과 재사용 충돌 또는 허용되지 않은 상태 전이."""


class CreditReservationNotFoundError(LookupError):
    """사용자와 요청 키에 속하는 예약이 없다."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditBindingInfo:
    reservation_id: UUID
    quote_id: UUID
    user_id: UUID
    request_key: UUID
    created_at: datetime
