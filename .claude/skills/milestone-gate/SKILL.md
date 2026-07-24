---
name: milestone-gate
description: Runs the end-of-milestone verification gate. Use when a milestone's Definition of Done has passed and before starting the next milestone. Prepares the smoke test, walkthrough script, and explain-back questions so the human can verify and defend the work.
---

# Milestone gate

`docs/MILESTONE_GATES.md` is the source of truth. Read it, then run the gate for
the milestone just completed.

This gate verifies the **human** understands the work, not that the software runs
— that is `definition-of-done`. Your job here is preparation and evidence, not
assessment. Do not mark a gate passed; only the human does that.

## What to do

1. **Run the smoke test.** Playwright suite locally and against the deployed
   environment. Report both results plainly. Do not fix failures inside the gate
   — report them; a failing smoke test means the milestone was not done.

2. **Produce a walkthrough script.** Number the steps of this milestone's user
   journey through the UI, and include **one failure path** to exercise
   deliberately: kill the worker, submit an invalid date, disconnect the network,
   force a recalculation failure. Say which URL to start from and what should
   appear at each step.

3. **Surface the questions.** Quote this milestone's questions from
   `MILESTONE_GATES.md` §3 verbatim. Do not answer them, do not summarise them,
   and do not soften them. The human answers from memory; supplying answers
   defeats the entire purpose of the gate.

4. **List what changed** since the last gate: new domain objects, new rules, new
   invariants relied on, decisions taken. Enough for the human to know what they
   are being asked to own.

5. **Prompt for demo assets** — remind which captures belong in
   `docs/demo-assets/` for this milestone, named `m<N>-<slug>.<ext>`.

6. **Offer to append** the human's written answers to
   `docs/decisions/milestone-notes.md` once they provide them.

## Hard gates

M3B, M6, and M8 are absolute. If the human cannot explain the trust model at any
of these, say so directly and recommend stopping. Do not proceed to the next
milestone's work in the same session.

## What not to do

- Do not answer the gate questions.
- Do not declare the gate passed.
- Do not start next-milestone work in the same session — start fresh, so the
  context reflects the new milestone's documents.
