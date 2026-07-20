# ADR-0004: Build a web application as the triage surface, replacing Notion

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 20 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | ADR-0001 |
| **Related** | ADR-0002, ADR-0003 |

---

## Context

ADR-0001 chose Notion as the triage surface, and its reasoning was sound: a tool only produces value if it is opened consistently, and Notion carried no adoption cost because it was already part of a daily routine. A dedicated application would have required establishing a new habit, and habits that depend on enthusiasm are the ones that lapse.

That reasoning is unchanged. What has changed is the assessment of what the second surface costs and what it returns.

**Three things came to light during implementation.**

First, the pipeline now holds materially more per posting than Notion was designed to receive. The delivery schema in design §8.1 was eleven flat properties. The `postings` table carries provenance per board, filter outcome, scoring output, normalisation inputs and first/last-seen timestamps. Projecting that into Notion properties discards most of it, and the discarded parts are precisely what is needed to judge whether the scorer is behaving.

Second, D8 requires the scorer to be validated against real postings before it is trusted, and design §12 item 9 names that as the step most commonly omitted. Validation means viewing a posting's description beside the model's score, matched skills, gaps and rationale, and forming a judgement. Notion is a poor instrument for that comparison; a purpose-built view is a good one.

Third, the deciding factor in ADR-0001 was adoption cost, and adoption cost is a function of *habit displacement*, not of technology. A web application at a fixed local address, opened alongside the pipeline it belongs to, is not obviously costlier to adopt than a Notion database — provided it is the **only** surface, not an additional one.

## Decision

**A web application will be built as the sole triage surface. Notion will not be used, and no posting data will be sent to it.**

Consequences that follow directly:

- Stage 4 no longer writes to an external service. Publication becomes a state transition within PostgreSQL: postings above threshold are marked published and thereby surfaced in the interface.
- Triage state — the Status property of design §8.1 — moves into the `postings` table.
- The `notion-client` dependency is removed, along with the token and database identifier from configuration.
- The web application and the scheduler run as two services from a single image, sharing the same database.

**The single-surface constraint from ADR-0001 is retained and is binding.** This decision replaces Notion; it does not add to it. If both surfaces end up in use, the reasoning in ADR-0001 has been violated and this decision has failed.

## Consequences

*Favourable:*

- Recurring cost stays zero, and one external dependency is eliminated. Notion's rate limits, interface changes and free-tier terms are no longer a consideration.
- No projection loss. The interface can display everything the pipeline knows, including run health, which §7.4 requires to be reviewed weekly and which Notion had no natural place for.
- The artefact's portfolio value (design §2.1, criterion 5) is materially higher. A service with a live pipeline behind it demonstrates more than a populated Notion database.
- Scorer calibration, the step §12 warns is usually skipped, becomes practical rather than tedious.

*Unfavourable, and accepted:*

- **Adoption risk is real and this decision does not eliminate it.** Notion had a genuine advantage that is now forfeited. The mitigation is that the interface must be opened as part of reviewing the pipeline, not as a separate ritual.
- No mobile access and no offline access, both of which Notion provided at no effort.
- Additional build scope, against a one-weekend time-box (design §11). This is the risk §11 names explicitly: the build is engaging and therefore easily mistaken for progress.

## Control

Design §11's time-box governs this decision as it governs the rest. The interface is to be built to the minimum that supports triage and scorer validation — a list, a detail view, a status transition and a run-health view. Anything further is deferred until the pipeline has produced applications.

If stages 3 and 4 are not operating by the end of the time-box, the interface is abandoned and postings are triaged directly from the database while applications are submitted.
