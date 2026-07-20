# Software Requirements Specification
## Automated Job Discovery Pipeline

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 21 July 2026 |
| **Status** | Approved |
| **Author** | Mohammed |
| **Supersedes** | — |

---

## 1. Introduction

### 1.1 Purpose

This document specifies the requirements for the Automated Job Discovery
Pipeline: a personal system that collects job postings from online boards,
removes duplicates, scores each posting against the operator's CV using a locally
hosted language model, and presents the ranked results in a web interface for
manual triage.

The specification is the reference against which the system is built and
verified. It records *what* the system must do; the design documents record
*how*.

### 1.2 Scope

The system serves a single operator conducting a job search alongside full-time
employment. It optimises for **signal quality and low operational overhead**, not
for the volume of postings collected or applications submitted.

**In scope:** discovery, deduplication, relevance scoring, and a triage surface.

**Out of scope** (design §2.2):

- Automated submission of applications.
- Maximising application volume.
- Serving any user other than the operator.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| Board | An online job site (e.g. Indeed, LinkedIn). |
| Collection | Retrieval of postings from boards. |
| Fingerprint | A deterministic hash identifying one real-world role across boards. |
| Posting | One real-world role, after deduplication. |
| Raw posting | One board's verbatim record, before deduplication. |
| Run | One execution of the pipeline. |
| Scoring | Assigning a 0–100 relevance value to a posting against the CV. |
| Publication | Marking a scored posting for display in the interface. |
| Triage | The operator's review and status assignment on a posting. |

### 1.4 References

- [Design record](job-discovery-pipeline-design.md) — originating decisions (D1–D15).
- [Technology stack](tech-stack.md) — concrete technology choices.
- Architecture Decision Records 0001–0004.

### 1.5 Requirement identifiers

Functional requirements are `FR-n`, external interface requirements `IR-n`, and
non-functional requirements `NFR-n`. Each requirement cites the design decision
it derives from where one exists.

---

## 2. Overall description

### 2.1 Product perspective

The system is a self-contained pipeline run on a single machine. It has no
external service dependencies at runtime: collection is anonymous and
unauthenticated, scoring runs locally through Ollama, and results are stored in a
local PostgreSQL database and served by a local web application. This isolation
is a deliberate property, not an accident of scale (ADR-0004).

### 2.2 Product functions

At a high level the system:

1. Collects postings from configured boards on a daily schedule.
2. Lands each board's output verbatim for reprocessing and diagnosis.
3. Deduplicates postings into one record per real-world role.
4. Scores each posting against the CV. **(planned)**
5. Publishes postings above a threshold. **(planned)**
6. Presents ranked postings for triage and records the operator's decisions.
7. Records per-run, per-source counts so silent decay is visible.

### 2.3 User characteristics

A single technical operator, able to run command-line tools and read a web
interface. No training material is required beyond this documentation.

### 2.4 Constraints

- **Zero recurring cost** (design §2.1). No paid services may be introduced.
- **Under five minutes of daily operator effort** after setup.
- **Single machine.** The deployment target is one Windows workstation with
  Docker.
- **One triage surface.** The interface replaces Notion; it does not supplement
  it (ADR-0004, binding).

### 2.5 Assumptions and dependencies

- Collection is anonymous and logged-out, from a residential connection, at
  conservative request rates (design §4).
- Ollama is installed and running on the host with a suitable model pulled.
- Docker is available for PostgreSQL and the application containers.

---

## 3. Functional requirements

### 3.1 Stage 1 — Collection

**FR-1.** The system shall collect postings from each configured board for each
configured search specification. *(D2)*

**FR-2.** Each search specification shall carry a term, an optional location, a
country, a remote flag, and the subset of boards to query. Specifications shall
be configurable without code change. *(D14)*

**FR-3.** The system shall support Indeed and LinkedIn. Boards found unusable in
assessment (Bayt, Glassdoor, Google) shall not be enabled by default. *(D11,
§4.3)*

