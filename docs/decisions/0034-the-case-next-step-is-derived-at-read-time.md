# ADR-0034: The case's next step is derived at read time

**Status:** Accepted, 24 September 2026
**Amends:** Domain RFC §44.1 (adds next steps to the overview) and adds §44.6
**Replaces:** the overview's Start here list

## Context

Coming back to a case after a break, a user could not tell where they had left off or what
to do next. The overview answered "what now" at two moments only:

- **Start here**, shown only while nothing was assessed. It was static: a date already set
  simply vanished instead of showing as done, and the trips step read the same with five
  trips as with none.
- **Needs your attention**, the requirements' own next actions, shown only after an
  assessment.

The rest of what a returning user needed was real but spread over four screens: stale
conclusions in the header, documents waiting for review on Evidence, things to do on
Issues, and trips with no document under Issues' notes.

## Decision

**One Next steps panel on the overview, derived by rules from the case's current state on
every read.** `assessments.next_steps.derive_next_steps` is a pure function over a small
snapshot the overview already reads. It returns what is done and at most three steps, the
first being the primary one. Its prose is rendered on the server from codes, like every
other sentence about a case.

The steps, in order, each included when its condition holds:

| Step | When |
|---|---|
| Set application date | there is no date |
| Add trips | there are no trips **and nothing has been assessed** |
| Review documents | documents are awaiting review |
| Run assessment | a date is set and nothing has been assessed |
| Update assessment | something is assessed and stale |
| Requirements' asks | the requirements have next actions (the cards below) |
| Work through issues | open issue actions, other than rechecks |
| Attach trip documents *(optional)* | open notes for trips with no document |
| Nothing left | none of the above |

**Rules, not a model.** Every condition is a fact the case already holds. A model would add
nothing but the chance of a step that is wrong, and directive 2 keeps anything that
decides about a case in code.

**Read time, never stored**, like the case phase (ADR-0009) and the passed-date notice
(ADR-0032). The steps are true whenever anyone looks and cannot go out of date, so nothing
has to invalidate them.

**It replaces Start here and absorbs Needs your attention.** Start here's own reasoning was
that two answers to "what now" are worse than one. The requirements' cards stay, now
titled "What your requirements ask", as the detail the requirements step links down to.

**No trips is asked about only before the first assessment.** "No trips" is ambiguous: not
entered yet, or genuinely none. After an assessment the totals already state zero, so a
standing request would nag someone who never left the UK, forever.

**Rechecks are one step.** Stale conclusions are `Update assessment`, and the recheck issues
behind them are left out of the issues step, so one job is not shown twice (ADR-0033).

**Trip documents are the only optional step**, and they appear only when the issue rule
already opens a note for them, which is once the case holds a document and the user has
not dismissed the note. English and Life in the UK documents are read, but those
requirements are not assessed, so a step asking for them would imply an effect they do not
have.

**No tally and no finish line.** Done items are statements ("5 trips recorded"), never "2 of
3" (CLAUDE.md §2.6). When nothing is left the step says the workspace has nothing left it
can check, that some requirements are not assessed here and that an application needs more,
and links to Requirements. It never says "ready" (§2.7). A property test holds both over
every combination of inputs.

## Consequences

- The overview always has an answer, for a new case and a returning one.
- The server names a destination (`CASE_DATA`, `EVIDENCE`, `REQUIREMENTS`, `ISSUES`,
  `PRIORITY_ACTIONS`) and the client maps it to a route, so the backend never owns URLs.
- Adding a step means a code, a condition in order, and its templates. The message tests
  fail on a code without them.

## Rejected

- **A model-written "what to do next".** Nondeterministic wording about a case's state is the
  thing the product is built to keep out.
- **Keep Start here and add a second panel for returning users.** Two answers to one
  question.
- **A progress bar or checklist of done over total.** A completion measure by another name.
- **A step for every requirement's next action.** Duplicates the cards, and at three steps
  would crowd out everything else.
- **Show the panel on every destination.** Each destination already has its own actions; the
  overview is where a returning user lands.
