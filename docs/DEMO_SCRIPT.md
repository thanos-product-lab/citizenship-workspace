# Running the canonical demo locally

The fifteen-step demo journey, in Chrome, against the local stack. Written to be followed while
clicking, not read once.

**Two of the fifteen need something the seed does not create, and one does not exist.**
Those are called out in place rather than at the end, because discovering them mid-demo is
how a recording gets abandoned.

---

## 0. Before you start

### The stack

```bash
just up          # postgres, redis, minio, api, worker — the worker carries beat
just dev         # Next.js on :3000
```

Check both are actually up, not just started:

```bash
curl -s localhost:8000/health/ready
# {"status":"ready","checks":{"database":true,"redis":true,"ai_provider":true}}
```

**The worker matters here and its absence is silent.** It carries the outbox relay, which
is what turns an uploaded document into a processed one. Without it a document sits at
*Uploaded · Not read yet* for ever, and the screen cannot tell you the difference between
"being read" and "will never be read" — that is a known gap (M8 gate finding 3b), not
something you are doing wrong.

### Go to `/sign-in`, not `/`

`http://localhost:3000/` returns **404**. So does the deployed root. This is Clerk's
middleware on a *dev* instance: without the dev-browser handshake it rewrites an
unauthenticated request to 404 rather than redirecting. In a real browser that has
completed the handshake you will be redirected normally, but a cold tab may not be.

Start at **`http://localhost:3000/sign-in`** and sign in.

### Seed into *your* Clerk user id

`just seed` defaults to `demo-user`, which is the CLI walkthroughs' identity and **not
yours** — a case seeded to it will not appear when you sign in, because every read is
scoped by owner.

Get your id from the Clerk dashboard (Users → the `user_2ab…` value), then:

```bash
just seed user_2ab...        # your Clerk user id
# Seeded synthetic demo case <case-id> for user_2ab...
```

Keep the case id it prints — every URL below uses it.

> The suite no longer wipes this case: `just test-be` runs against its own database. You
> also no longer have to stop the worker to run tests.

### What the seed gives you, and what it does not

Twelve trips, eleven uploaded documents (trip 6, Greece, deliberately has none), an
application date of 15 April 2027, and no assessments yet.

The eleven documents are **minimal synthetic PDFs** — one line each, "Synthetic travel
document - Italy 2026-05-04". With the worker running they will be classified and read,
which is enough to demonstrate the claim → confirm path, but they carry almost nothing to
extract. For the parts of the demo that turn on a *value*, use the real fixture in step 5.

**Local extraction makes real model calls.** `ai_provider: true` above means a live key is
configured, so the eleven seeded documents will each cost a fraction of a penny to process.
`AI_DAILY_SPEND_CEILING_USD` bounds it.

---

## The fifteen steps

### 1–2. Open the case and read the overview

`http://localhost:3000/cases/<case-id>`

What to look at: the counts by named state, and the absence of any percentage, fraction or
score anywhere. The derived phase is a quiet chip beside the title — context, not a verdict.

If the overview says nothing is assessed yet, press **Recalculate** in the header. On a
fresh seed there are no assessments until something asks for them.

### 3. Inspect travel history

`/cases/<case-id>/data` — the Case data destination, twelve rows.

Then `/cases/<case-id>/timeline` for the same facts as a chronological table with a visual
band above it. The Spain row is the one to read aloud: *14–26 April 2022, 10 days*, with
"1 day of this trip falls outside your qualifying period, so 10 days count." That sentence
is the single most common reason a user's own arithmetic disagrees with the product's.

### 4. Identify a conflicting return date — **needs a manual step**

**The seed does not create the conflict.** Trip 11 (Italy, 4–10 May 2026) is seeded
`CONFIRMED` with `EXACT` dates, and nothing disputes it. The conflict is *derived* — it
exists only once a confirmed document date disagrees with the record — so it arrives in
step 7, not before.

So treat step 4 as "here is the trip the conflict will be about", and create it in 5–7.

### 5. Upload the supporting document

`/cases/<case-id>/evidence` → the upload form. Three fields: **Document file**, **Document
type**, **Display name** (prefilled from the filename).

Use the real booking rather than the seeded stub:

```
services/platform/evals/fixtures/travel/italy_booking_amended_return.pdf
```

If it is not there, generate the fixtures first:

```bash
cd services/platform && uv run python evals/fixtures/make_documents.py
```

It is a Skyline Airways e-ticket for OKONKWO / AMARA, outbound 04 May 2026, **return 11 May
2026** — one day later than trip 11's record. That one day is the whole conflict.

**Worth doing deliberately:** file it under the *wrong* Document type. The row will then
show the classifier disagreeing with you out loud — "Analysis suggests: Travel booking" —
which is the machine's reading shown *beside* yours rather than replacing it.

Then attach it to trip 11 from `/cases/<case-id>/data` (the trip row offers an attach
control). Evidence attaches to a travel record, not to a fact — ADR-0021.

### 6. Review what the model read

Wait for the row to reach **Values proposed**; it takes around twenty seconds and the
screen says nothing while it happens (M8 gate finding 3). Then follow **Confirm what we
read** → `/cases/<case-id>/evidence/<item-id>/review`.

