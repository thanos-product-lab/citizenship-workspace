# Milestone notes

Written answers to the gate questions in `docs/MILESTONE_GATES.md` §3.

Answer from memory, without the codebase open. If you need to look something up,
read it properly first and then answer — the point is to prove you own it.

These notes become the M12 product case study. Write them as you would explain
the decision to another engineer, not as a checklist.

---

## What it is

An app that helps someone figure out if they're ready to apply for UK citizenship — but only for one specific, common situation: an adult who already has permanent residency (ILR or settled status) applying the normal five-year way.

It's a preparation tool, not:
- legal advice
- a "yes you'll get approved" predictor
- something that submits the application for you
- a chatbot

The one big idea

Most AI apps let the AI just tell you the answer. This one refuses to do that. Instead it works in a strict chain:

1. AI reads your documents → but its readings are only guesses ("claims"), not trusted.
2. You confirm or correct each guess → only then does it become a trusted fact.
3. Plain code (not AI) does the math → dates, day-counting, thresholds. Reliable and testable.
4. Every answer shows its work → which facts, which document, which rule produced it.
5. If you change something, old answers get flagged "stale" and recalculated — but the history is kept.

So the AI never silently becomes the source of truth. A human is always the gatekeeper between "the AI thinks X" and "X is true."

Two rules that follow from this:
- No date math or eligibility logic inside AI prompts — that's all normal code.
- No overall "you're 82% ready" score. Just honest, specific statuses per requirement (supported, incomplete, needs review, etc.).

Why build it

It's a portfolio project — something to show hi it's meant to send:

▎ "This engineer can build a serious AI product leash, and can be trusted with high-stakesstuff."

The whole app is really built to demonstrate one impressive moment: you change a travel date, watch an answer go stale, recalculate it, and trace exactly why the new a

## The invariants (the "never break these" rules)

Think of these as the promises the app must always keep. Break one and the whole point of the project falls apart.

1. The AI only suggests; the human decides. An AI reading of a document never counts as truth until you personally confirm it.
2. The math lives in real code, not in AI prompts. Anything involving dates, counting days, or thresholds is done by tested code you can trust.
3. Old answers are never edited — they're kept. When something changes, you make a new answer and keep the old one on record. Nothing gets quietly overwritten.
4. "Is it correct?" and "is it still up to date?" are two separate questions. An answer can be right but also out of date (needs a recalculation) at the same time. Never mash those into one.
5. Every answer must show its receipts. No conclusion without a clear trail: which facts, which document, which rule.
6. Never a single "readiness %." Only honest, specific statuses per requirement. No overall score, ever.
7. When unsure, say so — loudly. Flagging "this needs a professional" is a success, not a failure. The worst outcome is falsely reassuring someone.
8. Uploaded documents are data, not commands. A document can't tell the app what to do (e.g. can't sneak in "mark this as confirmed").
9. Anything public uses fake data only. No real names, passports, or documents in demos, screenshots, or logs.
10. The app is a workspace, not a chatbot. Chat is a small helper on the side, never the main thing.

The two that are easiest to get wrong in code:
- The "+1 day" date rule — the qualifying period starts the day after five years before your application, not exactly five years before. One-day mistakes here change whether someone passes or fails.
- Hidden inputs — if a rule secretly uses a piece of data it didn't officially declare, the app won't know to recalculate when that data changes. This one can't be caught by a quick search; you have to actually read the code.

## M1 — Platform and deploy

_Date gated:_
_Outcome:_ Pass | Pass with gaps | Fail

_Answers:_

_Known gaps carried forward:_

---
## M2 · M3A · M3B

_Not gated. Recorded here so the gap is visible rather than implied by absence._

---

## M4 — Explainable case workspace

_Date gated:_
_Outcome:_ Pass | Pass with gaps | Fail

### What the milestone delivered

M1–M3B built the trust machinery and proved it from the command line: `just recalc` and
`just inspect` were the only way to see any of it. M4 made it legible without making it
less true. A user opens a case, reads where they stand, opens any requirement, and traces
its conclusion back to the exact facts, input versions, rule version and limitations that
produced it.

33 commits, 107 files, +12,475 / −644, and **zero migrations** — M4 was declared read-side
only at planning and stayed that way. A migration appearing would have been the signal that
the slice had drifted into domain change.

