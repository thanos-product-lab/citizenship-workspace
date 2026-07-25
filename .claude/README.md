# `.claude/` configuration

Drop the `.claude/` directory at the repository root, alongside `CLAUDE.md`.

```
.claude/
├── settings.json                        permissions + hook wiring
├── agents/
│   ├── trust-model-reviewer.md          claims vs facts, immutability, provenance, stale
│   ├── rules-conformance-reviewer.md    implementation vs DETERMINISTIC_RULES_SPEC
│   ├── accessibility-reviewer.md        non-colour status, keyboard timeline, table alt, WCAG 2.2 AA
│   └── security-reviewer.md             case ownership, presigned URLs, PII, prompt injection, spend
├── hooks/
│   ├── protect-immutables.sh            PreToolUse — blocks (exit 2)
│   └── rules-guard.sh                   PostToolUse — warns, never blocks
└── skills/
    ├── vertical-slice/                  the standard task procedure
    ├── new-rule/                        adding a deterministic requirement rule
    ├── definition-of-done/              the completion gate
    └── milestone-gate/                  the end-of-milestone human-verification gate
```

## Organising principle

> `CLAUDE.md` states the invariants. Hooks enforce the mechanical ones. Agents
> audit the semantic ones. Skills make the right path the easy path.

The discipline that keeps this small: **never use an agent where a grep works.**
An agent is slower, costs context, and is less reliable at deterministic checks.

## Setup

```bash
chmod +x .claude/hooks/*.sh
```

`settings.json` wires two hooks, both present in `hooks/`: `protect-immutables.sh`
on `PreToolUse` and `rules-guard.sh` on `PostToolUse`. Every hook referenced in
`settings.json` has a file on disk; do not wire a hook that does not exist.

## When to run which reviewer

All four reviewers exist in `agents/`. Run the ones the change touches.

| Change touches | Reviewer |
|---|---|
| evidence, claims, facts, assessments, recalculation | `trust-model-reviewer` — **not optional** |
| rule evaluators, windows, thresholds, day counting | `rules-conformance-reviewer` |
| any user-facing screen or component | `accessibility-reviewer` |
| auth, storage, uploads, logging, model calls | `security-reviewer` |

## Optional / not yet wired

- **`format-and-vet.sh`** — not included. If you want format + typecheck on every
  edit, add the script (ruff + mypy for `services/platform`, eslint + tsc for
  `apps/web`) and wire it into `settings.json` `PreToolUse`. It is intentionally
  absent until the toolchain lands in M1.

## Deliberately not built

- **`contract-conformance-reviewer`** — OpenAPI drift is a deterministic CI check
  that already exists in the pipeline. An agent reading generated TypeScript to
  spot drift is slower and less reliable than the check you have.
- **`tenant-isolation-reviewer`** — no analogue. Single-owner case ownership is
  covered by the `security-reviewer`.
- **`new-capability` skill** — defer to M8. Writing it now means writing it
  against untested assumptions about extraction schemas. Write it after the
  week-2 spike shows you the real shape.

## Hook behaviour

`protect-immutables.sh` **blocks** edits to: `packages/api-client/generated/**`
(the generated OpenAPI client; the package scaffolding around it is authored and
editable), committed Alembic migrations, and the two source-of-truth RFCs
(`DETERMINISTIC_RULES_SPEC.md`, `DOMAIN_MODEL_RFC.md`). Uncommitted migrations are
editable by design — you need to be able to fix a revision before it ships. To
change a protected RFC, agree the change first (an ADR in `docs/decisions/`), then
apply it deliberately.

`rules-guard.sh` only **warns**. Its greps are cheap heuristics: year arithmetic
with no `+1 day` nearby, `sum(...absence...)`, `readiness_score`, frontend code
recomputing totals. It also runs `just test-rules` when rule code changes.
Expect occasional false positives — that is the right trade for a warning that
costs nothing.
