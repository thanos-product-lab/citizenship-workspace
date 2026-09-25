# Case study outline

**This is scaffolding, not a draft.** Each section gives what it has to establish, the
evidence to hang it on, and the trap to avoid. The words are yours, because a case study
written in someone else's voice is the one thing a reader can always tell.

**Target: 1,800 to 2,500 words.** Long enough to show judgement, short enough to be read.
Suggested lengths per section below add to about 2,100.

**The angle worth taking.** Most portfolio case studies say what was built. The strongest
material here is different and harder to fake: four separate occasions where the
verification was lying, and what changed each time. Section 5 is where that lives, and the
rest of the piece exists to make it land.

---

## 0. Opening (150 words)

**Establish:** what the product is, who it is for, and the one sentence that makes it
interesting.

The one sentence is roughly: model output is stored as a proposal and never affects a
conclusion until a person confirms it, and all the arithmetic is ordinary Python with tests.

**Evidence:** `README.md` opening, which already carries this framing.

**Trap:** do not open with the immigration domain. A reader does not need to understand
Section 6(1) to understand the problem, and three paragraphs of context loses them before
the point.

---

## 1. Why this is hard (250 words)

**Establish:** the failure mode the product is built against. A naturalisation readiness
tool that is confidently wrong is worse than no tool, because the user acts on it.

Name the specific shape: a model reads a date off a booking, the date is wrong, the total
absences figure is wrong, the product says "supported", and the user submits.

**Evidence:**

- CLAUDE.md directive 7: stopping or escalating is a successful outcome.
- The false reassurance rate as the headline metric rather than accuracy, and why: a model
  that abstains more has a worse pass rate and a better false reassurance rate.
  `EVAL_REPORT.md` §1.
- The M8 gate finding where a past application date produced every requirement green
  against a five year window that had closed eight months earlier. `milestone-notes.md`,
  M8 gate, finding 2. This is the failure happening, in your own product, found by driving
  it.

**Trap:** do not claim the product prevents bad applications. It prevents the product from
being the thing that misled you.

---

## 2. The one idea (300 words)

**Establish:** claims versus facts, and blind entry as its sharpest expression.

Two moves. Model output becomes an `ExtractedClaim`, which no rule can read. And for a
high risk field, the proposal is **not sent to the browser at all**, so the person reads
the document and types what it says.

Explain why the second follows from the first: if the model's reading sits beside an empty
box, most people type it without looking, and the confirmation means nothing.

**Evidence:**

- `m8/m8-slice3b-blind-entry.jpg`, the empty box beside the document.
- `m8/m8-slice3b-your-value-won.jpg`, a correction recorded with the model's original kept
  beside it.
- `m8/m8-slice3b-ambiguous-refused.jpg`, `03/04/2025` refused from a person for the same
  reason it is refused from a model.
- The invariant is structural: the rules engine has no parameter a claim could arrive
  through. `ARCHITECTURE_OVERVIEW.md`, the trust boundary diagram.
- The detail worth one sentence: the first version of the refusal message used the demo
  booking's real return date as its example, handing back the exact value blind entry
  withholds. Found by driving the screen, not by a test.

**Trap:** do not over-explain the mechanism. The screenshot of an empty box next to a
document does most of the work.

---

## 3. Four decisions, each with the alternative rejected (500 words, roughly 125 each)

**Establish:** that the design has reasons, and that the rejected option was considered
seriously rather than strawmanned.

### Conclusion and currency are separate fields

A result can be `SUPPORTED` and `STALE` at once. The rejected alternative was one status
field, which forces you either to lie about the conclusion or to pretend nothing changed.

**Evidence:** ADR-0001, `m4-supported-and-stale.jpg`.

### The trust gate has one implementation

Whether a trip counts towards the confirmed total was re-derived in three places. All three
type checked. The fix was not a corrected expression but a changed signature: the API
publishes the decision rather than the ingredients.

**Evidence:** ADR-0028, `m8/m8-timeline-agrees-with-the-assessment.txt`,
`m8/m8-case-data-shows-the-dispute.txt`. The commit messages for `49b59db` and `cfb9d30`
tell the story compactly.

### Simulation follows the rules, including when that is inconvenient

A mockup once taught that moving the application date one day would fix a failing presence
check. It would not: clearing an absent anchor means moving past the whole trip covering
it. The screen now says "still not satisfied on this date" rather than listing only what
improved.

**Evidence:** ADR-0002, `m5/m5-date-simulation.gif`. The earlier version reported only
improvements, which is the false reassurance shape arriving through a UI decision.

### A hostile PDF's JavaScript runs, and that is accepted

`sandbox` on the iframe was measured: with it, the viewer is blocked entirely and the PDF
does not render, for every token combination tried. So the choice was a working preview or
no preview, on the one screen whose task is reading a document.

**Evidence:** ADR-0026, and the compensating controls: strict `frame-src`, `object-src
'none'`, private bucket, short lived signed URLs, inline disposition withheld until the
bytes are verified.

**Trap:** four is the limit. A list of ten decisions reads as a changelog.

---

## 4. How I know it works (250 words)

**Establish:** three layers of verification that check different things, and what each
cannot see.

- **Property tests** for the arithmetic. Hypothesis generates the leap years and boundary
  cases nobody writes by hand. 21 property tests.
