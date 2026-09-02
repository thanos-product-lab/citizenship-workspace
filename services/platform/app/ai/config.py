"""Per-capability model configuration, and the schema versions that go with it.

Architecture RFC §19: each capability defines its own model, prompt version, schema
version and retry policy. A registry keyed by capability rather than one global
model setting, because "which model does the classifier use" and "which model does
the extractor use" are questions that will have different answers as soon as
`AI_EVALUATION_PLAN.md` §22's model-selection work happens, and a single setting
would make that a code change rather than a config one.

**On the prices.** They are recorded per capability alongside the model they price,
so a `ModelRun`'s cost is computed from the same object that chose the model — a
global price table can drift from the models it prices, and a cost figure derived
from a stale table is worse than none. They are **not verified against live
pricing**: AI_SPIKE_FINDINGS §2 makes the same caveat and it still stands. Token
counts come from the provider and are exact; the USD figure is arithmetic on a
constant a human must check.
"""

from dataclasses import dataclass

from app.ai.domain import Capability
from app.ai.prompts import PromptVersion
from app.ai.provider import ModelConfig
from app.core.config import Settings

#: USD per million tokens, (input, output). Unverified — see the module docstring.
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


@dataclass(frozen=True)
class CapabilityConfig:
    """Everything one capability needs to make a call, resolved together.

    `schema_version` is the version of the *output envelope* the capability returns.
    It is distinct from a claim's `value_schema_version` (the shape of one claim
    type's value), which arrives with claims in slice 3a — the two version different
    things and conflating them makes a schema change unattributable.
    """

    capability: Capability
    model: str
    prompt_version: PromptVersion
    schema_version: str

    def model_config_with(self, settings: Settings) -> ModelConfig:
        """Bind the deployment's bounds to this capability's model choice.

        Timeouts and the attempt cap come from settings rather than from the
        registry: they are properties of the deployment's tolerance, not of the
        capability, and one place to change them is what makes the task-deadline
        arithmetic in `service.py` checkable.
        """
        if self.model not in _PRICES:
            # Raise rather than default to zero. `_PRICES.get(model, (0.0, 0.0))`
            # made every call by an unpriced model cost nothing, so the ledger never
            # rose and the daily ceiling could never be reached — a fail-open in the
            # one control that bounds the bill, triggered by the ordinary act of
            # registering a capability with a new model.
            raise RuntimeError(
                f"{self.capability.value} is registered with model {self.model!r}, which has "
                "no entry in _PRICES. A model with no price computes a cost of zero, and a "
                "spend ceiling that reads a ledger of zeroes is not a ceiling. Add the price "
                "(and verify it against the provider's current list) before using the model."
            )
        input_price, output_price = _PRICES[self.model]
        return ModelConfig(
            model=self.model,
            timeout_seconds=settings.ai_request_timeout_seconds,
            max_attempts=settings.ai_max_attempts,
            input_price_per_mtok=input_price,
            output_price_per_mtok=output_price,
        )


#: The registry. A capability that is not here cannot be invoked — `service.invoke`
#: looks its config up rather than accepting one, so there is no way to call a
#: provider with an unregistered capability and an ad-hoc model.
REGISTRY: dict[Capability, CapabilityConfig] = {
    Capability.DOCUMENT_CLASSIFIER: CapabilityConfig(
        capability=Capability.DOCUMENT_CLASSIFIER,
        # 100% classification accuracy over 18 spike calls, including the
        # misleading-filename and injection documents, at ~$0.0001 per call
        # (AI_SPIKE_FINDINGS §2). Model selection proper belongs to the eval harness
        # with a representative corpus (AI_EVALUATION_PLAN §22), not to a registry
        # edit — this is the baseline, not a claim that nothing better exists.
        model="gpt-4o-mini",
        prompt_version=PromptVersion.CLASSIFY_DOCUMENT_V1,
        schema_version="classifier.v1",
    ),
    Capability.PROVIDER_PROBE: CapabilityConfig(
        capability=Capability.PROVIDER_PROBE,
        # The cheapest capable model: this call exists to prove the wiring, and
        # paying more to learn the same fact would be a strange choice.
        model="gpt-4o-mini",
        prompt_version=PromptVersion.PROVIDER_PROBE_V1,
        schema_version="probe.v1",
    ),
}


def config_for(capability: Capability) -> CapabilityConfig:
    try:
        return REGISTRY[capability]
    except KeyError:  # pragma: no cover — unreachable while REGISTRY is total
        raise RuntimeError(
            f"{capability.value} has no entry in app/ai/config.py REGISTRY. A capability "
            "must declare its model, prompt version and schema version before it can be "
            "invoked (Architecture RFC §19)."
        ) from None
