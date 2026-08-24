# ADR-0020: Processing progress is polled, not streamed

**Status:** Accepted
**Date:** 2026-08-24
**Milestone:** M7 (Evidence Foundation), slice 2

## Context

The roadmap's M7 platform scope names "SSE progress with polling fallback", and the
Technical Architecture RFC §22 prefers Server-Sent Events for document-processing
progress because the traffic is one-way, server to client.

Both were written before the API's authentication was settled. It authenticates with a
Clerk bearer token, and **`EventSource` cannot send request headers** — there is no API
for it. That leaves three ways to authenticate a stream, and none is free:

- **A token in the query string.** Threat model §6.4 forbids logging signed URLs, and a
  credential in a URL is the same shape: it lands in access logs, in `Referer`, and in
  browser history.
- **A cookie session.** Works, and introduces a second authentication mechanism beside
  the bearer token plus the first CSRF surface this API has had.
- **`fetch` with a `ReadableStream` instead of `EventSource`.** Can carry the header, but
  it is a hand-rolled SSE client: reconnection, backoff and event framing all become ours.

## Decision

**Poll, on a bounded interval, only while something is moving.**

`useEvidence` sets `refetchInterval` from the library's own contents: 1.5 seconds while
any document is in a state the worker moves it out of, and `false` otherwise. A settled
library generates no traffic at all.

One wrinkle drove most of the design. `UPLOADED` is where a document sits **both** before
validation starts and after it passes, because in this milestone nothing reads a
document's contents and "stored" is the honest state either way. So "poll until it leaves
`UPLOADED`" would never terminate. A freshly uploaded document is therefore watched for a
bounded window (15s) and then left alone; the state it lands on is correct regardless, and
a manual refresh costs nothing on a screen nobody is staring at.

## Consequences

- No new transport, no new auth path, no CSRF surface, and nothing to reconnect.
- Latency is up to one poll interval rather than instant. For a validation that takes
  well under a second, the user sees "Validating" briefly or not at all — which is
  honest, since the work really is that fast at this stage.
- Traffic is bounded by activity rather than by open tabs.
- **The roadmap's stated scope is not met**, deliberately, and this ADR is the record.
  MVP §8.9 — which is the acceptance boundary — asks for "processing progress" and says
  nothing about the transport.

## Revisit when

Extraction lands in slice 3 and processing takes long enough that a poll interval is
visible, **or** a second surface needs live updates. At that point the honest options are
the `fetch`-stream client or a cookie-authenticated stream endpoint, and the cost of
either is worth paying once there is more than one screen to justify it.

## Invariants touched

None. Progress reporting is a projection of `EvidenceItem.processing_status`, which is a
domain state either way — the transport does not touch what is said, only how often.
