"""Evidence: uploaded supporting documents, their files, and their processing state.

M7 scope. **No AI anywhere in this module.** Classification and structured claim
extraction are M8; what lands here is private storage, honest processing states, and
deletion. Extraction, when it arrives in slice 3, is PyMuPDF native text and page
metadata — deterministic, with no model call (Technical Architecture RFC §18 steps 5-6;
steps 8-11 are M8).

Deliberately absent, and not oversights:

- `ExtractedClaim`, `ExtractionRun`, `FactEvidenceLink` — M8, with the claim→fact path.
- `EvidenceTravelLink` — slice 4, with the rule change that gives it meaning.
- Full document text over HTTP — stored, never projected, until M8 has a review surface
  designed for it.
"""