**FR-4.** The failure of one board shall be recorded and shall not terminate the
run; remaining boards shall still be collected. *(§7.4)*

**FR-5.** The system shall record, per run, the number of postings collected from
each board individually.

**FR-6.** Collection shall apply a configurable inter-request delay, conservative
by default. *(§9.3)*

### 3.2 Landing

**FR-7.** The system shall persist each board's output verbatim, without
transformation or deduplication, in an append-only store. *(§8)*

**FR-8.** Landed records shall retain the complete collector output so that a
later decision to promote a field requires a backfill, not a re-collection.

### 3.3 Stage 2 — Normalisation and deduplication

**FR-9.** The system shall derive a deterministic fingerprint for each posting
from the normalised employer name, normalised title, and country. *(D12, §7.3.1)*

**FR-10.** Postings sharing a fingerprint shall be merged into a single record.
The URL from each contributing board shall be retained as provenance. *(§7.3)*

**FR-11.** Employer normalisation shall remove legal-entity suffixes only.
Descriptor words (e.g. *Technologies*, *Solutions*, *Group*) shall be retained,
so that distinct employers sharing a root name are not merged. *(§7.3)*

**FR-12.** Title normalisation shall retain seniority and discipline markers, so
that e.g. *Senior Data Engineer* and *Data Engineer* are not merged. *(§7.3)*

**FR-13.** Remote roles shall collapse to a single location value regardless of
the location string a board reports. On-site roles shall be distinguished by
country. *(§7.3)*

**FR-14.** Where a country cannot be resolved, the posting shall be marked with an
unresolved value rather than assigned a guessed country, and the count of
unresolved postings shall be recorded. *(§7.4)*

**FR-15.** Stage 2 shall be idempotent: reprocessing the same landed records shall
converge on the same set of postings without creating duplicates.

### 3.4 Stage 3 — Scoring **(planned)**

**FR-16.** The system shall apply a coarse title filter before scoring, to reduce
model invocations. The filter shall operate on the title only and shall not be
used for requirement analysis. *(D6)*

**FR-17.** The system shall score each filtered posting against the CV using a
locally hosted instruction-tuned model via Ollama, producing a 0–100 score,
matched skills, gaps, and a rationale. *(D5, D8)*

**FR-18.** Scoring output shall be validated against a fixed schema; malformed
model output shall be rejected rather than stored. *(D8)*

**FR-19.** The model that produced a score shall be recorded with the score, so a
model or prompt change is traceable.

**FR-20.** Scoring shall be re-runnable across the stored corpus after a prompt
change without re-collecting from any board. *(§7.2)*

### 3.5 Stage 4 — Publication **(planned)**

**FR-21.** The system shall publish postings whose score meets or exceeds a
configurable threshold. *(D7)*

**FR-22.** Publication shall be a state transition within the local database, not
a write to any external service. *(ADR-0004)*

**FR-23.** A rejected posting shall be retained indefinitely and shall not
resurface. *(D9)*

### 3.6 Triage interface

**FR-24.** The interface shall list published postings ranked by score, filterable
by triage status and searchable by title or company.

**FR-25.** The interface shall present, for each posting, its description beside
its score, matched skills, gaps, and rationale, to support scorer calibration.
*(D8, §12 item 9)*

**FR-26.** The interface shall allow the operator to set a posting's triage status
to New, Shortlist, Applied, or Rejected. *(§8.1)*

**FR-27.** Setting a status to Rejected shall suppress the posting from future
resurfacing. *(D9)*

**FR-28.** The interface shall present per-run, per-source counts and their trend
across recent runs, as the weekly review surface. *(§7.4)*

**FR-29.** Status transitions shall function without client-side scripting;
enhancement is progressive.

### 3.7 Orchestration

**FR-30.** The system shall execute the full pipeline once daily at a configurable
time. *(§7.1)*

**FR-31.** Each stage shall be independently executable against the stored data
without re-running the stages before it. *(§7.1)*

