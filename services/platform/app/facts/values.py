"""The claim→fact boundary, as types.

This is the file prime directive 1 lives in. *"AI output is a proposal, never a fact.
A trusted `FactVersion` is created only after an explicit user CONFIRM / CORRECT
decision."* Everywhere else that sentence is a rule someone has to follow; here it is
a shape that makes the alternative unspellable.

## The mechanism

There are exactly two things a `FactVersion` can be built from:

    FactVersion.from_review(reviewed: ReviewedValue, ...)
    FactVersion.from_user_entry(entered: UserEnteredValue, ...)

and a `ReviewedValue` can only be produced by `ClaimReviewDecision.outcome()`, a method
on a **flushed** decision row — `decision_id` is assigned on flush, so the object cannot
exist unless the decision it names is already durable.

`ExtractedClaim.proposed_value` is a `ProposedValue`. Nothing converts a `ProposedValue`
into a `ReviewedValue`. There is no `from_claim`, no `to_fact`, and no `cast` anywhere on
the path. So *"a claim cannot become a fact without a recorded decision"* is not a rule
this codebase follows — it is a `just typecheck` failure, with no `isinstance` guard for
anyone to delete.

That is the standard M5 set with `UnlinkedResult`, which has no `input_links` field so a
simulated result cannot be persisted (`requirements/evaluation.py`). The same argument,
applied to the more dangerous boundary.

## Why the values are split in two shapes

`EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` §41.1. A `date.v1` carries what the document
*says* and, separately, what that means — and the second is null whenever the document
does not determine it.

The split is the M8 spike's central finding made structural (AI_SPIKE_FINDINGS §3.1).
Given `03/04/2025` with no month in words anywhere, the model resolved it to a confident
`2025-04-03` three times out of three under a mild instruction, and abstained three times
out of three under a forceful one. A behaviour that swings entirely on prompt wording is
not a guarantee — the next model version can swing it back, silently, and the failure
would be a confident wrong date on a high-risk field.

So `iso` is advisory and `normalise` decides. A written form that does not parse
unambiguously produces `None` **whatever the model returned**, which is what makes the
deterministic normaliser the defence rather than defence in depth.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Literal


class ValueSchema(StrEnum):
    """The two shapes a claim's value may take (RFC §41.1).

    Two rather than one per field, because a per-field schema would version thirty
    things that change together and none of the things that change independently.
    """

    DATE_V1 = "date.v1"
    TEXT_V1 = "text.v1"


class SourceMethod(StrEnum):
    """How a trusted value came to be trusted (RFC §11).

    **AI is not among them, and cannot be added by accident**: the two AI-derived
    methods both name a human decision, and the database refuses a `FactVersion`
    carrying either without a `claim_review_decision_id` to point at.
    """

    USER_ENTERED = "USER_ENTERED"
    USER_CONFIRMED_AI_CLAIM = "USER_CONFIRMED_AI_CLAIM"
    USER_CORRECTED_AI_CLAIM = "USER_CORRECTED_AI_CLAIM"
    DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"


#: The source methods that require a review decision behind them. Named once here
#: because migration 0030's CHECK constraint says the same thing in SQL and
#: `tests/facts/test_boundary.py` asserts the two agree.
REVIEW_DERIVED = frozenset(
    {SourceMethod.USER_CONFIRMED_AI_CLAIM, SourceMethod.USER_CORRECTED_AI_CLAIM}
)


@dataclass(frozen=True)
class ProposedValue:
    """What a model said.

    No reviewer, no decision, and no field in which to hold one. This is the type
    `ExtractedClaim.proposed_value` has, so the dangerous object is dangerous at the
    type level everywhere it travels rather than only at the boundary it must not cross.
    """

    schema: ValueSchema
    #: Verbatim from the document. For `text.v1` this is the value; for `date.v1` it is
    #: the date as written, before anyone has decided what it means.
    raw: str
    #: The model's ISO reading of a `date.v1`, or None. **Advisory.** `normalise` is what
    #: decides, and disagrees with this whenever the written form is ambiguous.
    model_iso: str | None = None


@dataclass(frozen=True)
class ReviewedValue:
    """A value a human decided about, and the only thing `FactVersion.from_review` takes.

    Constructible **only** by `ClaimReviewDecision.outcome()`. Its `decision_id` is the
    id of a flushed row, so this object cannot be built before the decision it names is
    durable — which is the whole of "no fact without a recorded decision", expressed as
    a constructor precondition rather than as a check somebody runs.

    `source_method` is a `Literal` of the two review-derived methods. A
    `DETERMINISTIC_DERIVATION` or a `USER_ENTERED` cannot be smuggled through this path,
    and a review cannot produce anything else.
    """

    decision_id: uuid.UUID
    claim_id: uuid.UUID
    schema: ValueSchema
    raw: str
    normalised: str | None
    source_method: Literal[
        SourceMethod.USER_CONFIRMED_AI_CLAIM, SourceMethod.USER_CORRECTED_AI_CLAIM
    ]
    reviewed_by: str
    reviewed_at: datetime


@dataclass(frozen=True)
class UserEnteredValue:
    """A value the user typed with no model involved at all (RFC §13).

    Separate from `ReviewedValue` because it has no claim and no decision behind it —
    there was nothing to review. Kept in this file so that both ways of reaching a
    trusted value are visible in one place, and neither can be added to without the
    other being noticed.
    """

    schema: ValueSchema
    raw: str
    normalised: str | None
    entered_by: str
    entered_at: datetime


#: Date formats that determine a calendar date without a convention having to be assumed.
#:
#: Every one names its month, or is unambiguous by construction. `%d/%m/%Y` is
#: conspicuously absent and its absence is the point: `03/04/2025` is 3 April or 3 March
#: depending on whose convention applies, and nothing in a UK booking confirmation
#: settles which. Adding it here would silently re-introduce the guess this whole design
#: exists to refuse.
_UNAMBIGUOUS_FORMATS = (
    "%Y-%m-%d",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B, %Y",
)


def normalise(value: ProposedValue) -> str | None:
    """The deterministic reading of a written value, or None when there is not one.

    **Python decides this, never the prompt** (CLAUDE.md §2.2). `value.model_iso` is
    ignored entirely — not consulted as a hint, not used as a fallback — because a value
    that only sometimes reflects a deterministic rule is worse than one that never does:
    it looks reliable until the model changes.

    Returns None for an ambiguous date, and that is a *result*, not a failure. The claim
    is still created, still shown, and still reviewable; the human reads the document —
    where the month names and the booking's own logic are — and enters what it means.
    """
    if value.schema is ValueSchema.TEXT_V1:
        return " ".join(value.raw.split()) or None

    text = value.raw.strip()
    for fmt in _UNAMBIGUOUS_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_entered_date(text: str) -> date | None:
    """A date a *user* typed, read the same way the normaliser reads a document.

    The same formats, on purpose. A person entering `03/04/2025` into the blind-entry
    field is as ambiguous as a document containing it, and accepting it would let the
    interaction that exists to remove a guess quietly reintroduce one.
    """
    for fmt in _UNAMBIGUOUS_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None
