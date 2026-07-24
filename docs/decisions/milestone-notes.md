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
