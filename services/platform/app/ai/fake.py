"""A provider that never dials, for local development and tests.

The same shape as `storage_backend="memory"`, and it carries the same warning:
**it asserts behaviour only and must never be used to claim anything about model
quality, cost or safety.** A green test against this proves the plumbing works, not
that a model does.

The risk it introduces is real and worth naming: a deployment misconfigured onto the
fake would serve fabricated structured output as though a model had produced it,
which is the false-reassurance failure with the model removed entirely. Two guards,
and the first is the one that matters:

1. `check_ai_configuration` refuses to boot outside local environments when
   `AI_PROVIDER=fake`. A production deployment cannot select it at all.
2. It returns only what a test scripted, and raises `AssertionError` when a call is
   made with nothing scripted. The factory builds it with an empty script, so a
   deployment that somehow reached it errors rather than serving fabricated values —
   accidental protection today, and not something to rely on once slice 2 scripts
   responses for local development.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import cast

from pydantic import BaseModel

from app.ai.domain import Capability, ModelRunStatus
from app.ai.prompts import SystemPrompt
from app.ai.provider import DocumentText, ModelConfig, ProviderResult


@dataclass
class FakeProvider:
    """Returns a scripted result. Records what it was asked, so a test can assert on
    the boundary — that the document never reached the system prompt, that no tools
    were offered — rather than only on the answer."""

    name: str = "fake"
    #: Scripted outcomes, consumed in order. Exhausting them is an error rather than
    #: falling back to a default: a test that makes more calls than it scripted has
    #: changed behaviour and should say so.
    responses: list[ProviderResult[BaseModel] | Exception] = field(default_factory=list)
    #: Every call, as (capability, system prompt text, document text).
    calls: list[tuple[Capability, str, str]] = field(default_factory=list)
    #: Seconds to sleep per call, so a test can exercise the task deadline.
    latency_seconds: float = 0.0

    def generate_structured[T: BaseModel](
        self,
        *,
        capability: Capability,
        system: SystemPrompt,
        document: DocumentText,
        output_schema: type[T],
        config: ModelConfig,
    ) -> ProviderResult[T]:
        self.calls.append((capability, system.text, str(document)))
        if self.latency_seconds:
            time.sleep(self.latency_seconds)
        if not self.responses:
            raise AssertionError(
                f"FakeProvider had no scripted response for call {len(self.calls)} "
                f"({capability.value}). Script one, or assert on the call count."
            )
        scripted = self.responses.pop(0)
        if isinstance(scripted, Exception):
            raise scripted
        # The one cast in the module, and it is confined to the test double: a
        # scripted response is whatever the test wrote, and only the test knows it
        # matches the schema it asked for.
        return cast("ProviderResult[T]", scripted)


def succeeded(
    parsed: BaseModel, *, input_tokens: int = 100, output_tokens: int = 20
) -> ProviderResult[BaseModel]:
    """A successful scripted result, with a real hash over the real output so the
    `output_hash` assertions in tests are testing the hash and not a placeholder."""
    return ProviderResult(
        status=ModelRunStatus.SUCCEEDED,
        parsed=parsed,
        latency_ms=12,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        attempts=1,
        output_hash=hashlib.sha256(parsed.model_dump_json().encode()).hexdigest(),
        failure_class=None,
    )


def failed(
    status: ModelRunStatus,
    *,
    failure_class: str = "SyntheticFailure",
    input_tokens: int = 0,
    output_tokens: int = 0,
    attempts: int = 1,
) -> ProviderResult[BaseModel]:
    """A scripted failure. Tokens default to zero but are settable, because a
    provider bills for a call whose output failed to validate and the ledger has to
    see that."""
    return ProviderResult(
        status=status,
        parsed=None,
        latency_ms=9,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        attempts=attempts,
        output_hash=None,
        failure_class=failure_class,
    )
