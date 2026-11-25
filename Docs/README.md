# Documentation

Formal documentation for the Automated Job Discovery Pipeline.

## Reading order

Start with the design record for the reasoning behind the system, then the SRS
for what it is required to do, then the design documents for how it is built.
The three guides are task-oriented and can be read as needed.

| Document | Purpose | Audience |
|---|---|---|
| [Design record](job-discovery-pipeline-design.md) | The originating decisions and their rationale | Everyone |
| [Technology stack](tech-stack.md) | The concrete technology choices | Everyone |
| [Software Requirements Specification](software-requirements-specification.md) | What the system must do | Everyone |
| [System Architecture](design/system-architecture.md) | Structure, stages, runtime topology | Developers, operators |
| [Data Model](design/data-model.md) | Entities, relationships, schema | Developers |
| [Refactor Plan](design/refactor-plan.md) | Phased refactor and package restructure **(proposal)** | Developers |
| [Reports Implementation Plan](design/reports-implementation-plan.md) | The six admitted reports, phased **(proposal)** | Developers |
| [Deployment Guide](deployment-guide.md) | Standing the system up | Operators |
| [Development Guide](development-guide.md) | Working on the code | Developers |
| [Operations Guide](operations-guide.md) | Running it day to day | Operators |

## Architecture Decision Records

Numbered, immutable once accepted. A later ADR may supersede an earlier one; the
earlier record is retained.

| ADR | Decision | Status |
|---|---|---|
| [0001](ADRs/0001-notion-as-tracking-surface.md) | Notion as the tracking surface | Superseded by 0004 |
| [0002](ADRs/0002-no-jobsync-integration.md) | Do not integrate JobSync | Accepted |
| [0003](ADRs/0003-build-collection-and-scoring.md) | Build collection and scoring | Accepted |
| [0004](ADRs/0004-web-app-replaces-notion.md) | Web application replaces Notion | Accepted |
| [0005](ADRs/0005-ui-config-and-db-search-profiles.md) | UI config & DB-backed search profiles | Accepted |
| [0006](ADRs/0006-scoring-model-lifecycle.md) | Scoring model lifecycle — selection, training, testing | Superseded by 0007 |
| [0007](ADRs/0007-scoring-evaluation-and-score-history.md) | Scoring evaluation metric and score history | Accepted |
| [0008](ADRs/0008-report-system-scope.md) | Report system — admission criteria and scope | Accepted |
| [0009](ADRs/0009-last-seen-at-contamination-detection.md) | Detecting `last_seen_at` contamination for R2 | Decision superseded by 0012 |
| [0010](ADRs/0010-r2-span-computation-strategy.md) | Where R2's span arithmetic runs — Python, SQL, or the write path | Accepted |
| [0011](ADRs/0011-job-type-taxonomy-for-arrangement-mix.md) | `job_type` taxonomy for the work-arrangement-mix report | Accepted |
| [0012](ADRs/0012-retrieval-date-column-split.md) | Split `last_seen_at` into `updated_at` and `last_retrieved_at` | Accepted |
| [0013](ADRs/0013-posting-status-history.md) | Transactional audit table for triage status transitions | Accepted |
| [0014](ADRs/0014-status-transition-row-locking.md) | `SELECT ... FOR UPDATE` for concurrent status transitions | Accepted; case 2 superseded by 0015 |
| [0015](ADRs/0015-employer-level-suppression.md) | Employer-level suppression, derived at read time | Accepted |
| [0016](ADRs/0016-collect-stage-filter-verdicts.md) | Filter verdicts — derived criteria, derived visibility | Accepted |
| [0017](ADRs/0017-board-seniority-label-reliability.md) | Board seniority label — how far to trust it when it hides a posting | Accepted (as built; DeepEval indicator noted) |
| [0018](ADRs/0018-per-profile-title-rules.md) | Per-profile title rules — two levels, one combination rule | Accepted |
| [0019](ADRs/0019-jobspy-linkedin-seniority-crash.md) | JobSpy's LinkedIn seniority parse — guarding against a whole-search crash | Accepted (option C: fixed upstream, JobSpy 1.4.1) |
| [0020](ADRs/0020-seniority-for-boards-without-a-label.md) | Seniority for boards that declare none — title fallback, or seniority in the search term? | Accepted (option A, with profile guidance) |
| [0021](ADRs/0021-ui-styling-hand-written-tokens.md) | Styling the triage interface — hand-written design tokens, self-hosted assets | Accepted |

