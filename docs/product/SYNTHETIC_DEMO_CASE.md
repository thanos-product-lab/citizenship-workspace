# Synthetic Demo Case

### Status

Accepted for implementation
Version: 1.0
Rule set: `2026.07.0`
Blocks: M3A (seed + input verification), M3B (assessment verification)

---

## 1. Purpose

One canonical synthetic applicant, used for **every** purpose: seed data,
development, unit tests, integration tests, Playwright flows, AI evaluation
fixtures, screenshots, and the demo video. One fixture, one set of expected
numbers. Divergence between any two uses is a defect.

Every expected value in this document was **derived by hand from
`DETERMINISTIC_RULES_SPEC.md`, not produced by running the implementation.** That
is the point: this fixture is the independent oracle the implementation is tested
*against*. If a test computes its own expected value from the same code it is
testing, it proves nothing. The numbers here, and the working shown for them, are
the check.

All identities, documents, and reference numbers are fictional.

---

## 2. The applicant

```
Name                 Amara Okonkwo  (fictional)
Date of birth        14 March 1988
Status type          EU settled status (EUSS)
Status granted on    1 March 2025
Married to British   No
May already British  No
Proposed app date    15 April 2027   (initial — fails presence, see §5)
```

This is a deliberately *near-miss* case: broadly strong, but with one
presence-failing application date, a total-absence count close to the limit, one
conflicting record, one unevidenced trip, and one missing referee. It exercises
every readiness state the MVP must show without being contrived into failure.

---

## 3. Derived windows  `[RULES_SPEC §3–4]`

From proposed application date **15 April 2027**:

```
qualifying_period   16 April 2022  →  15 April 2027   (5y, +1 day rule)
final_year          16 April 2026  →  15 April 2027   (365 days)
physical_presence   16 April 2022                     (= qualifying start)
```

Note the `+1 day`: five years before 15 Apr 2027 is 15 Apr 2022, but the
inclusive five-year period *ending* on the application date **begins** 16 Apr
2022. The presence anchor is 16 April 2022, not the 15th. This single day is why
the case fails and then resolves.

---

## 4. Travel history

Twelve trips. Absence days are counted **endpoint-exclusive** — the departure and
return days are UK days and do not count `[RULES_SPEC §5.1]`. Days shown are the
count falling **inside the qualifying window** (16 Apr 2022 – 15 Apr 2027).

| # | Destination | Depart | Return | Absent days | Evidence | Confidence |
|---|---|---|---|---|---|---|
| 1 | Spain | 2022-04-14 | 2022-04-26 | 10 | booking | EXACT |
| 2 | Portugal | 2022-08-10 | 2022-09-20 | 40 | booking | EXACT |
| 3 | France | 2023-02-03 | 2023-03-01 | 25 | booking | EXACT |
| 4 | United States | 2023-07-01 | 2023-09-06 | 66 | booking | EXACT |
| 5 | Germany | 2024-01-15 | 2024-02-14 | 29 | booking | EXACT |
| 6 | Greece | 2024-06-05 | 2024-07-15 | 39 | **none** | EXACT |
| 7 | Japan | 2024-11-02 | 2024-12-28 | 55 | booking | EXACT |
| 8 | Italy | 2025-05-04 | 2025-06-25 | 51 | booking | EXACT |
| 9 | Canada | 2025-09-01 | 2025-10-28 | 56 | booking | EXACT |
| 10 | Spain | 2026-02-01 | 2026-03-25 | 51 | booking | EXACT |
| 11 | Italy (final-year) | 2026-05-04 | 2026-05-10 | 5 | booking | EXACT |
| 12 | United States (final-year) | 2026-05-16 | 2026-05-29 | 12 | booking | EXACT |

> **M3B / M4 staging.** At M3B every trip seeds as `CONFIRMED + EXACT` — the §6.1
> trust gate admits only exact records, and the headline totals (439, final-year 17)
> depend on trip 11 being trusted. The *conflict* on trip 11 needs the evidence/extraction
> model, which is **M4**. Crucially, at M4 trip 11's confirmed **fact** stays 10 May
> `EXACT` (so it remains trusted and 439 / 17 do not move); the uploaded booking document
> yields an untrusted extracted **claim** of 11 May that *conflicts with that fact*
> (`CONFLICTING_CLAIMS`, the claims-vs-facts model), driving `residence.travel_consistency`
> to `INCONSISTENT` and producing the trip-6 unevidenced limitation. Confirming the 11 May
> claim then corrects the fact to 11 May → 440 / 18. At M3B the stale-recalculation demo
> (§7) is a *direct edit* of trip 11's return (10 → 11 May), standing in for that M4
> confirm-correction. (Note: the record's `date_confidence` never becomes `CONFLICTING` —
> that would drop trip 11 out of the trusted union and change 439 / 17; the conflict lives
> at the claim layer, not the fact.)

