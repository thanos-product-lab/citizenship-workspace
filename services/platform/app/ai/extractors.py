"""The extraction schemas: what a document says about itself.

`TravelRecordExtractor` (Architecture RFC §19's third capability) plus the two test-result
extractors added in slice 5. Everything the classifier could get wrong was routing;
everything these can get wrong reaches a person as a proposal about their own case.

**One schema per document kind, chosen before the call.** The classifier's constrained
output picks the extractor, so a document never influences the schema used to read it.
That is also why these are separate `Capability` members rather than one: `invoke`
resolves the prompt from `REGISTRY[capability]`, so one capability is one prompt, and
§3.2's finding — a date rule in a shared block made the *classifier* answer AMBIGUOUS
about dates — is the standing reason not to merge prompt text.

**Every date is two fields.** `as_written` is verbatim; `iso` is the model's reading and
is null whenever the document does not determine one. `iso` is then *ignored* — the
deterministic normaliser in `facts/values.py` decides, because the M8 spike measured
this behaviour swinging from 0/3 to 3/3 on prompt wording alone (AI_SPIKE_FINDINGS
§3.1) and something that moves with a prompt is not a guarantee.

**The output schema carries no authority.** No `confirmed`, `eligible`, `approved`,
`valid` or `status`. A document instructing the model to mark a trip confirmed has
nowhere to put the answer.

**Formats are pinned.** `iso` says YYYY-MM-DD in its description, because the spike got
`2026-05-11T18:40:00Z` from an unconstrained `str` and the schema was at fault rather
than the model (§3.3).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.facts.domain import ClaimType


class ExtractedDate(BaseModel):
    """A date as the document writes it, and what the model thinks it means."""

    model_config = ConfigDict(extra="forbid")

    #: Exactly as it appears in the document, or null if the field is absent.
    as_written: str | None = Field(max_length=100)
    #: The model's reading. **Advisory and unused** — `facts.values.normalise` decides.
    #: Kept so an evaluation can measure how often the two agreed.
    iso: str | None = Field(
        default=None,
        max_length=40,
        description=(
            "Calendar date only, formatted exactly YYYY-MM-DD. Never a time, a timezone "
            "or the letter T. Null if the document does not determine the date."
        ),
    )


class Journey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    departure: ExtractedDate
    arrival_return: ExtractedDate
    origin: str | None = Field(default=None, max_length=200)
    destination: str | None = Field(default=None, max_length=200)
    booking_reference: str | None = Field(default=None, max_length=100)
    traveller_name: str | None = Field(default=None, max_length=200)


class TravelExtraction(BaseModel):
    """The capability's whole output surface."""

    model_config = ConfigDict(extra="forbid")

    journeys: list[Journey] = Field(max_length=20)


#: Which claim type each journey field becomes, and whether it is a date.
#:
#: A mapping rather than a chain of `if`s so that "every field this capability can
#: propose" is a list somebody can read, and so a field added to the schema without a
#: claim type is a `KeyError` at the one place claims are built rather than a value that
#: silently never reaches review.
TRAVEL_FIELDS: dict[str, ClaimType] = {
    "departure": ClaimType.TRAVEL_DEPARTURE_DATE,
    "arrival_return": ClaimType.TRAVEL_RETURN_DATE,
    "origin": ClaimType.TRAVEL_ORIGIN,
    "destination": ClaimType.TRAVEL_DESTINATION,
    "booking_reference": ClaimType.TRAVEL_BOOKING_REFERENCE,
    "traveller_name": ClaimType.TRAVEL_TRAVELLER_NAME,
}


class TestOutcome(StrEnum):
    """Whether the candidate passed the test the document reports.

    An enum, not a `str`, and that is doing two jobs. §3.3: an unconstrained `str` is an
    open question, and open questions get answered in ways nobody intended. And it is the
    authority guard — a document instructing the model to mark the applicant eligible has
    nowhere to put the answer, because this field accepts two words and neither of them is
    about the applicant. It reports the *test*.
    """

    PASS = "PASS"
    FAIL = "FAIL"


class CefrLevel(StrEnum):
    """The CEFR scale, closed. A level is the one field on an English certificate that a
    rule will eventually compare against a threshold, so "B1 (Pass)" or "b1" arriving as
    free text would push the parsing somewhere it cannot be versioned."""

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class EnglishLanguageExtraction(BaseModel):
    """What an English-language certificate says. `extra="forbid"` (MVP §8.10).

    Every field is optional except the date, which is always the two-field `ExtractedDate`
    — absent is `as_written: null`, which is different from present-but-unreadable and the
    review queue needs to tell them apart.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_name: str | None = Field(default=None, max_length=200)
    test_provider: str | None = Field(default=None, max_length=200)
    cefr_level: CefrLevel | None = None
    overall_result: TestOutcome | None = None
    #: When the test was *taken*. A certificate carries several dates and this is the one
    #: a rule would read; see the prompt for why the issue date is not it.
    date_of_test: ExtractedDate


class LifeInUkExtraction(BaseModel):
    """What a Life in the UK pass notification says. `extra="forbid"`."""

    model_config = ConfigDict(extra="forbid")

    candidate_name: str | None = Field(default=None, max_length=200)
    #: The unique reference that identifies the *result*, which a notification carries
    #: alongside a booking reference that identifies the appointment.
    unique_reference: str | None = Field(default=None, max_length=100)
    overall_result: TestOutcome | None = None
    test_date: ExtractedDate


#: Same contract as `TRAVEL_FIELDS`: schema field name → the claim type it proposes. A
#: field added to a schema without an entry here is a `KeyError` where claims are built,
#: not a value that silently never reaches review.
#:
#: The claim types are namespaced by category (`english.`, `life_in_uk.`), which is what
#: makes a cross-wired entry checkable rather than merely unlikely — see
#: `test_every_field_in_both_schemas_maps_to_a_claim_type`.
ENGLISH_FIELDS: dict[str, ClaimType] = {
    "candidate_name": ClaimType.ENGLISH_CANDIDATE_NAME,
    "test_provider": ClaimType.ENGLISH_PROVIDER,
    "cefr_level": ClaimType.ENGLISH_CEFR_LEVEL,
    "overall_result": ClaimType.ENGLISH_OVERALL_RESULT,
    "date_of_test": ClaimType.ENGLISH_TEST_DATE,
}

LIFE_IN_UK_FIELDS: dict[str, ClaimType] = {
    "candidate_name": ClaimType.LIFE_IN_UK_CANDIDATE_NAME,
    "unique_reference": ClaimType.LIFE_IN_UK_UNIQUE_REFERENCE,
    "overall_result": ClaimType.LIFE_IN_UK_OVERALL_RESULT,
    "test_date": ClaimType.LIFE_IN_UK_TEST_DATE,
}


#: How much of the document the extractor sees. Larger than the classifier's window
#: because a booking's return leg can sit well below the fold, and a truncated read
#: would silently propose a one-way trip.
MAX_INPUT_CHARACTERS = 20_000
