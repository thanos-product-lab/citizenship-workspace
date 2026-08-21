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

  Two `xfail(strict=True)` tests in `tests/security/test_rls_login_role.py` carry it — the
  raising half and the silent half separately, because a fix that only restored the
  refreshes would leave the second one green and wrong. **This blocks M7, not just "wants
  its own change".** M7 is the first surface where a forgotten tenant is a document leak
  rather than a row leak, and the control that catches a forgotten tenant is ADR-0006 R1
  Option A — which this defect makes un-adoptable. The fix is to re-establish the tenant
  per transaction: record the user id on `Session.info` and re-apply role and GUC from an
  `after_begin` listener.

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

_Known gaps carried forward:_

- **The mid-request tenant loss is unfixed**, blocks the production half of ADR-0006 R1,
  and should block M7. Two `xfail(strict=True)` markers, so they fail the moment it is
  fixed — and separately, so a partial fix cannot pass.
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
