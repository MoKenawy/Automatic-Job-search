# Job Discovery Pipeline

Automated job discovery and screening. Collects postings from multiple boards,
deduplicates them into one record per real-world role, scores them against a CV
using a locally hosted model, and presents the ranked results in a local web
interface for triage. No data leaves the machine and there is no recurring cost.

## Documentation

Full documentation is in [../Docs/](../Docs/):

- [Documentation index](../Docs/README.md)
- [Software Requirements Specification](../Docs/software-requirements-specification.md)
- [System Architecture](../Docs/design/system-architecture.md) · [Data Model](../Docs/design/data-model.md)
- [Deployment](../Docs/deployment-guide.md) · [Development](../Docs/development-guide.md) · [Operations](../Docs/operations-guide.md)
- [Design record](../Docs/job-discovery-pipeline-design.md) · [Technology stack](../Docs/tech-stack.md)

## Requirements

- Python 3.12 (managed by uv)
- Docker (PostgreSQL + application containers)
- Ollama on the host (for scoring)

## Quick start

```bash
cp .env.example .env      # then edit
docker compose up -d      # postgres, migrate, web, scheduler
```

Then open <http://localhost:8000>. For development against a host-side
environment:

```bash
uv sync
docker compose up -d postgres
uv run pytest
uv run python -m app web --reload
```

See the [Deployment Guide](../Docs/deployment-guide.md) for the full procedure.

## Status

Stages 1–2 (collection, deduplication) and the triage interface are implemented
and operating. Stages 3–4 (scoring, publication) are specified and pending — they
require a CV at `data/cv.txt` and a model pulled into Ollama. See design record
§12.
