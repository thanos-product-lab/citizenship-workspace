"""The provider boundary. One SDK, called directly, behind a narrow protocol.

Architecture RFC §19: *"The provider abstraction exists to preserve control and
testability, not to build a multi-model platform."* So this is a `Protocol` with one
method and two implementations — the real one and a fake for tests — rather than a
plugin system.

Four properties are structural rather than careful, and each is here because the
alternative is a defect that no test would name:

**Document content cannot become an instruction.** `generate_structured` takes
`system: SystemPrompt` and `document: DocumentText`. A `SystemPrompt` can only be
built from a `PromptVersion` (see `prompts.py`), and `DocumentText` is a distinct
type, so every place untrusted content travels is greppable and the two can never
be confused for one another. Directive 8; Architecture §23.4.

**No tool can be invoked.** There is no `tools` parameter, on the protocol or on
the SDK call. A document instructing the model to "call another tool" is asking for
something that does not exist in the request.

**No document can choose its own schema.** `output_schema` is passed by the caller,
which picks it from the classifier's closed enum — a separate, schema-constrained
call. Architecture §23.4's "change output schemas".

**A terminal failure is not retried.** The spike's first live run hit
`insufficient_quota` and this adapter's ancestor retried it three times, turning a
1.8s named failure into a 5.4s anonymous one (AI_SPIKE_FINDINGS §5). No retry adds
credit to an account or fixes a rejected key. Retrying a terminal error is three
more chances to occupy a worker — the same argument `evidence/extraction.py` makes
about documents that exhaust the read deadline.

What this module does **not** do: decide whether a call is affordable, write a
`ModelRun`, or enforce the task deadline. That is `service.py`, so that no caller
can reach a provider while skipping the ledger.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Protocol

import structlog
from pydantic import BaseModel

from app.ai.domain import Capability, ModelRunStatus
from app.ai.prompts import SystemPrompt

_log = structlog.get_logger()


class DocumentText(str):
    """Untrusted document content, and the only untrusted input to a model call.

    A distinct type so that `grep -r DocumentText` enumerates every place document
    content can travel, and so that handing one to anything expecting a
    `SystemPrompt` is a type error. It subclasses `str` because it *is* text and
    wrapping it in a dataclass would mean unwrapping it at every use, which is the
    kind of friction that gets removed by the next person.
    """

    __slots__ = ()


@dataclass(frozen=True)
class ModelConfig:
    model: str
    timeout_seconds: float
    max_attempts: int
    temperature: float = 0.0
    #: USD per million tokens, input and output. Carried on the config rather than
    #: looked up globally so that a `ModelRun`'s cost is computed from the same
    #: object that chose the model — a price table that can drift from the model it
    #: prices is a cost figure nobody can defend.
    input_price_per_mtok: float = 0.0
    output_price_per_mtok: float = 0.0

    def cost_usd(self, *, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_price_per_mtok
            + output_tokens / 1_000_000 * self.output_price_per_mtok
        )


@dataclass(frozen=True)
class ProviderResult:
    """What one invocation produced. Always a verdict: `status` is never absent, and
    `parsed` is populated if and only if `status is SUCCEEDED`."""

    status: ModelRunStatus
    parsed: BaseModel | None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    attempts: int
    output_hash: str | None
    #: The provider exception's class name. Never its message — a provider message
    #: can quote the request body, and the request body is the document.
    failure_class: str | None


class AIProvider(Protocol):
    def generate_structured(
        self,
        *,
        capability: Capability,
        system: SystemPrompt,
        document: DocumentText,
        output_schema: type[BaseModel],
        config: ModelConfig,
    ) -> ProviderResult: ...


#: Provider conditions no retry can resolve. Matched against the exception's string
#: because the SDK reports them as error *codes* inside a generic error class, so the
#: class alone cannot distinguish "no credit" from "briefly rate limited" — and those
#: want opposite responses.
_TERMINAL_MARKERS = (
    "insufficient_quota",
    "credit_balance_exhausted",
    "invalid_api_key",
    "account_deactivated",
    "model_not_found",
    "permission_denied",
)


def _is_terminal(exc: Exception) -> bool:
    return any(marker in str(exc).casefold() for marker in _TERMINAL_MARKERS)


def _is_timeout(exc: Exception) -> bool:
    return "timeout" in type(exc).__name__.casefold()


class OpenAIProvider:
    """The real adapter. Constructed with a client so tests can supply their own."""

    name = "openai"

    def __init__(self, client: object) -> None:
        self._client = client

    def generate_structured(
        self,
        *,
        capability: Capability,
        system: SystemPrompt,
        document: DocumentText,
        output_schema: type[BaseModel],
        config: ModelConfig,
    ) -> ProviderResult:
        started = time.monotonic()
        input_tokens = output_tokens = 0
        status = ModelRunStatus.FAILED
        failure_class: str | None = None

        for attempt in range(1, config.max_attempts + 1):
            try:
                completion = self._client.chat.completions.parse(  # type: ignore[attr-defined]
                    model=config.model,
                    temperature=config.temperature,
                    timeout=config.timeout_seconds,
                    messages=[
                        # The instruction. Built from a version key; no document
                        # content can reach this string (see prompts.py).
                        {"role": "system", "content": system.text},
                        # The document. Untrusted, and confined to this one place.
                        {"role": "user", "content": str(document)},
                    ],
                    response_format=output_schema,
                )
            except Exception as exc:
                failure_class = type(exc).__name__
                terminal = _is_terminal(exc)
                status = (
                    ModelRunStatus.TERMINAL
                    if terminal
                    else ModelRunStatus.TIMED_OUT
                    if _is_timeout(exc)
                    else ModelRunStatus.FAILED
                )
                # The class name and the capability, never the message: a provider
                # error can quote the request, and the request is the document.
                _log.warning(
                    "ai.provider_call_failed",
                    capability=capability.value,
                    failure_class=failure_class,
                    attempt=attempt,
                    terminal=terminal,
                )
                if terminal:
                    return _result(
                        status, None, started, input_tokens, output_tokens, attempt, failure_class
                    )
                continue

            usage = completion.usage
            input_tokens += getattr(usage, "prompt_tokens", 0) or 0
            output_tokens += getattr(usage, "completion_tokens", 0) or 0
            message = completion.choices[0].message

            if getattr(message, "refusal", None):
                # A refusal is a verdict, not an error: the provider understood and
                # declined. Retrying would not change that, and fabricating a
                # fallback is exactly what AI_EVALUATION_PLAN §8.14 forbids.
                return _result(
                    ModelRunStatus.REFUSED,
                    None,
                    started,
                    input_tokens,
                    output_tokens,
                    attempt,
                    None,
                )

            if message.parsed is None:
                # Output that would not satisfy the schema. Worth retrying — this is
                # the one failure a second attempt genuinely fixes — but never worth
                # accepting: MVP §8.10 requires invalid structured output to create
                # no claim.
                status = ModelRunStatus.INVALID_OUTPUT
                failure_class = "SchemaValidationFailed"
                continue

            raw = message.parsed.model_dump_json()
            return _result(
                ModelRunStatus.SUCCEEDED,
                message.parsed,
                started,
                input_tokens,
                output_tokens,
                attempt,
                None,
                output_hash=hashlib.sha256(raw.encode()).hexdigest(),
            )

        return _result(
            status,
            None,
            started,
            input_tokens,
            output_tokens,
            config.max_attempts,
            failure_class,
        )


def _result(
    status: ModelRunStatus,
    parsed: BaseModel | None,
    started: float,
    input_tokens: int,
    output_tokens: int,
    attempts: int,
    failure_class: str | None,
    output_hash: str | None = None,
) -> ProviderResult:
    return ProviderResult(
        status=status,
        parsed=parsed,
        latency_ms=int((time.monotonic() - started) * 1000),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        attempts=attempts,
        output_hash=output_hash,
        failure_class=failure_class,
    )
