---
name: new-capability
description: Procedure for adding an AI capability — schema, prompt version, model config, failure state, eval fixtures, and the boundary rules a capability must not break. Use whenever a new model-backed capability is added or an existing one's prompt, schema or model changes.
---

# Adding an AI capability

The sibling of `new-rule`. A rule is deterministic Python; a capability is a model
call, and the whole point of the architecture is that the second can never quietly
become the first.

Architecture RFC §19: **no universal AI function, no agent framework.** A capability
is narrow, typed, versioned, and independently evaluated.

## Before writing code

State this back:

```
Capability:
What it proposes (never decides):
Input (what the model sees, and what it does not):
Output schema + version:
Prompt version:
Model + why that one:
Failure state:
Eval fixtures:
```

## The six things a capability must declare

Every one of these has a home already. A capability missing any of them is not
finished.

1. **Output schema** — a Pydantic model with `extra="forbid"`. Unknown fields are
   rejected (MVP §8.10). **No field may carry authority**: no `confirmed`,
   `eligible`, `approved`, `status` or `conclusion`. A document instructing the model
   to mark an applicant eligible must have nowhere to put the answer.
2. **Prompt** — a file in `app/ai/prompts/` and a member of `PromptVersion`. Never a
   Python string literal, so a prompt change is a reviewable diff and
   `prompt_version` on a `ModelRun` names something recoverable.
3. **Registry entry** — `app/ai/config.py` `REGISTRY`, giving model, prompt version
   and schema version. A capability absent from the registry cannot be invoked.
4. **`Capability` enum member** — `app/ai/domain.py`.
5. **Failure state** — what the *user* sees when this capability fails. Not an
   exception type: a state. A silent skip is false reassurance (directive 7).
6. **Eval fixtures** — at least one clean case, one adversarial, and a manifest entry
   in `services/platform/evals/manifests/` with `expected` and, where the document
   contains a plausible wrong answer, `must_not_extract`.

## Rules that are not negotiable

- **Call through `ai.service.invoke`.** It owns the spend ceiling, the task deadline
  and the `ModelRun` record. Reaching a provider any other way skips all three.
- **Document text travels as `DocumentText`, in the user message, and nowhere else.**
  It cannot reach a `SystemPrompt` — that is a type error, and it must stay one.
- **Never pass `tools`.** There is no parameter for it; do not add one.
- **The schema is chosen before the call**, from a prior constrained output. A
  document must never influence which schema is used to read it.
- **`model_confidence` grants no authority.** Nothing may branch on it to skip,
  shorten or auto-approve review (RFC §36).
- **Output is a proposal.** A capability may create an `ExtractedClaim`. It may never
  create a `FactVersion` — and `FactVersion.from_review` will not let it.

## Prompt hygiene

**Share as little text between capabilities as possible.** The M8 spike put a
date-ambiguity rule in a shared block; the extractor obeyed it and the *classifier*
started reporting documents as `AMBIGUOUS` because their dates were — answering the
wrong question and suppressing extraction entirely (AI_SPIKE_FINDINGS §3.2). If two
prompts need the same sentence, repeat it.

**Pin formats explicitly.** An unconstrained `str` field is an open question, and open
questions get answered in ways you did not intend — the same spike got
`2026-05-11T18:40:00Z` where it wanted `2026-05-11`, and the schema was at fault, not
the model (§3.3).

## Before declaring it done

- `just lint`, `just typecheck`, `just test-be`
- `just eval` — and read the output, including the abstention numbers
- Add the capability's fixtures to the manifest *before* running the eval, so the
  first number you see is measured against ground truth authored independently
  (§9), not against what the model happened to return.

## Then review

`security-reviewer` — always, for anything touching the provider boundary, prompts,
or what is recorded about a call.
`trust-model-reviewer` — always, once a capability can produce a claim.
