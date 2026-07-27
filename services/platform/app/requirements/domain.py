"""Shared requirement vocabulary: the Conclusion enum and rule-set provenance.

`Conclusion` and `Currency` are two independent axes (ADR-0001): a result has a
conclusion (what we concluded) and, once persisted at M3B, a currency (whether that
conclusion is still current). They must never be collapsed into one enum. M2 uses
only `Conclusion`; `Currency` is defined here so the vocabulary is in one place.
"""

from enum import StrEnum


class Conclusion(StrEnum):
    SUPPORTED = "SUPPORTED"
    INCOMPLETE = "INCOMPLETE"
    INCONSISTENT = "INCONSISTENT"
    NEAR_THRESHOLD = "NEAR_THRESHOLD"
    REQUIRES_JUDGEMENT = "REQUIRES_JUDGEMENT"
    PROFESSIONAL_REVIEW_RECOMMENDED = "PROFESSIONAL_REVIEW_RECOMMENDED"
    NOT_CURRENTLY_SATISFIED = "NOT_CURRENTLY_SATISFIED"
    NOT_YET_ASSESSED = "NOT_YET_ASSESSED"


class Currency(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    PROVISIONAL = "PROVISIONAL"


# All M2 rule versions are 1.0.0 within rule set 2026.07.0 (RULES_SPEC §7). These
# travel in the RouteSupportEvaluated event so a past decision stays reproducible
# even before persisted rule versions exist.
RULE_SET = "2026.07.0"
SEMANTIC_VERSION = "1.0.0"
