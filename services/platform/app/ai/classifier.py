"""DocumentClassifier: which of the four supported kinds of document is this?

Architecture RFC §19's first capability, and deliberately the first one built. It is
the lowest-stakes model output in the system: it proposes nothing a user could confirm
into a fact, so the whole boundary — run records, cost accounting, timeout, retry,
injection resistance — is exercised with nothing trusted downstream.

**What it decides, and what it does not.** It decides which extractor will read the
document in slice 3a. It does *not* change `EvidenceItem.category`, which the user
chose at upload and which remains theirs. A disagreement between the two is a signal
worth surfacing, not a correction to apply — and there is no code path that writes the
model's answer over the user's.

**Why the classification is not a claim.** An `ExtractedClaim` is a proposed *value* a
user may confirm into a `FactVersion`. A category is neither: no requirement reads it,
no assessment depends on it, and there is nothing in the fact model it could become.
It is routing metadata, and it lives on the `ExtractionRun` that produced it rather
than in the claim tables — which is also why slice 2 can ship before the claim→fact
path exists without shipping something that half-resembles it.

**What the model sees.** The text M7's parser read, bounded, and the page count.
Not the filename, not the user's declared category, not anything about the case.
The filename omission is deliberate and is what MVP §8.10's misleading-filename
criterion asks for: a document named `settled-status.pdf` containing a restaurant menu
must be classified on the menu.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.evidence.domain import EvidenceCategory


class ClassifiedCategory(StrEnum):
    """The classifier's closed output set: the four supported categories, plus the two
    ways of declining to choose.

    `UNSUPPORTED` and `AMBIGUOUS` are outcomes, not errors. AI_EVALUATION_PLAN §3.2:
    *"correct abstention is a success"* — a document the classifier refuses to force
    into a category is a document whose fields will not be read out with the wrong
    schema, which is the failure this enum exists to make avoidable.
    """

    IMMIGRATION_STATUS = "IMMIGRATION_STATUS"
    ENGLISH_LANGUAGE = "ENGLISH_LANGUAGE"
    LIFE_IN_THE_UK = "LIFE_IN_THE_UK"
    TRAVEL_SUPPORT = "TRAVEL_SUPPORT"
    #: A real document of a kind this workspace does not handle.
    UNSUPPORTED = "UNSUPPORTED"
    #: The text does not determine which supported category applies.
    AMBIGUOUS = "AMBIGUOUS"


#: The categories that select an extractor in slice 3a. `UNSUPPORTED` and `AMBIGUOUS`
#: are absent by construction, so "which extractor runs" has no answer for them —
#: a document nobody could classify cannot have its fields read out under a guess.
EXTRACTABLE: dict[ClassifiedCategory, EvidenceCategory] = {
    ClassifiedCategory.IMMIGRATION_STATUS: EvidenceCategory.IMMIGRATION_STATUS,
    ClassifiedCategory.ENGLISH_LANGUAGE: EvidenceCategory.ENGLISH_LANGUAGE,
    ClassifiedCategory.LIFE_IN_THE_UK: EvidenceCategory.LIFE_IN_THE_UK,
    ClassifiedCategory.TRAVEL_SUPPORT: EvidenceCategory.TRAVEL_SUPPORT,
}


class ClassificationOutput(BaseModel):
    """The capability's whole output surface.

    `extra="forbid"`, so a model returning a field nobody asked for fails validation
    rather than having it quietly ignored (MVP §8.10: *"Unknown fields are not
    accepted"*).

    **No field here can carry authority.** There is no `confirmed`, `eligible`,
    `approved`, `valid` or `conclusion`. A document instructing the model to mark an
    applicant eligible has nowhere to put the answer, which is the strongest of the
    injection controls precisely because it needs no vigilance to hold.
    """

    model_config = ConfigDict(extra="forbid")

    category: ClassifiedCategory
    #: How well the text fits the chosen category. **Display metadata only.** Nothing
    #: branches on it — no threshold skips review, shortens a check, or promotes a
    #: classification (RFC §36: "Model confidence never grants additional authority").
    confidence: float = Field(ge=0.0, le=1.0)
    #: One short sentence naming what decided it, shown to the user beside the
    #: category. Bounded because it is the one free-text field the model controls and
    #: it is rendered: an unbounded string is an unbounded thing to put on a page.
    reasoning: str = Field(max_length=300)


#: How much of the document the classifier sees.
#:
#: A classifier needs the top of a document, not all of it — letterheads, titles and
#: reference numbers are what distinguish these four kinds, and they are on page one.
#: Capping the input is also the per-call cost bound doing real work: `extraction.py`
#: allows 200,000 characters, and sending all of them would cost roughly forty times
#: what the M8 spike measured per document, for an answer decided in the first few
#: hundred.
MAX_INPUT_CHARACTERS = 6_000