**This is the screen the trust model rests on.** The document is on the left. On the right,
the return date field is an **empty box** — the model's reading is not on the page, because
the API does not send it. `proposed_value` is null for a pending high-risk claim. You read
the document and type what it says; the system works out afterwards whether that was a
confirmation or a correction.

Two things to try here:

- Type `11/05/2026`. The server **refuses it** and names an acceptable shape — the same
  refusal it gives a model, for the same reason: that string has two readings and nothing on
  the page settles it.
- Type `11 May 2026`. It is accepted, and because it matches what the model proposed the
  badge reads **Confirmed**. Enter `10 May 2026` instead and it reads **Corrected**, with
  the model's original proposal preserved beside it.

### 7. Confirm the value, creating the conflict

Confirming **11 May 2026** is what makes the document disagree with the record's 10 May.
The trip is now disputed: it is held back from the confirmed total rather than counted while
flagged, because counting it would apply half of RULES_SPEC §6.1 and contradict the other
half.

### 8. Watch the old assessment go stale

Back on `/cases/<case-id>/requirements`. The conclusions that declared a dependency on this
input are marked **Stale**, and the ones that did not are untouched — that selectivity is
the point. A result reads `Supported` and `Stale` **at the same time**: the conclusion was
not rewritten into something false, and the currency does not pretend nothing happened.

### 9. Recalculate

**Recalculate** in the case header. New `AssessmentRun`, new results, prior ones marked
Superseded and still inspectable. On the canonical case the total absences arc is
**439 → 434 → 440**.

### 10–11. Open a requirement and read it down

`/cases/<case-id>/requirements/residence.final_year_absences`, and
`residence.total_absences` for the fuller explanation stack.

Every layer is a real heading, so the document outline *is* the explanation structure:
**Why this assessment was made · Facts used · Travel records used · Evidence used · Rule
used · Limitations · Next action**. The disputed trip appears as *"Confirmed · conflicting
dates — Did not count towards the confirmed figure"*, and the fact that caused it is named.

Open **Assessment history** to see both earlier runs with their rule versions.

> **Known gap, visible here:** the Rule layer declares that no guidance version was
> recorded (`guidance_version_recorded: false`). The product wants a version and a
> retrieval date on every source link. It says so rather than filling it in — deferred to M9.

### 12–13. Change the application date and watch presence change

`/cases/<case-id>/data` → the application-date card.

Enter **20 April 2027** and press **Preview this date**. The window slides, the total drops
439 → 434, and physical presence is **still not satisfied**. That middle result is the one
worth pausing on: a five-day move changed the arithmetic and fixed nothing, because clearing
an absent anchor means moving past the entire trip covering it — ten days here. The screen
says *"Still not satisfied on this date"* rather than leaving you to notice.

Then take the offered **25 April 2027**. Presence flips to **Supported**, the total settles
at 429, and every conclusion carries a **Preview** badge — nothing has been written. No run,
no result, no provenance: a simulated result has no field to record any, so persisting one is
a type error rather than a guard.

**Save** it if you want the case to move; that is two requests, and between them the case is
genuinely stale.

### 14. Resolve the last open issue

`/cases/<case-id>/issues`. **Recheck now** clears the stale items at once — not through a
special case in the recalculation path, but because the reconciler finds their causes gone.
They move to Settled with their history kept.

The coverage gap on trip 6 (Greece, no document) stays open as **information, not an
action**, because nothing in the assessment depends on it. That the queue says so is the
honesty the feature is for.

> You may see the phase chip read "Resolving issues" while the queue reads "Nothing needs
> your attention". Both are correct and measure different things — the phase derives from
> requirement conclusions (ADR-0009) and this case has one that is `NOT_CURRENTLY_SATISFIED`,
> which is a requirement outcome and deliberately not an issue. Logged as a gap.

### 15. Preparation summary — **does not exist**

M10, and M10 is outside the plan of record (M0–M8 plus the release slice). There is no
screen. Fourteen of the fifteen steps run; this one is a known limitation, stated rather
than worked around.

---

## Resetting

There is no reset endpoint. Re-running the seed creates a **new** case rather than
replacing the old one:

```bash
just seed <your-clerk-user-id>
```

To remove the previous one, delete it from the UI — which since the release slice actually
completes: the objects leave MinIO and every case-scoped row goes, leaving a tombstone that
names no one. See ADR-0030.

---

## If something looks wrong

| Symptom | Cause |
|---|---|
| `/` is a 404 | Clerk dev instance without the browser handshake. Use `/sign-in`. |
| Signed in, no cases | Seeded to `demo-user` instead of your Clerk id. Reseed. |
| Document stuck at *Uploaded · Not read yet* | The worker is not running. `docker compose start worker`. |
| Upload fails, API logs look clean | MinIO is down, or `STORAGE_PUBLIC_ENDPOINT_URL` is unset so the presigned URL names `minio:9000`, which resolves only inside the compose network. |
| Document preview is an empty box | `STORAGE_ORIGIN` / the CSP `frame-src`. Locally it defaults to `http://localhost:9000`. |
