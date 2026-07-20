# Automated Job Discovery Pipeline
## Design and Decision Record

**Author:** Mohammed
**Date:** 20 July 2026
**Status:** Approved — partial implementation complete
**Document type:** Architecture decision record and implementation plan

---

## 1. Purpose

This document records the evaluation, decisions, and target architecture for an automated job discovery and screening pipeline intended to support a personal job search conducted alongside full-time employment.

It captures the reasoning behind each decision so that the choices remain reviewable later, and so the effort can be discontinued or redirected on evidence rather than on impression.

---

## 2. Problem statement

A job search run in parallel with full-time work is constrained by attention, not by information availability. Job postings are abundant; the scarce resources are the time to evaluate relevance and the discipline to follow through on applications.

The system must therefore optimise for **signal quality and low operational overhead**, not for volume of postings collected or applications submitted.

### 2.1 Success criteria

| # | Criterion |
|---|---|
| 1 | A small, ranked set of genuinely relevant postings is available each morning without manual searching |
| 2 | Daily operator effort after setup is under five minutes |
| 3 | Recurring cost is zero or negligible |
| 4 | Pipeline failure is visible rather than silent |
| 5 | The artefact has secondary value as a portfolio piece |

### 2.2 Explicit non-goals

- Automated submission of applications
- Maximising application volume
- Serving any user other than the author

---

## 3. Landscape survey

The open-source tooling in this space divides into four layers. Each was assessed independently.

### 3.1 Layer 1 — Discovery and collection

| Project | Assessment |
|---|---|
| **JobSpy** | Actively maintained MIT-licensed Python library. Scrapes LinkedIn, Indeed, Glassdoor, Google, ZipRecruiter, Bayt and BDJobs concurrently into a single tabular result. Bayt coverage is material given the regional context. **Selected.** |
| **JobFunnel** | Archived by its author. The stated reason was that job boards adopted aggressive anti-automation measures, and rebuilding on browser automation proved too slow and fragile. Retained as a design reference only. |
| **ATS board APIs** | Greenhouse, Lever, Ashby and Workday publish unauthenticated JSON endpoints for listed roles. Structurally more durable than scraping. **Deferred to phase 2.** |

### 3.2 Layer 2 — Tracking and matching

| Project | Assessment |
|---|---|
| **JobSync** | Self-hosted Next.js application; Prisma and SQLite storage; AI resume review and job-to-CV matching via local or hosted models. Functionally strong. **Not adopted** — see §5. |
| **Resume-Matcher** | Open-source ATS-style scoring of a CV against a job description. Not required under the selected design. |

### 3.3 Layer 3 — Automated application agents

Agent-based tools that navigate application forms and submit on the candidate's behalf were surveyed and **rejected outright**. They breach platform terms of service, break frequently as page structures change, and mass submission is generally counterproductive to candidacy quality.

### 3.4 Layer 4 — Orchestration

Scheduled execution with notification delivery is a common pattern and requires no dedicated project. Addressed directly in the architecture below.

---

## 4. Blocking and access risk assessment

An assessment was made of the risk of access restriction per source. **These figures are calibrated estimates derived from observed platform behaviour, not measured rates.** No authoritative published data exists.

The assessment assumes **anonymous, logged-out collection from a residential connection at low request rates.** This distinction is material: account suspension is only possible where session credentials are supplied. Under the selected design no credentials are supplied to any board, so the exposure is limited to temporary IP-level restriction.

| Source | Estimated IP restriction risk | Account risk |
|---|---|---|
| Greenhouse / Lever / Ashby | Negligible | Not applicable |
| Bayt | Low | Not applicable |
| Google Jobs | Low to moderate | Not applicable |
| ZipRecruiter | Moderate | Not applicable |
| Indeed | Moderate to high | Not applicable |
| Glassdoor | High | Not applicable |
| LinkedIn | Very high | Near-certain if authenticated |

### 4.1 Governing factors

Request rate and IP reputation influence outcomes more than the choice of source. Collection from a residential connection at intervals of ten seconds or more sits at the low end of each range; collection from datacentre address space at concurrency will trigger restriction on the more aggressive platforms within a single session.

### 4.2 Consequence assessment

Restrictions are typically temporary and affect automated collection only. The material risk is not loss of access but **silent degradation** — collection returning empty or partial results while continuing to report success. This risk is addressed explicitly in §7.4.

### 4.3 Measured results — 20 July 2026

The estimates above were tested against JobSpy 1.1.82: anonymous, logged out, from
a residential connection, at low volume (8–10 results per call).
**Where measurement and estimate disagree, the measurement governs.**

