# ADR-0025: An ExtractionRun references its ModelRun rather than copying it

**Status:** Accepted
**Date:** 2026-09-02
**Milestone:** M8 slice 2 (DocumentClassifier)

## Context

Two documents describe what a model invocation leaves behind, and they were written
independently.

`EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` §8 gives `ExtractionRun` twenty-one fields,
including `provider`, `model`, `prompt_version`, `schema_version`, `latency_ms`,
`input_tokens`, `output_tokens`, `estimated_cost`, `retry_number`, `trace_id` and
`output_hash`.

`Evidence_First_Citizenship_Workspace_Technical_Architecture_RFC.md` §20 asks for a
`model_runs` record on **every model invocation**, with an almost identical column
list — provider, model, prompt version, schema version, latency, tokens, estimated
cost, status, retry count, trace id, output hash.

M8 slice 1 built `model_runs` as Architecture §20 specifies. Implementing §8
literally would put the same eleven columns on a second table.

That is not merely redundant. The two tables would disagree, and the disagreement
would be invisible:

- **A retry makes several invocations.** One extraction that retries twice is three
  provider calls with three latencies and three token counts. `ExtractionRun` has one
  of each column, so it can only hold one — and whichever it holds, the spend ceiling
  reading `model_runs` and a human reading `extraction_runs` would see different
  numbers for the same work.
- **`model_runs` is deliberately outside the tenant** and `extraction_runs` is
  deliberately inside it (it carries `case_id` and needs an RLS policy). Copying cost
  and token data across that boundary puts a deployment-wide accounting figure into a
  case-scoped, user-deletable row.
- **Case deletion is terminal.** Deleting a case removes its `extraction_runs`. If
  those rows were the record of what was spent, deleting a case would erase spending
  history — and the ceiling would be re-derivable to a lower number by a user action.

## Decision

`extraction_runs` carries a nullable `model_run_id` foreign key and none of the
provider/cost/latency columns. It keeps what is genuinely its own: which capability
ran, against which file and which processing run, for which case, with what status,
over what input (`input_hash`), and what the run concluded.

`model_run_id` is nullable because an invocation can be refused before it is made —
the spend ceiling, or the task deadline — and the extraction run still needs to exist
to record that nothing happened and why.

**Foreign key direction is load-bearing.** The reference points from
`extraction_runs` (child) to `model_runs` (parent). `tests/security/test_rls_coverage.py`
derives case-scoped tables as the transitive closure of foreign keys *from* `cases`,
following child→parent edges; a parent is only pulled in if it is itself a child of
something reachable. Pointing the key the other way would make `model_runs`
case-scoped, which would require an RLS policy on the spend ledger and put it in the
case-deletion path — undoing every property ADR-worthy about keeping it global.

## Consequences

`EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` §8's field list is superseded by this ADR on
the eleven duplicated columns. The RFC's *intent* — that every extraction is
independently identifiable, attributable and costed — is preserved exactly; it is
satisfied through a join rather than through duplication.

The join is one hop and is not on any hot path: nothing renders a document library
page from `model_runs`.

Per CLAUDE.md's source-of-truth precedence, an RFC and the code disagreeing means the
RFC wins unless the RFC is changed. This ADR is that change, recorded rather than
diverged from silently. §8 should gain a pointer to it.

## Alternatives rejected

**Copy the columns and accept the duplication.** Simplest to write, and it fails on
the first retry — two tables reporting different token counts for one piece of work,
with nothing to say which is right.

**Drop `model_runs` and keep only `ExtractionRun`.** Loses every invocation that is
not an extraction: the provider probe today, `GuidanceExplainer` and
`IssueSummariser` later. Architecture §20 says *every* invocation, and a spend ceiling
that only sees extraction is not a spend ceiling.

**Make `model_runs` case-scoped so the two can be one table.** Rejected in slice 1 and
still rejected: the ceiling is a deployment-wide bound on a bill, and a per-tenant
ledger cannot express it.
