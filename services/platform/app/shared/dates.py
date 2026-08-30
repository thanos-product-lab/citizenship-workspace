"""The calendar range every user-entered date has to fall inside.

**Not a domain rule.** The rules spec has nothing to say about how old an applicant may
be or how far ahead someone may plan, and this file must never become the place such a
thing is decided — a threshold that affects a conclusion belongs in
`DETERMINISTIC_RULES_SPEC.md` with a `[GUIDANCE]` or `[PRODUCT]` tag and a rule version
behind it. This is the weaker, prior question: is the value a date a human could have
meant at all?

Two reasons it exists, and the second is the one that matters.

**It stops the arithmetic falling over.** `qualifying_window` subtracts five years, so a
date before year six raises `ValueError: year -4 is out of range` from the stdlib and
surfaces as a 500 on a field the user typed into.

**It stops the product answering confidently about an input that cannot be true.** A
route profile carrying `date_of_birth = 0995-12-11` was assessed without hesitation:
`route.adult_applicant → SUPPORTED`, for an applicant 1031 years old. Nothing was broken.
Every rule did exactly what it was told, and the answer was worthless. Directive 7 asks
for visible uncertainty over false reassurance, and the most confident possible answer
derived from a typo is the purest false reassurance the product can produce.

Found by driving the M7 gate walkthrough by hand. 793 backend tests passed throughout,
because every fixture in the suite holds a sensible date — which is the general shape of
what a test suite cannot tell you.

**Why reject rather than escalate.** `REQUIRES_JUDGEMENT` exists for a case that is
genuinely hard, and treating a mistyped year as case complexity would put a real
escalation state to work hiding a data-entry slip. A value outside this range is not an
assessment that needs care; it is a question that was never well formed. The user is told
which field and what range, and fixes it — which they cannot do if the product quietly
assesses it instead.

The range is deliberately generous. It is a sanity bound, not a plausibility bound: 1900
admits an applicant who would be 126, and the *rules* are what decide whether an age or a
holding period supports the route. Narrowing this to something demographically plausible
would be moving a domain judgement into schema validation, where it would be invisible to
the rules spec and versioned by nothing.
"""

from datetime import date

#: The earliest date any user-entered field may carry.
MIN_ENTERED_DATE = date(1900, 1, 1)

#: The latest. Generous on purpose — a proposed application date is a *plan*, and the
#: simulator's whole job is trying values that have not happened yet.
MAX_ENTERED_DATE = date(2100, 12, 31)

__all__ = ["MAX_ENTERED_DATE", "MIN_ENTERED_DATE"]
