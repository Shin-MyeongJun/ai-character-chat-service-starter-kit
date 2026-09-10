from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GetUserCommand:
    user_id: UUID


@dataclass(frozen=True, slots=True)
class UserAccessInfo:
    id: UUID
    role: str
    status: str