Two structural features the fixture must reproduce:

- **Trip 1 covers the presence anchor.** It departs 14 Apr 2022 and returns 26
  Apr; the absent set includes 16 Apr 2022. So the applicant was *outside* the UK
  on the anchor date — presence fails. It also demonstrates **boundary clipping**:
  the trip's full absent span is 15–25 Apr (11 days), but only 16–25 Apr (10
  days) fall inside the qualifying window, because 15 Apr is before the window
  starts. The seed must store the true trip and let the rule clip.
- **Trip 11 carries the eventual conflict.** At M3B it is a plain EXACT record
  returning 10 May 2026. The competing document value (11 May) and the resulting
  `CONFLICTING` state are introduced at M4; trip 11 is the seed of the
  stale-recalculation demo (§7) either way.

---

## 5. Expected assessment outputs  `[per requirement, RULES_SPEC §7]`

These are the trusted-mode conclusions for the **initial** application date
(15 Apr 2027), with trip 11's return at its M3B seed value (10 May 2026). The rows
for `knowledge.*`, `referees.*`, `character.review`, and `preparation.case_complete`
are shown for completeness but are **M4+** — their input records do not exist at M3B,
so they read `NOT_YET_ASSESSED` here. The `travel_consistency` row reflects the M3B
staging (§4): trip 11 is EXACT, so it is `SUPPORTED`; the `INCONSISTENT` state arrives
with the M4 conflict.

| Requirement | Conclusion | Key figure | Working |
|---|---|---|---|
| `route.adult_applicant` | **SUPPORTED** | age 39 | DOB 1988-03-14, ≥18 |
| `route.supported_status` | **SUPPORTED** | EUSS | supported status type |
| `route.standard_section_6_1` | **SUPPORTED** | — | not spouse, not may-be-British, adult+status both SUPPORTED |
| `status.holding_period` | **SUPPORTED** | earliest 2026-03-01 | granted 2025-03-01 +1y; app 2027-04-15 ≥ earliest+7d |
| `residence.qualifying_period` | **SUPPORTED** | window derived | §3 |
| `residence.physical_presence_start_date` | **NOT_CURRENTLY_SATISFIED** | anchor 2022-04-16 | anchor ∈ trip 1 absent set; nearest resolving date **2027-04-25** (see §8) |
| `residence.total_absences` | **NEAR_THRESHOLD** | **439** | union of all trips within window; band 421–450; 11 days below 450 |
| `residence.final_year_absences` | **SUPPORTED** | **17** | trips 11 (5) + 12 (12) within final year; ≤75 |
| `residence.travel_consistency` | **SUPPORTED** (M3B) | boundary note | all trips EXACT → consistent; trip 1 covers the anchor → `NEAR_STANDARD_THRESHOLD` limitation. **M4:** the 11 May claim conflicts with trip 11's confirmed fact → INCONSISTENT; trip 6 unevidenced → INFORMATION |
| `knowledge.life_in_uk` | **SUPPORTED** | ref present | LIUK recorded with reference value |
| `knowledge.english_language` | **SUPPORTED** | B1, valid | SELT B1, taken 2026-01-10, valid to 2028-01-10; app before expiry−30d |
| `referees.first` | **SUPPORTED** | complete | all fields, ≥3y, no disqualifier |
| `referees.second` | **INCOMPLETE** | empty slot | second referee missing |
| `character.review` | **SUPPORTED** | acknowledged | no disclosure |
| `preparation.case_complete` | **INCOMPLETE** | aggregate | driven by second referee INCOMPLETE + presence NOT_CURRENTLY_SATISFIED |

### Absence total — full working

```
Trip contributions within 16 Apr 2022 – 15 Apr 2027 (endpoint-exclusive):
 Spain      10   (15–25 Apr abroad; 15 Apr clipped → 16–25 = 10)
 Portugal   40
 France     25
 USA        66
 Germany    29
 Greece     39
 Japan      55
 Italy'25   51
 Canada     56
 Spain'26   51
 Italy FY    5
 USA FY     12
 ──────────────
 union     439      (no overlaps, so union = sum)

Band [RULES_SPEC §7.6]: 421–450 → NEAR_THRESHOLD, 11 days below the 450 limit.
```

