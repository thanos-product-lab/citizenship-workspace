# ADR-0030: The case purge holds the tenant throughout and borrows privilege exactly twice

**Status:** Accepted — release slice, 13 September 2026
**Resolves:** the terminal-purge deferral tracked since [ADR-0005](0005-defer-postgres-rls-to-a-hardening-slice.md)
**Related:** [ADR-0006](0006-postgres-rls-via-a-non-superuser-role.md), [ADR-0017 (migration)](../../services/platform/migrations/versions/0017_evidence_owner_function.py), [ADR-0023](0023-the-tombstone-keeps-the-storage-key.md)

## Context

`DELETE /cases/{id}` has existed since M2. It moved a case to `DELETION_PENDING`,
blocked writes, hid it from every read, and emitted `CaseDeletionRequested` — which sat
in `NO_CONSUMER` with a comment assigning the work to M11. For eight milestones a
deleted case was a case its owner could no longer see, with all of its rows and all of
its objects still in place. MVP §15's Security Gate says "complete case deletion is
tested"; the honest answer was no.

Building the consumer raised two questions that only look like plumbing.

## Decision 1 — the purge runs tenant-scoped, and does not escalate

The purge is the most destructive operation in the product: twenty-four `DELETE`
statements, each scoped by a hand-written predicate. The tempting shape is to run it as
the owner role — it is a system operation, it has no user behind it, and RLS is only
defence in depth.

**Rejected.** Running under the tenant means a wrong predicate cannot reach another
user's rows *at all*, because the policy filters them before the predicate is consulted.
That is not theoretical: mutation testing substituted `1 = 1` for the `case_id` predicate
on `evidence_items`, and the bystander assertion still passed — RLS had absorbed a
mutation that would otherwise have destroyed every evidence item in the database.

That result also condemned the test, which is recorded here because it is the more
useful half. A test whose bystander is *another tenant's* case measures RLS, not the
predicate. The bystander is now **a second case owned by the same user**, where only the
`case_id` in each predicate stands between the purge and the user's other case. Three
further mutations survived until the bystander was built the same way as the subject —
seeding alone populates eleven of twenty-four tables, so an unscoped predicate on a table
the fixture never filled destroyed nothing anyone could notice.

Both bounds are now asserted separately, and keeping them separate is what stops one
quietly standing in for the other.

## Decision 2 — privilege is borrowed twice, narrowly, rather than granted once, broadly

Two writes the purge must make are writes `app_rls` must not be able to make generally.

**`model_runs.output_hash`.** The role has `INSERT, SELECT` and no `UPDATE`: provider
telemetry is append-only from the request path. But §51.2 step 6 requires the hash to go —
it is a fingerprint, and keeping it would let anyone with database access confirm that a
specific model output had been produced here, which is the question a deletion exists to
stop answering. Granting the role `UPDATE` on `model_runs` would widen every request
handler's privilege to serve one statement.

**`cases.owner_user_id`.** This one is not about grants. The policy on `cases` *is*
`owner_user_id = current_setting('app.user_id')`, as both `USING` and `WITH CHECK`, so a
tenant-scoped connection can never set that column to anything but its own value. **The
row's ownership is what the policy is made of, which makes giving it up necessarily a
privileged act.**

Both are `SECURITY DEFINER` functions (migration `0036`), each taking a case id and doing
one thing, following `evidence_owner` from `0017`: `SET search_path = public`, `EXECUTE`
revoked from `PUBLIC` and granted to the application role alone. Two functions rather than
one because they are called at different moments — hashes before `extraction_runs` is
deleted, since that table is the only route to them; ownership last, because after it the
row is invisible to the tenant doing the work.

### The consequence, which is the point rather than a side effect

A tombstone owned by nobody matches nobody, so **the former owner cannot read their own
deleted case.** Domain §7.4 asks for "a minimal non-identifying deletion audit"; this is
the strongest form that can take. What remains says a deletion happened, to a case on this
route, and when it was asked for — not whose it was.

## Decision 3 — the table list is explicit, the coverage check is derived

`_DELETION_ORDER` is hand-written, children before parents, because a reviewer has to be
able to read what this destroys; a clever traversal producing the right answer would be
unauditable. A hand-written list is also exactly how a table added in a later milestone is
silently missed — so it is not trusted. `test_every_case_scoped_table_is_purged` derives
the case-scoped set from the live schema, the same way `test_rls_coverage.py` derives it
for policies, and fails on the migration that introduces a table nobody added.

Explicit for reading, derived for correctness. The ordering is checked against
`pg_constraint` for the same reason: a parent deleted first fails on a foreign key, and
the purge would abandon a case half-destroyed.

## Consequences

- Case deletion is terminal in fact and not only in the state machine (Domain §52).
- Verified against the running stack, not only in tests: 11 objects gone from MinIO
  (`head` → `None`), 166 rows, 80 events, 22 hashes scrubbed. See
  `docs/demo-assets/m11/m11-case-deletion-completes.txt`.
- **Cases deleted before this shipped will never be purged.** Their outbox rows are
  already marked published, and the relay does not revisit them. Any deployment carrying
  `DELETION_PENDING` cases from before this deploy needs them re-emitted by hand. Recorded
  in `KNOWN_LIMITATIONS.md` rather than solved, because a migration that re-emits events
  is a migration that can re-emit the wrong ones.
- Eight of twenty-four tables are not reached by the test fixture — the AI and claim path
  has no synchronous producer, so a document reaches `extracted_claims` only through the
  worker and this suite runs none. Named in `NOT_POPULATED_BY_THE_FIXTURE`, so widening
  the coverage is a deletion from that list.