| Source | Estimated | Measured | Note |
|---|---|---|---|
| Indeed | Moderate to high | **Works** | Egypt via `country_indeed="egypt"` |
| LinkedIn | Very high | **Works** | Anonymous collection succeeded |
| Bayt | Low | **403 Forbidden** | Refused on first request; no warm-up period |
| Glassdoor | High | **Unsupported** | Hard error: not available for Egypt |
| Google | Low to moderate | **Empty** | No cursor returned for either query form |

Two estimates were materially wrong, in opposite directions. Bayt — rated the
lowest risk of the scraped sources, and cited in D2 as a reason to select JobSpy —
is the only source to refuse outright. LinkedIn, rated the highest risk, collects
without difficulty when logged out. The distinction drawn in §4 between account
risk and IP risk holds; the ordering of IP risk did not.

Glassdoor's failure is not a restriction. The source has no Egyptian coverage at
all, so it is removed from consideration rather than mitigated.

A further observation with direct bearing on §7.3: **a total failure returns a
DataFrame of shape (0, 0)** — no columns, not merely no rows. Collection code that
inspects columns before checking emptiness will raise rather than record an empty
run, converting a visible failure into a crash.

---

## 5. Options considered

### Option A — Adopt JobSync alone

Deploy the existing self-hosted tracker; add postings manually.

*Advantages:* no development effort; resume review and matching already implemented.
*Disadvantages:* introduces a second daily tool requiring a new habit; discovery remains manual.

### Option B — Integrate JobSpy with JobSync

Bridge collection into the existing tracker.

*Advantages:* combines automated discovery with mature tracking.
*Disadvantages, assessed in detail:*

1. **Storage contention.** JobSync uses SQLite. An external writer operating against the same file while the application holds connections produces lock contention under concurrency.
2. **No machine-facing ingestion interface.** JobSync uses account-based authentication. No documented token or API-key path exists for external writers; a custom authenticated route would have to be added.
3. **Runtime boundary.** JobSpy is Python; JobSync is TypeScript. A separate scheduled process is required regardless.
4. **Schema impedance.** JobSpy produces flat records; JobSync normalises company, title and location as related entities. Every insertion becomes an upsert chain.
5. **Duplicate handling.** JobSpy returns the same posting from multiple boards. JobSync deduplicates its own ingestion only.
6. **Purpose mismatch.** JobSync's analytics measure application activity and outcomes. Injecting unreviewed listings degrades precisely the metrics that make it useful.

### Option C — Custom collection and scoring, delivered into Notion *(selected)*

Build the discovery and scoring layers; deliver output into the existing Notion workspace, which already serves as the daily working surface.

*Advantages:* no new daily tool or habit; no integration friction; the tracking surface is already in active use; the build is aligned with an existing specialisation interest.
*Disadvantages:* resume review and CV-matching features available in JobSync must be reimplemented if wanted.

---

## 6. Decision register

| # | Decision | Rationale |
|---|---|---|
| D1 | Build discovery and screening only; no automated application submission | Terms-of-service exposure; fragility; counterproductive to candidacy |
| D2 | Use JobSpy for collection | Actively maintained; multi-board. *Regional (Bayt) coverage was part of this rationale and did not survive measurement — see §4.3 and D11* |
| D3 | ~~Do not adopt JobSync; deliver into Notion instead~~ **Superseded by D15** | See §5, Option C |
| D15 | Build a web application as the sole triage surface; do not use Notion | Supersedes D3. The pipeline holds more per posting than Notion can usefully receive, and scorer validation (D8, §12 item 9) requires viewing description, score and rationale together. Single-surface constraint retained and binding — see ADR-0004 |
| D4 | Use PostgreSQL for staging rather than SQLite | Contention is not a genuine constraint at this scale; adopted for future vector-search capability and portfolio legibility |
| D5 | Score using a locally hosted model via Ollama | Zero marginal cost; no data leaves the machine; full prompt control |
| D6 | Apply a regular-expression title filter as a coarse pre-filter only | Reduces model invocations; unsuitable for requirement analysis, where unstructured phrasing produces false negatives |
| D7 | Publication threshold set at 60 of 100 | Deliberately permissive at outset; to be tightened after one week of calibration |
| D8 | Use a 7–8 billion parameter instruction-tuned model | Adequate for structured scoring; JSON validity to be verified on twenty postings before the scorer is trusted |
| D9 | Retain rejected postings indefinitely | Serves as a permanent suppression list preventing resurfacing |
| D10 | Defer ATS board polling and vector matching to phase 2 | Scope control |
| D11 | Collect from Indeed and LinkedIn only at outset | The only two sources measured to work (§4.3). Bayt, Glassdoor and Google recorded as known-broken rather than silently retried |
| D12 | Fingerprint on employer + title + **country**, not city | Boards localise and format city names irreconcilably (§7.3.1). Country collides reliably; city cannot without a brittle alias table |
| D13 | Do not promote salary fields to columns | Measured 0/10 populated on both working sources. Retained in the raw payload against later change |
| D14 | Config expressed as explicit search specs, not term × location product | `country_indeed` accepts one country per call, so international and remote searches require separate invocations with differing parameters |

