"""Immutable wallet contracts and preserved unclassified history."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CreditReservationStatus(StrEnum):
    RESERVED = "reserved"
    COMMITTED = "committed"
    RELEASED = "released"


class CreditAccountNotFoundError(LookupError):
    """No account exists; reads and reservations never create one."""


class InsufficientCreditError(ValueError):
    """The available balance cannot cover the requested amount."""


class CreditReservationConflictError(ValueError):
    """An idempotency identity or terminal transition conflicts."""


class CreditReservationNotFoundError(LookupError):
    """No reservation belongs to the supplied identity."""


class InvalidCreditCommandError(ValueError):
    """Invalid identifiers, opaque metadata or amount."""


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCreditBalanceCommand:
    user_id: UUID
    currency_code: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LockCreditAccountCommand:
    user_id: UUID
    currency_code: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCreditReservationCommand:
    user_id: UUID
    currency_code: str
    namespace: str
    request_key: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ReserveCreditCommand:
    user_id: UUID
    currency_code: str
    namespace: str
    request_key: UUID
    amount: int
    reference_id: UUID
    reason: str
    settlement_key: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CommitCreditReservationCommand:
    user_id: UUID
    currency_code: str
    namespace: str
    request_key: UUID
    reservation_id: UUID
    result_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ReleaseCreditReservationCommand:
    user_id: UUID
    currency_code: str
    namespace: str
    request_key: UUID
    reservation_id: UUID


class CreditBucket(StrEnum):
    FREE = "free"
    PAID = "paid"


class CreditClassificationRequiredError(CreditAccountNotFoundError):
    """Legacy data exists; approved classification is required before activation."""


class CreditGrantConflictError(CreditReservationConflictError):
    """A grant key was reused with different terms."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PrepareCreditWalletCommand:
    user_id: UUID
    currency_code: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GrantCreditCommand:
    user_id: UUID
    currency_code: str
    bucket: CreditBucket
    amount: int
    reason: str
    reference_id: UUID
    namespace: str
    request_key: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditBucketInfo:
    balance_credit: int
    reserved_credit: int
    available_credit: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditBalanceInfo:
    user_id: UUID
    currency_code: str
    balance_credit: int
    reserved_credit: int
    available_credit: int
    free: CreditBucketInfo
    paid: CreditBucketInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditReservationInfo:
    id: UUID
    user_id: UUID
    currency_code: str | None
    namespace: str
    request_key: UUID
    reference_id: UUID
    reason: str
    settlement_key: str
    status: CreditReservationStatus
    reserved_credit: int
    result_id: UUID | None
    transaction_id: UUID | None
    created_at: datetime
    finalized_at: datetime | None
    free_amount: int | None
    paid_amount: int | None
    allocation_status: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditTransactionInfo:
    id: UUID
    user_id: UUID
    currency_code: str | None
    namespace: str | None
    request_key: UUID | None
    operation: str
    amount: int
    reason: str
    reference_id: UUID | None
    idempotency_key: str
    created_at: datetime
    free_amount: int | None
    paid_amount: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditCursor:
    created_at: datetime
    id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListCreditTransactionsCommand:
    user_id: UUID
    currency_code: str | None  # None selects only unclassified history.
    namespace: str | None = None
    reason: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    cursor: CreditCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class ListCreditReservationsCommand(ListCreditTransactionsCommand):
    status: CreditReservationStatus | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditTransactionPageInfo:
    items: tuple[CreditTransactionInfo, ...]
    next_cursor: CreditCursor | None


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditReservationPageInfo:
    items: tuple[CreditReservationInfo, ...]
    next_cursor: CreditCursor | None
