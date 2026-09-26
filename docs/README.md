# Documentation

A map of what is here, what each document is for, and which ones describe the product as it
is today. Code, tests and the project's skills cite these documents by section number, so
their structure is stable: they are indexed here rather than rewritten.

## Start here

Four documents, in this order, give an accurate picture of the product in under an hour.

1. [Product guide](product/PRODUCT.md): what it is, who it is for, and how it works, in plain
   language for any reader.
2. [Architecture overview](architecture/ARCHITECTURE_OVERVIEW.md): how the system works, from
   what runs where to how the rules count days, and where to look up the details.
3. [Known limitations](KNOWN_LIMITATIONS.md): what it does not do, which gaps are deliberate,
   and which are still open.
4. [Demo script](DEMO_SCRIPT.md): the canonical demonstration, step by step, on the local
   stack.

## Current

Maintained and authoritative. If the code disagrees with one of these, the code is wrong.

| Document | Answers |
|---|---|
| [Product guide](product/PRODUCT.md) | **For any reader.** Who it is for, what it does, what the results mean, and what it does not do |
| [Architecture overview](architecture/ARCHITECTURE_OVERVIEW.md) | **The one to read.** How the system works end to end, and which spec section answers which question |
| [Deterministic rules spec](architecture/DETERMINISTIC_RULES_SPEC.md) | Look-up reference: date semantics, day counting, thresholds, banding |
| [Domain model RFC](architecture/DOMAIN_MODEL_RFC.md) | Look-up reference: entities, enums, invariants and state machines |
| [Evidence and claim lifecycle RFC](architecture/EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md) | Look-up reference: how a document is stored, read, proposed from, reviewed and deleted |
| [Known limitations](KNOWN_LIMITATIONS.md) | Open gaps, deliberate boundaries, and resolved entries (numbers are stable) |
| [Deployment](DEPLOYMENT.md) | Environments, services, secrets and how a deploy happens |
| [Demo script](DEMO_SCRIPT.md) | Running and showing the canonical demo locally |
| [Security and privacy](security/SECURITY_AND_PRIVACY_THREAT_MODEL.md) | The one security document: a two-minute summary at the top, then every threat and its control |
| [Design](design/DESIGN_SYSTEM_FOUNDATIONS.md) | The one design document: tokens, themes and contrast, how the interface behaves (§11), and the accessibility pass (§12) |
| [AI evaluation](evaluations/EVAL_REPORT.md) | The one evaluation document: the false-reassurance rate, what the corpus does not cover, the release gates, the spike, and every run |

## Reference

Authoritative for the sections the code cites, but not maintained as a whole. Read them for
the reasoning behind a decision, not as a description of the current build.

| Document | Why it is kept |
|---|---|
| [Release gate audit](RELEASE_GATE_AUDIT.md) | The record of the release decision: every release gate and its state |
| [Case study outline](product/CASE_STUDY_OUTLINE.md) | Raw material for the case study, until the case study itself exists |

## Decisions

The [decisions index](decisions/README.md) lists every architecture decision record (ADR) in
one line each, saying what was decided, and names the five to read first. Numbers are
permanent, because code and tests cite them.

## Retired

Development history that no longer describes the product lives in git history, not here:
the walkthrough scenarios and their findings, the milestone notes (M0 to the release slice),
the July 2026 reconciliation, the original technical architecture RFC (its lasting content
is in the architecture overview), the UI/UX direction document (its lasting rules are in the
design document's §11), the AI evaluation plan, spike findings and per-run results (folded
into the evaluation report), the product thesis, the MVP scope and acceptance criteria, and the
synthetic demo case specification (the product guide replaces the first two; the seed script
`app/seed/demo_case.py` now defines the demo case), and the per-milestone demo captures with their shot list (the
demo will be one video recorded at the end). Read any of them with, for example,
`git show a37b05a:docs/decisions/milestone-notes.md`.

The implementation roadmap and the milestone gates were retired once the build finished.
Code, docs and ADRs still use their milestone labels (M0 to M12) to say when something was
built; read the originals with `git show aad44b0:docs/IMPLEMENTATION_ROADMAP.md` and
`git show aad44b0:docs/MILESTONE_GATES.md`.