---

## 7. Target architecture

### 7.1 Overview

A scheduled four-stage pipeline executing once daily. Each stage is independently re-runnable and idempotent. Data flows in one direction.

```
Scheduled trigger (daily, 06:00)
        │
        ▼
Stage 1 — COLLECT      JobSpy queries configured boards
        │              Output: raw postings, unmodified
        ▼
Stage 2 — NORMALISE    Fingerprint generation; cross-board deduplication
        │              Output: one record per real-world posting
        ▼
   ┌────────────────────────────────┐
   │  PostgreSQL (containerised)    │
   │  raw landing · deduplicated    │
   │  postings · employers · runs   │
   └────────────────────────────────┘
        │
        ▼
Stage 3 — SCORE        Title filter, then local model evaluation
        │              Output: score, matched skills, gaps, rationale
        ▼
Stage 4 — PUBLISH      Records above threshold marked published (D15)
        │
        ▼
Manual triage by the operator
```

### 7.2 Rationale for the staging database

The staging layer is the principal design decision. It establishes an idempotency boundary with three consequences:

1. A failure in publication does not cost a collection run.
2. Scoring may be re-run across the full corpus after prompt changes without re-querying any board.
3. Rejected postings persist, preventing recurrence.

### 7.3 Deduplication approach

The same posting is returned by multiple boards with differing identifiers, URLs and cosmetic variations in employer and title strings. A deterministic fingerprint is derived from normalised employer name, normalised title, and **normalised country**.

Two normalisation decisions were made deliberately, and both trade a tolerable failure for an intolerable one:

- **Employer normalisation removes legal-entity suffixes only.** Descriptor words such as *Technologies*, *Solutions* or *Group* are retained. Removing them merges genuinely distinct employers sharing a root name. Displaying one posting twice is a nuisance; concealing a posting behind a false merge is a lost opportunity.
- **Location resolves to country, not city.** See §7.3.1. Remote roles are additionally collapsed to a single value, since boards disagree on the nominal location of a remote role.

#### 7.3.1 Why country and not city — revised 20 July 2026

This section originally specified city-level separation for on-site roles. Measurement
against live boards showed that to be unimplementable. The same search returns:

```
Indeed     القاهرة, C, EG
LinkedIn   Cairo, Egypt
LinkedIn   Cairo, Cairo, Egypt
```

Indeed localises the city name to Arabic; LinkedIn returns English, and is not
self-consistent about repeating the governorate. No normalisation of these strings
collides without a hand-maintained bilingual alias table, which would fail silently
on the first unmapped city — the intolerable failure mode this section exists to avoid.

Country is recoverable from every observed form (`EG`, `Egypt`) over a small closed
vocabulary. Resolving to country therefore restores the property the fingerprint
requires: **the same posting from two boards produces the same value.**

The cost is accepted deliberately: one employer advertising the same title in two
cities within one country now merges into a single record. For a search centred on
one metropolitan area this is close to free, and where it does bite, the merged record
retains both source URLs under provenance, so neither posting is concealed.

Note also that `scrape_jobs` **flattens location to a display string**. JobSpy's
internal `Location(country, city, state)` object is not exposed through the DataFrame,
so country must be parsed back out of the flattened string.

### 7.4 Failure visibility

Per-run, per-stage record counts are persisted. The dominant failure mode is not an error but a successful run returning progressively fewer results as a source begins restricting access. Counts trending toward zero while the process exits successfully is the signal to investigate. Weekly review is required.

---

## 8. Data model

Four entities, described here in narrative form.

| Entity | Purpose | Notes |
|---|---|---|
| **Employers** | Normalised employer records | Carries a suppression flag to exclude an employer permanently |
| **Raw postings** | Append-only landing zone | Verbatim collector output, retained for reprocessing and diagnosis. No transformation or deduplication applied |
| **Postings** | One record per real-world role | Keyed on fingerprint. Holds provenance (which boards surfaced it, and the URL for each), filter outcome, scoring output, publication state, and suppression flag |
| **Runs** | One record per execution | Start and finish times, per-stage counts, status, and error detail |

### 8.1 Triage state (D15)

Triage state lives on the posting rather than in an external system. `status` takes one of New, Shortlist, Applied or Rejected, defaulting to New on publication.