A **Proposed** record states evidence and options and decides nothing; it binds no
behaviour until it is accepted. ADR-0017, 0019 and 0020 were opened that way and
have since been accepted.

## Project structure

```
Automatic-Job-search/
├── Docs/                          # This documentation set
│   ├── design/                    # Design documents
│   │   ├── system-architecture.md
│   │   ├── data-model.md
│   │   └── refactor-plan.md       # Phases + restructure (proposal)
│   ├── ADRs/                      # Architecture Decision Records
│   │   └── 000N-*.md
│   ├── job-discovery-pipeline-design.md
│   ├── tech-stack.md
│   ├── software-requirements-specification.md
│   ├── deployment-guide.md
│   ├── development-guide.md
│   └── operations-guide.md
│
└── app/                           # The application
    ├── pyproject.toml             # Project, dependencies, tool config (uv)
    ├── uv.lock                    # Pinned dependency graph
    ├── .python-version            # Pinned interpreter (3.12)
    ├── Dockerfile                 # Single image for web + scheduler + migrate
    ├── docker-compose.yml         # Four services
    ├── alembic.ini                # Migration configuration
    ├── .env.example               # Configuration template
    │
    ├── migrations/                # Alembic migrations
    │   └── versions/
    │
    ├── src/app/                   # Application package
    │   ├── __main__.py            # Typer CLI entry point
    │   ├── config.py              # Typed settings (pydantic-settings)
    │   ├── scheduler.py           # APScheduler daily trigger
    │   ├── collect/               # Stage 1 — JobSpy collection
    │   ├── normalise/             # Fingerprinting and deduplication
    │   │   ├── country.py
    │   │   ├── employer.py
    │   │   ├── title.py
    │   │   └── fingerprint.py
    │   ├── filters/               # Relevance and experience criteria (D6, ADR-0016)
    │   │   ├── levels.py          # The seniority scale and both vocabularies
    │   │   ├── titles.py          # Include/exclude patterns
    │   │   ├── combine.py         # The two tri-state combinators (ADR-0018)
    │   │   ├── resolve.py         # Stored profile fields -> one posting's criteria
    │   │   └── verdict.py         # One posting, two criteria, one verdict
    │   ├── pipeline/              # Stage orchestration and persistence
    │   │   ├── runner.py          # Run tracking and stage sequencing
    │   │   ├── collect_stage.py   # Stage 1 persistence
    │   │   ├── normalise_stage.py # Stage 2 dedup upsert
    │   │   └── filter_stage.py    # Filter verdicts and the run funnel
    │   ├── db/                    # SQLAlchemy models, session, read-time seams
    │   │   ├── visibility.py      # Read-time withholding (ADR-0015, ADR-0016)
    │   │   └── attribution.py     # Posting → run → profile traversal
    │   └── web/                   # FastAPI triage interface
    │       └── templates/         # Jinja2 templates
    │
    └── tests/                     # pytest suite
```

## Document status

Stages 1 and 2 (collection and deduplication) are implemented and operating. So
is the filter that runs between stages 2 and 3, which records title and
experience verdicts (ADR-0016, ADR-0018). Stages 3 and 4 (scoring and
publication) are specified but not yet implemented. Where a document describes
unimplemented behaviour it is marked **(planned)**.

The design record and the technology stack are dated snapshots of the original
plan. Where they differ from the code, System Architecture and the ADRs describe
the system as built.