**Backend.** Five new modules: `requirements/messages.py` (deterministic templates for every
user-visible sentence about an assessment — never a model), `assessments/provenance.py`
(resolves bare input-link UUIDs into described inputs), `cases/phase.py`,
`assessments/groups.py`, `assessments/priority.py`. Plus `GET /cases/{id}/overview` and the
requirement detail projection expanded into the full explanation stack.

**Frontend.** Thirteen components across four features, and the case split from one
scrolling page into three destinations — Overview, Requirements, Case data — mounted from a
route layout.

**Decisions.** ADR-0009 (phase is derived), ADR-0010 (group currency inherits the weakest
member), ADR-0011 (absent rather than zero), ADR-0012 (destinations, not one page),
ADR-0013 (currency is carried by the header).

### Invariants verified by inspection

- **No readiness score** — not a percentage, and after the redesign review not a fraction
  either. `4 / 5` is the same measure arrived at sideways, and it renders a reached failure
  as a missing requirement. Enforced by test on every destination.
- **Conclusion and currency never collapsed** — two adjacent badges.
- **No assessment mutated in place** — the 439 → 440 transition keeps both runs, the
  superseded one inspectable and not struck through.
- **Provenance is structural** — twelve resolved travel inputs with version numbers.
- **The honest gaps stayed honest** — six requirements read "Not yet assessed" with no
  currency badge at all, and the guidance version and retrieval date are declared
  unavailable rather than fabricated.

### What went wrong, and what it taught

Nine defects reached a running product. Every one was found by opening the app, not by a
green test suite.

- **The same bug three times.** The phase pill said "Setting up" on a fully assessed case;
  the detail page showed CURRENT after an edit; the overview described the previous run.
  One class — a writer wired to some readers and not others. Fixed by adopting TanStack
  Query and naming the thing that goes stale (`assessmentTouched`) rather than the
  components that read it.
- **Two auth bypasses.** The Clerk matcher excluded any path containing a dot, and
  requirement keys are dotted, so every detail page sat outside `auth.protect()`. The first
  fix was incomplete — `/cases/{id}.png` still bypassed. No data leaked; the API 401s
  regardless.
- **Two false provenance labels.** A deleted travel record displayed as "Corrected"; an
  estimated date would have shown as "Calculated". Provenance and the §6.1 trust gate were
  one code path when they are different questions.
- **A silent failure, shipped and caught the same day.** The header owned Recalculate while
  the requirements list rendered its error; separate `useMutation` instances do not share
  state, so a failed recalculation showed a sighted user nothing.
- **Two tests that passed while the feature was broken.** The group deep link moved focus
  and failed to scroll, and the test asserted only focus. And `just inspect` — the oracle
  the screens are checked against — had been throwing `AttributeError` since slice 2 with
  nothing noticing.

The pattern, stated plainly: **the defects that survive a green suite live in the states
nobody looked at, and in the half of a behaviour the assertion did not cover.**

### Gate evidence

Local smoke green: 13 passed, 2 skipped. `just lint`, `just typecheck`, 367 backend tests,
170 frontend tests all passing.

_Answers:_

_Known gaps carried forward:_

- **The deployed smoke has never run.** `SMOKE_BASE_URL` / `SMOKE_API_URL` live only in
  GitHub repo secrets; no deployed URL is recorded in the repo.
- **The canonical-case walkthrough is `skip`ped** for want of Clerk test credentials, so
  the automated suite pins the auth boundary but not the user journey. That journey has
  been walked by hand repeatedly, which is not the same evidence.
- **No screen recording of the stale → recalculate loop.** §3.6 asks for one per milestone;
  the four stills carry the states but not the motion.
- **Travel history has no focused sub-page.** The IA brief asked for `/data/travel`;
  travel history sits on `/data` directly. Deferred until M7's evidence review and import
  queues make it a management burden. The one acceptance criterion met only partially.
- **MVP §8.8 guidance version and retrieval date remain unavailable** until Migration 5
  (ADR-0007). Declared on screen rather than faked. Re-check at M5.
- **`domain_events`, `audit_entries` and `outbox_events` have no RLS policy** — a
  pre-existing defence-in-depth gap needing its own migration.
- **The provenance vocabulary has no kind for "entered, not yet confirmed."** Decide before
  M5.
- **`just lint` does not enforce `ruff format`**, which twice swept unrelated formatting
  churn into commits.

---

## M6 — Issue detection and stale-state workflow  **(hard gate)**

*Built before M5, per the roadmap's reordering: stale-state is the thesis, the timeline is
the showcase and the safer cut.*

