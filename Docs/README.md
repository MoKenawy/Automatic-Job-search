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
| [Object Model Refactor](design/oop-refactor.md) | Paradigm assignment and phased refactor plan **(proposal)** | Developers |
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

## Project structure

```
Automatic-Job-search/
├── Docs/                          # This documentation set
│   ├── design/                    # Design documents
│   │   ├── system-architecture.md
│   │   ├── data-model.md
│   │   └── oop-refactor.md        # Paradigm assignment (proposal)
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
    │   ├── pipeline/              # Stage orchestration and persistence
    │   │   ├── run.py             # Run tracking
    │   │   ├── collect_stage.py   # Stage 1 persistence
    │   │   └── normalise_stage.py # Stage 2 dedup upsert
    │   ├── db/                    # SQLAlchemy models and session
    │   └── web/                   # FastAPI triage interface
    │       └── templates/         # Jinja2 templates
    │
    └── tests/                     # pytest suite
```

## Document status

All documents describe the system as at 21 July 2026. Stages 1 and 2 (collection
and deduplication) are implemented and operating; stages 3 and 4 (scoring and
publication) are specified but not yet implemented. Where a document describes
unimplemented behaviour it is marked **(planned)**.
