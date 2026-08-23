# ADR-0018: Evidence content is served by short-lived presigned URL, not proxied

**Status:** Accepted
**Date:** 2026-08-23
**Milestone:** M7 (Evidence Foundation), slice 1

## Context

MVP §8.9 requires that documents are not publicly accessible, that upload URLs expire,
and that old signed URLs cannot reach deleted files. Two mechanisms can deliver a private
file to its owner:

- **A presigned URL.** The API authorises, then hands the browser a signed URL it uses
  against the object store directly. Bytes never touch the web process.
- **A proxied download.** The API authorises and then streams the bytes itself.

They differ on one property that matters: **a presigned URL cannot be revoked.** Once
issued it is valid until it expires, whatever happens to the case, the item, or the
user's session. A proxy revokes perfectly — the next request simply gets a 403.

Domain §51.1 step 2 says evidence deletion must "revoke or expire signed URLs". Only half
of that is achievable with presigning.

## Decision

**Presign, with a 60-second TTL, and say plainly that revocation is not available.**

The window is bounded by the TTL, and the URL was issued to the owner *after*
`require_case_access` passed — so the realistic exposure is a user's own URL leaking in
the seconds after they requested it, not a stranger reaching another tenant's document.
Deletion is asynchronous but prompt, and once the purge runs the URL returns 404, which is
the operative half of "old signed URLs cannot access deleted files" and is asserted
directly in `tests/evidence/test_storage_minio.py`.

The URL is returned as JSON rather than as a 302, so a signed URL never lands in the
address bar or in a `Referer` header — threat model §6.4 forbids logging signed URLs, and a
redirect writes one into browser history.

## Alternatives rejected

- **Proxy downloads through the API.** Revokes properly, and was seriously considered. It
  puts document bytes through the web process, which cuts directly against the decision to
  keep Tier-3 content out of API responses and out of the Next.js server's memory for as
  long as possible (§7.4 of the M7 plan; the same reason full extracted text is not
  projected until M8). Trading a bounded 60-second window for a permanent byte path
  through the application is the wrong direction.
- **A shorter TTL.** Below about 30 seconds a slow connection starts failing legitimate
  downloads, and the failure is invisible to us — it happens between the browser and the
  store.
- **Single-use URLs.** S3 has no such thing. Emulating one needs a proxy, which is the
  rejected option above.

## Review trigger

**Revisit if real documents from friend testing are ever processed.** Threat model §21
gates that separately, and the balance changes when the content is a real person's
immigration status rather than a synthetic fixture. Until then this is a decision, not an
open question.

## Invariants touched

- Domain §51.1 step 2 is met by expiry, not by revocation. Recorded rather than glossed.
- Domain §52 ("evidence preview URLs are short-lived and case-authorised") — upheld: the
  URL is a consequence of the ownership check, never a substitute for it.