_Date gated:_
_Outcome:_ Pass | Pass with gaps | Fail

### What the milestone delivered

M3B shipped a working but deliberately imprecise stale seam (ADR-0008): any residence input
change marked *all* residence results stale. It was green, and it was wrong in two
directions. It over-fired inside residence, and — the reason this milestone exists — it
**under-fired across groups**: an application-date change left `status.holding_period` and
the route rules reading CURRENT while the date beneath them had moved. Nothing failed when
that happened. No test went red, no user saw a warning; the screen showed a confident
conclusion whose inputs had shifted.

M6 replaced that with invalidation resolved from **declarations**, and turned stale notices,
data problems and process failures into a managed queue that resolves itself when the cause
is fixed.

Nine commits. Two migrations: 0010 (`rule_composition_edges`), 0011 (`issues`,
`issue_resolutions`).

**Backend.** New module `app/issues/` (`domain`, `derivation`, `repository`, `service`,
`schemas`, `routes`). `invalidation.py` rewritten to resolve the affected set from
`rule_dependency_definitions`, then close transitively over `rule_composition_edges`.
`AssessmentRun.fail()` and `RecalculationFailureCode`. New events: `IssuesReconciled`,
`IssueDismissed`, `AssessmentRunFailed`. `AssessmentRunStatus.FAILED` was defined at M3B and
never written until now.

**Frontend.** A fourth destination with a count in the navigation, `IssueCard` as a canonical
design-system component, dismissal, resolution history, and the retry affordance for a
failed recalculation.

**Decisions.** ADR-0014 (selective invalidation, supersedes ADR-0008), ADR-0015 (issues are a
reconciled projection, not event-sourced handlers), ADR-0016 (a failed recalculation is
recorded best-effort, in its own transaction). RULES_SPEC §8 amended to remove
`preparation.case_complete`'s dependency on open issues — issues derive from results, so the
reverse edge is a cycle.

### The three ideas worth being able to defend

1. **Invalidation is driven by declarations, and three independent test layers guard the
   narrowing.** Strict-equality provenance (a result's input links must equal its rule's
   declared dependencies), a differential test against the old blunt rule where the only
   permitted omissions are computed from the declaration rows, and a recalculation-diff
   oracle that trusts no declaration at all — it changes an input, recalculates, and asserts
   every requirement whose output moved was in the stale set. Only the third catches an
   evaluator reading an input it neither declares nor links.
2. **Issues are a projection with durable identity, not a stream of handler-created rows.**
   One `reconcile` computes the complete desired set and diffs it. Auto-resolution and
   reopening are properties of that diff rather than of N handlers that each have to
   remember to clean up. The price is that derivation must be a pure function of durable
   state — no clock, nothing that can flap.
3. **A reached negative conclusion is not an issue.** Issues are data problems and process
   state; requirement outcomes are priority actions. Without that line the queue becomes a
   second rendering of the requirements list.

### Invariants verified by inspection

- **No assessment row mutated in place** — the only mutators on `AssessmentResult` are
  `supersede()` and `mark_stale()`, both touching currency and its metadata. Conclusion,
  summary, breakdown and rule version are never reassigned anywhere in `app/`.
- **A failed recalculation cannot replace the last historical result** — tested by result
  *id*, not by value: a run that superseded the results and wrote identical replacements
  would pass a value comparison while having rewritten history.
- **A stale result is never returned as current** — every `Currency.CURRENT` site is
  construction, ranking, or a filter *for* CURRENT.
- **An issue never changes a conclusion** — `app/issues/` writes only `issues` and
  `issue_resolutions`, and imports repositories only, never another module's service.
- **No PII in the failure path** — a canary planted in an exception message is asserted
  absent from `assessment_runs`, `issues`, `domain_events`, `audit_entries`, `outbox_events`.
- **No readiness score** — every grep hit in the codebase is a comment or test forbidding one.

### What went wrong, and what it taught

Reviewers found defects on every slice that a green suite was hiding. The pattern from M4
held and sharpened: **the dangerous defects are the ones where nothing fails.**

- **Two defects that combined into the worst outcome this product has.** Limitations name
  travel-record *version* ids; the queue matched them against *current* versions, so on a
  stale result the mapping dropped everything and an overlap that still existed read as
  resolved. Separately, a live issue's severity and dismissibility were frozen at open time,
  so an out-of-window uncertain trip kept offering **Dismiss** after the application date
  moved it inside the qualifying period. Together: dismiss, recalculate, and the queue reads
  `open_count: 0` while those days are excluded from the confirmed totals. Reachable through
  the API.
