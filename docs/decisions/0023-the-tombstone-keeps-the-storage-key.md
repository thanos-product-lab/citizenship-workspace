# ADR-0023: The tombstone keeps the storage key, and clears the name wherever it was copied

**Status:** Accepted
**Date:** 2026-08-28
**Milestone:** M7 (Evidence Foundation), slice 5

## Context

Domain §51.1 step 7 says a deleted evidence item retains "only minimal non-sensitive
tombstone metadata". It does not enumerate the fields, so slice 5 had to decide what
survives the purge — and the M7 plan's own wording said to blank the storage key.

Deletion is the slice that proves the rest of the milestone. A product whose central claim
is that nothing silently becomes truth has to handle something that *was* true ceasing to
be so, and the tombstone is where that lands in the data: the row that remains after the
bytes are gone, holding whatever we decided a destroyed document is still allowed to say
about itself.

## Decision

**Keep `storage_key`. Clear `display_name`, `original_filename`, `checksum`, the extracted
text row, and the same name wherever another table copied it.**

### Keeping the storage key is a deviation from the plan

Three reasons, in ascending order of importance.

The mechanical one: `uq_evidence_files_storage_key` is a plain `UNIQUE` constraint, not
partial on `deleted_at IS NULL` the way `uq_evidence_files_item_checksum` is. Blanking the
key collides on the second deletion in a case. This alone would be a reason to look again,
not a reason to decide.

The substantive one: **the key discloses nothing the row does not already carry.** It is
`build_key`'s server-generated randomness plus a `case_id` that is a column on the same
row. It is not derived from the filename, the content, or anything the user typed. After
the object is deleted it addresses nothing.

The operational one: a purge can fail. `storage.delete` raising leaves the item
`DELETION_PENDING` with bytes present, and after the retries are exhausted nothing will
try again. The retained key is what lets an operator act on the `evidence.purge_abandoned`
log line — without it, the record of an incomplete destruction names no object.

### The checksum is different, and goes

A checksum is a **content fingerprint**, not an identifier. Retaining it would let anyone
with database access ask "was this exact document ever uploaded here?" and get an answer —
which is precisely the question a deletion exists to stop answering. That it is also how
duplicate detection works is why it has to be cleared deliberately rather than left because
it is useful.

### The name is cleared wherever it was copied

`display_name` is the user's own words for their document, and that argument does not stop
at a table boundary. `DUPLICATE_EVIDENCE` denormalises the name into
`issues.message_parameters` — twice, because the surviving twin carries it as `other_name`
— and resolving an issue writes only `status` and `resolved_at`. So clearing the column
alone left the name of a destroyed document in two resolved rows.

`_tombstone` now calls `issues_service.forget_evidence_names` **before** blanking the
column, since that is the last moment the twin's copy can be matched.

## Consequences

- The tombstone is inspectable and useless: ids, `case_id`, `category`, `media_type`,
  `size_bytes`, the timestamps, and a key addressing nothing.
- **The twin is matched by name, not by id.** `other_name` is all that row holds — the
  sibling was never recorded as an identifier. The structural fix is to store
  `other_item_id` and resolve names at render time, the way `_resolve_evidence_link`
  already refuses to carry a name into provenance. Not done here: it changes the shape of
  a rendered issue, which is wider than a purge should reach. **Carried as a known gap.**
- The match is scoped to one case. A name is not a fingerprint, but widening it would
  still be reaching into another user's rows to answer a question nobody asked — the
  boundary Domain §15 draws for checksums applies to the weaker signal too.
- Tombstones are counted, not ignored: the coverage gate reads "has this case ever held a
  document?" from them, so deleting the last document leaves the gaps visible rather than
  closing every notice at the moment coverage got worse.
- No migration. `deleted_at` existed on both tables, `lifecycle_status` already carried
  `DELETION_PENDING` and `DELETED`, and the tombstone clears columns rather than adding
  any. Checked rather than assumed, because the plan asked for its absence to be verified.

## Alternatives rejected

**Blank the storage key, as the plan said.** It collides on the second deletion, and the
collision is the lesser problem: the key identifies nothing, so blanking it buys no privacy
while destroying the one handle on a failed purge.

**Delete the row outright instead of tombstoning.** Loses the coverage gate's only source
for "has ever held evidence", so deleting the last document would close every coverage
notice at the exact moment coverage got worse. Also loses the audit trail's referent.

**Clear the checksum but keep a truncated prefix** for duplicate detection across
deletions. A prefix of a fingerprint is a weaker fingerprint, not a non-fingerprint, and
detecting duplicates against documents the user has destroyed is not a feature.

## Invariants touched

- **Domain §51.1 step 7** — this ADR is the record of what "minimal non-sensitive" was
  taken to mean.
- **CLAUDE.md §11** (keep names and identifiers out of logs, traces and events). The
  `EvidenceDeleted` event deliberately omits the storage key: an earlier draft carried it
  so the purge consumer would need no lookup, which the rule six lines above it forbids in
  as many words.
- **Domain §52** — a storage key is never authorisation. Retaining it is safe *because*
  nothing treats it as a credential; `worker/context.py` resolves the tenant from
  `evidence_items → cases`, explicitly not from the key.