**FR-32.** The system shall record, per run, a start time, a finish time, a
terminal status, per-stage counts, and any error. A run that leaves a
non-terminal status indicates the process died. *(§7.4)*

---

## 4. External interface requirements

**IR-1.** The system shall provide a command-line interface exposing each stage
(`collect`, `normalise`, `score`, `publish`), a full run (`run-all`), the
scheduler (`serve`), the web server (`web`), run status (`status`), and effective
configuration (`config`).

**IR-2.** The system shall provide a web interface over HTTP presenting the views
of §3.6.

**IR-3.** The web interface shall expose a health endpoint that confirms both
process liveness and database reachability.

**IR-4.** All configuration shall be supplied by environment variables or a
`.env` file, validated at startup. *(tech-stack)*

**IR-5.** The system shall collect from boards via the JobSpy library and score
via the Ollama HTTP API. No board credentials shall be supplied. *(§4)*

---

## 5. Non-functional requirements

### 5.1 Performance

**NFR-1.** A daily run shall complete within a few minutes at an expected volume
below one hundred postings.

**NFR-2.** Daily operator effort after setup shall be under five minutes.
*(§2.1)*

### 5.2 Cost

**NFR-3.** Recurring cost shall be zero. No component shall introduce a per-call
or subscription fee. *(§2.1, §9.1)*

### 5.3 Reliability and observability

**NFR-4.** The dominant failure mode — a run that succeeds while returning
progressively fewer results — shall be made visible through persisted per-source
counts and their trend. *(§7.4)*

**NFR-5.** A stage failure shall not corrupt stored data; stages shall be
re-runnable to recover. *(§7.2)*

**NFR-6.** Schema changes shall be applied through versioned, reversible
migrations. *(tech-stack T1)*

### 5.4 Security and privacy

**NFR-7.** No data shall leave the machine. Scoring is local; there is no external
delivery target. *(D5, ADR-0004)*

**NFR-8.** No board account credentials shall be stored or transmitted, limiting
exposure to temporary IP-level restriction. *(§4)*

**NFR-9.** Secrets in configuration shall be masked in diagnostic output.

### 5.5 Portability and maintainability

**NFR-10.** The system shall run from a single container image plus a database
container, brought up by one command. *(ADR-0004)*

**NFR-11.** The interpreter version shall be pinned and the dependency graph
locked, so builds are reproducible. *(tech-stack)*

**NFR-12.** The system shall be one language end to end (Python). *(tech-stack)*

### 5.6 Constraint on scope

**NFR-13.** The build is time-boxed. If the pipeline is not operating by the end
of the time-box, postings are triaged manually and applications submitted while
the build is deferred. The pipeline justifies itself only in use. *(§11)*

---

## 6. Requirements traceability

| Requirement group | Design decisions | Verified by |
|---|---|---|
| Collection (FR-1…6) | D2, D11, D14 | `tests/test_collect.py`; live run |
| Landing (FR-7…8) | §8 | live run; row counts |
| Deduplication (FR-9…15) | D12, §7.3 | `tests/test_fingerprint.py`, `test_employer.py`, `test_country.py` |
| Scoring (FR-16…20) | D5, D6, D8 | *(pending implementation)* |
| Publication (FR-21…23) | D7, D9, ADR-0004 | *(pending implementation)* |
| Triage (FR-24…29) | ADR-0004, §7.4, §8.1 | `tests/test_web.py` |
| Orchestration (FR-30…32) | §7.1, §7.4 | `pipeline/run.py`; live run |

---

## 7. Verification status

As at 21 July 2026:

- **Verified and operating:** FR-1 through FR-15, FR-24 through FR-32 (excluding
  the parts that depend on scores existing).
- **Specified, not implemented:** FR-16 through FR-23 (stages 3 and 4).

Deduplication has been verified on live data: a single real-world posting
returned by both Indeed and LinkedIn, with irreconcilable location strings,
merged correctly into one record carrying both source URLs (design §7.3.1).

*End of document.*