Rejected is the suppression mechanism required by D9: a rejected posting is retained indefinitely and never resurfaces, so a separate suppression flag on the posting is unnecessary. Employer-level suppression remains distinct, since it must exclude every posting from that employer including ones not yet seen.

### 8.2 Interface

A local web application, served from the same image as the scheduler (ADR-0004). Minimum scope, per the §11 time-box:

| View | Purpose |
|---|---|
| Posting list | Published postings, ranked by score, filterable by status |
| Posting detail | Description beside score, matched skills, gaps and rationale — the comparison D8 and §12 item 9 require |
| Status transition | New → Shortlist → Applied, or Rejected |
| Run health | Per-run, per-source counts; the weekly review surface required by §7.4 |

---

## 9. Operational considerations

### 9.1 Cost

Recurring cost is zero, and after D15 there is no external service in the pipeline at all. Collection is anonymous and unauthenticated, scoring runs locally, and delivery is a state transition within the local database. Only electricity is consumed.

The sole potential cost is proxy provision, required only if a source begins restricting access and that source is judged worth retaining.

### 9.2 Throughput

No external interface rate limit applies after D15. Publication is a database update over fewer than one hundred rows daily and is not a throughput consideration. The binding rate constraint is collection etiquette, addressed below.

### 9.3 Collection etiquette

Request delay is configurable and set conservatively. Proxy configuration is supported but unused by default. Increasing the delay is the first remedy for restriction; proxy provision is the last.

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Silent collection decay | High | High | Per-run counts persisted; weekly review |
| Source restricts access | Moderate | Moderate | Conservative rate limiting; multi-source design degrades gracefully; ATS polling in phase 2 removes the dependency |
| Scorer diverges from operator judgement | Moderate | High | Manual review of a sample before the scorer is trusted; permissive initial threshold |
| Over-aggressive filtering conceals relevant roles | Moderate | High | Filter applied to title only; pass and fail counts logged for inspection |
| False employer merge conceals postings | Low | High | Employer normalisation deliberately conservative |
| **Project displaces the job search** | **High** | **High** | See §11 |

---

## 11. Principal risk

The most significant risk to the stated objective is not technical. This build is engaging, adjacent to an existing specialisation interest, and therefore easily mistaken for progress. Applications are not submitted while a scoring model is being tuned.

**Control:** the build is time-boxed to one weekend. If the pipeline is not operating by the end of that period, postings are to be added manually and applications submitted while the build is deferred. The pipeline justifies itself only if it survives contact with actual use.

---

## 12. Implementation status

*Corrected 20 July 2026. Items 1, 2, 4 and 5 were previously recorded as complete;
no such code existed. The table now reflects the working tree.*

| # | Item | Status |
|---|---|---|
| 1 | Repository scaffold, configuration, container definition | Partial — `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `config.py` written; CLI and scheduler outstanding |
| 2 | Database schema and migration | Outstanding — deliberately deferred until the collector's real output was known (§4.3) |
| 3 | Collection stage | Outstanding |
| 4 | Fingerprinting and deduplication | Outstanding — approach revised, see §7.3.1 |
| 5 | Title filter configuration | Outstanding |
| 6 | Scoring stage | Outstanding — requires the author's CV to construct the prompt |
| 7 | Publication stage | Outstanding |
| 8 | Orchestrator | Outstanding |
| 9 | Validation against a seeded sample | Outstanding |
| 10 | Scheduled deployment | Outstanding |
| 11 | Source availability verified against live boards | **Complete** — see §4.3 |

Item 9 is the item most commonly omitted and should not be. A scorer that quietly disagrees with the operator's judgement is worse than no scorer, because its output will be trusted.

---

## 13. Outstanding items

1. Provision of the CV in plain text to construct the scoring prompt (blocks item 6).
2. Confirmation of the specific model to be used, following JSON-validity verification.
3. Calibration of the publication threshold after one week of operation.

---

## 14. Phase 2 candidates

Not committed. To be reconsidered only against demonstrated need.

- **ATS board polling.** Direct collection from Greenhouse, Lever and Ashby endpoints for a curated employer list. Structurally more durable than scraping and, for a narrow search, likely higher precision. Requires assembling a target employer list, which has independent value.
- **Vector matching.** Semantic ranking of postings against the CV using embeddings held in the same database, as an alternative or complement to per-posting model invocation.
- **Automated resume tailoring.** The principal capability forgone by not adopting JobSync.

---

## 15. Note on sources

Statements regarding platform behaviour, licensing and interface availability derive from project documentation and vendor sources consulted on 20 July 2026, and carry the uncertainty caveats already noted at point of use (§4, §9.1). One additional item: a previously noted JobSync capability for polling Greenhouse and Lever endpoints was not corroborated by the project's current documentation and should not be relied upon.

*End of document.*