The sensitivity rule `[RULES_SPEC §6.2]` does not downgrade here: at M3B every trip
is CONFIRMED + EXACT, so the provisional total equals the trusted total and the
machinery has nothing to act on. (At M4, trip 11's confirmed fact stays 10 May and
trusted, so the trusted final-year count is 17; the untrusted 11 May *claim* would put
the provisional count at 18 — both in the SUPPORTED band, so the sensitivity machinery
would run without firing, the common case it exists to handle.)

---

## 6. Required states coverage  `[MVP §13]`

The fixture must produce, and the demo must show, at least one of each:

| Required state | Produced by |
|---|---|
| Supported | most requirements |
| Near threshold | `residence.total_absences` (439) |
| Inconsistent | `residence.travel_consistency` (trip 11 conflict) — **M4** |
| Incomplete | `referees.second` (missing) — **M4**; at M3B, any requirement whose input record does not exist yet reads `NOT_YET_ASSESSED` |
| Not currently satisfied | `residence.physical_presence_start_date` (initial date) |
| Stale (currency) | any residence result after a residence input changes (§7) |
| Final resolved state | after §7 + §8 |

At M3B the fixture produces Supported, Near threshold, Not currently satisfied, and
Stale. Inconsistent and the referee-driven Incomplete require M4 input models.

---

## 7. The stale transition  `[demo-critical]`

The scripted sequence that proves immutable-assessment + stale-recalculation. **At
M3B** it runs as a direct edit of trip 11 (steps 2–3 collapse into one edit); the
document-upload / extraction / confirm-correction framing is the **M4** version.

```
1. Initial state: trip 11 return = 10 May 2026, EXACT.
   total_absences = 439 (NEAR_THRESHOLD), CURRENT.
2. (M4) User uploads the booking document; extraction proposes return = 11 May 2026.
3. User edits (M3B) / CONFIRMS the correction (M4): trip 11 return = 11 May 2026.
4. A new confirmed TravelRecordVersion is created (old version retained).
5. Dependent residence results are marked STALE in the same transaction.
   - total_absences: conclusion still NEAR_THRESHOLD, currency now STALE.
6. Recalculation runs.
   - new total = 440 (still NEAR_THRESHOLD), currency CURRENT.
   - previous result becomes SUPERSEDED, remains inspectable.
```

The absence total moves **439 → 440** — a one-day change that does not cross a
band boundary. This is intentional: it demonstrates that the *conclusion* can be
unchanged while the *currency* cycles CURRENT → STALE → SUPERSEDED, which is
exactly the conclusion-vs-currency separation from ADR-0001. A fixture where the
band also flipped would conflate the two ideas.

---

## 8. The resolving application date  `[demo-critical]`

```
1. physical_presence_start_date = NOT_CURRENTLY_SATISFIED at 15 Apr 2027.
   Rule returns nearest resolving date: 25 Apr 2027.
   (Trip 1 returned 26 Apr 2022, so its absent set is 16–25 Apr 2022 within the
    window. Application dates 15–24 Apr 2027 have anchors 16–25 Apr 2022, all inside
    that set. The first clear anchor is 26 Apr 2022 — the return day, a UK day →
    application date 25 Apr 2027. The rule searches forward and returns it.)
```

**Verify this by hand before seeding** — the resolving date depends on trip 1's
exact return. With trip 1 returning 26 Apr 2022, the anchor is an absent date for
application dates whose anchor falls 16–25 Apr 2022, i.e. application dates
15–24 Apr 2027. The first supported application date is **25 April 2027** (anchor
26 Apr 2022, a UK day — the return day counts as present).

> Implementation note: the seed and the presence-rule test must agree on
> **25 April 2027** as the resolving date for this fixture, derived from trip 1
> returning 2022-04-26. If trip 1's dates are ever changed, this number must be
> re-derived — it is not independent of the travel history. (RULES_SPEC §9 shows the
> same construction on a shorter trip returning 20 Apr → resolving date 2027-04-19.)

After moving to 25 Apr 2027, the whole qualifying window shifts forward by 10
days; absence totals must be recalculated (some early Spain days drop out, no new
late days enter, since the final-year trips remain inside). Recompute at seed
time and record the post-move total alongside this fixture before relying on it
in a test.

---

## 9. Knowledge, referees, character detail

```
Life in the UK
  completion_state = COMPLETED
  reference_value  = "LIUK-8842190"  (fictional)
  → SUPPORTED

English language
  route        = SELT
  level        = B1
  test_taken   = 2026-01-10
  selt_expires = 2028-01-10   (test_taken + 2y)
  app 2027-04-15 ≤ expiry − 30d → SUPPORTED

Referee 1 (FIRST)
  professional, known 6 years, not disqualified → SUPPORTED

Referee 2 (SECOND)
  not provided → INCOMPLETE  (raises MISSING_REQUIRED_FACT issue)

Character
  review_acknowledged = true, no disclosure → SUPPORTED
```

