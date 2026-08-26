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

## M5 — Timeline and application-date simulation

*Built after M6, per the roadmap's reordering. In progress; this section grows per slice.*

_Date gated:_
_Outcome:_ Pass | Pass with gaps | Fail

### Slice 1 — the RLS test harness

M5 adds no tables, which made it the cheapest moment to retrofit the harness the RLS
policies had been living without — and it had to exist before M7 adds evidence tables and
private storage.

The framing that started the slice was half wrong, and worth correcting because the wrong
half is reassuring. RLS *was* verified: `set_tenant` issues `SET ROLE app_rls`, switching
into a non-superuser role drops the owner's bypass, and `tests/cases/test_rls.py` had four
passing isolation tests. Two things were not verified. Six of the thirteen case-scoped
tables had no isolation test at all — `case_memberships`, the three assessment tables,
`issues`, `issue_resolutions` — their policies asserted only by the migration that wrote
them. And no test could see a code path that *forgets* `set_tenant`, because the login role
is a superuser (ADR-0006 R1). That second one is the M6 bug.

Four commits. One migration: 0012 (catalog grants). No application code changed.

**New suite, `tests/security/`.** `test_rls_matrix.py` covers all thirteen tables both ways
a policy can be wrong — failing to hide (`USING`) and failing to reject (`WITH CHECK`).
The write probe copies a real row into a temp table, gives it a fresh id, and has the
tenant role insert it back, so it needs no per-table row builder and cannot drift from the
schema. `test_rls_coverage.py` derives the protected set from the schema — reachable from
`cases` by foreign key, or carrying a `case_id` — rather than from a list, and asserts
ENABLE, FORCE and a policy on each. `test_tenant_wiring.py` walks the FastAPI dependency
graph and requires `get_tenant_session` under every `{case_id}` route.

