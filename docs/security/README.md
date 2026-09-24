# Security

- [`SECURITY_AND_PRIVACY_THREAT_MODEL.md`](SECURITY_AND_PRIVACY_THREAT_MODEL.md): the
  controls, and what each defends against. It covers the list set by the Technical
  Architecture RFC §23.4: broken object-level authorisation, guessed evidence identifiers,
  cross-case evidence access, malicious PDF uploads, prompt injection inside documents,
  excessive model spending, PII leakage through logs, stale presigned URLs, malformed files,
  and model output containing invented references.
- [`ACCESSIBILITY_PASS.md`](ACCESSIBILITY_PASS.md): what was verified on the core flows, how,
  and what was not.

Security-relevant decisions are indexed under "Security, tenancy and storage" in
[`../README.md`](../README.md#decisions).