The missing second referee is deliberate — it keeps `preparation.case_complete`
at INCOMPLETE even after the presence date is resolved, giving the demo a final
"resolve the last issue" beat (add the second referee) before the case reaches a
fully prepared state.

---

## 10. Expected open issues

Issues are a durable, user-actionable model owned by **M6** (Issue Detection). The
eventual issue set, and what of it is live:

| Issue type | Cause | Dismissible | Status |
|---|---|---|---|
| `NEAR_THRESHOLD` | total absences 439, against a threshold of 450 | No | ✅ **live** — the one issue the case shows standing still |
| `STALE_ASSESSMENT` | appears transiently after §7 step 5 | No (auto-resolves) | ✅ **live** — four issues, not five (§7) |
| `CONFLICTING_CLAIMS` | trip 11 return date 10 vs 11 May | No | ❌ M8 — needs somewhere to hold the competing value |
| `MISSING_EVIDENCE` | trip 6 (Greece) unevidenced | Yes (INFORMATION) | ❌ M7 — no evidence model |
| `MISSING_REQUIRED_FACT` | second referee absent | No | ❌ no reachable producer (below) |
| `PROCESSING_FAILURE` | a recalculation that did not finish | No | ✅ **live** — not by this fixture; see below |

**What the canonical case produces at M6.** Exactly one standing issue: `NEAR_THRESHOLD`
on `residence.total_absences`. Editing trip 11 opens four `STALE_ASSESSMENT` issues in the
same transaction; recalculation resolves all four into the settled list while the
near-threshold issue **stays open**, because 439 → 440 does not widen the margin. That
contrast is the demo — issues that clear themselves beside one that does not, for a visible
reason.

**`MISSING_REQUIRED_FACT` has no reachable producer, and not only because referees are
unmodelled.** The type derives from a requirement concluding INCOMPLETE for want of a fact.
The only such branch today is `status.holding_period` when `status_granted_on` is missing —
and route confirmation *requires* that field for exactly the status types that activate a
case (§9.4), so an active case always has it. The type becomes reachable when a subsystem
with optional facts arrives: referees and knowledge records (M9/M10), or a route-profile
edit path. Recorded here rather than shipped as an unreachable branch.

**Three other issue types are producible but not by this fixture**, and are covered by
`tests/issues/test_derived_types.py` instead: `OVERLAPPING_TRAVEL`, `UNCERTAIN_TRAVEL_DATE`
(in-window, not dismissible; out-of-window, dismissible — the only dismissible thing in the
product today), and `UNSUPPORTED_COMPLEXITY`, which the absence bands raise above 450 days.
The canonical case is deliberately clean of all three: it demonstrates a well-kept case, and
loading it with every defect at once would make the stale transition harder to see.

**`PROCESSING_FAILURE` is reachable but deliberately unreachable *by data*.** It is raised
when the case's most recently finished `AssessmentRun` has `status = FAILED` (ADR-0016) —
process state, not case state, so no fixture can produce it and no input a user supplies
can. `tests/assessments/test_failed_recalculation.py` covers it by breaking result
persistence mid-run. Demonstrating it by hand needs the same: the failure is genuinely
exceptional, which is the point of making it durable.

---

## 11. Seeding and reset

- The fixture seeds via the same command path a real user would use, not by raw
  SQL insert — this exercises the real validation and versioning, and catches
  drift between seed and product behaviour.
- At M3B trip 11 seeds as a single EXACT value (return 10 May 2026). Seeding the two
  competing values (spreadsheet 10 May, document 11 May) needs the evidence model and
  is **M4**.
- Trip 1 seeds with its true dates (14–26 Apr 2022); the boundary clipping to 10
  counted days is the *rule's* job, never baked into the seed.
- `SYNTHETIC_DEMO_CASE` reset is a distinct operation from user case deletion and
  must never run against a real case `[DOMAIN_MODEL §51.3]`.

---

## 12. Numbers to re-derive if the fixture changes

These are coupled; changing travel data invalidates them and they must be
recomputed by hand:

- total absences (439) and post-conflict total (440)
- final-year absences (17)
- presence anchor membership and the resolving application date (25 Apr 2027)
- per-trip counted days (§4 table)
- which band each total falls in

The `+1 day` window, endpoint-exclusive counting, and union-not-sum are fixed by
the rules spec and do not change with the fixture.