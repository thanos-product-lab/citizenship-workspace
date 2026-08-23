# ADR-0019: The storage key travels to the client in a signed token, not a reservation row

**Status:** Accepted
**Date:** 2026-08-23
**Milestone:** M7 (Evidence Foundation), slice 1

## Context

Uploading is two HTTP calls with a direct-to-storage PUT between them (Technical
Architecture RFC §18). The storage key is minted by the server — threat model §12:
"Original filenames are metadata only and never determine storage paths" — and has to
reach the second call somehow.

The first implementation persisted an `EvidenceItem` and an `EvidenceFile` at presign
time and looked the key up on completion. It failed for a reason worth recording: it
committed case-scoped rows with **no domain event**, so it had to call `session.commit()`
directly, bypassing `UnitOfWork` — the only sanctioned commit path in the product, whose
entire purpose is to make "business state written without an event" structurally
impossible. It was the only raw `session.commit()` in `app/`.

Working around that guard for the first new aggregate in five milestones is the wrong
direction. The alternatives were to invent a `PENDING_UPLOAD` processing status and an
`EvidenceReserved` event — both changes to Domain §14.4 and §38, so RFC changes
(CLAUDE.md §7) — for a state no user can observe, plus an orphan row behind every
abandoned upload and a sweeper to clean them up.

## Decision

**Presign writes nothing. The key travels through the client inside an HMAC-signed
token, and the document is recorded in one command when its bytes are confirmed present.**

    POST .../evidence/uploads   mint key, sign PUT URL, sign token.   No DB write.
    (browser PUTs the bytes)
    POST .../evidence           HEAD the object, then item + file + event, one UnitOfWork.

The token (`app/evidence/upload_token.py`) binds the storage key to the case that
authorised it, to the media type baked into the presigned PUT's own signature, and to an
expiry. So it cannot be re-pointed at another object, cannot be replayed into another of
the user's own cases, and cannot outlive the URL it accompanies.

**It carries integrity, not authority.** Presenting a valid token proves the server minted
the key; it proves nothing about ownership. The recording call re-runs
`require_case_access` like every other route, and the token's case id must match the case
in the path. A token is not a capability.

## Consequences

- `UnitOfWork` keeps its guarantee unbroken: there is still exactly zero raw
  `session.commit()` in `app/`.
- Every column on both tables is `NOT NULL`: an `evidence_items` row that exists is a
  document the case really holds, and an `evidence_files` row that exists has bytes behind
  it. No nullable "not yet" columns to explain, and no filtering on them in every query.
- An abandoned upload leaves an orphaned *object* in the store but no database row. That
  is the right way round — a sweeper over storage is a background job, where a sweeper
  over case-scoped rows would be a background job touching user data.
- **A new secret.** `UPLOAD_TOKEN_SECRET`. Unset means a per-process key, which is fine
  for one API instance and silently wrong for several — a token signed by one replica
  would be rejected by another, and the symptom is intermittent 422s indistinguishable
  from tampering. `check_upload_secret()` therefore **refuses to boot** outside
  `local`/`docker`/`test` rather than warning into a log, and rejects a configured secret
  shorter than 32 characters.
- **Recording is idempotent on the storage key**, and that is a security property rather
  than a convenience. This is the retry-prone call — the bytes are already stored — and
  without idempotency a retry violates the storage-key unique constraint, whose
  `IntegrityError` renders SQLAlchemy's bound parameters (key, filename, checksum) into a
  500 and from there into the logs. Found in review; `hide_parameters=True` on the engine
  closes the wider class.

## Alternatives rejected

- **Let the client send the key back.** A client-supplied key is a client-supplied storage
  path. Threat model §12 forbids it outright, and it would make the key a credential —
  the exact inversion Domain §52 exists to prevent.
- **Keep the reservation row and emit a reservation event.** Needs a new §38 event type
  and a new §14.4 status, so two RFC changes, to describe a state that is invisible to the
  user and meaningless to the domain.
- **Keep the reservation row and keep the raw commit.** Leaves the one guard that makes
  the outbox reliable with a hole in it, in the milestone that finally builds the outbox
  *reader*.

## Invariants touched

- CLAUDE.md §2.1 is untouched (no claims here yet), but the `UnitOfWork` discipline that
  will carry claims in M8 is preserved rather than precedent-broken.
- Domain §52 "storage keys are not permissions" — upheld, and now also true of the token.
