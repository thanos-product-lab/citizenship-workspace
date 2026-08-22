# Documentation Reconciliation — 2026-07-24

### Status

Apply to the live repository. Each item states the file, the change, and the
authority for it. Nine are mechanical; two (items 2 and 7) carry ADRs because
they correct a document against the project's own rules.

**Precedence used throughout:** `IMPLEMENTATION_ROADMAP.md` is newest and wins on
sequencing; `DETERMINISTIC_RULES_SPEC.md` and `DOMAIN_MODEL_RFC.md` win on rule
and domain semantics; the two "cut" decisions and the new rule were confirmed by
the project owner on 2026-07-24.

---

## Item 1 — Three milestone maps

**Problem:** Technical Architecture RFC §31 (Phase 1–6), MVP Scope §17
(Milestone 1–7), and the Roadmap (M0–M12) number the build differently, so "M6"
is ambiguous across documents.

**Resolution:** The Roadmap's M0–M12 is the single canonical build order. The
other two are retained as their own framings but must cross-reference it.

**Changes:**

- `docs/architecture/..._Technical_Architecture_RFC.md` §31 — add at the top of
  the section:
  > **Canonical build order lives in `docs/IMPLEMENTATION_ROADMAP.md` (M0–M12).**
  > The phases below are a coarser architectural grouping; where they disagree on
  > sequence, the Roadmap wins.
- `docs/product/MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md` §17 — add the same pointer.
- `CLAUDE.md` — add to §8 (How to work in this repo):
  > When any document says "M*n*", it refers to the Roadmap's numbering. The
  > Technical RFC phases and MVP milestones are alternative framings, not the
  > build order.

---

## Item 2 — Timeline mockup does math the rules forbid  *(ADR-0002)*

**Problem:** `..._UI_UX.md` §8.3 shows moving the application date from 15 April
2027 to 16 April 2027 flipping start-date presence from "Not supported" to
"Supported" and reducing the absence total 426 → 424. Under
`DETERMINISTIC_RULES_SPEC.md`, both halves are wrong:

1. Moving the application date forward shifts the whole five-year window forward
   (§3, §4.2). Clearing an absent anchor date usually needs a **multi-day** move,
   not one day — you have to move past the entire trip that covers the anchor.
2. Moving the window forward drops early absent days and picks up later ones; it
   does not simply subtract two days. The direction and magnitude shown are
   arbitrary.

A developer building this screen could copy the wrong behaviour directly into the
simulator.

**Resolution:** Replace the mockup with a rules-consistent example. Use the
worked example from `DETERMINISTIC_RULES_SPEC.md` §9, where the Spain trip
(14–20 April 2022) covers the anchor date and the resolving move is to 20 April
2027.

**Change** — `docs/design/..._UI_UX.md` §8.3, replace the mockup block with:

```text
Move proposed application date

15 April 2027
Qualifying start: 16 Apr 2022 · you were abroad (Spain, 14–20 Apr 2022)
Start-date presence: Not supported

20 April 2027
Qualifying start: 21 Apr 2022 · after your Spain trip
Start-date presence: Supported

Total absences recalculate as the whole 5-year window moves.
Preview before saving.
```

Add a caption:

> The window moves as a whole. Clearing an absent start date means moving past
> the trip that covers it — often several days, not one. Exact totals come from
> the server; never compute them in the mockup or the client.

See ADR-0002.

> **Superseded 2026-08-22, and left in place as the record of what was proposed.**
> The replacement block above is itself wrong by one day: the return day is a UK day
> (`DETERMINISTIC_RULES_SPEC.md` §5.1), so a trip returning 20 Apr 2022 resolves at
> **19 April 2027**, not the 20th. Do not re-apply this block; `UI_UX.md` §8.3 and
> ADR-0002 now carry the corrected version. The error survived a reconciliation whose
> entire purpose was catching it, which is worth knowing about this document.

---

## Item 3 — Stale "please fix" instruction

**Problem:** `DETERMINISTIC_RULES_SPEC.md` §4.2 contains a note telling the reader
to correct the final-year window in `..._UI_UX.md` §7.2 (the 366-day error). That
correction has already been applied. The instruction is now stale and, worse,
implies an error that is no longer present.

