# ADR-0003: Build custom collection and scoring rather than adopt an existing tracker's features

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 20 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | — |
| **Related** | ADR-0001, ADR-0002 |

---

## Context

ADR-0001 selected Notion as the tracking surface and ADR-0002 ruled out integrating with JobSync. Together these forgo capabilities the rejected tracker already provides — notably CV review and posting-to-CV matching, both already built and working.

This ADR records the build-versus-adopt reasoning for what remains, and the deliberate choice of which capabilities to reimplement and which to abandon.

The capabilities in question divide cleanly:

- **Discovery and ranking** — finding postings and scoring them against a CV. Not solved by any adopted component.
- **Tracking** — status, history, follow-up. Solved by ADR-0001 at zero build cost.
- **CV tailoring** — generating role-specific CV variants. Available in the rejected tracker; not available under the selected design.

An asymmetry governs the decision. Tracking is low-value to build custom and high-value to place where attention already goes. Discovery and ranking is the reverse: it is the part no adopted tool solves for this specific search, and the part where a bespoke implementation genuinely outperforms a general one, because the scoring criteria are personal and the target niche is narrow.

## Decision

**Collection and scoring will be built. Tracking will not. CV tailoring is deliberately abandoned for now.**

Specifically:

- **Collection** uses JobSpy as a library rather than a reimplementation. The multi-board scraping problem is genuinely solved by an actively maintained project; rebuilding it would be waste.
- **Deduplication and normalisation** are built, because they depend on judgements specific to this search — see the fingerprint reasoning in the design document.
- **Scoring** is built against a locally hosted model, using a prompt constructed around the actual CV. This is the component where a general tool is weakest and a specific one strongest.
- **Tracking** is not built. See ADR-0001.
- **CV tailoring** is not built and not adopted.

## Consequences

### Positive

- The build is confined to the components where custom implementation genuinely outperforms an adopted one.
- Scoring criteria, prompt and threshold are fully controllable and can be tuned against observed disagreement with the operator's own judgement.
- Scoring runs locally, so no CV or search history leaves the machine and no per-posting cost is incurred.
- The resulting system has secondary value as a portfolio artefact, aligned with an existing specialisation direction.

### Negative

- **CV tailoring is lost.** This is the most substantial capability forgone. If role-specific CV generation later proves to be the highest-value activity in the search, this decision — and possibly ADR-0001 — should be reopened rather than worked around.
- Approximately four components must be written and maintained: collection, normalisation, scoring and publication.
- A scorer that quietly disagrees with the operator's judgement is worse than no scorer, because its output will be trusted. This risk is created by the decision to build and must be actively mitigated, not assumed away.

### Neutral

- The regular-expression title filter is a deliberate coarse pre-filter only. It reduces model invocations but is unsuitable for analysing requirements, where unstructured phrasing produces false negatives.

## Alternatives considered

### Adopt a tracker's CV-matching features and forgo automated discovery

**Rejected on a diagnosis of the actual constraint.** The bottleneck in a search conducted alongside full-time work is attention, not information availability. Postings are abundant. However, this diagnosis is an assumption, and the review trigger below tests it.

### Build everything, including tracking

**Rejected.** Tracking is tedious to build, valuable only if used daily, and already solved by a tool in active use. Building it would consume the time-box without improving the outcome.

### Adopt nothing and search manually

**Rejected**, but with a caveat that materially constrains this decision: manual search is the fallback if the build overruns. The build is time-boxed to one weekend precisely because the failure mode of this ADR is a well-engineered pipeline that displaces the applications it was meant to support.

## Mandatory validation

The scorer is not to be trusted until validated. Before the pipeline is relied upon:

1. Structured-output validity is confirmed across twenty postings.
2. Scores for ten postings are compared against the operator's own independent judgement.

The publication threshold is set deliberately permissively at outset so that calibration can occur against observed output rather than assumption.

## Review trigger

Reopen if either premise fails:

- **If relevant postings run short**, the discovery diagnosis was wrong; extend collection to ATS board endpoints for a curated employer list.
- **If applications are prepared but not converting**, CV tailoring is the binding constraint, and adopting the tool rejected in ADR-0001 becomes the stronger option.