**The non-superuser connection.** `app_test_login` (LOGIN, NOSUPERUSER, `app_rls`'s grants)
is provisioned by a session fixture and used by a second engine. Test-only: nothing in
`docker-compose.yml`, `ci.yml`, `railway.json` or `app/core/config.py` moved, and the app
still connects as the owner. `test_the_recovery_enters_the_rls_tenant_context` now runs the
recovery on that connection instead of hand-building `SET ROLE app_rls` in the test body —
the old version simulated the enforcement it was checking, so deleting the test's own setup
line would have silently stopped it testing anything.

### What went wrong, and what it taught

- **The harness found a real defect on its first end-to-end request, and it is not small.**
  `set_tenant` binds role and tenant at *session* scope, deliberately, because the unit of
  work commits mid-request and `SET LOCAL` would not survive that (ADR-0006, deviating from
  ADR-0005). But SQLAlchemy releases the connection when a session's transaction ends, and
  `app/core/db.py` resets role and tenant on checkin — so the statement after a commit runs
  with neither:

  ```
  set_tenant(session, "user_a")   ->  (app_rls, 'user_a')
  session.commit()                ->  connection returns to the pool, reset fires
  session.execute(...)            ->  (app_test_login, '')
  ```

  The security review found the blast radius is eleven call sites across six modules —
  every state-mutating endpoint in the product. Six of them raise `InvalidRequestError`
  from a `session.refresh` after the commit, which is loud.

  **The seventh does not, and it is the one that matters.**
  `_run_trusted_assessment` commits, then the route builds its response from
  `list_requirements` (`app/assessments/service.py:160`), which queries afterwards and
  tenantless. `POST /assessments/recalculate` therefore returns **HTTP 200** with
  `result_count: 9` and every requirement reading `NOT_YET_ASSESSED`, currency `null` —
  while the rows it just wrote say `SUPPORTED` / `CURRENT`, as the next `GET /requirements`
  confirms. A silent wrong answer on the assessment path, on the one endpoint whose job is
  to report what the rules concluded, and invisible on the owner connection where the same
  call returns the correct mix. The first draft of these notes said "the very first command
  in the product fails", which reads as a startup-shaped bug you would notice in seconds.
  This is not that.

  Carried as two `xfail(strict=True)` tests — the raising half and the silent half
  separately, because a fix that only restored the refreshes would leave the second one
  green and wrong — and then **fixed in slice 1b** (see below) rather than deferred, because
  it blocked M7 rather than merely wanting its own change: M7 is the first surface where a
  forgotten tenant is a document leak rather than a row leak, and the control that catches a
  forgotten tenant is ADR-0006 R1 Option A, which this defect made un-adoptable.

- **ADR-0006 R5 is the same defect through a different door, and should be merged into it.**
  R5 records that a pre-first-commit `ROLLBACK` reverts the non-LOCAL role and GUC —
  verified on a `NullPool` engine: `('app_rls', 'user_a')` before, `('citizenship', None)`
  after. Its blast-radius claim still holds (no handler re-queries after such a rollback),
  so it stays latent. But R5 and the commit case are one root cause — tenant state has
  connection and transaction lifetime while being recorded at session scope — and the
  `after_begin` fix closes both. The ADR files them as separate risks; they are one.

- **`ALTER DEFAULT PRIVILEGES` is retroactive in the direction nobody checks.** Migration
  0004 granted `app_rls` full DML on every table the owner creates *after* it, so the
  catalog tables in 0007 and 0010 were born writable and their explicit `GRANT SELECT`
  granted nothing they did not already have — a no-op sitting beside a comment reading
  "SELECT for the app role". The request role could rewrite `rule_versions`, which is what
  makes a past conclusion reproducible. Migration 0012 revokes it.

- **And the same table list missed `alembic_version`,** which 0004 also granted full DML
  and which every request role could therefore use to rewrite the migration head. It
  escaped 0012 *and* the new coverage test for one shared reason: both derived their
  universe from `Base.metadata`, and it has no ORM model. Migration 0013 revokes it, and
  the coverage test now reads `pg_class`, so the next table Postgres knows about and Python
  does not has to be classified rather than skipped. A derived rule is only as wide as
  what it derives from.

- **A rejection test needs a positive control.** All thirteen write-rejection tests would
  pass against a `WITH CHECK (false)` policy that denies every write to everyone — the
  distinction being drawn is *whose* write is refused, and only one side of it was
  asserted. The same probe row is now offered again as the row's own owner, and the policy
  must not be what stops it. Six of the thirteen hit a unique constraint instead, which is
  fine: the assertion is only that the refusal is not the policy's.

- **A test-only login role is the one thing a test run leaves behind.** The first version
  created `app_test_login` with a fixed password and no teardown, against whatever
  `DATABASE_URL` resolved to. The `TRUNCATE` teardown and the Alembic upgrade would already
  be catastrophic against a shared database, but both are loud; a permanent
  password-authenticated role with schema-wide DML is silent. It now refuses any non-local
  host, generates the password per session (`CREATE ROLE ... PASSWORD` is not redacted by
  `log_statement`), and drops the role afterwards.

- **A dropped policy is not the mutation to test with.** Postgres reads a table with RLS
  enabled and no policy as deny-all, so dropping one fails closed and breaks the feature
  rather than leaking. `DISABLE ROW LEVEL SECURITY` is the mutation that models the real
  regression.

- **`FORCE` is invisible to behavioural tests.** Policies apply to a non-owner role whether
  or not a table is forced, so `NO FORCE` leaves every isolation test green. FORCE is what
  applies policies to the *owner* — the role a forgotten `set_tenant` runs as. Only catalog
  introspection can see it, which is why the two files exist and why neither covers the
  other.

- **A route-graph scan finds nothing if it does not recurse.** `include_router` does not
  splice handlers into `app.routes` on FastAPI 0.139; it appends a wrapper holding the
  original router. The first version of `test_tenant_wiring.py` scanned one level, found
  ten wrappers and zero endpoints, and passed. Every "assert the bad set is empty" test in
  that file now has a coverage guard beside it.

### Gate evidence — slice 1

Six mutations, each restored after:

| # | Mutation | Result |
|---|---|---|
| 1 | `ALTER TABLE issues DISABLE ROW LEVEL SECURITY` | 4 reds, incl. *"issues leaked rows to another tenant"* and *"readable without a tenant on a non-superuser connection"* |
| 2 | `ALTER TABLE issues NO FORCE ROW LEVEL SECURITY` | 1 red — *"case-scoped tables without FORCE"*. Invisible to every behavioural test |
| 3 | `DROP POLICY issue_resolutions_tenant` | red (fails closed: the arrangement can no longer write) |
| 4 | `GRANT UPDATE ON rule_versions TO app_rls` | 1 red — *"app_rls can \['UPDATE'\] on rule_versions"* |
| 5 | delete `set_tenant` from `_record_failed_run` | 1 red — `assert 'COMPLETED' == 'FAILED'`; the policy refused the insert and the recovery swallowed it |
| 6 | add `evidence_items(id, case_id → cases)` with no policy — the M7 shape, created in raw SQL with no ORM model | 4 reds, with no test written for the table |
| 7 | `GRANT UPDATE ON alembic_version TO app_rls` | 1 red (migration 0013) |

Mutation 6 is the one the slice exists for: a table added in a later milestone is covered
the moment its migration runs, not when someone remembers to write a test. **That claim was
only half true as first written**, and the review caught it. Coverage was structural —
enabled, forced, has *a* policy — which cannot tell a correct policy from
`FOR SELECT USING (true)`, and the behavioural matrix that could parametrised over a
hand-maintained tuple with nothing tying the two together.
`test_the_behavioural_suite_covers_every_derived_case_scoped_table` now asserts them equal,
so a new table is forced into the matrix, and from there into `seeded_case`, because
`_assert_populated` fails on a table the arrangement never reaches. The derivation also
moved off `Base.metadata` onto `pg_constraint` and `information_schema`, so the mutation
above holds even for a table created in raw SQL with no ORM model behind it — which is the
form the `alembic_version` miss took. The claim is true now, and four tests carry it.

`just lint`, `just typecheck`, 506 backend tests + 2 xfailed, 205 frontend tests,
zero API-client drift, migrations 0012 and 0013 applied.

### Slice 1b — making the tenant survive its own transaction

The defect slice 1 found, fixed. **ADR-0017.**

The tenant now lives on `Session.info`, and an `after_begin` listener re-applies role and
GUC whenever the session opens a transaction — which includes the autobegin after every
commit and every rollback. Both settings became `is_local=True` in a single round trip,
because local is the right scope once something re-arms them per transaction: they unwind on
their own and no connection can carry a tenant anywhere. `clear_tenant` exists for the one
caller that must act as the owner on a session that has been in a tenant context.

Registered on the `Session` class rather than one sessionmaker, so it covers the request
session, the recalculation-failure recovery's own session, the CLI scripts and the seed —
anything that calls `set_tenant`, by construction rather than by remembering.

Both `xfail` markers flipped to `XPASS` and, being strict, turned red — which is what they
were for. They are now three ordinary regression tests: the raising half, the silent half,
and the mechanism itself including the rollback case that ADR-0006 filed separately as R5.

**R5 was the same bug.** ADR-0006 recorded it as a narrow latent risk — a pre-first-commit
rollback reverting the role and GUC, harmless because no handler re-queries afterwards — and
even named the fix ("establish the tenant on a connection checkout/begin event so it survives
rollbacks"). What it did not see is that the same root cause breaks on **commit** too, which
is not latent at all. Two entries, one defect.

**What the comment cost.** The docstring on `set_tenant` asserted that `is_local=False`
"keeps both set across the request's transaction boundaries (the unit of work commits
mid-request)". Non-LOCAL does survive a `COMMIT` — but not the pool checkin the commit
triggers, and the checkin listener was added by the same ADR. A sentence that is half right
about the mechanism is worse than no comment: it answers the question a reader would
otherwise ask.

Verified by mutation (neutering the listener turns all three tests red, only on the
non-superuser connection) and in the browser against the canonical case: create a case,
run an assessment, and read 439 days / near threshold, presence not satisfied at 16 April
2022, resolving date 25 April 2027.

_Known gaps carried forward:_

- **`test_tenant_wiring.py` keys on `{case_id}` appearing in the route path**, which is a
  URL convention rather than a property of the handler. M7 is where that breaks: a
  `GET /api/v1/evidence/{evidence_id}/download` is case-scoped and invisible to the check.
  Either assert no case-scoped aggregate is addressable outside a `{case_id}` prefix, or
  invert the check to an allowlist of routes that legitimately need no tenant.
- **`domain_events`, `audit_entries` and `outbox_events` still have no policy** — now an
  allowlist in `test_rls_coverage.py` rather than prose, so removing a name from the list
  is what closing the gap looks like. Carried from M2.
- **The non-superuser role is test-only.** Local, CI and Railway still connect as a
  superuser, and `rls.login_role_superuser` still logs at boot.
- **`just lint` still does not enforce `ruff format`**, and swept unrelated files into the
  working tree again during this slice; reverted by hand for the third time.

### Demo assets — M5

`docs/demo-assets/m5/`, captured on a fresh seed after the shell and copy revisions:

- `m5-date-simulation.gif` — 20 April moves the window and the total and does *not* fix
  presence; 25 April does. The middle frame is ADR-0002's whole argument.
- `m5-save-and-reassess.gif` — select then recalculate, the header and phase moving.
- `m5-timeline-table.png` — the Spain row: eleven days away, ten counted, and why.
- `m5-timeline-band.png` — the shape, with the anchor-covering trip drawn taller.

Each is described in `docs/demo-assets/README.md` in terms of what it is evidence *of*,
and the regeneration steps note that the timeline capture needs a case that has **not**
been moved to 25 April — after the move the Spain row reads 0 days and the picture tells
a different story than the M3B and M4 oracles it is meant to agree with.

---

## M7 — Evidence foundation

*In progress; this section grows per slice.*

_Date gated:_
_Outcome:_ Pass | Pass with gaps | Fail

### Slice 1 — private evidence storage

A document can be uploaded to a private bucket, listed, and opened through a 60-second
signed URL. No worker, no extraction, no AI.

**Two designs changed under review, both because a test or a guard refused the first
attempt.**

- **The reservation row became a signed token (ADR-0019).** The first shape wrote an
  `EvidenceItem` and an `EvidenceFile` at presign time so the storage key could be looked
  up on completion. It committed case-scoped rows with no domain event, which meant
  calling `session.commit()` directly — the only raw commit in `app/`, bypassing the one
  guard that makes "state written without an outbox row" structurally impossible. Rather
  than widen a hole in `UnitOfWork` in the milestone that finally builds the outbox
  *reader*, the key now travels through the client inside an HMAC token that binds it to
  the case, the media type and an expiry. Nothing is persisted until the bytes exist, so
  every column on both tables is NOT NULL and an abandoned upload leaves no row at all.
- **A flush ordering bug the RLS policy caught before any test did.** SQLAlchemy orders a
  flush from `relationship()` dependencies, not from raw FK columns, so `evidence_files`
  inserted before `evidence_items` and its policy — which predicates through its parent —
  correctly refused a row whose parent did not yet exist. The fix is the existing
  `session.flush()` convention from `residence.add_travel_record`. Worth recording because
  the policy behaved as a *correctness* check here, not only as a tenant boundary.

### What the harness caught, and what it missed

`test_rls_coverage` fired on the migration exactly as designed — its docstring has named
`evidence_items` as the test case since M5, and mutation 6 of that gate created this table
shape to prove it. That worked first time.

**The route check did not.** Both of its M7 weaknesses were found by mutation, and neither
was the one the M5 notes predicted:

1. **A handler can take a tenantless session and still pass.** The check looked for
   `get_tenant_session` anywhere in the dependency tree, and `require_case_access` puts
   one there for free. Switching the evidence content route to `Depends(get_db)` passed
   every assertion in the file, while leaving the handler's own queries outside RLS — on
   a superuser login role, that session sees every tenant. Now
   `test_no_handler_takes_a_session_that_skipped_the_tenant` checks the route's *direct*
   dependencies, where a handler's own `Depends(get_db)` appears.
2. **The prefix constraint's table→URL derivation was too naive to catch its own motivating
   case.** `evidence_items` yielded only `evidence-item`, so a real
   `GET /api/v1/evidence/{id}/content` — the exact URL the M5 notes named — slipped
   straight through. Candidates now include the first token of the table name.

The M5 note's own suggested fix (invert to an allowlist) was necessary and not sufficient.
Both holes sat *behind* it.

### What the reviewers found, and what it cost

Seven violations across two reviews, and **five of them were things a green suite was
hiding** — the M4/M5/M6 pattern again, sharper.

- **A retried upload logged the storage key, the filename and the checksum.** The
  `session.flush()` for the file row sits outside `UnitOfWork`, so the storage-key unique
  violation escaped as a raw `IntegrityError` → 500, and SQLAlchemy renders bound
  parameters into the message. Reachable by any client that loses the response to step 3
  and retries — no malice needed. Recording is now idempotent on the storage key, and
  `hide_parameters=True` on the engine closes the wider class.
- **The presigned PUT had no size ceiling.** `declared_size_bytes` is a client's claim and
  the real check ran *after* the bytes were in the bucket — verified against MinIO: a URL
  presigned for a 10-byte declaration accepted 40 MB with a 200, and the object stayed,
  with no row naming it. Now a presigned **POST** with `content-length-range` in the signed
  policy, so the store refuses the body. The ceiling moved from a promise to a control.
- **The route allowlist exempted the two routes that read and write `cases`.** Both already
  depend on `get_tenant_session`; the stated reason did not describe the code. An
  unnecessary exemption is worse than a stale one, because it absolves a future rewiring in
  silence — and `test_the_allowlist_names_only_routes_that_exist` asks about existence, not
  necessity. Twin guard added.
- **The `Uploaded` badge was invisible in dark mode: 1.99:1.** The dark blocks re-declare
  status and currency tokens but never provenance, and `EvidenceState` picked a provenance
  token. Measured in Chromium at 14px. The glyph is `currentColor`, so the non-colour
  signal failed too — the State column read as an empty cell, which on that screen means
  "no state". `ai_proposed` had the same defect at 2.67:1, pre-existing since M4.
- **The submit button dropped keyboard focus to `<body>` and announced nothing** for the
  length of an upload, and the retry button did the same. `headingRef` and `tabIndex={-1}`
  were both present in `EvidenceDestination` and `.focus()` was never called — the Issues
  pattern copied structurally and left unwired.
- **The first `<th scope="row">` in a `.cw-trips` table** inherited a rule written for
  column headers: 12px, subtle, `white-space: nowrap`. At 320px the document name rendered
  in a 428px box and clipped mid-word, and the row's most important content was the
  smallest type in it.

**Two of the fixes' own tests were wrong**, which is the part worth remembering:

- the storage-key guard test asserted `"cases/" not in body` against the *content*
  response — but a presigned GET **is** the object's address, so it names the key by
  construction. The assertion was over-strict on the one response where it could not hold;
  narrowed to the library and detail projections, where it does.
- the content-type test tampered with the multipart part header instead of the signed
  `Content-Type` **field**, got a 204, and would have read as "the policy does not work".
  The policy was fine; the test was aiming past it.

And one accessibility test **does not defend what it describes**: jsdom does not reproduce
the browser's blur-on-disable, so swapping `aria-disabled` back to `disabled` leaves the
focus assertion green. The attribute assertion is what actually catches it. Both are kept,
and the file says which is which — a test that looks like a guard and is not is the exact
thing this suite exists to stop.

### Gate evidence — slice 1

Ten mutations, each restored after:

| # | Mutation | Result |
|---|---|---|
| 1 | `DROP POLICY evidence_items_tenant` | 46 errors + 1 failure; fails closed — the arrangement can no longer write |
| 2 | content route takes `Depends(get_db)` | **green at first** → harness strengthened → now 1 red |
| 3 | content route moved to `/api/v1/evidence/{id}/content` | **green at first** → derivation fixed → now 1 red, naming the exact route |
| 5 | storage-key generator returns a fixed suffix | 1 red — *"two keys for the same item never collide"* |
| 6a | MinIO unreachable with `CW_EXPECT_MINIO=1` | 5 errors, not skips — the storage security assertions cannot silently vanish |
| 6b | the `minio`-marked file excluded from the run | 1 red — `test_storage_integration_tests_actually_ran` |
| 7 | `original_filename` interpolated into `Content-Disposition` | 6 red, incl. all three CRLF-injection cases |
| 8 | exempt a route from the tenant check that already passes it | 1 red, naming the route |
| 9 | drop `content-length-range` from the signed policy | 2 red — oversized and empty bodies both accepted |
| 10 | remove the idempotent lookup from `record_upload` | 2 red — a retried recording 500s |

`just lint`, `just typecheck`, **589 backend tests with MinIO live and zero skips**, 265
frontend tests, zero API-client drift, migration 0014 applied. Seven MinIO-backed security
assertions ran green against a live bucket: unsigned GET refused, URL expiry, deleted
object 404, signed content-type enforced, **oversized body refused with nothing written**,
**empty body refused**, and a single-line disposition from a CRLF filename.

Verified in Chrome against real MinIO, not only in tests: unsigned GET at the object's own
address → 403, signed → 200, TTL 60s, no `storage_key` in any document response, another
case's evidence id → 404 byte-identical to an unknown id, and zero rows in `domain_events`,
`audit_entries` or `outbox_events` containing a filename, a key or `.pdf`.

### Two CI-only failures

Both are recorded because neither was reproducible locally, and that is the point.

`ApplicationDateCard`'s "announces what the date does not fix" test failed on CI and
passed locally, five runs out of five, before and after. It is a real race and not an
infrastructure hiccup: the panel text comes from the preview, while the announcement is
set by an **effect keyed on that preview**, so `findByText` can resolve on the commit
before the effect has flushed and the live region is still empty. It was the only
live-region *text* assertion in the suite written without a `waitFor` — the two in
`IssuesDestination` assert presence, which cannot race — so it was the one that broke.

Worth recording because the diff that surfaced it changed one line in that file, an
import path, and nothing about its timing. A slower machine was the whole difference. The
lesson is the file's own: an assertion that reads state set by an effect has to wait for
it, and passing locally is not evidence that it does.

**Second: `bitnami/minio:latest` does not exist.** The new backend CI job could not pull
its MinIO image at all. Bitnami moved their catalogue to `bitnamilegacy/` during 2025 and
`bitnami/minio` now has **zero tags** — the image was chosen because it is the widely
copied GitHub Actions recipe for MinIO, and never checked against the registry.

The underlying reason that recipe exists is real: the official `minio/minio` image needs
`server /data` as a command, and a `services:` block cannot supply one. So MinIO is now an
explicit `docker run` step with a readiness loop we control, on the official image at a
**pinned** `RELEASE.*` tag. `docker-compose.yml` moved to the same pin: `latest` on both
sides looks like agreement and is not, since each resolves whenever it last pulled — a
storage behaviour could differ between a green local run and a red CI one with nothing in
the diff to explain it.

Verified by running a container with the exact workflow command and pointing the storage
suite at it — 39 passed — rather than by pushing and waiting.

### The deployment failure

The fail-closed added in response to the security review took Railway down: the API
crash-looped on `RuntimeError: UPLOAD_TOKEN_SECRET must be set outside local
development`, ten restarts, nothing else in the logs. The guard did exactly what it was
built to do.

**Three deploys were spent establishing a fact one log line already knew**, and that is
the more useful failure. The guard raised from the FastAPI lifespan, where
`merged_lifespan` recurses once per mounted router: ~100 traceback frames per crash, ten
crashes in the restart loop, and **824 of the 1001 log lines the platform retained were
`async with original_context(app)`**. The line naming the cause, and the
`app.configuration` line added specifically to answer "is it actually set?", were both
pushed out of the retained window.

Configuration is now validated in `create_app()`, at import: 44 lines instead of ~100,
zero nested frames, the diagnostic first so it survives any truncation, and the failure
lands before the health check has anything to poll. A guard nobody can read is a guard
that costs three deploys. The pre-deploy migration is unaffected — `migrations/env.py`
imports the domain modules, never `app.main`.

**The other defect is that the same commit did not update the deployment
docs.** A required environment variable was introduced and `docs/DEPLOYMENT.md` still
listed six. Adding a boot-blocking requirement without documenting it in the same change
is how a security control becomes an outage.

It also surfaced something larger, which the local-only verification could not:
**evidence upload cannot work on Railway at all yet.** There is no managed object storage
there, the storage settings default to a local MinIO, and `ensure_bucket()` deliberately
runs only under `local`/`docker`. So the deployed app boots, lists an empty library, and
fails on the first upload. M7 slice 1 is complete locally and **not deployable** until a
private S3-compatible bucket is provisioned — recorded here rather than discovered at the
milestone gate, which asks for "deployed environment still works, not just local".

_Known gaps carried forward:_

- **Evidence upload is not functional on Railway** until a private bucket exists and the
  `STORAGE_*` variables are set on both the API and the worker. Boots fine; uploads fail.
- **`AWAITING_CONFIRMATION` ships unreachable.** No producer until claims exist in M8. The
  UI must not offer it as a stage a document might enter.
- **Magic-byte validation is not in slice 1.** The declared media type is bound into the
  presigned PUT's signature, so a client cannot upload under a *different* label — but it
  can upload bytes that contradict the label it chose. Verification needs the content, so
  it belongs to the worker's `VALIDATING` state in slice 2.
- **An abandoned upload leaves an orphaned object** in the store with no row pointing at
  it. No sweeper yet; it is storage-side rather than case-scoped, which is the right way
  round.
- **`UPLOAD_TOKEN_SECRET` is unset everywhere.** Per-process signing key: correct for one
  API instance, silently wrong for several — the symptom is intermittent 422s that look
  like tampering. Now **refuses to boot** outside `local`/`docker`/`test`, and rejects a
  configured secret under 32 characters.
- **An orphaned object has no sweeper.** An upload whose bytes land but whose recording
  call never arrives leaves an object with no row pointing at it. Storage-side rather than
  case-scoped, which is the right way round, but slice 5 builds deletion on the assumption
  that `evidence_files` enumerates every object — so a bucket lifecycle expiry rule should
  land before it.
- **Sentry's default fetch breadcrumbs would capture the presigned URL** including its
  signature, which threat model §6.4 forbids. No Sentry SDK in the repo yet; the denylist
  requirement is recorded against `useUploadEvidence.ts` while the reasoning is fresh.
- **A `DELETION_PENDING` case still serves evidence reads and content URLs.** Writes are
  blocked, which is what matters now; the read guard belongs with slice 5.
- **`domain_events`, `audit_entries` and `outbox_events` still have no RLS policy** —
  carried from M2, and now more pressing: slice 2 builds the reader that consumes them.

### Slice 2 — the outbox reader, and tenant context outside a request

The outbox has a reader; a Celery task establishes an RLS tenant with no request around
it; an uploaded document's bytes are checked against the type it claimed.

**Deviation from the plan:** `EvidenceProcessingRun` came forward from slice 3, because
§4 requires the first worker task to be idempotent and the run table is where
`idempotency_key` lives. Slice 3 extends the same run into extraction rather than
inventing a second concept.

`EvidenceProcessingRun` also settled a question the plan left open: what a *successful*
validation leaves behind. `SUCCEEDED` maps back to `UPLOADED`, because in this slice
nothing reads a document's contents, so "stored" and "stored and checked" say the same
true thing to a user. Claiming more would be the reassurance the product exists to avoid.

### What went wrong, and what it taught

**Three defects found before review, all in the same shape: the code did something, and
the thing it did was nothing.**

- **The relay redelivered its entire backlog on every pass.** `autoflush=False`, so
  `published_at` had not reached the database before the next `SELECT ... FOR UPDATE`
  claimed the same rows again.
- **The tenant mark landed on the wrong object.** `tenant_scoped` applied *inside*
  `celery_app.task` stamps the plain function, which Celery then wraps in a `Task` the
  harness cannot see through. Decorator order is load-bearing.
- **A document could strand in `VALIDATING` forever.** `autoretry_for` re-raises when
  retries run out and the task simply ends — run still RUNNING, item still VALIDATING,
  nothing left that could move them, and the client polling every 1.5s for as long as the
  tab was open.

**And then the review found that the fix for the third one was unreachable**, which is
the finding worth keeping.

The idempotency short-circuit fired on *any* existing run for the key — including the
RUNNING one the same delivery had written seconds earlier. So the retry found its own
attempt, returned `already_done=True`, and the task succeeded having done nothing.
`request.retries` never advanced, the exhaustion branch never executed, `abandon_run` was
dead code in production, and the original defect was worse than diagnosed: **the retries
were not happening at all.** My test for it called `abandon_run` directly, so it was
green while the only path that would call it was unreachable. A RUNNING run under the same
key is this delivery's own attempt, not a duplicate; §16.2 allows "a new attempt record",
and that is what it now is.

**The task-tenant harness did not catch the mutation it advertised.** Its docstring said
`test_a_tenantless_task_session_sees_no_evidence_at_all` was "the mutation the gate runs —
delete `set_tenant` from `case_task` — expressed as a standing test". It was not: the test
opened its own session and never called `case_task` at all. The reviewer neutralised
`set_tenant` and all ten tests passed, along with the rest of the security suite. The
guardrail rested entirely on an attribute anyone could stamp on a task that never
established a tenant.

The fix needed a design change, not a test change: `case_task` hard-coded
`get_sessionmaker()`, so it could only ever run on the superuser connection where RLS is
inert. It now takes an injectable factory — production passes nothing — and the tests
drive the real wrapper on the non-superuser role. The mutation now kills two tests.

**Which surfaced a genuine correctness bug the superuser connection had been hiding.**
`resolve_evidence_owner` must run before any tenant exists, so RLS cannot police it — and
under a real non-superuser role it returned **zero rows**. Every document would have sat
at `UPLOADED` forever while the logs reported the evidence absent. The privilege is now
explicit: a `SECURITY DEFINER` function (migration 0017), one id in, three columns out,
`EXECUTE` granted to the application role alone, `search_path` pinned. Accidental
privilege became stated privilege, and ADR-0006 R1 is no longer blocked by this path.

Also removed: `resolve_case_owner`, dead on arrival — an ownership oracle taking any case
id with no user, no membership check and no tenant, exported from a module the *API*
imports, whose docstring claimed a uniqueness that `resolve_evidence_owner` also claimed.
Two functions each documented as the only one of their kind is how the second gets called
from a request path.

### Gate evidence — slice 2

| # | Mutation | Result |
|---|---|---|
| 1 | delete `set_tenant` from `case_task` | 2 red (was **0** before the harness was rebuilt) |
| 2 | short-circuit on any run, not only settled ones | 1 red — the retry does nothing |
| 3 | drop `evidence_file_id` from the dispatch kwargs | 1 red — kwargs shape |
| 4 | rename an event type without deciding its consumer | 1 red — `test_every_event_type_has_a_decision_recorded` |

`just lint`, `just typecheck`, **639 backend tests**, 273 frontend, zero API-client drift,
migrations 0015–0017 applied.

Verified against real infrastructure, twice — before and after the review fixes: beat
schedules, the relay dispatches, the worker resolves its own tenant from an evidence id
alone, a real PDF reaches `SUCCEEDED`/`UPLOADED` in two seconds, an executable labelled
`application/pdf` reaches `FAILED`/`UNSUPPORTED` with `CONTENT_DOES_NOT_MATCH_TYPE`, and
**the trace propagates** — `trace-abc-123` landed on its run, so browser → API → outbox →
worker now holds end to end.

_Known gaps carried forward:_

- **`domain_events`, `audit_entries` and `outbox_events` still have no RLS policy.**
  Carried since M2, and now load-bearing: the relay reads `outbox_events` with no tenant
  by design. It reads one table and forwards identifiers, which is what makes that
  survivable rather than correct.
- **The worker never checks whether its login role is a superuser.** `app/main.py` warns
  at API boot; the worker and beat processes do not, and they are now the processes where
  it matters most.
- **SSE is deferred** — ADR-0020. Polling is bounded by activity, and `UPLOADED` sits in
  neither the in-flight nor the terminal set because it means two different things.

## M7 slice 3 — deterministic extraction, processing runs, retry

A document now says what was read out of it. PyMuPDF reads the native text layer in the
worker, the reading is stored in Postgres, and the library shows page count, pages read and
character count. There is no model anywhere in this path — it decodes, it does not infer,
which is why the output is neither an `ExtractedClaim` nor a `FactVersion` but untrusted
material of exactly the same standing as the file it came from.

**The bound that mattered was not the one in the plan.** §7.5 specified a page cap, a memory
limit and a time limit. The page cap turned out to bound the wrong thing: it limits how much
text comes *out*, not what it costs to get. A ~6 KB PDF whose content stream nests Form
XObjects — each invoking the next twice — costs exponential time inside a single
`get_text()` call and produces two characters. Seconds at depth 20, an hour at depth 30, from
a genuine PDF three orders of magnitude under the upload limit that passes every check before
this one. Any authenticated user could hold a worker slot indefinitely. The fix is a
wall-clock deadline checked between pages, plus Celery's soft limit for the single page that
never returns; `SoftTimeLimitExceeded` derives from `Exception`, so it had to be re-raised
explicitly before the parser-failure handlers, which were otherwise reporting Celery's own
deadline to the user as a corrupt file.

**A three-page scan reported as "Read".** `character_count` was `len("\n".join(pages))`,
which counts the separators — three empty pages gave 2 characters, `has_text_layer` came out
true, and the user was told the text had been read from a document with no text in it. That
is a false reassurance produced by a string operation, and directive 7 makes it the most
important class of bug in the product. Counting page text and stripping whitespace fixed it;
migration 0018's consistency constraint then rejected every corrected multi-page scan, so
migration 0020 restates it against the content itself.

Findings that were green only because nothing tested them: the accessibility review found
that a retry refusal reverted the button and said nothing, that polling rewrote the state
cell every 1.5 seconds without a word reaching the live region, and that focus landed on
`<body>` when a successful retry unmounted the button under the user's finger. Writing the
completion-announcement test found a fourth I had introduced in the fix: a row first seen
mid-flight looked newly arrived at the moment it settled, so the one transition worth
announcing was the one that stayed silent.

`"Read"` became `"Text read"` in the same pass. Alone in a table cell it is a homograph — it
flips between "this was done" and an instruction depending on how it is read aloud.

**A false affordance the browser found and no test could have.** Retryability keyed on the
processing status, and `FAILED` covers two unlike things: a worker stopped by its own
resource bound, where the box may simply have been busy and asking again is reasonable, and
a password-protected document, which is encrypted every time you read it. Both were offered
"Read it again". Pressing it on the second spent a worker slot to reach the identical
failure — the same mistake this module already refuses for `UNSUPPORTED`, whose comment
reads "a button that cannot work is worse than no button". The domain already drew the line
(`RESOURCE_LIMIT` is documented as user-retryable, the rest are properties of the file); the
retry gate just never read it. Now one `may_retry` function serves both the command's guard
and the projection that draws the button, so the screen cannot offer what the command will
refuse.

### Gate evidence — slice 3

| # | Mutation | Result |
|---|---|---|
| 1 | remove the wall-clock deadline | 1 red — the nested-XObject fixture no longer returns |
| 2 | swallow `SoftTimeLimitExceeded` in `extract` | 1 red — reported as `UnreadableDocument` |
| 3 | `character_count = len("\n".join(pages))` | 1 red — the multi-page scan reads as `COMPLETED` |
| 4 | ignore `retry_count` in the attempt bound | 1 red — redelivery loops past `MAX_ATTEMPTS` |
| 5 | drop the `onSettled` focus arming | 2 red — focus falls to `<body>` |
| 6 | return instead of throwing `RetryRefusal` | 2 red — the refusal is silent |
| 7 | never announce a terminal transition | 1 red |
| 8 | narrow the retry lock to the pressed row | 1 red — a second press abandons the first |
| 9 | make every `FAILED` retryable regardless of code | 2 red — the password-protected button returns |

_Known gaps carried forward:_

- **320px reflow is unverified.** Chrome will not size a window below 606px wide, so the
  narrowest real check available here is 606px, which passes. The `th` selector was added to
  the reflow rule by inspection, not by seeing it.
- **Live polling cannot be verified through the automated browser.** The driven window is
  occluded, so `document.visibilityState` is `hidden` and TanStack Query suspends
  `refetchInterval` — correctly, and it looks exactly like a broken poll. Overriding the
  visibility API in page script showed the real behaviour: `Uploaded` → `No text found`
  without a reload, with the transition announced. Worth knowing before someone else spends
  an hour on the same false bug.
- **`ReadTookTooLong` is terminal by choice, not by evidence.** A document that exhausted
  the bound once will exhaust it again, and auto-retrying is three more chances to occupy a
  worker. The user can still ask for it deliberately, which is a decision to revisit if an
  honest slow document ever hits it.

## M7 slice 4a — evidence coverage: the trip link and the unevidenced trip

A document can now support a trip, and the assessment notices. Attaching a booking to a
travel record stales `residence.travel_consistency` and nothing else; a confirmed trip with
no document attached reports itself in the requirement detail and, once the case holds any
document at all, in the issue queue. The canonical case shows exactly two standing issues:
`NEAR_THRESHOLD` on the absence total, and one `MISSING_EVIDENCE` on trip 6 (Greece).

**Three specification divergences were settled before any code**, because each was a place
where the RFCs described a world M8 will build and M7 had to live in now.

The load-bearing one: RULES_SPEC §7.8 defined an unevidenced trip as one with no
`FactEvidenceLink`. That table hangs off `FactVersion`, so the spec made an M7 detection
depend on an M8 entity for no reason connected to what it measures. `EvidenceTravelLink`
(Domain §11.9) now joins `FactEvidenceLink` rather than waiting for it, and §7.8 asks about
"any available evidence link" so M8 widens the graph instead of rewriting the rule.

**The link points at the travel record, not the version** (ADR-0021). Editing a trip's dates
creates a new version; a version-scoped link would drop every attachment on every date
correction, and the rule would then report a newly unevidenced trip as though the user had
detached something. This is the opposite choice to `FactEvidenceLink`, and the difference is
not an inconsistency: a fact's *value* is the thing being evidenced, so a changed value
genuinely needs re-evidencing, while a trip's identity survives a date correction.

**A link is an assertion, not a verification.** Nothing reads an attached document to decide
whether it actually supports the trip. Matching a booking's dates against the trip's would
have been deterministic and would have looked like a check — a guess dressed as one, and a
support column that read as verification would be false reassurance of exactly the kind
directive 7 exists to prevent. `EvidenceLinkInput` carries two ids and nothing else, so the
narrow shape is the enforcement rather than a convention.

**The evidence fan-out is one requirement, deliberately.** Attaching a document must not
stale `residence.total_absences`: a user who deletes a booking has not changed how many days
they were absent, only how well supported their account of it is. Both directions are
tested, at the unit level and end to end.

**The `MISSING_EVIDENCE` suppression gate is a judgement call**, so it is stated rather than
buried. A case with twelve trips and nothing uploaded would have opened twelve identical
items, burying the one issue that needs a decision. The limitation is emitted either way and
the travel history shows every trip's support state, so nothing is hidden — what is
suppressed is the duplication of that into a queue whose value is that everything in it is
actionable. The gate turns on *uploading*, not *attaching*: keying on attachment would make
the first attach open issues for every other trip, which reads as being punished for
progress.

**ADR-0022: the first second rule version made ADR-0014's gap reachable.** Invalidation
resolves dependencies against the *currently active* rule version, so a v1-produced result
left CURRENT is one whose declared dependencies nobody is reading. v2 only adds a dependency,
so the hazard would not have fired this time — relying on that would be relying on an
accident of one change. The activation migration stales every result v1 produced, narrowing
the gap by construction; the proper fix (joining dependencies to
`AssessmentResult.rule_version_id`) stays at M9.

### Gate evidence — slice 4a

| # | Mutation | Result |
|---|---|---|
| 1 | `ALTER TABLE evidence_travel_links DISABLE ROW LEVEL SECURITY` | 3 red in the RLS matrix |
| 2 | attach stales via `TRAVEL_RECORD` instead of `EVIDENCE_SUPPORT` | 2 red — the totals restale too |
| 3 | count every trip as evidenced | 4 red |
| 4 | drop the `EVIDENCE_LINK` provenance links | 2 red |
| 5 | drop the confirmed-only filter | 1 red |
| 6 | remove the `MISSING_EVIDENCE` suppression gate | 6 red |
| 7 | make the issue non-dismissible | 1 red |
| 8 | offer in-flight documents for attaching | 1 red |
| 9 | strip the per-document accessible names | 2 red |
| 10 | make a failed detach silent again | 1 red |
| 11 | freeze the notice sequence counter | 1 red |
| 12 | unbind the attach error from the select | 1 red |

`just lint`, `just typecheck`, **720 backend tests**, 303 frontend, `just test-rules` green,
zero API-client drift, migrations 0021–0022 applied.

Verified in Chrome against real MinIO, Postgres and Redis: eleven trips show their document,
Greece shows "None attached", attaching announces and returns focus to the heading, and
**detaching stales `residence.travel_consistency` alone while the three absence figures stay
CURRENT** — conclusion `SUPPORTED`, currency `STALE`, the two axes visibly separate. The
stale sentence reads "The documents attached to your travel records changed after this was
worked out." Recalculating reopens the Greece issue.

### Two things the tests could not have found

**The seed's upload was broken against real MinIO.** `_upload_bytes` posts to the presigned
URL as a browser does, but dropped `Content-Type` from the signed field set as redundant
beside the file's own type. A presigned POST policy signs the field set, so the store
rejected everything with a bare 403. Invisible to the suite because the in-memory adapter
takes the other branch — only `just seed` against MinIO exercises the httpx path.

**`just seed` and `just api` had no storage credentials.** Compose supplies them to the
containers; the host recipes got nothing, and boto3 fails with `NoneType has no attribute
access_key`, which names nothing. Both recipes now carry the MinIO dev defaults.

### What the accessibility review found, and what it says about jsdom

Five gate failures, and the instructive thing is that four of them were invisible to the
test suite because jsdom does not model what a browser does.

- **A failed detach was completely silent.** The response's `error` was never destructured,
  so a screen-reader user pressed Remove, heard nothing, and the document was still there —
  indistinguishable from a dead button. The attach path already reported its refusals, so
  the asymmetry was an oversight rather than a design.
- **`disabled` on the focused submit button drops focus to `<body>`.** The success path
  recovered by chance, because closing the dialog re-focused the trigger; the *refusal*
  path did not, leaving the user outside the dialog and outside its Tab trap with an alert
  they could not reach. `globals.css` already wrote this rule down — "`aria-disabled` is
  used instead of `disabled` so focus is not dropped mid-operation" — and this dialog broke
  it. jsdom does not implement the behaviour, which is exactly why the suite was green.
- **The attach refusal was a floated banner, not bound to the select it was about.**
  Announced once and then gone: a user returning to the combo box heard only the options
  again, with nothing saying which choice had been refused.
- **A realistic document name broke reflow.** The upload form defaults the display name to
  the filename, so `Ryanair_booking_confirmation_ATH_20220414` is the ordinary case. A flex
  item's default `min-width: auto` refuses to shrink below its content's min-content width
  and the name has no spaces to break at — at a 320px viewport the page went to 400px wide
  and carried the Remove control off-screen entirely. The destination cell had needed
  exactly this treatment already.
- **Two identical notices in a row announced once.** Setting the same string twice is a
  React state bail-out: no re-render, no DOM mutation, nothing announced. Attaching an
  outbound and a return booking to one trip is the ordinary flow, and it was the second
  that went silent.

Also taken: the destination is now a `<th scope="row">`. Without a row header nothing
supplied the trip name when a screen reader reached the Actions cell, so a row read "Remove
Athens booking from your trip to Spain" and then a bare "Remove" — and the *less* qualified
label is the one that deletes the whole trip.

_Known gaps carried forward:_

- **A borderline contrast case, accepted.** The muted inline "Remove" beside a document name
  measures 2.46:1 against the adjacent text, under the 3:1 that 1.4.1 asks for when colour
  distinguishes a control. Accepted because the column header and the button role supply
  context that a link in running prose would not, and left recorded rather than fixed
  silently.
- **The test suite races the compose worker.** Beat relays every unpublished outbox row it
  finds, including ones tests write, so `docker compose up` + `just test-be` means a live
  worker processing test fixtures. It surfaced as `evidence_processing_runs: 0 -> 11`
  during a loop of read-only date simulations. A session-scoped sentinel now fails with a
  message naming the fix. The first version of that guard was useless — it checked at
  session end, but every test truncates `outbox_events`, so it read "not published" from a
  row that no longer existed.
- **320px reflow is now verified for this column**, by measuring the real stylesheet in a
  320px probe container rather than by resizing the window, which Chrome will not do below
  606px. The row fits, the name wraps, and the Remove control lands at 320px rather than the
  400px the review measured. The rest of the page is still unverified at that width.
- **`DUPLICATE_TRAVEL_RECORD` and `DUPLICATE_EVIDENCE` are 4b.** §7.8 and the Domain enum
  now distinguish a duplicate travel *record* from a duplicate *document*; neither
  detection is built.