**Change** — `docs/architecture/DETERMINISTIC_RULES_SPEC.md` §4.2, replace the
"Correction to an existing document" callout with:

> The final-year window is 365 days: `[application_date − 1y + 1d, application_date]`.
> (`..._UI_UX.md` §7.2 was corrected to `16 April 2026 – 15 April 2027` on
> 2026-07-23; earlier drafts showed a 366-day window.)

Keep the historical note — it explains the boundary — but stop asking for an
action that is done.

---

## Item 4 — Are the two AI explanation features in scope?

**Problem:** MVP Scope §9 lists `GuidanceExplainer` and `IssueSummariser` as
included capabilities; the Roadmap lists them as M9 optional and first-to-cut.

**Resolution (owner decision, 2026-07-24):** Roadmap wins. Both are **optional,
post-plan-of-record, first-to-cut.** The deterministic guidance *registry* and
rule-to-source links stay in scope; only the AI-generated explanation and issue
summaries are optional.

**Changes:**

- `docs/product/MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md` §9 — move `GuidanceExplainer`
  and `IssueSummariser` out of the included list into a new subsection:
  > **Optional AI capabilities (not in the plan of record).**
  > `GuidanceExplainer` and `IssueSummariser` are deferred to M9 and are the first
  > features cut under time pressure. The MVP's guidance value comes from the
  > deterministic registry and rule-to-source provenance, which remain in scope.
  > Deterministic templates cover all core explanation needs.
- `docs/product/MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md` §10 (Out of Scope) — no
  change; these are deferred, not excluded.

---

## Item 5 — Config references reviewers that don't exist

**Problem:** Setup/config references two reviewer agents that were never created
(`contract-conformance-reviewer`, `tenant-isolation-reviewer`). Any automated step
invoking them fails.

**Resolution:** These were deliberately not built (see `.claude/README.md`,
"Deliberately not built"). Remove every reference so nothing tries to call them.

**Changes:**

- Search the repo for both names and remove or rewrite each call site:
  ```
  grep -rn "contract-conformance-reviewer\|tenant-isolation-reviewer" .
  ```
- Anywhere a workflow or skill lists reviewers to run, replace with the four that
  exist: `trust-model-reviewer`, `rules-conformance-reviewer`,
  `accessibility-reviewer`, `security-reviewer`.
- Contract conformance is a CI check (OpenAPI drift), not an agent — confirm the
  drift check exists in the CI workflow and delete any agent-based stand-in.

---

## Item 6 — `.claude/README.md` describes things that aren't there

**Problem:** The config README describes settings and files that don't match the
actual `.claude/` contents.

**Resolution:** Regenerate the README from the real directory. Do not describe
aspirational structure.

**Change** — replace `.claude/README.md`'s file-tree and settings sections with
the actual output of:

```
find .claude -type f | sort
```

and the actual keys present in `.claude/settings.json`. Every file listed must
exist; every hook wired in `settings.json` must be present on disk. If
`format-and-vet.sh` is still referenced but not yet ported, either add it or
remove its wiring — do not leave a wired hook with no file (see Item 9).

---

## Item 7 — "Stale" mislabelled as a status  *(ADR-0001)*

**Problem:** MVP Scope §6 and at least one other doc list **Stale** in the same
bulleted list as `Supported`, `Incomplete`, etc. This contradicts the project's
own invariant (Domain Model §3.5, CLAUDE.md §2.4): **conclusion and currency are
orthogonal.** `Stale` is a currency, not a conclusion. A result is, for example,
`SUPPORTED` *and* `STALE` at once — it cannot be `STALE` *instead of* a
conclusion.

**Resolution:** Separate the two axes everywhere they are listed together.

**Change** — `docs/product/MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md` §6, replace the
single list with two:

```markdown
Each supported requirement has a **conclusion** (one of):

- Supported
- Incomplete
- Inconsistent
- Near threshold
- Requires judgement
- Professional review recommended
- Not currently satisfied
- Not yet assessed

…and a **currency**, tracked separately:

- Current
- Stale
- Superseded
- Provisional

A result carries both. `Supported` + `Stale` is valid and means: this was
supported under the previous inputs, which have since changed; recalculate.
```

Audit for the same error elsewhere:

```
grep -rn "Stale" docs/ | grep -iE "supported|incomplete|inconsistent"
```

