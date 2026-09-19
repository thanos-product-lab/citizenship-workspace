# Demo video shot list

Three to five minutes, edited from captures that already exist wherever possible. This
gives the order, the asset behind each shot, and **the one thing each shot has to make a
viewer understand**. It does not give the words, which are yours.

**The arc.** A product that refuses to score you, shows its working, makes a person read
the document rather than the machine's guess, and then shows what happens when that
disagrees with what you had already told it.

Total below is about four and a half minutes, which leaves room to trim rather than to pad.

---

## The shots

| # | Time | On screen | Asset | The point it has to make |
|---|---|---|---|---|
| 1 | 0:00 to 0:20 | Case overview | `m4-case-overview.jpg` | There is no score. Counts by named state, then the one thing needing attention. A viewer should notice the absence of a percentage before it is mentioned. |
| 2 | 0:20 to 0:50 | Residence timeline, ending on the Spain row | `m5/m5-timeline-table.png`, `m5/m5-timeline-band.png` | The product shows its arithmetic. "14 April to 26 April, 10 days" with the sentence explaining that one day falls outside the window. This is the most common reason a user's own sum disagrees. |
| 3 | 0:50 to 1:10 | Uploading the amended booking, then the row reaching "Values proposed" | **Needs capturing (A)** | A document has been read and six values proposed. None of them is true yet. |
| 4 | 1:10 to 1:50 | The review split view: document left, **empty box** right | **Needs capturing (B)**, still exists at `m8/m8-slice3b-blind-entry.jpg` | The heart of it. The model's reading is not on screen, because the API does not send it. The person reads the page and types what it says. |
| 5 | 1:50 to 2:10 | The corrected field | `m8/m8-slice3b-your-value-won.jpg` | The person typed 10 May, the model had read 11 May, the fact is theirs and the model's proposal is kept beside it. Correcting does not erase what was proposed. |
| 6 | 2:10 to 2:25 | The refusal | `m8/m8-slice3b-ambiguous-refused.jpg` | `03/04/2025` has two readings, so it is refused from a person for the same reason it is refused from a model. The product declines to guess. |
| 7 | 2:25 to 2:55 | Requirement detail showing 434 and the disputed trip | **Needs capturing (C)**, text version at `m8/m8-slice4-conflict-explained.txt` | Confirming the document's date made it disagree with a trip the user entered. The trip is held back from the confirmed total, named as disputed, and the fact that caused it is listed. |
| 8 | 2:55 to 3:25 | Conclusions going stale, then Recalculate, then assessment history | `m6/m6-slice1-selective-invalidation.gif`, `m4-assessment-history-439-to-440.jpg` | Exactly the conclusions that depended on the change go stale, and not the others. Recalculating writes new results and leaves the old ones readable with the rule version that produced them. |
| 9 | 3:25 to 3:50 | A recalculation that fails | `m6/m6-slice4-failed-recalculation.gif` | The failure becomes a durable item rather than a toast that disappears. The copy says nothing changed without claiming the run did or did not happen. |
| 10 | 3:50 to 4:20 | Date simulation: 20 April, then 25 April | `m5/m5-date-simulation.gif` | Moving the date five days changes the arithmetic and fixes nothing, and the screen says so. Then the date that does work. Nothing is written either time. |
| 11 | 4:20 to 4:30 | Back to the overview | `m4-case-overview.jpg` | Still no score. |

## What still needs capturing

Three, all in the same flow, so one session covers them.

**A. Upload to "Values proposed".** Screen recording of the Evidence destination: choose the
amended Italy booking, upload, and let the row reach `AWAITING_CONFIRMATION`.

The reading takes about twenty seconds and the screen says nothing during it, which is
limitation 10. **Cut that wait in the edit.** Worth knowing that the cut hides a real gap,
so the case study should mention the silence rather than the video pretending it is not
there.

**B. Blind entry as motion.** The still carries the empty box; the video needs the act. Show
the document pane, the empty field, typing the date read off the page, then Save and the
badge appearing. Optionally show the refusal first by typing `11/05/2026`, which makes shot
6 unnecessary and saves fifteen seconds.

**C. The requirement detail after the conflict.** `residence.total_absences` reading 434
confirmed days, the disputed trip marked "Confirmed, conflicting dates, did not count
towards the confirmed figure", and the fact named under Facts used. A still is enough; a
slow scroll down the explanation stack is better.

Capture all three against the seeded case following `docs/DEMO_SCRIPT.md` steps 5 to 7, at
1280px wide to match the existing assets.

## The cheaper cut, if capture time is short

Drop shot 7 and use shot 8's trip edit path for the whole stale and recalculate sequence.
That path is fully captured already, so only A and B need recording.

The cost is real: the AI section then has no consequence. The viewer sees a document
confirmed and never sees it change anything, which removes the link between the careful
review and the number on the requirement page. Take this cut only if C cannot be recorded.

## Deliberately left out

**The issue queue** (`m6/m6-slice2-issue-queue.gif`, `m6/m6-slice3-dismissal.gif`). Good
material, and the video is full. It also needs more setup than a viewer will hold, because
the interesting part is that one item clears itself while another does not.

**Deletion** (`m7/m7-slice5-delete-and-stale.gif`). The strongest asset not used. It shows a
document going and exactly one rule noticing. Swap it in for shot 9 if the failure state
feels too inside baseball for the audience.

**Every terminal capture.** They are the oracle the screens are checked against, and they
are unreadable at video size. They belong in the repository and the case study, not here.

**The Life in the UK and English certificate flows.** They demonstrate that the review
machinery generalises, which is an engineering point rather than a product one, and the
video is about the product.

## Constraints

Synthetic data only. The case is Amara Okonkwo, the figures are 439, 434 and 440, and the
resolving date is 25 April 2027. Every asset above was captured on that case, so the numbers
agree across shots. **Check they still agree after any recapture**, because a figure that
moves between two shots is the one thing a careful viewer will notice.

No Clerk user button appears on case detail pages, so no real account is on screen.