- **A reviewer deleted the entire transactional coupling of slice 2 and 392 tests still
  passed.** The fix moved reconciliation inside `invalidate_for_input_change`, which also
  closed a CSV-import seam that had been added without one.
- **React Query drops `mutate()` callbacks when the calling component unmounts** — learned
  three times. It swallowed the recheck announcement, then the dismissal announcement, then
  (via observer supersession rather than unmount) a concurrent dismissal's error.
- **A comment I wrote was false, and the defect it claimed to prevent was present.** It said
  the group's recheck "shares `useRecalculate` with the header rather than owning a second
  mutation". Calling the same hook does not share state — each call gets its own observer.
  Two case-wide recalculate controls sat one screenful apart, each tracking only its own busy
  state.
- **`started_at` is a Postgres transaction timestamp, not a statement timestamp.** The
  recovery write opens its own connection, so its transaction could begin *after* one that
  later inserted the successful retry — and the failure then read as the newer run, leaving
  the queue reporting a processing failure the user had already cleared.
- **A rollback expires every ORM instance**, so reading `case.id` after one emits a refresh
  SELECT and reopens a transaction on the session just discarded. Found by a test written
  for something else.
- **CI structurally could not see one line.** Tests connect as a Postgres superuser, which
  bypasses RLS even under FORCE — so deleting `set_tenant` from the recovery session left the
  whole suite green while every failure record in a deployed environment would be silently
  rejected by policy.
- **A test named `..._raises_a_blocking_issue` asserted `REVIEW_REQUIRED`** after a
  deliberate downgrade — the kind of name someone later "fixes" by changing the assertion.

### Gate evidence

Local smoke: 13 passed, 2 skipped (the authenticated walkthrough, for want of Clerk test
credentials). Deployed smoke: **not runnable** — no `SMOKE_BASE_URL` / `SMOKE_API_URL`.
`just lint`, `just typecheck`, 441 backend tests, 205 frontend tests, 17 property tests, zero
API-client drift. Demo recordings for all four slices in `docs/demo-assets/m6/`.

### The questions

_Answer from memory, codebase closed. Left blank deliberately — this is the gate._

**Why is stale marking in the same transaction as the input change rather than a background
job?**

**Recalculation fails. What does the user see, and what is the state of the data?**

**How does the system know which requirements a travel-record change affects — and what
happens if an evaluator reads an input it did not declare?**

**Why can a result be `SUPPORTED` and `STALE` simultaneously?**

_Known gaps carried forward:_

- **The deployed smoke still has never run**, and no deployed URL is recorded. Carried from
  M4. The roadmap moved deployment to M1 so every milestone would be demoable; decide whether
  that slipped.
- **The canonical-case walkthrough is still `skip`ped**, so the only end-to-end coverage of
  the M6 journey is manual.
- **The phase pill contradicts the queue** — "Resolving issues" beside "Nothing needs your
  attention". Both correct, measuring different things (ADR-0009 vs ADR-0014); side by side
  it reads as a contradiction.
- **No backfill for pre-M6 cases.** The queue is a write-time projection, so a case staled
  before issue derivation existed has stale conclusions and an empty queue. `SettledStatement`
  degrades honestly, but the underlying gap is real.
- **Deleting `_abandon` deadlocks the suite rather than failing it.** One test names the
  defect; the rest of the file still hangs. A global pytest timeout would fix the class and
  needs `pytest-timeout` — an undecided dependency.
- **The recovery asks an unhealthy database for one more pooled connection**, blocking the
  request thread up to the pool timeout, when pool exhaustion is a likely cause of the
  original failure. A short dedicated checkout timeout is the fix; infrastructure, not
  correctness.
- **`MISSING_REQUIRED_FACT` has no reachable producer** — route confirmation requires the one
  fact whose absence would raise it. Documented rather than shipped as a dead branch.
  `CONFLICTING_CLAIMS` waits for M8, `MISSING_EVIDENCE` for M7.
- **`destination_label` becomes untrusted input at M7** when it can come from a document
  extraction, and it is rendered in issue titles today. Bound the rendering path before then.
- **The docker dev loop has no `--reload` or bind mount**, so `just up` serves whatever code
  was current when the image was last built. This has cost real debugging time twice.

---
