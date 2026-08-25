# Evidence-First Citizenship Workspace

## Deterministic Rules Specification

### Status

Proposed for implementation
Version: 0.1
Rule set version: `2026.07.0`
Project: Evidence-First Citizenship Workspace
Route: UK naturalisation under Section 6(1), standard five-year route

---

## 1. Purpose and Standing

This document defines the exact deterministic semantics for every rule the MVP
evaluates. It is the authority for date arithmetic, day counting, thresholds,
conclusion banding, and summary codes.

It is **blocking for Milestone 3B** and is the source from which the synthetic
demo case's expected numbers are derived.

Every rule below is tagged:

- **[GUIDANCE]** — stated in official Home Office guidance or statute. Cited.
- **[PRODUCT]** — a product judgment this document commits to. Not law. Defensible,
  documented, and the reason the product exposes limitations rather than verdicts.

Distinguishing these matters: **[GUIDANCE]** items must be re-verified when a
guidance version changes; **[PRODUCT]** items are ours to revise, but only through
a new rule version.

---

## 2. Sources of Record

| ID | Source | Version captured | Retrieved |
|---|---|---|---|
| `GUIDE_AN` | Guide AN — Naturalisation booklet: the requirements and the process | April 2026 | 2026-07-23 |
| `DISCRETION` | Nationality policy: Naturalisation as a British citizen by discretion (accessible) | as published, last updated 2025-11-11 | 2026-07-23 |
| `BNA_1981_SCH1` | British Nationality Act 1981, Schedule 1, para 1 | current consolidated | 2026-07-23 |

Canonical URLs:

- `GUIDE_AN` — `https://assets.publishing.service.gov.uk/media/69ea07d1606c20d4121632fd/Guide_AN_-_April_2026.pdf`
- `DISCRETION` — `https://www.gov.uk/government/publications/naturalisation-as-a-british-citizen-by-discretion-nationality-policy-guidance/naturalisation-as-a-british-citizen-by-discretion-accessible`
- `BNA_1981_SCH1` — `https://www.legislation.gov.uk/ukpga/1981/61/schedules`

### 2.1 Standing policy risk — read this before implementing

The UK is mid-reform. An "earned settlement" framework was consulted on
(consultation closed 12 February 2026) and a Statement of Changes (HC 1691) was
laid before Parliament on 5 March 2026. Commentary anticipates an "earned
citizenship" model that may lengthen qualifying periods and raise the English
requirement from B1 to B2. **As of the April 2026 Guide AN, none of this has
changed the section 6(1) requirements below.**

Two consequences for implementation:

1. This is a live validation of the `RuleVersion` / `GuidanceVersion`
   architecture. Do not shortcut it. The rules in this document *will* change,
   and historical assessments must survive that change unrewritten.
2. Add a `GUIDANCE_REVIEW_REQUIRED` check to the release checklist: before any
   public demo or portfolio submission, re-verify `GUIDE_AN` is still the current
   edition. If it is not, mark affected rule versions `REVIEW_REQUIRED` rather
   than silently updating them.

---

## 3. The Off-By-One That Everything Depends On

**[GUIDANCE]** `GUIDE_AN`, "Requirement to have been in the UK on the first day of
the qualifying period":

> If you are applying under section 6(1), you must have been in the UK exactly 5
> years before your application was received. For example, if your application is
> received on 05/01/2022 you should have been physically present in the UK on
> 06/01/2017.

