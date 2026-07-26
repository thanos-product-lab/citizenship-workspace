"""The domain-event base class.

Payloads are *explicit narrow fields*, never a loose dict (§38.1): each event is a
frozen dataclass whose `payload()` returns only object identifiers, enums, version
numbers, and reason codes. No free text, names, or document content ever enters an
event — that rule is enforced here by construction, not by reviewer vigilance.
"""

import uuid
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class DomainEvent:
    aggregate_id: uuid.UUID

    aggregate_type: ClassVar[str]
    event_type: ClassVar[str]

    def payload(self) -> dict[str, Any]:
        raise NotImplementedError
