"""TravelRecordExtractor: what a booking says about a journey.

Architecture RFC §19's third capability, and the first that proposes values a user can
confirm into facts. Everything the classifier could get wrong was routing; everything
this can get wrong reaches a person as a proposal about their own travel.

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

#: How much of the document the extractor sees. Larger than the classifier's window
#: because a booking's return leg can sit well below the fold, and a truncated read
#: would silently propose a one-way trip.
MAX_INPUT_CHARACTERS = 20_000