Fix any other list that mixes the axes. See ADR-0001.

---

## Item 8 — `route.standard_section_6_1` has no rule

**Problem:** The requirement key `route.standard_section_6_1` appears in the
Domain Model's requirement list but `DETERMINISTIC_RULES_SPEC.md` defines no rule
for it.

**Resolution (owner decision, 2026-07-24):** Define a real rule. It is the
composite guard that confirms the case is a standard, single-applicant Section
6(1) naturalisation — the natural home for the two "stop" conditions (spouse
route, may-already-be-British) that currently have no clean rule owner.

**Change** — add to `docs/architecture/DETERMINISTIC_RULES_SPEC.md` §7, after
§7.2:

> ### 7.2b `route.standard_section_6_1`
>
> **[PRODUCT]** Composite guard confirming the case fits the one supported route:
> standard five-year Section 6(1), single applicant, not the spouse/civil-partner
> route, and not a possible existing British citizen. This rule is where
> onboarding "stop" conditions become an assessment conclusion rather than being
> handled only in the UI.
>
> **Inputs:** `route_profile.married_to_british_citizen`,
> `route_profile.may_already_be_british`, and the conclusions of
> `route.adult_applicant` and `route.supported_status`.
>
> | Condition | Conclusion |
> |---|---|
> | not spouse-route, not may-be-British, adult + status both `SUPPORTED` | `SUPPORTED` |
> | `married_to_british_citizen = true` | `PROFESSIONAL_REVIEW_RECOMMENDED` — spouse route unsupported |
> | `may_already_be_british = true` | `REQUIRES_JUDGEMENT` — may not need naturalisation |
> | `route.adult_applicant` or `route.supported_status` not satisfied | `NOT_CURRENTLY_SATISFIED` |
> | route profile not confirmed | `NOT_YET_ASSESSED` |
>
> **Dependencies:** `ROUTE_PROFILE` (any current version),
> plus the two named upstream requirement results.
>
> Summary codes: `ROUTE_STANDARD_CONFIRMED`, `ROUTE_SPOUSE_UNSUPPORTED`,
> `ROUTE_MAY_BE_BRITISH`, `ROUTE_PREREQUISITES_UNMET`.

Then add it to the dependency matrix (§8) with the two upstream requirement
dependencies, and note in the matrix that this is the only requirement that
depends on other requirements' conclusions rather than on raw inputs.

---

## Item 9 — Field described but missing from the schema list

**Problem:** A data field is described in prose in one doc but absent from the
authoritative field list in the Domain Model.

**Resolution:** The Domain Model is authoritative for schema. Either add the
field to the relevant aggregate's field list or remove the prose reference.

**Change:** Identify the field, then reconcile toward the Domain Model:

```
# find the mismatch, then:
# - if the field is genuinely needed → add it to the aggregate in DOMAIN_MODEL_RFC.md
#   with type and invariants, and add a migration note
# - if it is vestigial → delete the prose reference
```

Do not leave a field that some code will expect and the schema does not define.
If uncertain which way to reconcile, the field does **not** exist until the
Domain Model says so.

---

## Item 10 — `test-rules` command undocumented

**Problem:** `.claude/hooks/rules-guard.sh` calls `just test-rules`, but no doc
defines that recipe.

**Resolution:** Define it. It is the property-based rule suite the hook and the
milestone gates both rely on.

**Changes:**

- `CLAUDE.md` §5 (Commands) — add:
  ```
  just test-rules     # Hypothesis property suite for deterministic rules (RULES_SPEC §10)
  ```
- `justfile` — add the recipe, scoped to the rule tests:
  ```
  test-rules:
      cd services/platform && uv run pytest tests/rules -m property -q
  ```
  (Adjust the path/marker to match the actual test layout once M3B exists. Until
  then the recipe should exist and exit 0 on an empty selection, so the hook does
  not error.)

---

## Application order

1. Items 1, 3, 5, 6, 10 — mechanical, no judgment. Do first.
2. Items 4, 8 — apply the owner decisions above.
3. Items 2, 7 — apply with their ADRs (next section).
4. Item 9 — reconcile toward the Domain Model.

After applying, re-run the audit greps in items 5 and 7 to confirm zero
remaining hits, and confirm every hook in `settings.json` has a file on disk.
