"""What the adapter does when the provider does not cooperate.

The centrepiece is the terminal-versus-retryable split, which is here because the M8
spike's first live run got it wrong: an exhausted credit balance was retried three
times, turning a 1.8s named failure into a 5.4s anonymous one (AI_SPIKE_FINDINGS §5).
"""

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app.ai.domain import Capability, ModelRunStatus
from app.ai.prompts import PromptVersion, SystemPrompt
from app.ai.provider import DocumentText, ModelConfig, OpenAIProvider


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class _StubClient:
    """Enough of the SDK's surface to drive the adapter, and no more."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.requests: list[dict[str, Any]] = []
        self.chat = self

    @property
    def completions(self) -> "_StubClient":
        return self

    def parse(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Usage:
    prompt_tokens = 100
    completion_tokens = 20


class _Message:
    def __init__(self, parsed: BaseModel | None, refusal: str | None = None) -> None:
        self.parsed = parsed
        self.refusal = refusal


class _Completion:
    def __init__(self, parsed: BaseModel | None, refusal: str | None = None) -> None:
        self.usage = _Usage()
        self.choices = [type("C", (), {"message": _Message(parsed, refusal)})()]


def _call(client: _StubClient, attempts: int = 3) -> Any:
    return OpenAIProvider(client).generate_structured(
        capability=Capability.PROVIDER_PROBE,
        system=SystemPrompt(PromptVersion.PROVIDER_PROBE_V1),
        document=DocumentText("ping"),
        output_schema=_Out,
        config=ModelConfig(model="gpt-4o-mini", timeout_seconds=5, max_attempts=attempts),
    )


class _QuotaError(Exception):
    pass


class _TransientError(Exception):
    pass


class _APITimeoutError(Exception):
    pass


def test_an_exhausted_credit_balance_is_not_retried() -> None:
    """The spike's defect, as a test. No retry adds credit to an account, and three
    attempts at a terminal error is three more chances to occupy a worker."""
    client = _StubClient(
        [
            _QuotaError(
                "Error code: 429 - {'error': {'message': 'You have no credits remaining.', "
                "'type': 'insufficient_quota', 'code': 'credit_balance_exhausted'}}"
            )
        ]
    )
    result = _call(client)

    assert result.status is ModelRunStatus.TERMINAL
    assert result.attempts == 1
    assert len(client.requests) == 1, "a terminal error must cost exactly one request"
    assert result.failure_class == "_QuotaError"


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 401 - {'error': {'code': 'invalid_api_key'}}",
        "Error code: 404 - {'error': {'code': 'model_not_found'}}",
        "Error code: 403 - {'error': {'code': 'permission_denied'}}",
    ],
)
def test_the_other_terminal_conditions_are_not_retried_either(message: str) -> None:
    client = _StubClient([_QuotaError(message)])
    assert _call(client).status is ModelRunStatus.TERMINAL
    assert len(client.requests) == 1


def test_a_transient_error_is_retried_up_to_the_cap() -> None:
    """The other side of the split: a failure another attempt could fix gets them."""
    client = _StubClient([_TransientError("503 upstream"), _TransientError("503 upstream")])
    result = _call(client, attempts=2)

    assert result.status is ModelRunStatus.FAILED
    assert result.attempts == 2
    assert len(client.requests) == 2


def test_a_transient_error_that_then_succeeds_returns_the_output() -> None:
    client = _StubClient([_TransientError("503"), _Completion(_Out(value="ok"))])
    result = _call(client)

    assert result.status is ModelRunStatus.SUCCEEDED
    assert result.parsed == _Out(value="ok")
    assert result.attempts == 2
    # Tokens accumulate across attempts: the provider billed for the failed one too.
    assert result.input_tokens == 100


def test_a_timeout_is_reported_as_a_timeout() -> None:
    client = _StubClient([_APITimeoutError("timed out"), _APITimeoutError("timed out")])
    result = _call(client, attempts=2)
    assert result.status is ModelRunStatus.TIMED_OUT


def test_invalid_structured_output_is_retried_and_never_accepted() -> None:
    """MVP §8.10: invalid structured output creates no claim. The adapter retries —
    this is the one failure a second attempt genuinely fixes — but a `parsed` of None
    is never dressed up as a result."""
    client = _StubClient([_Completion(None), _Completion(None), _Completion(None)])
    result = _call(client)

    assert result.status is ModelRunStatus.INVALID_OUTPUT
    assert result.parsed is None
    assert result.attempts == 3
    assert result.failure_class == "SchemaValidationFailed"


def test_a_refusal_stops_immediately() -> None:
    client = _StubClient([_Completion(None, refusal="I cannot help with that")])
    result = _call(client)

    assert result.status is ModelRunStatus.REFUSED
    assert len(client.requests) == 1, "a refusal is a verdict; retrying it asks again"


def test_the_request_carries_the_document_as_a_user_message_only() -> None:
    client = _StubClient([_Completion(_Out(value="ok"))])
    _call(client)

    messages = client.requests[0]["messages"]
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user"]
    assert messages[1]["content"] == "ping"
    assert "ping" not in messages[0]["content"]
    assert "tools" not in client.requests[0]


def test_the_output_hash_is_over_the_real_output() -> None:
    import hashlib

    parsed = _Out(value="ok")
    client = _StubClient([_Completion(parsed)])
    result = _call(client)
    assert result.output_hash == hashlib.sha256(parsed.model_dump_json().encode()).hexdigest()
