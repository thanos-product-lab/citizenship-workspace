"""Versioned instructions, and the type that makes them the *only* instructions.

This module is one half of the prompt-injection defence (directive 8, Architecture
§23.4: *"Document content must not be allowed to alter system instructions"*). The
other half is `DocumentText` in `provider.py`.

## What is actually guaranteed, and what is not

An earlier version of this file claimed the boundary was structural — *"not because
nobody wrote one, but because writing one means adding a constructor"*. A security
review executed the bypasses and four of them worked. The claim was false, and a
false claim about a safety boundary is worse than an honest weaker one, because it
stops people looking. What follows is what the code does.

**Enforced at runtime, and tested:**

- `SystemPrompt` accepts only a `PromptVersion` member. A plain `str` is rejected by
  an explicit `isinstance` check — necessary because `PromptVersion` is a `StrEnum`
  and `StrEnum.__hash__ is str.__hash__`, so `_PROMPTS["provider_probe.v1"]` would
  otherwise hit the dict and a type annotation alone would not stop it.
- The text is **never stored on the instance**. `text` is a read-only property that
  looks the version up on each access, and `__slots__` holds only `version`. So
  `object.__setattr__(prompt, "text", ...)` — which walks straight around a raising
  `__setattr__`, as the review demonstrated — has no slot to write into and a
  property with no setter to call, and raises.
- `_PROMPTS` is a `MappingProxyType`, so the registry itself cannot be mutated to
  poison every future prompt.

**Not enforced, and unenforceable in Python:** a subclass can override `text`, and
`object.__setattr__` can still write `version`. `@final` makes the first a mypy
error, which is the standard the rest of this milestone holds (see
`requirements/evaluation.py`'s `UnlinkedResult`) — a type error rather than an
assertion someone can delete. It is not a runtime guarantee and is not described as
one.

The `version` write matters less than it looks: `text` resolves through `_PROMPTS`,
so overwriting `version` can only ever select *another approved prompt file* or
raise `KeyError`. There is no value it can be set to that produces attacker-chosen
instruction text.

**The guarantee that actually carries the weight is a data-flow one:** no code path
passes document-derived text to `SystemPrompt`, and the lookup is a whitelist, so
even the rejected raw-string form could only ever have selected an approved prompt
file. `tests/ai/test_prompt_boundary.py` pins both the runtime checks and the
data-flow property.

## Why prompts are files

Prompts live in `prompts/*.txt` rather than in Python string literals so that a
prompt change is a reviewable diff of prose, and so that `prompt_version` on a
`ModelRun` names a file whose exact contents at that version can be recovered.

**Capabilities share as little text as possible.** The M8 spike put a
date-ambiguity rule in a block every capability shared; the extractor obeyed it and
the *classifier* began reporting documents as AMBIGUOUS because their dates were —
answering the extractor's question, wrongly, and suppressing extraction entirely
(AI_SPIKE_FINDINGS §3.2). Shared prose couples capabilities in ways that surface as
one capability's behaviour changing when another's prompt is edited. If two prompts
need the same sentence, prefer repeating it.
"""

import pathlib
from enum import StrEnum
from types import MappingProxyType
from typing import final

_PROMPT_DIR = pathlib.Path(__file__).parent / "prompts"


class PromptVersion(StrEnum):
    """Every instruction the system can issue. Adding a capability adds a member
    here and a file beside it; there is no third way to obtain a prompt."""

    PROVIDER_PROBE_V1 = "provider_probe.v1"
    CLASSIFY_DOCUMENT_V1 = "classify_document.v1"


def _load(version: PromptVersion) -> str:
    path = _PROMPT_DIR / f"{version.value}.txt"
    if not path.is_file():
        # At import, not at call time: a missing prompt file is a packaging error,
        # and discovering it on the first user request means discovering it in
        # production. The mapping below forces every version to resolve on import.
        raise RuntimeError(f"prompt file missing for {version.value}: expected {path.name}")
    return path.read_text(encoding="utf-8").strip()


#: Resolved eagerly so an incomplete deployment fails at boot, and wrapped in a
#: read-only proxy so the registry cannot be reassigned entry by entry. A plain dict
#: here meant `_PROMPTS[V] = "..."` silently changed every prompt issued thereafter.
_PROMPTS: MappingProxyType[PromptVersion, str] = MappingProxyType(
    {version: _load(version) for version in PromptVersion}
)


@final
class SystemPrompt:
    """An instruction to the model. Constructible only from a version key.

    `@final` and the absence of a stored `text` are the enforcement; see the module
    docstring for exactly which parts hold at runtime and which are mypy-only.
    """

    __slots__ = ("version",)

    version: PromptVersion

    def __init__(self, version: PromptVersion) -> None:
        if not isinstance(version, PromptVersion):
            # Not redundant with the annotation. `PromptVersion` is a `StrEnum`, so a
            # bare string hashes equal to a member and would sail through the lookup
            # below — mypy rejects it, nothing else did until this line existed.
            raise TypeError(
                f"SystemPrompt takes a PromptVersion, not {type(version).__name__}. "
                "Every instruction must name a versioned prompt file; text that did "
                "not come from one is not an instruction this system issues."
            )
        object.__setattr__(self, "version", version)

    @property
    def text(self) -> str:
        """Looked up per access rather than stored, so there is no instance attribute
        for `object.__setattr__` to overwrite."""
        return _PROMPTS[self.version]

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("SystemPrompt is immutable; construct a new one from a PromptVersion")

    def __repr__(self) -> str:
        # The version, never the text: a prompt in a traceback is a prompt in a log
        # (Architecture §20, CLAUDE.md §11 — unredacted prompts stay out of logs).
        return f"SystemPrompt({self.version.value})"