Read the example carefully. Five years before 05/01/2022 is 05/01/**2017**, but
the guidance names 06/01/**2017** — the following day.

This is not an error in the guidance. The statutory period is *"the period of 5
years ending with the date of the application"* (`BNA_1981_SCH1` para 1(2)(a)).
A five-year period ending 05/01/2022 **begins** on 06/01/2017, because both
endpoints are inclusive. The second worked example in the guidance (s.6(2),
received 05/05/2021 → present on 06/05/2018) confirms the same construction.

Therefore:

```
qualifying_period_start = application_date − 5 years + 1 day
qualifying_period_end   = application_date
```

A naive `application_date − 5 years` is **wrong by one day**, and it is wrong in
the most consequential place in the product: the physical-presence anchor date.
An applicant who flew out on that date passes under the correct rule and fails
under the naive one, or vice versa.

Treat this as the single highest-value test in the suite.

---

## 4. Canonical Date Semantics

All dates are calendar `DATE` values with no timezone. No rule in this
specification uses a timestamp.

### 4.1 Year arithmetic **[PRODUCT]**

Use `dateutil.relativedelta` semantics: subtracting *n* years from a date yields
the same month and day *n* years earlier, clamped to the last valid day of the
month where that date does not exist.

The only case where clamping applies is 29 February.

| Application date | − 5 years | Clamped | `+ 1 day` → qualifying start |
|---|---|---|---|
| 2027-04-15 | 2022-04-15 | — | 2022-04-16 |
| 2028-02-29 | 2023-02-29 (invalid) | 2023-02-28 | 2023-03-01 |
| 2027-03-01 | 2022-03-01 | — | 2022-03-02 |
| 2028-03-01 | 2023-03-01 | — | 2023-03-02 |

Guidance does not address the 29 February case. This document commits to
clamping, and any case whose application date is 29 February carries a
`LEAP_DAY_BOUNDARY_ASSUMPTION` limitation at `INFORMATION` severity so the
assumption is visible rather than hidden.

### 4.2 Windows

```
qualifying_period = [application_date − 5y + 1d,  application_date]     # inclusive
final_year        = [application_date − 1y + 1d,  application_date]     # inclusive
physical_presence_date = qualifying_period.start
```

`final_year` spans exactly 365 days (366 across a leap day). Both windows are
closed intervals.

> The final-year window is 365 days: `[application_date − 1y + 1d, application_date]`.
> (`Evidence_First_Citizenship_Workspace_UI_UX.md` §7.2 was corrected to
> `16 April 2026 – 15 April 2027` on 2026-07-23; earlier drafts showed a 366-day
> window.)

---

## 5. Absence Day Counting

### 5.1 The rule **[GUIDANCE]**

`GUIDE_AN`, "Absences from the UK":

> We only count whole days' absences from the UK. We will not count the dates
> when you leave and enter the UK as absences. For example, if you left the UK
> on 22 September and returned on 23 September you will not be classed as having
> been absent from the UK.

`DISCRETION` states the same rule in caseworker terms.

### 5.2 Set semantics **[PRODUCT]**

Model a trip not as a scalar count but as a **set of absent dates**:

```
absent_dates(trip) = { d : departure_date < d < return_date }
```

Both endpoints excluded. For a trip departing 22 September and returning 23
September the set is empty — matching the guidance example exactly.

Totals are the **cardinality of the union** across trips, intersected with the
relevant window:

```
total_absence_days      = | ( ⋃ absent_dates(t) for t in trusted_trips ) ∩ qualifying_period |
final_year_absence_days = | ( ⋃ absent_dates(t) for t in trusted_trips ) ∩ final_year |
```

Union rather than summation is deliberate, and it buys three properties for free:

- **Overlapping trips do not double-count.** Overlap still raises an issue
  (it indicates a data problem), but it does not corrupt the number.
- **Duplicate records are idempotent.** Re-importing a CSV cannot inflate a total.
- **The monotonicity invariant holds by construction.** "Adding one confirmed
  absence day never decreases the total" is true of set union and would *not* be
  reliably true of naive summation with clipping.

That last point matters: one of your mandatory Hypothesis properties is only
provable because of this modelling choice.

### 5.3 Window clipping

Intersection handles boundary-straddling trips without special cases. A trip
that departs before `qualifying_period.start` and returns inside it contributes
only the absent dates falling within the window.

### 5.4 Reference implementation

```python
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


def absent_dates(departure: date, return_: date) -> set[date]:
    """Whole days outside the UK. Departure and return days count as UK days."""
    if return_ <= departure:
        return set()
    n = (return_ - departure).days - 1
    return {departure + timedelta(days=i + 1) for i in range(n)}


def window(application_date: date, years: int) -> tuple[date, date]:
    """Closed interval of `years` ending with the application date."""
    start = application_date - relativedelta(years=years) + timedelta(days=1)
    return start, application_date


def count_in_window(trips, application_date: date, years: int) -> int:
    start, end = window(application_date, years)
    union: set[date] = set()
    for t in trips:
        union |= absent_dates(t.departure_date, t.return_date)
    return sum(1 for d in union if start <= d <= end)
```

For a five-year case the union is at most a few hundred dates; set materialisation
is acceptable and far easier to reason about than interval arithmetic. Revisit
only if profiling shows a problem.

---

## 6. Input Trust Gating

### 6.1 Trusted inputs **[PRODUCT]**

A `TravelRecordVersion` enters a **trusted** assessment only when all hold:

```
lifecycle_status = ACTIVE
review_state     = CONFIRMED
date_confidence  = EXACT
```

Anything else — `UNCERTAIN`, `ESTIMATED`, `CONFLICTING`, `DRAFT` — is excluded
from trusted totals and may appear only in provisional previews.

### 6.2 The sensitivity rule **[PRODUCT]** — the anti-false-reassurance mechanism

Excluding uncertain records is necessary but not sufficient. A case with 51
confirmed absence days and three unrecorded trips is *not* comfortably within
threshold, and reporting `SUPPORTED` on the confirmed subset alone would be
exactly the false reassurance the product exists to prevent.

So every threshold rule computes **two** figures:

```
trusted_total     = union over CONFIRMED + EXACT records only
provisional_total = union over all ACTIVE records, uncertain included
```

and applies:

> If `trusted_total` falls in a satisfied or near band, but `provisional_total`
> would fall in a worse band, the conclusion is **downgraded** to the band implied
> by `provisional_total`, capped at `INCOMPLETE`, and carries a
> `UNCONFIRMED_RECORDS_AFFECT_CONCLUSION` limitation at `REVIEW_REQUIRED` severity.

The conclusion is never *upgraded* by provisional data. Uncertainty can only make
the answer more cautious.

**Summary code when capped [PRODUCT].** When the downgrade is *capped* to `INCOMPLETE`
(the provisional band is more severe than `INCOMPLETE`), the result carries the
rule's `*_UNCONFIRMED_REVIEW` summary code, **not** the provisional band's failure
code. Otherwise an `INCOMPLETE` conclusion would show an `…_EXCEEDED` headline that
overstates unconfirmed data. When the downgrade is *not* capped (e.g. to
`REQUIRES_JUDGEMENT`), the summary code is the provisional band's code, which matches
the conclusion. Either way the `UNCONFIRMED_RECORDS_AFFECT_CONCLUSION` limitation
carries `{trusted_days, provisional_days}` and the affected record ids.

This single rule is the largest contributor to a low false-reassurance rate, and
it should have its own eval fixture.

---

## 7. Requirement Rules

Each rule below gives its key, inputs, computation, conclusion banding, summary
codes, and citations. All rule versions in this document are `1.0.0` within rule
set `2026.07.0`.

---

### 7.1 `route.adult_applicant`

**[GUIDANCE]** `GUIDE_AN`: applicant must be aged 18 or over when they apply.

**Inputs:** `applicant.date_of_birth`, current application date.

```
age_at_application = years between date_of_birth and application_date
```

**[PRODUCT]** Age attainment for a 29 February birth uses the UK convention — the
applicant attains the next year of age on **1 March** in a non-leap year, not 28
February. This deliberately differs from the §4.1 `relativedelta` clamping used for
qualifying-period *window* arithmetic (which clamps to 28 February): window
boundaries and age attainment are separate computations.

| Condition | Conclusion |
|---|---|
| `age ≥ 18` | `SUPPORTED` |
| `age < 18` | `NOT_CURRENTLY_SATISFIED` + route unsupported (registration, not naturalisation) |
| DOB missing | `NOT_YET_ASSESSED` |

Summary codes: `ROUTE_ADULT_CONFIRMED`, `ROUTE_APPLICANT_UNDER_18`.

---

### 7.2 `route.supported_status`

**[GUIDANCE]** `GUIDE_AN`, "Lawful Residence" and "Immigration time restrictions":
ILR, indefinite leave to enter, or EUSS settled status normally satisfies both
lawful residence and freedom from time restrictions.

| `status_type` | Conclusion |
|---|---|
| `ILR`, `ILE`, `EU_SETTLED_STATUS` | `SUPPORTED` |
| `OTHER` | `PROFESSIONAL_REVIEW_RECOMMENDED` — route unsupported |
| `UNKNOWN` / absent | `NOT_YET_ASSESSED` |

**[PRODUCT]** Pre-settled status is explicitly out of scope and must stop
onboarding, per MVP §4.2. Withdrawal Agreement automatic permanent residence is
also unsupported — `GUIDE_AN` notes such applicants must still evidence lawful
residence across the whole period, which the MVP does not model.

Summary codes: `STATUS_TYPE_SUPPORTED`, `STATUS_TYPE_UNSUPPORTED`,
`STATUS_PRE_SETTLED_UNSUPPORTED`.

---

### 7.2b `route.standard_section_6_1`

**[PRODUCT]** Composite guard confirming the case fits the one supported route:
standard five-year Section 6(1), single applicant, not the spouse/civil-partner
route, and not a possible existing British citizen. This rule is where onboarding
"stop" conditions become an assessment conclusion rather than being handled only
in the UI.

**Inputs:** `route_profile.married_to_british_citizen`,
`route_profile.may_already_be_british`, and the conclusions of
`route.adult_applicant` and `route.supported_status`.

| Condition | Conclusion |
|---|---|
| not spouse-route, not may-be-British, adult + status both `SUPPORTED` | `SUPPORTED` |
| `married_to_british_citizen = true` | `PROFESSIONAL_REVIEW_RECOMMENDED` — spouse route unsupported |
| `may_already_be_british = true` | `REQUIRES_JUDGEMENT` — may not need naturalisation |
| `route.adult_applicant` or `route.supported_status` not satisfied | `NOT_CURRENTLY_SATISFIED` |
| route profile not confirmed | `NOT_YET_ASSESSED` |

**Dependencies:** `ROUTE_PROFILE` (any current version), plus the two named
upstream requirement results.

Summary codes: `ROUTE_STANDARD_CONFIRMED`, `ROUTE_SPOUSE_UNSUPPORTED`,
`ROUTE_MAY_BE_BRITISH`, `ROUTE_PREREQUISITES_UNMET`.

---

### 7.3 `status.holding_period`

**[GUIDANCE]** `GUIDE_AN`: under the five-year route the applicant must be free
from immigration time restrictions on the date of application **and for the
12-month period before it**.

**Inputs:** `immigration.status_granted_on`, application date.

```
earliest_application_date = status_granted_on + 1 year
```

| Condition | Conclusion |
|---|---|
| `application_date ≥ earliest + 7 days` | `SUPPORTED` |
| `earliest ≤ application_date < earliest + 7 days` | `SUPPORTED` + `STATUS_PERIOD_NARROW_MARGIN` limitation (`CAUTION`) |
| `application_date < earliest` | `NOT_CURRENTLY_SATISFIED`, with `earliest_application_date` returned |
| `status_granted_on` missing | `INCOMPLETE` |

**[PRODUCT]** A `status_granted_on` of 29 February adds one year with the §4.1
`relativedelta` clamp (→ 28 February in a non-leap year), the same semantics as the
qualifying-period window. This is the permissive direction (the earliest date lands one
day earlier than a strict anniversary) and deliberately differs from the §7.1
age-attainment convention (1 March); the effect is at most one day on a rare input.

**[PRODUCT]** The seven-day caution band exists because guidance does not state
the boundary to the day, and because "the date the application is received" is
not fully within the applicant's control. The product surfaces the margin rather
than asserting a same-day pass.

`NOT_CURRENTLY_SATISFIED` must return `earliest_application_date` as a structured
parameter so the UI can offer a forward-planning date instead of a dead end.

Summary codes: `STATUS_PERIOD_SATISFIED`, `STATUS_PERIOD_NARROW_MARGIN`,
`STATUS_PERIOD_NOT_YET_MET`.

---

### 7.4 `residence.qualifying_period`

Derives and exposes the window. Always `SUPPORTED` once an application date
exists — it is a calculation, not a test — but it owns the breakdown that every
other residence rule cites.

**Breakdown payload:**

```json
{
  "application_date": "2027-04-15",
  "qualifying_period_start": "2022-04-16",
  "qualifying_period_end": "2027-04-15",
  "final_year_start": "2026-04-16",
  "final_year_end": "2027-04-15",
  "physical_presence_date": "2022-04-16",
  "derivation": "application_date - 5 years + 1 day"
}
```

| Condition | Conclusion |
|---|---|
| application date present | `SUPPORTED` |
| absent | `NOT_YET_ASSESSED` |

Summary code: `QUALIFYING_PERIOD_DERIVED`.

---

### 7.5 `residence.physical_presence_start_date`

**[GUIDANCE]** `GUIDE_AN`: must have been physically present in the UK (including
the Isle of Man or Channel Islands) on the day five years before the application
is received.

```
present = physical_presence_date ∉ union(absent_dates(t) for t in trusted_trips)
```

Because departure and return days count as UK days (§5.1), a trip *departing* on
the anchor date still satisfies presence, as does one *returning* on it. This
falls out of the set model with no special-casing — but it is
counter-intuitive enough to deserve its own tests.

| Condition | Conclusion |
|---|---|
| anchor date not in absent union | `SUPPORTED` |
| anchor date in absent union (trusted) | `NOT_CURRENTLY_SATISFIED` |
| anchor date in absent union (provisional only) | `INCOMPLETE` + `UNCONFIRMED_RECORDS_AFFECT_CONCLUSION` |
| no application date | `NOT_YET_ASSESSED` |

**[PRODUCT]** On `NOT_CURRENTLY_SATISFIED`, the rule must also return the nearest
alternative application dates whose anchor date is not an absent date — searching
forward up to 90 days. `GUIDE_AN` itself notes the Home Office "may see if there
is another, later date we can use." Offering the resolved date turns a refusal
into an action, and it is the moment the demo flow hinges on.

Summary codes: `PRESENCE_CONFIRMED`, `PRESENCE_NOT_SUPPORTED`,
`PRESENCE_UNCERTAIN`.

---

### 7.6 `residence.total_absences`

**[GUIDANCE]** `GUIDE_AN`: no more than **450 days** outside the UK in the
five-year qualifying period. Discretion tiers from the same source:

| Band | Guidance position |
|---|---|
| ≤ 450 | Normal permitted absences |
| ≤ 480 | Normally disregarded |
| ≤ 900 | Disregarded only if all other requirements met and home, family and a substantial part of estate are in the UK. Above 730 days, residence of 8 years normally expected |
| > 900 | Only very rarely disregarded; application likely to fail |

`DISCRETION` adds: where the applicant exceeds the permitted absence by 30 days
or less, the caseworker **must** exercise discretion unless there are other
grounds for refusal.

**Banding [PRODUCT]:**

| `total_absence_days` | Conclusion |
|---|---|
| 0 – 420 | `SUPPORTED` |
| 421 – 450 | `NEAR_THRESHOLD` |
| 451 – 480 | `REQUIRES_JUDGEMENT` |
| 481 – 900 | `PROFESSIONAL_REVIEW_RECOMMENDED` |
| > 900 | `NOT_CURRENTLY_SATISFIED` + `PROFESSIONAL_REVIEW_RECOMMENDED` |

The 30-day near band mirrors the Home Office's own must-exercise-discretion
margin, which makes it defensible rather than arbitrary.

Note that exceeding 450 is deliberately **not** `NOT_CURRENTLY_SATISFIED`.
Guidance says discretion is normally exercised up to 480, and asserting failure
where the Home Office would normally grant is its own kind of harm.

The sensitivity rule (§6.2) applies.

Summary codes: `TOTAL_ABSENCES_WITHIN_THRESHOLD`,
`TOTAL_ABSENCES_NEAR_THRESHOLD`, `TOTAL_ABSENCES_DISCRETION_LIKELY`,
`TOTAL_ABSENCES_REVIEW_REQUIRED`, `TOTAL_ABSENCES_EXCEEDED`, plus
`TOTAL_ABSENCES_UNCONFIRMED_REVIEW` for the §6.2 capped-downgrade state (see below).

Parameters on every code: `{days, threshold, window_start, window_end, trip_count}`,
with `provisional_days` added whenever the sensitivity rule runs.

---

### 7.7 `residence.final_year_absences`

**[GUIDANCE]** `GUIDE_AN`: no more than **90 days** outside the UK in the final
12 months. Discretion tiers:

| Band | Guidance position |
|---|---|
| ≤ 90 | Normal permitted |
| ≤ 100 | Normally disregarded |
| 101 – 179 | Disregarded where UK links (family, home, substantial estate) are demonstrated, or where justified by Crown service or compelling occupational/compassionate reasons |
| ≥ 180 | Only in the most exceptional circumstances |

**Banding [PRODUCT]:**

| `final_year_absence_days` | Conclusion |
|---|---|
| 0 – 75 | `SUPPORTED` |
| 76 – 90 | `NEAR_THRESHOLD` |
| 91 – 100 | `REQUIRES_JUDGEMENT` |
| 101 – 179 | `PROFESSIONAL_REVIEW_RECOMMENDED` |
| ≥ 180 | `NOT_CURRENTLY_SATISFIED` + `PROFESSIONAL_REVIEW_RECOMMENDED` |

The near band here is 15 days rather than 30 — proportionally wider (16.7% vs
6.7%) because a single forgotten fortnight abroad flips the result, and because
the final-year limit is the more common cause of refusal.

The sensitivity rule (§6.2) applies.

Summary codes (the §7.6 set with the `TOTAL_ABSENCES_` stem replaced by
`FINAL_YEAR_`): `FINAL_YEAR_WITHIN_THRESHOLD`, `FINAL_YEAR_NEAR_THRESHOLD`,
`FINAL_YEAR_DISCRETION_LIKELY`, `FINAL_YEAR_REVIEW_REQUIRED`, `FINAL_YEAR_EXCEEDED`,
plus `FINAL_YEAR_UNCONFIRMED_REVIEW` for the §6.2 capped-downgrade state.

---

### 7.8 `residence.travel_consistency`

**[PRODUCT]** Data-quality rule. Produces no eligibility conclusion of its own;
it exists to surface problems that would otherwise silently distort the totals.

Detections, each raising a typed issue:

| Detection | Issue type |
|---|---|
| `departure_date > return_date` | rejected at validation, never persisted |
| Two active trips whose absent-date sets intersect | `OVERLAPPING_TRAVEL` |
| Two active trips with identical dates and destination | `DUPLICATE_TRAVEL_RECORD` (see below) |
| Trip with `date_confidence ∈ {ESTIMATED, UNKNOWN}` inside the qualifying period | `UNCERTAIN_TRAVEL_DATE` |
| Trip whose absent-date set contains `physical_presence_date` | `NEAR_THRESHOLD` (boundary-critical) |
| Confirmed trip with no available evidence link | `MISSING_EVIDENCE` (`INFORMATION` severity) |
| Trip wholly outside the qualifying period | informational only; excluded from totals |

| Condition | Conclusion |
|---|---|
| no detections | `SUPPORTED` |
| only informational detections | `SUPPORTED` + limitations |
| overlaps or conflicts present | `INCONSISTENT` |
| uncertain dates present | `INCOMPLETE` |

Summary codes: `TRAVEL_RECORDS_CONSISTENT`, `TRAVEL_RECORDS_OVERLAP`,
`TRAVEL_RECORDS_CONFLICT` (a `CONFLICTING` date confidence, distinct from a set overlap),
`TRAVEL_RECORDS_UNCERTAIN`, `TRAVEL_RECORDS_UNEVIDENCED`. Detection limitation codes:
`CONFLICTING_SOURCE_DATES`, `OVERLAPPING_TRAVEL`, `UNCERTAIN_TRAVEL_DATE`,
`NEAR_STANDARD_THRESHOLD` (boundary-critical), `TRAVEL_OUTSIDE_WINDOW` (`INFORMATION`),
`MISSING_TRAVEL_EVIDENCE` (`INFORMATION`).

**"Available evidence link" [PRODUCT], M7.** Deliberately not the name of a table. A trip
is evidenced when *some* link of `availability = AVAILABLE` points at it. At M7 that means
an `EvidenceTravelLink` (Domain §11.9), which attaches a document directly to a travel
record. At M8, `FactEvidenceLink` (Domain §22) joins it, attaching a document to a fact
version. The rule asks the same question of a wider graph rather than being rewritten, and
neither link kind is privileged over the other.

Earlier drafts of this row named `FactEvidenceLink` specifically. That was wrong in a way
worth recording: `FactEvidenceLink` hangs off `FactVersion`, so a spec written that way
made an M7 detection depend on an M8 entity, and the detection could not be built at all
until facts existed — for no reason connected to what it actually measures.

**Coverage is not window-scoped**, unlike the `CONFLICTING` and `{ESTIMATED, UNKNOWN}`
detections below. A trip wholly outside the qualifying period still appears in the user's
travel history and is still a trip they may be asked to evidence; suppressing its coverage
state would make the history's support column silently incomplete. What is window-scoped is
whether a *questionable date* can distort a total, which is a different question.

**M3B scope note [PRODUCT].** At M3B this rule detects conflicts (`CONFLICTING` confidence),
overlaps (intersecting absent-date sets, which also catches identical-date duplicates),
uncertain dates, boundary-critical trips, and out-of-window trips. "Inside the qualifying
period" is read as *the trip has at least one absent day within the window*; a trip wholly
outside the window is informational only. Both `CONFLICTING` and `{ESTIMATED, UNKNOWN}`
detections are window-scoped this way, so a questionable date on out-of-window history that
cannot affect the assessment is not surfaced as an inconsistency. This rule creates
structured limitations, not `Issue` rows — issue derivation is M6.

**Deferral status [PRODUCT], corrected at M7.** An earlier version of this note said
destination-aware `DUPLICATE_EVIDENCE` and the unevidenced-trip `MISSING_EVIDENCE`
detection "arrive in M4". Both halves were wrong. `destination_country_code` has existed on
`TravelRecordVersion` since M3B, so the duplicate detection was never blocked on a field;
and M4 shipped without either. Current status:

- `MISSING_EVIDENCE` (unevidenced trip) — **M7 slice 4a**, against `EvidenceTravelLink`.
- Duplicate travel records (identical dates *and* destination) — **M7 slice 4b**, and see
  the note below on the issue type it raises.

**The `DUPLICATE_EVIDENCE` row names a duplicate *travel record*, not a duplicate
document.** Two unlike detections had collected under one issue type: this one, where the
user has entered the same trip twice, and Domain §15's checksum collision, where the user
has uploaded the same file twice. They have different causes, different affected objects,
and different remedies — merge two trips, versus delete a redundant upload. At M7 slice 4b
they split: this row raises `DUPLICATE_TRAVEL_RECORD`, and `DUPLICATE_EVIDENCE` keeps the
meaning its name implies.

---

### 7.9 `knowledge.life_in_uk`

**[GUIDANCE]** `GUIDE_AN`: satisfied by passing the Life in the UK test. No
expiry. Exemption at 65+ or where a long-term physical or mental condition
prevents compliance. EUSS settled-status holders will not have met it at
settlement and must meet it before naturalising.

| `completion_state` | Conclusion |
|---|---|
| `COMPLETED` with reference value | `SUPPORTED` |
| `COMPLETED` without reference value | `INCOMPLETE` |
| `NOT_PROVIDED` | `INCOMPLETE` |
| `EXEMPTION_CLAIMED` | `REQUIRES_JUDGEMENT` |
| `UNKNOWN` | `NOT_YET_ASSESSED` |

**[PRODUCT]** Age-based exemption is *not* auto-applied even when DOB implies
65+. The MVP records preparation state; it does not adjudicate exemptions.

Summary codes: `LIUK_RECORDED`, `LIUK_MISSING`, `LIUK_EXEMPTION_CLAIMED`.

---

### 7.10 `knowledge.english_language`

**[GUIDANCE]** `GUIDE_AN`, "Knowledge of Language requirement". Satisfied by any
of: an approved SELT at **B1 CEFR or higher**; a UK degree taught in English; a
qualifying overseas degree with Ecctis confirmation; a qualifying postgraduate
diploma; nationality of a listed majority-English-speaking country; or an ILR
granted on the basis of a B1 qualification.

Critically, and deterministically checkable:

> Test results are only valid for two years from the date the test is taken. Once
> the validity of your test expires after two years, the qualification cannot be
> relied upon to support your application to naturalise.

**Rule:**

```
if evidence_route == SELT:
    selt_expires_on = test_completed_on + 2 years
    valid = application_date <= selt_expires_on
```

| Condition | Conclusion |
|---|---|
| SELT, B1+, `application_date ≤ expiry − 30 days` | `SUPPORTED` |
| SELT, B1+, within 30 days of expiry | `NEAR_THRESHOLD` + `SELT_EXPIRING_SOON` |
| SELT, B1+, expired at application date | `NOT_CURRENTLY_SATISFIED` |
| SELT below B1 | `NOT_CURRENTLY_SATISFIED` |
| Degree / nationality / ILR-B1 route | `REQUIRES_JUDGEMENT` |
| `EXEMPTION_CLAIMED` | `REQUIRES_JUDGEMENT` |
| `NOT_PROVIDED` | `INCOMPLETE` |

**[PRODUCT]** Only the SELT path is adjudicated deterministically, because only it
has an unambiguous machine-checkable condition. Every other route routes to
`REQUIRES_JUDGEMENT` — the MVP records that a claim exists without ruling on
Ecctis equivalence or nationality lists.

The SELT expiry check is a genuinely useful deterministic result: an applicant
who took B1 three years ago and assumes they are covered is a realistic and
costly failure mode, and this catches it. **[PRODUCT]** The 30-day warning band
accounts for processing time between preparation and submission.

Summary codes: `ENGLISH_SELT_VALID`, `ENGLISH_SELT_EXPIRING`,
`ENGLISH_SELT_EXPIRED`, `ENGLISH_LEVEL_INSUFFICIENT`,
`ENGLISH_ALTERNATIVE_ROUTE_REVIEW`, `ENGLISH_MISSING`.

---

### 7.11 `referees.first` and `referees.second`

**[GUIDANCE]** `GUIDE_AN`, "Referees". Two referees required.

- One referee may be of any nationality but **must be a professional person**.
- The other **must hold a British citizen passport** and be **either** a
  professional person **or** over the age of 25.
- **Each referee must have known the applicant for at least 3 years.**
- Neither may be related to the applicant, related to the other referee, the
  applicant's solicitor or agent, or employed by the Home Office.
- A referee with an imprisonable conviction in the last 10 years is not usually
  accepted.

**Per-slot completeness [PRODUCT]:**

| Condition | Conclusion |
|---|---|
| all recorded fields present, `known_applicant_duration ≥ 3 years`, no disqualifier | `SUPPORTED` |
| fields present but duration `< 3 years` | `NOT_CURRENTLY_SATISFIED` |
| any disqualifier answered `true` | `NOT_CURRENTLY_SATISFIED` |
| slot empty | `INCOMPLETE` |
| combination cannot be evaluated (e.g. professional status ambiguous) | `REQUIRES_JUDGEMENT` |

**Cross-slot check**, evaluated on `referees.second`: at least one slot must
satisfy the British-passport-holder condition and at least one must satisfy the
professional-person condition (the same referee may satisfy both only if the
other independently meets its own requirement). Failure →
`NOT_CURRENTLY_SATISFIED` with `REFEREE_COMBINATION_INVALID`.

**[PRODUCT]** The MVP does not adjudicate what constitutes a "professional
person" — it records the user's answer. Anything ambiguous escalates rather than
concludes. This is a deliberate boundary; MVP §5.4 excludes a full referee
eligibility engine.

Summary codes: `REFEREE_COMPLETE`, `REFEREE_MISSING`,
`REFEREE_DURATION_INSUFFICIENT`, `REFEREE_DISQUALIFIED`,
`REFEREE_COMBINATION_INVALID`.

---

### 7.12 `character.review`

**[PRODUCT]** The MVP records acknowledgement only and never adjudicates.

| Condition | Conclusion |
|---|---|
| `character.review_acknowledged = true`, no disclosure | `SUPPORTED` |
| any disclosure present | `PROFESSIONAL_REVIEW_RECOMMENDED` |
| not acknowledged | `INCOMPLETE` |

Never `NOT_CURRENTLY_SATISFIED`. The product has no standing to conclude a
person is not of good character.

Summary codes: `CHARACTER_ACKNOWLEDGED`, `CHARACTER_DISCLOSURE_PRESENT`,
`CHARACTER_NOT_REVIEWED`.

---

### 7.13 `preparation.case_complete`

Aggregate. Derived, never independently calculated.

**Reads results only, never issues.** An earlier version of this table also required "no
open blocking issues". It must not: issues are derived *from* results, so a rule reading
issues makes results depend on issues depend on results, which breaks the issue reconciler's
idempotency guarantee and puts this rule on the wrong side of "an issue never directly
changes an assessment conclusion" (CLAUDE.md §2). Nothing is lost — an issue is a projection,
so a blocking issue's cause is already present as a limitation or conclusion on the result it
was derived from. See §8 and ADR-0014.

| Condition | Conclusion |
|---|---|
| all other current results `SUPPORTED` | `SUPPORTED` |
| any `NOT_CURRENTLY_SATISFIED` | `NOT_CURRENTLY_SATISFIED` |
| any `PROFESSIONAL_REVIEW_RECOMMENDED` | `PROFESSIONAL_REVIEW_RECOMMENDED` |
| any `INCONSISTENT` | `INCONSISTENT` |
| any `INCOMPLETE` or `NOT_YET_ASSESSED` | `INCOMPLETE` |
| any `NEAR_THRESHOLD` or `REQUIRES_JUDGEMENT`, others supported | `NEAR_THRESHOLD` |
| **any current result `STALE`** | `NOT_YET_ASSESSED` + `STALE_INPUTS_PRESENT` |

Severity ordering, most to least severe:

```
NOT_CURRENTLY_SATISFIED
PROFESSIONAL_REVIEW_RECOMMENDED
INCONSISTENT
INCOMPLETE
REQUIRES_JUDGEMENT
NEAR_THRESHOLD
NOT_YET_ASSESSED
SUPPORTED
```

Summary code: `PREPARATION_STATE_DERIVED` with a per-group state map.

---

## 8. Rule Dependency Matrix

Drives selective invalidation (Domain Model §41.5, roadmap M6).

| Rule | Depends on |
|---|---|
| `route.adult_applicant` | `applicant.date_of_birth`, application date |
| `route.supported_status` | `immigration.status_type` |
| `route.standard_section_6_1` | `route_profile` (spouse / may-be-British answers), plus the results of `route.adult_applicant` and `route.supported_status` |
| `status.holding_period` | `immigration.status_granted_on`, application date |
| `residence.qualifying_period` | application date |
| `residence.physical_presence_start_date` | application date, **all** active travel records |
| `residence.total_absences` | application date, **all** active travel records |
| `residence.final_year_absences` | application date, **all** active travel records |
| `residence.travel_consistency` | **all** active travel records, application date, **all** active evidence links (from v2.0.0, M7) |
| `knowledge.life_in_uk` | Life in the UK knowledge record |
| `knowledge.english_language` | English knowledge record, application date |
| `referees.first` | referee slot FIRST, referee slot SECOND (cross-check) |
| `referees.second` | referee slot SECOND, referee slot FIRST (cross-check) |
| `character.review` | `character.review_acknowledged` |
| `preparation.case_complete` | all current assessment results |

Five consequences worth noting.

**The evidence fan-out is one, and that narrowness is the point.** `EVIDENCE_SUPPORT` is
declared by `residence.travel_consistency` alone. Attaching or removing a document must
stale the consistency verdict and **must not** touch `residence.total_absences`,
`residence.final_year_absences`, or the physical-presence date — those read travel records,
and a document is not a travel record. A user who deletes a booking has not changed how
many days they were absent; they have changed how well supported their own account of it
is. Collapsing the two would make every upload invalidate the whole residence group, which
is over-firing of exactly the kind ADR-0014 exists to prevent, and it would teach the user
that the totals are less stable than they are.

**The application-date fan-out is nine, not eight.** Eight requirements above name
the application date directly. `route.standard_section_6_1` names none of its own —
it composes `route.adult_applicant`, which does — so the full closure is **nine**.
Count the direct dependants and the composite separately; conflating them is how the
composite gets dropped from an invalidation set.

> `preparation.case_complete` is excluded from every count in this section. It composes
> *all* current results (and reacts to their currency, per §7.13), so it is in every
> non-empty closure — including it would add one to every number here and distinguish
> nothing. Its edges land with its evaluator; until then it has no rule version and resolves
> to nothing.

> Implemented today the number is **eight**: seven declared dependants plus the
> composite, because `knowledge.english_language` has no evaluator yet. Those two
> eights are not the same eight. `test_selective_invalidation.py` therefore *derives*
> the expected set from the declaration rows plus composition closure, treating the
> literal as a sanity check that carries its own derivation — so giving
> `english_language` an evaluator raises the count honestly rather than looking like a
> regression against this section.

**The referee slots are mutually dependent** because of the cross-slot combination
check. That mutuality is expressed as a `REFEREE_RECORD` *input* dependency on both
sides — each slot reads the other slot's recorded fields, not its conclusion — so it is
matched in a single pass and is not a composition cycle.

**Composition closure must run to a fixed point** all the same, because chains can be
deeper than one hop: once `preparation.case_complete` has an evaluator,
`case_complete → standard_section_6_1 → adult_applicant` is two hops, and a single-level
expansion would under-fire on it.

**`route.standard_section_6_1` is the only requirement that depends on other
requirements' *conclusions*** rather than on raw inputs; invalidating either upstream
result must re-evaluate it. Since ADR-0014 that edge is declared in
`rule_composition_edges` (Domain §25.4) rather than left implicit.

**`preparation.case_complete` depends on current results only.** An earlier version of
this table had it depending on open issues as well. It must not: issues are *derived
from* results, so a rule reading issues makes results depend on issues depend on
results. That cycle breaks the issue reconciler's idempotency guarantee, and it puts a
rule on the wrong side of "an issue never directly changes an assessment conclusion"
(CLAUDE.md §2). Nothing is lost — an issue is a projection, so everything it could tell
this rule is already present in the results and limitations it was derived from.

---

## 9. Worked Example

Application date **15 April 2027**, EU settled status granted **1 March 2025**.

**Windows:**

```
qualifying_period      2022-04-16 → 2027-04-15
final_year             2026-04-16 → 2027-04-15
physical_presence_date 2022-04-16
```

**Trips (all confirmed, exact):**

| Destination | Departure | Return | Absent dates | Days |
|---|---|---|---|---|
| Spain | 2022-04-14 | 2022-04-20 | 15–19 Apr 2022 | 5 |
| Italy | 2026-05-04 | 2026-05-10 | 5–9 May 2026 | 5 |
| United States | 2026-05-16 | 2026-05-29 | 17–28 May 2026 | 12 |

**`residence.physical_presence_start_date`:** the Spain trip's absent set (15–19 Apr
2022) contains 2022-04-16 → the anchor date **is** an absent date →
`NOT_CURRENTLY_SATISFIED`. The return day 2022-04-20 is a UK day (§5.1), so it is the
first clear anchor: forward search finds 2027-04-19 (anchor 2022-04-20, outside the
Spain set) as the nearest resolving date. This is precisely the "move the application
date" moment in the demo script. (Corrected 2026-08-12 from an earlier off-by-one that
read 2027-04-20 / anchor 2022-04-21; the return day counts as present, so the first
clear anchor is the return day itself — the same construction the demo case §8 uses to
land on 2027-04-25 for its longer trip 1.)

**`status.holding_period`:** earliest = 2025-03-01 + 1y = 2026-03-01.
15 Apr 2027 ≥ 2026-03-08 → `SUPPORTED`.

**`residence.final_year_absences`:** Italy 5 + US 12 = **17 days**, both wholly
inside the final year. 17 ≤ 75 → `SUPPORTED`.

**Boundary check on Spain:** departure 14 Apr 2022 is *before* the qualifying
period start (16 Apr 2022), return is inside. Intersection yields only 16–19 Apr
2022 = 4 days counted toward `total_absences`, not 5. The 15 Apr absent date
falls outside the window and is correctly excluded.

This example alone exercises the off-by-one, boundary clipping,
exclusive-endpoint counting, and the presence-anchor interaction. Make it fixture
number one.

---

## 10. Mandatory Test Properties

Beyond the invariants already listed in `CLAUDE.md` §9:

```
qualifying_period_start == application_date − 5 years + 1 day, for all dates
  including 29 February and 1 March in leap and non-leap years.

The Guide AN worked example holds exactly:
  application 2022-01-05 → presence date 2017-01-06.

A trip departing on day D and returning on day D+1 contributes zero absent days.

A trip departing exactly on the physical-presence date satisfies presence.
A trip returning exactly on the physical-presence date satisfies presence.
A trip spanning the physical-presence date does not.

Absence totals are invariant under re-ordering of the travel record list.

Adding a duplicate of an existing trip changes no total.

Two overlapping trips contribute the cardinality of their union, never the sum.

Clipping is exact: a trip straddling a window boundary contributes only the
  absent dates inside the window.

trusted_total <= provisional_total, always.

A conclusion is never upgraded by provisional data.

Every banding function is monotonic: more absence days never yields a
  less severe conclusion.
```

Hypothesis strategies should generate application dates across 2024–2032, trips
of 0–400 days at random offsets, and deliberately clustered dates within ±3 days
of every window boundary.

---

## 11. Open Questions Deferred

- **Isle of Man and Channel Islands.** `GUIDE_AN` treats presence there as UK
  presence for the anchor date. The MVP does not model them as distinct
  destinations; a trip recorded to Jersey counts as an absence. Documented
  limitation, `INFORMATION` severity. Revisit only if a test case demands it.
- **Future intentions** (`GUIDE_AN`: an absence of 6+ continuous months casts
  doubt). A deterministic 180-day continuous-absence detector is cheap and would
  raise `REQUIRES_JUDGEMENT`. Deferred to post-MVP; noted because it is one of
  the few remaining deterministic checks available.
- **Crown service alternative routes.** Out of scope; must stop onboarding.
- **Earned citizenship transition.** No implementation until rules are laid. The
  rule-version architecture is the mitigation.

---

## 12. Rule Set Versioning

This document defines rule set `2026.07.0`. Each requirement's `RuleVersion`
carries `semantic_version = 1.0.0`, `rule_set = 2026.07.0`, and links to the
guidance sections cited above.

A change to any **[GUIDANCE]** item requires a new rule set version and new rule
versions for affected requirements. A change to any **[PRODUCT]** item requires a
new rule version for the affected requirement only.

In both cases, historical assessment results retain their original rule version
and remain inspectable unchanged. That is the whole point.
