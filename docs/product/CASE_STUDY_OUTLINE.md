# Case study outline

A plan for the case study, not the case study itself. Each part says what it needs to get
across, what to point to, and the mistake to avoid. The writing should be yours: readers can
always tell when a case study is written in someone else's voice.

**Length:** about 2,000 words. Long enough to show judgement, short enough to finish.

**The angle:** most portfolio case studies describe what was built. The stronger story here
is harder to fake: four times the checks said everything was fine and it was not, and what
changed each time (part 5). Everything else sets that up.

**Link, don't embed:** the [demo video](https://www.loom.com/share/37e9a02e63bf42aeb975a9aa968a5af4)
and the [architecture overview](../architecture/ARCHITECTURE_OVERVIEW.md). Timestamps below
refer to the video.

---

## 1. Opening (about 150 words)

**Get across:** what it is, who it is for, and the one idea. The AI's reading of a document
is stored as a suggestion and never affects a result until a person confirms it, and all the
arithmetic is ordinary, tested Python.

**Point to:** the README's first paragraphs, which already say this.

**Avoid:** opening with immigration law. A reader doesn't need Section 6(1) to understand
the problem, and three paragraphs of background will lose them.

## 2. Why this is hard (about 250 words)

**Get across:** a readiness tool that is confidently wrong is worse than no tool, because
people act on it. Make it concrete: the AI misreads a date on a booking, the absence total is
wrong, the product says "supported", and the person applies.

**Point to:**
- The safety measure is the false-reassurance rate, not accuracy. A model that says "I'm not
  sure" more often scores worse on accuracy and better on safety
  ([evaluation report](../evaluations/EVAL_REPORT.md) §1).
- It happened here: a past application date once showed every requirement as fine, against
  a five-year window that had closed months earlier. It was found by using the product, not
  by a test ([known limitations](../KNOWN_LIMITATIONS.md) entry 11).

**Avoid:** claiming the product prevents bad applications. It stops the product from being
the thing that misled you.

## 3. The one idea, shown (about 300 words)

**Get across:** suggestions versus facts, and the empty box as the sharpest example. For the
dates that matter, the AI's answer is not even sent to the browser. You read the document and
type what it says. If the AI's answer sat next to the box, most people would copy it without
looking, and the confirmation would mean nothing.

**Point to:**
- The video at 0:36 (the empty box) and 0:52 (`11/05/2026` refused, because it means
  different days in different countries).
- The rules engine has no way to receive a suggestion at all
  ([architecture overview](../architecture/ARCHITECTURE_OVERVIEW.md), the trust boundary
  diagram).
- One small story worth a sentence: the first version of the refusal message used the demo
  booking's real return date as its example, handing back exactly the value the empty box
  withholds. Found by using the screen.

**Avoid:** over-explaining. The empty box does most of the work.

## 4. Four decisions, and what was rejected (about 500 words)

**Get across:** the design has reasons, and the rejected options were taken seriously.
Roughly 125 words each, and no more than four.

- **A result and whether it is up to date are separate.** A result can be Supported and out
  of date at the same time. One combined status would force you to either rewrite the result
  or pretend nothing changed. Video at 1:16; ADR-0001.
- **One place decides whether a trip counts.** It used to be worked out in three places,
  including the browser, and all three compiled. The fix was to publish the answer instead
  of the ingredients. ADR-0028.
- **The date preview tells you when things don't improve.** An early design suggested moving
  the date one day would fix a failing check. It wouldn't, and the screen now says "still not
  satisfied on this date". Video at 2:04 to 2:10; ADR-0002.
- **JavaScript inside a PDF is allowed to run in the preview.** Sandboxing the preview was
  tried and stopped PDFs rendering at all, on the one screen whose job is reading a
  document. The risk is contained in other ways. ADR-0026.

**Avoid:** a longer list. Ten decisions reads like a changelog.

## 5. Where the checks were wrong (about 450 words)

**The strongest part. Give it room.**

**Get across:** four times the checks passed and the thing was wrong, and the change each
one led to. Not war stories: each fix makes the whole kind of mistake harder.

1. **The trust decision, made three times.** The same "does this trip count?" logic lived in
   a rule, an API view and a React component. All type-checked; they disagreed. Fixed by
   making the API publish the decision, so recombining it is now a type error (ADR-0028).
2. **The AI tests, wrong four times.** Four apparent model failures were bugs in the test
   harness. The worst: a prompt-injection test checked nothing, because the assertion that
   would have caught it had been removed while tidying the test. The measuring tool had been
   loosened to fit what it measured, by the person who built it
   ([evaluation report](../evaluations/EVAL_REPORT.md) §6).
3. **One walkthrough.** Three defects found in minutes, on a case the test data
   never created. Over a thousand tests, four review passes and a green AI test suite had
   all missed them, because every automated check used the same seeded case with everything
   running.
4. **Breaking the code to test the tests.** Replacing a "this case only" condition in case
   deletion with "every case", a change that would delete everyone's documents, still
   passed. The database's row-level security was catching it instead, so the test was
   measuring the wrong thing.

**The thread:** none of these was caught by a failing test. They were caught by using the
product, by looking at what it actually showed, and by deliberately breaking it.

**Avoid:** making this humble. It is the most senior part of the piece. The point is not
that mistakes happened; it is that each one changed the structure rather than getting a
patch.

## 6. What I left out, and why (about 200 words)

**Get across:** scope discipline you can see, not just claim. Pick three that show different
kinds of judgement:

- **Guidance versions.** Rather than invent a version and retrieval date, the product says
  it doesn't record them yet. Made-up provenance would be the worst thing it could ship.
- **Reading immigration status documents.** Held back, because nothing would compare them
  with what the applicant already entered, so it would add a new way to be falsely
  reassured (ADR-0029).
- **Spotting the same document across different people's cases.** Not a gap: it would mean
  reading other people's data.

**Point to:** [known limitations](../KNOWN_LIMITATIONS.md) entries 2, 6 and 8.

**Avoid:** listing everything that was cut.

## 7. What is still wrong (about 150 words)

**Get across:** that you know, and said so first. Lead with the gap that connects to others:
the product cross-checks dates and nothing else, though the AI also reads names and
destinations. That one gap is why immigration documents aren't read, why the AI tests have
no wrong-name case, and why an Italy booking attached to a Greece trip is only reported as a
date problem.

**Point to:** [known limitations](../KNOWN_LIMITATIONS.md) entry 1.

**Avoid:** ending on an apology. A limitation you state reads as judgement; the same gap
found by a reader reads as an oversight.

---

## Numbers you can use

- 1,230 backend tests and 517 frontend tests, including property-based tests for every date
  rule (`just test-rules`). Don't lead with these; part 5 deliberately undercuts them.
- AI safety: 0% false reassurance over 16 test documents, all legible. Say "on legible
  documents": the report names the harder cases it does not cover yet.
- Speed and cost of the AI calls: median 927ms, 95th percentile 2.8s, $0.0169 across 98
  calls.

## Where the raw material is

Development notes and screenshots from the build were retired from the working tree but
remain in git history, and they are the richest source for parts 2 and 5:

- The milestone notes, written as things went wrong:
  `git show a37b05a:docs/decisions/milestone-notes.md`
- The interview-style questions from the milestone gates, which make a fast first draft if
  answered in writing: `git show aad44b0:docs/MILESTONE_GATES.md`
- Older screenshots, for example:
  `git show a37b05a:docs/demo-assets/m8/m8-slice3b-blind-entry.jpg > blind-entry.jpg`
