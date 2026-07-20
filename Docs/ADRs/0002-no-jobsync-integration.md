# ADR-0002: Do not integrate the collector with JobSync

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 20 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | — |
| **Related** | ADR-0001, ADR-0003 |

---

## Context

Before the tracking surface was settled (ADR-0001), an appealing arrangement presented itself: use JobSpy for automated collection and JobSync for tracking, bridging the two. This would combine mature discovery with mature tracking and appeared to require only a modest adapter.

The two projects were not designed to interoperate. JobSync provides no native connector for external collectors, so the bridge would be bespoke. A detailed assessment was made of what that bridge would actually entail.

### Findings

**1. Storage contention.** JobSync uses SQLite with Prisma, distributed as a container. SQLite permits a single writer. An external process writing to the same database file while the application holds its own connections produces lock contention under any real concurrency. This alone forces the integration through an interface layer rather than direct writes.

**2. No machine-facing ingestion interface.** JobSync uses account-based authentication established at first run. Nothing in its documentation describes a token or API-key path intended for external writers. Route handlers exist, but determining whether they can be driven by an external process — or adding an authenticated route to a third-party codebase — is unbudgeted work on a dependency that will keep moving.

**3. Runtime boundary.** JobSpy is a Python library; JobSync is almost entirely TypeScript. A separate scheduled process is required in any case, so the integration does not simplify the deployment topology.

**4. Schema impedance.** JobSpy produces flat records. JobSync normalises company, title and location as related entities with their own identifiers. Every insertion becomes an upsert chain against a schema owned by an upstream project, which is free to change it.

**5. Duplicate handling.** JobSpy queries multiple boards concurrently and returns the same posting several times with differing identifiers and URLs. JobSync deduplicates its own ingestion, not a foreign collector's. Deduplication has to happen before the bridge regardless.

**6. Purpose mismatch.** This proved the strongest objection. JobSync is an *application* tracker: its analytics measure activity and outcomes across roles actually applied to. Injecting several hundred unreviewed listings degrades precisely the metrics that give the tool its value.

The cumulative assessment: the bridge is not a modest adapter. It is a bespoke integration against an upstream schema and authentication model that will keep moving, in service of a tool whose model of the world the pipeline output actively distorts.

## Decision

**No integration between the collector and JobSync will be built.** The collector will own its own staging store and deliver directly to the surface chosen in ADR-0001.

## Consequences

### Positive

- No dependency on an upstream project's internal schema, authentication model or release cadence.
- No storage contention: the staging database has exactly one writer.
- Deduplication, scoring and publication are owned end to end and can be changed without coordination.
- The delivery interface — Notion's — is public, documented, versioned and intended for machine clients, which is the property the JobSync path lacked.

### Negative

- JobSync's built-in features are forgone entirely. See ADR-0003 for the build-versus-adopt consequences.
- A staging store must be operated that would otherwise have been unnecessary. Assessed as worthwhile on its own merits: it establishes an idempotency boundary allowing collection, scoring and publication to fail and re-run independently.

## Alternatives considered

### Write directly to the JobSync database

**Rejected.** Storage contention (finding 1) and coupling to an upstream schema (finding 4). Prisma migrations on the upstream side would silently break the writer.

### Add an authenticated ingestion route to JobSync and maintain a fork

**Rejected.** Creates a permanent merge burden against an actively developed project, in exchange for features not central to the objective.

### Stage postings separately and promote only applied-to roles into JobSync

Retain JobSync as the tracker, but insulate it: the collector writes to its own store, and only roles actually being applied to are promoted across — a handful per week rather than hundreds.

**Seriously considered, and the strongest form of the integration.** It resolves findings 1, 5 and 6 by reducing write volume to near zero and preserving the integrity of JobSync's analytics. It was not adopted because ADR-0001 subsequently removed the premise: with Notion as the tracking surface, there is nothing to promote into. Had a dedicated tracker been retained, this would have been the recommended arrangement.

## Review trigger

Revisit only if a dedicated tracker is adopted after all, in which case the staged-promotion alternative above becomes the starting point rather than direct integration.
