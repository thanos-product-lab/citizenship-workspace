---
name: vertical-slice
description: The standard procedure for implementing any milestone slice in this repo. Use at the start of any task that adds or changes product behaviour — a new endpoint, screen, rule, or capability. Encodes the task pattern from IMPLEMENTATION_ROADMAP.md section 9.
---

# Implementing a vertical slice

A slice is a coherent user capability, not a layer. If the change only touches
one layer, it is probably too thin or wrongly scoped.

## Before writing code

State this back explicitly:

```
Milestone:
Vertical slice:
User outcome:
Source docs read:
```

Then:

1. **Read the source docs.** Always `CLAUDE.md`. Plus whichever apply:
   `MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md` for the boundary,
   `DOMAIN_MODEL_RFC.md` for entities and invariants,
   `DETERMINISTIC_RULES_SPEC.md` for anything touching rules or dates,
   `Evidence_First_Citizenship_Workspace_UI_UX.md` for anything visual.
2. **Inspect what already exists.** Do not assume greenfield.
3. **State your assumptions.** Explicitly, as a list. Assumptions that go
   unstated become defects.
4. **Name the affected domain modules** and confirm the change respects module
   boundaries — no reaching into another module's internals.
5. **Write measurable acceptance criteria.** "Works" is not one.
6. **List expected migrations.** New revision only; never edit a committed one.
7. **List expected tests**, including any property-based invariants from
   `CLAUDE.md` §9 or `DETERMINISTIC_RULES_SPEC.md` §10 that this slice touches.

**Stop and get approval** before coding if the slice touches the domain model,
migrations, deterministic rules, or the claim→fact→assessment path. Use plan
mode. These are the changes that are expensive to unwind.

## While coding

- Implement the **smallest complete slice**. Resist adjacent improvements.
- Keep domain logic in `service.py` / `domain.py`, out of route handlers.
- Add tests in the same change, not after.
- Regenerate the API client (`just api-client`) if any schema changed.
- Build the **empty, loading, error, and retry states** now. A slice without them
  is not done — see `definition-of-done`.
- Preserve observability: trace IDs propagate, no PII in logs or events.
- Update the relevant doc if behaviour changed.

## After coding

Report, in this order:

- files changed
- migrations added
- tests written and their result
- commands run
- trade-offs taken
- known gaps
- the next smallest task

## Then review

Dispatch the reviewers that apply:

| Slice touches | Run |
|---|---|
| evidence, claims, facts, assessments, recalculation | `trust-model-reviewer` |
| rule evaluators, windows, thresholds, day counting | `rules-conformance-reviewer` |
| any user-facing screen or component | `accessibility-reviewer` |
| auth, storage, uploads, logging, model calls | `security-reviewer` |

For a slice touching the assessment path, `trust-model-reviewer` is not optional.

## Context hygiene

Start a fresh session per milestone. Long sessions drift from `CLAUDE.md`, and a
compacted context is exactly where invariants get quietly dropped.
