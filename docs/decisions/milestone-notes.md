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
