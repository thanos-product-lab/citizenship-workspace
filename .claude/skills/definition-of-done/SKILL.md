---
name: definition-of-done
description: The completion gate for a slice or milestone. Use before claiming any work is finished, and at the end of every milestone. Encodes IMPLEMENTATION_ROADMAP.md section 10.
---

# Definition of done

A slice is **not** done because the component renders, the endpoint returns 200,
a model produced plausible output, or the happy path worked once.

## Slice gate

- [ ] The user outcome stated at the start actually works end to end
- [ ] Acceptance criteria pass, checked individually rather than in aggregate
- [ ] Domain model remains consistent; no new entity invented outside the RFC
- [ ] Migration added as a new revision; committed migrations untouched
- [ ] API client regenerated; drift check passes
- [ ] Frontend and backend tests pass
- [ ] Empty, loading, error, and retry states exist and were manually seen
- [ ] Keyboard path works; status is legible without colour
- [ ] Traces and structured logs present; no PII in logs, events, or telemetry
- [ ] Relevant docs updated
- [ ] The canonical synthetic case still produces its expected results
- [ ] No hidden out-of-scope dependency introduced

## Milestone gate

Everything above, plus:

- [ ] The milestone's user journey demoable start to finish
- [ ] Reviewers run and findings resolved: `trust-model-reviewer` where the
      assessment path was touched, `rules-conformance-reviewer` for rule changes,
      `accessibility-reviewer` for UI, `security-reviewer` for auth, storage,
      uploads, or model calls
- [ ] Demo assets captured into `docs/demo-assets/` while the work is fresh
- [ ] CI green on main
- [ ] Deployed environment still works, not just local

## Invariant spot-check

Before closing any milestone that touched the assessment path, verify by
inspection rather than assumption:

- [ ] No unconfirmed claim can reach a trusted assessment
- [ ] No assessment row is mutated in place
- [ ] Conclusion and currency remain separate
- [ ] A stale result cannot be returned as current through any API path
- [ ] Every current trusted result references exact input versions and a rule version
- [ ] No readiness percentage exists anywhere in the product

If any of these cannot be confirmed, the milestone is not done regardless of
what the checklist above says.
