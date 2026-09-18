# amount는 currency 단위의 Decimal 금액이며 cost_credit과 다르다. latency_ms의 단위는 밀리초다.
# sale_id는 환불의 원매출 ID이고 매출 이벤트에서는 None이다.
# occurred_at은 실제 발생 시각, attributed_at은 통계 귀속 시각으로 환불도 원매출 날짜에 귀속한다.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
