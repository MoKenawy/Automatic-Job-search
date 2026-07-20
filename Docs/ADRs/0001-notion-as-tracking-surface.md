# ADR-0001: Use Notion as the tracking and triage surface

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 20 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | — |
| **Related** | ADR-0002, ADR-0003 |

---

## Context

The pipeline produces a ranked set of job postings each morning. Those postings need a surface where they can be reviewed, triaged into a shortlist, and tracked through to an outcome.

Two candidate surfaces were available:

1. **A dedicated self-hosted job tracker** — specifically JobSync, a Next.js application providing status tracking, application analytics, CV review and posting-to-CV matching.
2. **The existing Notion workspace** — already in daily use for task management, organised into dated pages with an established routine for carrying items forward.

The dedicated tracker is functionally richer. It offers analytics and CV features that Notion does not provide out of the box.

The deciding consideration was not functionality but **adoption cost**. A tracker only produces value if it is opened consistently. A second self-hosted application, with its own login, its own dashboard and its own daily routine, requires establishing a new habit. Tools that depend on a new habit are the ones most likely to be abandoned once initial enthusiasm fades — and abandonment here means the pipeline continues producing output that nobody reads.

Notion carries no adoption cost. It is already opened every morning as part of an established routine. A job pipeline database is one more database in a system already in active use.

## Decision

**Job postings will be delivered into a Notion database. No dedicated job-tracking application will be adopted.**

The Notion database will hold: title, company, score, status, location, source, date posted, URL, model rationale, identified gaps, and a hidden fingerprint for reconciliation against the staging database.

Triage remains manual. The pipeline ranks and delivers; it does not decide.

## Consequences

### Positive

- No new daily habit is required; the delivery surface is already load-bearing.
- No second application to host, authenticate against, update or maintain.
- Delivery is a single unidirectional write to a documented public interface, avoiding all integration complexity described in ADR-0002.
- Notion's interface is available without charge on the free plan, with no per-call fees. Recurring cost is zero.
- Triage happens where the day is already planned, so a shortlisted role can become a task without leaving the tool.

### Negative

- Application analytics — outcome rates, funnel visualisation — are not available and would have to be constructed manually if wanted. Assessed as low value at the volumes involved.
- CV review and posting-to-CV matching, available in the rejected tracker, must be reimplemented. See ADR-0003.
- Notion permits approximately three requests per second per integration, requiring serialised writes. At expected volumes this is not a constraint.
- The free plan limits file uploads to five megabytes. Immaterial for text properties; relevant only if tailored CVs are attached later, and a CV in that format sits well below the limit.

### Neutral

- Status transitions are performed by hand. At the volumes involved this is a few clicks per week, not a burden worth automating.

## Alternatives considered

### Adopt JobSync as the tracking surface

Deploy the self-hosted tracker and use its native features; add postings to it manually at first.

**Rejected.** The functionality is genuine and the CV-matching features are attractive. But it introduces a second daily tool at precisely the point where the search is competing with full-time work for attention. The risk of it going unopened outweighs the features gained. This alternative would become preferable if CV tailoring were judged the highest-value capability — see ADR-0003.

### Deliver to a spreadsheet

**Rejected.** Lower adoption cost than a dedicated tracker but higher than Notion, which is already open. No advantage over the selected option.

### Deliver by notification only

Push high-scoring postings to a messaging channel with no persistent store on the delivery side.

**Rejected.** Provides no triage state. A posting seen and not acted upon is lost, with nothing to return to.

## Review trigger

Revisit if the Notion database proves inadequate for triage in practice — specifically if postings are consistently delivered but not reviewed, which would indicate the failure this decision was intended to prevent has occurred anyway.
