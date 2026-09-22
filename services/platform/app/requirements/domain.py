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


# The route rules' version within rule set 2026.07.0 (RULES_SPEC §7). It travels in the
# RouteSupportEvaluated event so a past decision stays reproducible — which is the whole
# reason it has to move whenever any route rule's behaviour does. It is a single coarse
# stamp over all three, so it reads as "the route logic at the time", not as a per-rule
# version; the persisted `AssessmentResult.rule_version_id` is what carries those.
#
# 1.1.0: `route.standard_section_6_1` stopped treating an undetermined prerequisite as a
# failed one (§7.2b, migration 0037). `route.adult_applicant` and `route.supported_status`
# are unchanged and remain 1.0.0 in `rule_versions`.
RULE_SET = "2026.07.0"
SEMANTIC_VERSION = "1.1.0"
