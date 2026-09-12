# ADR-0029: `DocumentClaimExtractor` is a family of three capabilities, two of them built

**Status:** Accepted
**Date:** 2026-09-11
**Milestone:** M8 (Evidence and extraction), slice 5

## Context

Four documents name `DocumentClaimExtractor` as a single AI capability:
`IMPLEMENTATION_ROADMAP.md` §M8, `MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md`,
`EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` §8, and `AI_EVALUATION_PLAN.md` §4.2 — the last of
which also specifies `capability: DocumentClaimExtractor` as the value an eval manifest row
carries. `Capability.DOCUMENT_CLAIM_EXTRACTOR` existed in the enum from slice 2, with no
registry entry, so it was never invocable.

It reads three document kinds: immigration status, English language, Life in the UK.

**It cannot be one capability.** `ai.service.invoke` resolves both `prompt_version` and
`schema_version` from `REGISTRY[capability]`:

```python
capability_config = config_for(capability)
system = SystemPrompt(capability_config.prompt_version)
```

So one `Capability` member is exactly one prompt and one recorded schema version. Three
document kinds with three different field sets need three prompts — and AI_SPIKE_FINDINGS
§3.2 is the standing reason not to merge prompt text: a date-ambiguity rule placed in a
block shared between capabilities made the *classifier* start answering `AMBIGUOUS` because
documents' dates were ambiguous, suppressing extraction entirely.

A single capability could only have been honoured by one prompt covering all three kinds and
one superset schema carrying every field — which is the shared-block mistake plus a schema
in which an English certificate has somewhere to put a grant date.

## Decision

**Three capabilities, named for what they read.** Two built in slice 5:

- `Capability.ENGLISH_LANGUAGE_EXTRACTOR` — `extract_english_language.v1`, `english.v1`
- `Capability.LIFE_IN_UK_EXTRACTOR` — `extract_life_in_uk.v1`, `life_in_uk.v1`
- `ImmigrationStatusExtractor` — **deferred**, see below

`Capability.DOCUMENT_CLAIM_EXTRACTOR` is **removed** rather than kept as an alias. It was
never in the registry, so it was never invocable, so no `ModelRun` can name it — nothing
recorded resolves to it. An enum member for a capability that will not exist is a promise
the code does not keep.

`DocumentClaimExtractor` survives as the *family* name in the roadmap. The amendments below
say so in each affected document rather than leaving the code to disagree with them silently
(CLAUDE.md §12).

## Why immigration status is deferred

Not scope fatigue. Its documents propose `date_of_birth`, `status_type` and
`status_granted_on` — **the same three answers the user typed at onboarding** into
`RouteProfileVersion`. And nothing compares a confirmed `CaseFact` to the route profile:
`assessments/conflicts.py` filters on `TRAVEL_DATE_CLAIM_TYPES`, and
`ClaimType.IMMIGRATION_STATUS_GRANTED_ON` has no consumer anywhere outside its own enum
definition.

So a document stating a grant date that contradicts what the user typed would produce a
confirmed fact sitting silently beside a contradicting profile answer, with no surface
comparing them and no issue raised. That is the same defect class as the travel conflict that
took all of slice 4 to build — and the class this milestone's reviews have caught three times
since. Shipping it knowingly would be the false reassurance directive 7 exists to prevent.

What it needs first: fact-versus-route-profile conflict detection, reusing the slice-4
machinery. Its eval fixture stays in the manifest with ground truth authored before any
model ran, tagged `capability_not_built`, and the runner prints it as **NOT RUN** rather than
omitting it — a corpus whose totals overstate what was measured is the failure mode the first
eval run of this milestone demonstrated.

## Consequences

- `by capability` in the eval report separates the three. That matters under §12: a HIGH-risk
  immigration extractor averaged with two MEDIUM ones is exactly the hiding §12 forbids.
- Three prompt files where the roadmap implied one, each repeating the injection and
  date-ambiguity paragraphs rather than importing them. Duplication is the point;
  `test_the_two_extractor_prompts_share_no_wording_with_the_classifier` asserts they have
  not converged.
- The two flat extractors share `_extract_flat`, and `extract_travel` does not. The line is
  drawn at the shape of the work rather than the count of capabilities: these two are one
  operation over two configurations, travel's claims are journey-scoped.
- Manifest `capability:` values no longer match AI_EVALUATION_PLAN §4.2 as written; §4.2 is
  amended.

## A consequence found by review, and recorded rather than fixed

**RFC §16's cross-document conflict is now reachable.** These claim types sit outside
`JOURNEY_SCOPED_CLAIM_TYPES`, so `scope_key_for` returns `""` and the resulting facts are
case-level: one English test result per case. A second certificate proposing a different test
date therefore appends a **new version** of the same fact rather than creating a second fact.

Supersession is correct and nothing is lost in Postgres — verified: two `FactVersion` rows,
`version_number` 1 and 2, the second marked as superseding. But **no surface shows it**.
`FactRepository.versions_of` has no caller in `app/`, `/facts` returns the current version
only, and no issue is derived. So which certificate becomes the case's answer is decided by
the order the user pressed Confirm, and on screen the result is indistinguishable from a
correction — the same failure the slice-3a review caught for journeys.

Before this slice no claim type produced a case-level fact through review, so
`append_version`'s supersession branch was unreachable that way. Slice 5 makes it reachable.

RFC §42.4 already names this as the trigger to revisit — *"a conflict between two documents
(§16) has no travel record to hang an issue on"* — so the deferral is sanctioned, but the
trigger has now fired **inside** M8 and this is the record of that. The cheap fix, when it is
taken, is a derivation rather than a table: raise an issue when a case-level fact acquires a
version whose value differs from its predecessor's and whose `FactEvidenceLink` names a
different evidence item. `issues.derive` is already that shape. Building `ConflictCandidate`
is not required.

## Amendments this ADR makes

| Document | Change |
|---|---|
| `IMPLEMENTATION_ROADMAP.md` §M8 | `DocumentClaimExtractor` reads as a family of three |
| `MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md` | same |
| `EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` §8 | capability list names the three |
| `AI_EVALUATION_PLAN.md` §4.2 | manifest `capability:` values are the per-kind names |
