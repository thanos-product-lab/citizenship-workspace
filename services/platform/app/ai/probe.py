"""One real, tiny model call, so a deployment can prove its key works.

`check_ai_configuration` proves a key is *present*. It cannot prove the key is
accepted, that the account has credit, or that the model name still exists — and the
M8 spike's first live run failed on exactly the second of those, with a perfectly
well-formed key (AI_SPIKE_FINDINGS §5). Presence is not reachability, and the gap
between them is where the local-green/deployed-red failures live.

So the deployed smoke calls this, and it is deliberately the smallest thing that can
fail the way a real capability fails: one system prompt from the registry, one
schema-constrained response, through `service.invoke`, recorded as a `ModelRun` and
counted against the day's ceiling like any other invocation. A probe that bypassed
the ledger would be testing a path the product does not use.

**It costs money, so it is not open.** The route requires a shared secret and is
disabled entirely when that secret is unset. The alternative — an unauthenticated
endpoint that bills the account on every request — is a denial-of-wallet primitive,
and putting one on a public host to make a smoke test easier would be trading a real
risk for a small convenience.
"""

from pydantic import BaseModel, ConfigDict

from app.ai.domain import Capability
from app.ai.provider import AIProvider, DocumentText
from app.ai.service import AiBudget, Invocation, invoke
from app.core.config import Settings


class ProbeOutput(BaseModel):
    """The smallest useful structured output. `extra="forbid"` even here, because the
    probe is also a live check that strict structured outputs still behave — if the
    provider starts returning unknown fields, this is where it shows up first."""

    model_config = ConfigDict(extra="forbid")

    status: str


#: Fixed, tiny, and not user-controlled. The probe exercises the provider boundary,
#: not extraction, so there is no reason for any caller to influence what is sent —
#: and a probe that accepted arbitrary text would be an open relay to the model.
_PROBE_INPUT = DocumentText("ping")


def run_probe(
    provider: AIProvider,
    *,
    settings: Settings,
    trace_id: str | None = None,
) -> Invocation[ProbeOutput]:
    return invoke(
        provider,
        capability=Capability.PROVIDER_PROBE,
        document=_PROBE_INPUT,
        output_schema=ProbeOutput,
        budget=AiBudget(seconds=settings.ai_task_deadline_seconds),
        trace_id=trace_id,
        settings=settings,
    )