- **An evaluation suite** for the model, reporting false reassurance rather than accuracy.
  0.0% over 16 measured fixtures, and the report names the three fixture classes the corpus
  omits, which are the ones most likely to produce a false reassurance.
- **Driving it in a browser**, which is what actually found the defects.

**Evidence:** `EVAL_REPORT.md`, `just test-rules`, `RELEASE_GATE_AUDIT.md` for the measured
figures (p50 927ms, p95 2837ms, $0.0169 over 98 runs; 276,952 log lines searched for PII
with zero hits).

**Trap:** do not lead with test counts. 1,128 backend tests is a number, not an argument,
and section 5 is about to undercut it deliberately.

---

## 5. Where the verification lied (450 words)

**The strongest section. Give it room.**

**Establish:** four occasions where the checks passed and the thing was wrong, and the
structural change each one produced. Not anecdotes. Each has a fix that makes the class of
error harder.

1. **The trust gate, three times.** The same decision re-derived in a rule, a projection and
   a React component. Every version type checked. Fixed by changing what the API publishes,
   so recombining the ingredients is now a type error. ADR-0028.

2. **The eval harness, four times.** Four apparent model failures were defects in the
   instrument. The worst: an injection fixture graded no authority channel at all, because
   the assertion that would have caught it existed and was deleted while "generalising" a
   test. That is the instrument being loosened to accommodate the thing it measures, by the
   person who built it. `EVAL_REPORT.md` §6.

3. **The M8 gate walkthrough.** Three defects and a workflow hazard in minutes, on a case
   the seed does not create. 1,114 backend tests, 381 frontend tests, four reviewer passes
   and a green eval suite had all missed them, because every automated check used the seeded
   case with the stack healthy. `milestone-notes.md`, M8 gate.

4. **Mutation testing my own tests.** Substituting `1 = 1` for a `case_id` predicate in the
   case purge, a change that would destroy every evidence item in the database, passed.
   Row level security had absorbed it, because the bystander case belonged to a different
   tenant. The test was measuring the policy, not the predicate it claimed to test.
   `milestone-notes.md`, release slice.

**The thread:** none of these was found by a failing test. They were found by driving it,
by looking at the rendered artefact rather than the source, and by deliberately breaking
the implementation to see whether the tests noticed.

**Trap:** resist making this humble. It is the most senior thing in the piece. The point is
not that mistakes happened; it is that each one produced a structural change rather than a
patch.

---

## 6. What I cut, and why that was right (200 words)

**Establish:** scope discipline as a demonstrated behaviour rather than a claim.

Pick three:

- **The guidance registry** (M9). Rather than fabricate a version and retrieval date, the
  API ships `guidance_version_recorded: false` and the screen says so. Fabricated
  provenance would be the worst defect this product could ship.
- **The immigration status extractor.** Deferred because nothing compares a confirmed fact
  to the route profile, so it would have added a false reassurance path knowingly.
  ADR-0029.
- **Cross case duplicate detection.** Not a gap. Matching across cases means reading another
  user's rows, and a checksum is a fingerprint.

**Evidence:** `KNOWN_LIMITATIONS.md` entries 2, 6 and 8. The retired roadmap's §7.3 cut order
(`git show aad44b0:docs/IMPLEMENTATION_ROADMAP.md`).

**Trap:** do not list everything cut. Three that show different kinds of judgement beats ten
that show one.

---

## 7. What is still wrong (150 words)

**Establish:** that you know, and said so first.

Lead with the one that connects: the product cross checks dates and nothing else, though it
extracts names and destinations too. That single gap is why immigration status documents are
never read, why the eval corpus has no wrong applicant fixture, and why an Italy booking
attached to a trip to Greece is reported only as a date disagreement.

**Evidence:** `KNOWN_LIMITATIONS.md` entry 1, and the link it draws to entries 6 and 14.

**Trap:** do not end apologetically. A visible limitation reads as judgement; the same gap
found by a reader reads as an oversight. That sentence is already in the limitations file
and is worth reusing.

---

## Material you have not used yet

Worth knowing it is there.

- `milestone-notes.md`, 1,800 lines of what went wrong per milestone, written at the time.
  Retired from the working tree in the September 2026 docs review; read it with
  `git show a37b05a:docs/decisions/milestone-notes.md`.
- The captures cited as evidence above (`m4-*.jpg`, `m5/*.gif`, `m8/*` and the rest) were
  retired the same way; they show an earlier design, and the case study will use the final
  demo video. Retrieve one with, for example,
  `git show a37b05a:docs/demo-assets/m8/m8-slice3b-blind-entry.jpg > blind-entry.jpg`.
  This is the richest source in the repository and almost none of it is in the outline
  above.
- The three hard gates from the retired milestone gates §3 (M3B, M6, M8;
  `git show aad44b0:docs/MILESTONE_GATES.md`) are written as an
  interviewer would ask them. Answering them in writing is the fastest route to a draft.
- The M9 to M12 gate questions are unanswered and double as a closing section: "what in this
  product is most likely to be wrong, and how would a user find out?"

## Formats

A written case study is the deliverable. Two things it should link rather than contain: the
demo video, and `ARCHITECTURE_OVERVIEW.md`. Screenshots earn their place in sections 2 and
3 and nowhere else.
