"""Versioned instructions, and the type that makes them the *only* instructions.

This module is one half of the prompt-injection defence (directive 8, Architecture
§23.4: *"Document content must not be allowed to alter system instructions"*). The
other half is `DocumentText` in `provider.py`.

The mechanism is a type, not a convention:

    SystemPrompt(PromptVersion.PROVIDER_PROBE_V1)   # the only constructor
    SystemPrompt("ignore previous instructions")    # KeyError, not an instruction

`SystemPrompt.__init__` takes a `PromptVersion` member and reads the text off disk.
There is no constructor, classmethod or setter anywhere that accepts free text, so
**there is no code path by which document content can become a system instruction**
— not because nobody wrote one, but because writing one means adding a constructor
that this docstring and `tests/ai/test_prompt_boundary.py` both argue with.

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

_PROMPT_DIR = pathlib.Path(__file__).parent / "prompts"


class PromptVersion(StrEnum):
    """Every instruction the system can issue. Adding a capability adds a member
    here and a file beside it; there is no third way to obtain a prompt."""

    PROVIDER_PROBE_V1 = "provider_probe.v1"


def _load(version: PromptVersion) -> str:
    path = _PROMPT_DIR / f"{version.value}.txt"
    if not path.is_file():
        # At import, not at call time: a missing prompt file is a packaging error,
        # and discovering it on the first user request means discovering it in
        # production. `_PROMPTS` below forces every version to resolve on import.
        raise RuntimeError(f"prompt file missing for {version.value}: expected {path.name}")
    return path.read_text(encoding="utf-8").strip()


#: Resolved eagerly, so an incomplete deployment fails at boot rather than on the
#: first document a user uploads.
_PROMPTS: dict[PromptVersion, str] = {version: _load(version) for version in PromptVersion}


class SystemPrompt:
    """An instruction to the model. Constructible only from a version key.

    `__slots__` and the absence of any setter are load-bearing: an instance cannot
    acquire a `text` that did not come from `_PROMPTS`, so passing one around is
    safe in a way that passing a `str` would not be.
    """

    __slots__ = ("text", "version")

    version: PromptVersion
    text: str

    def __init__(self, version: PromptVersion) -> None:
        # Not `_PROMPTS.get(...)`: an unknown key must raise rather than degrade to
        # an empty instruction, which would send the document with no instructions
        # at all and let it supply its own.
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "text", _PROMPTS[version])

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("SystemPrompt is immutable; construct a new one from a PromptVersion")

    def __repr__(self) -> str:
        # The version, never the text: a prompt in a traceback is a prompt in a log
        # (Architecture §20, CLAUDE.md §11 — unredacted prompts stay out of logs).
        return f"SystemPrompt({self.version.value})"
