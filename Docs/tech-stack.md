# Automated Job Discovery Pipeline
## Technology Stack

**Author:** Mohammed
**Date:** 20 July 2026
**Status:** Approved
**Companion to:** [job-discovery-pipeline-design.md](job-discovery-pipeline-design.md)

---

## 1. Purpose

This document fixes the concrete technology choices for the pipeline. The
load-bearing decisions (JobSpy, PostgreSQL, Ollama, Notion) are made in the
design record's decision register (D1–D10); this document records the choices
downstream of them and the three that genuinely forked.

---

## 2. Principles

The stack follows the design record's optimisation target: **signal quality and
low operational overhead**, zero recurring cost, and secondary value as a
portfolio piece (§2, criterion 5). Concretely:

- One language end to end. JobSpy is Python, so the whole pipeline is Python.
- Managed migrations and a legible schema — the schema is a portfolio artefact.
- Every stage independently re-runnable and idempotent, per design §7.1.
- Nothing that incurs a per-call fee or ships data off the machine.

---

## 3. Stack at a glance

| Concern | Choice | Version | Fixed by / rationale |
|---|---|---|---|
| Language / runtime | Python | 3.12 | JobSpy is Python (design D2) |
| Dependency management | **uv** | latest | Reproducible `uv.lock`; fast; single tool for venv + run |
| CLI / orchestrator | Typer | latest | Each pipeline stage a subcommand — matches re-runnable-stages design |
| Collection | JobSpy | latest | Design D2 |
| Staging store | PostgreSQL | 16 | Design D4 |
| Vector capability | pgvector | pg16 image | Pre-empts phase 2 vector matching (design §14) |
| DB access | **SQLAlchemy 2.0** | 2.0.x | Managed models; clean pgvector integration; portfolio legibility |
| Migrations | **Alembic** | latest | Versioned, reversible migrations |
| DB driver | psycopg | 3.x | SQLAlchemy backend |
| Scoring runtime | Ollama | latest | Design D5, D8 |
| Scoring model | 7–8B instruction-tuned | TBC | Design D8; final pick pending JSON-validity check (design §13.2) |
| Scoring client | ollama (python) | latest | Official client |
| Output validation | Pydantic | 2.x | Enforces scorer JSON contract (design D8) |
| Delivery | notion-client | latest | Official Notion SDK (design D3) |
| Config | pydantic-settings | latest | Typed config from `.env` |
| Scheduling | **APScheduler in app container** | latest | Containerised scheduler; portable; all-Python |
| Containerisation | Docker + docker-compose | — | Design §7.1 (containerised) |
| Lint / format | Ruff | latest | Single fast tool |
| Testing | pytest | latest | Fingerprint/dedup tests (design §12 item 4) |

---

## 4. The three forked decisions

### T1 — DB access: SQLAlchemy 2.0 + Alembic

Chosen over raw psycopg + hand-run `.sql` files. The extra ceremony buys managed,
reversible migrations and a clean path to pgvector for phase 2. The schema is
named as a portfolio artefact in design D4, and mapped models read better than
raw SQL for a reviewer. Trade-off accepted: an ORM layer over four tables.

### T2 — Scheduling: APScheduler inside the app container

The design record says "cron, daily 06:00", but the deployment host is Windows 11,
where cron does not exist. Rather than depend on Windows Task Scheduler (ties the
project to one machine) the app runs as its own long-lived container beside
Postgres, with an APScheduler `BlockingScheduler` firing the `run-all` command at
06:00. This keeps scheduling in-language and testable, and keeps the whole system
portable via `docker-compose up`. Trade-off accepted: a long-running process
rather than a one-shot task.

### T3 — Dependency management: uv

Chosen over Poetry and pip. Reproducible lockfile, fast, one tool for the venv,
locking, and running. Trade-off accepted: newest of the three options.

---

## 5. Container topology

```
docker-compose
├── postgres        image: pgvector/pgvector:pg16
│                   volume: pgdata (persistent)
│                   exposes: 5432
│
└── app             image: python:3.12-slim + uv
                    depends_on: postgres
                    process: APScheduler BlockingScheduler
                             └─ 06:00 daily ─▶ python -m app run-all
                    mounts: .env (config), CV text (scoring prompt)
```

Ollama runs on the host (not containerised) so it can use host GPU/CPU directly;
the app container reaches it over the host network. Postgres data persists in a
named volume so the suppression list and raw landing zone survive restarts
(design D9, §7.2).

---

## 6. Repository layout (target)

```
app/
├── pyproject.toml          # uv-managed, project + dev deps
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── .env.example
├── migrations/             # Alembic versions
└── src/
    └── app/
        ├── __main__.py     # Typer entrypoint (run-all + per-stage)
        ├── config.py       # pydantic-settings
        ├── scheduler.py    # APScheduler bootstrap
        ├── db/             # SQLAlchemy models + session
        ├── collect/        # Stage 1 — JobSpy
        ├── normalise/      # Stage 2 — fingerprint + dedup
        ├── score/          # Stage 3 — title filter + Ollama + Pydantic
        └── publish/        # Stage 4 — Notion
```

Maps one-to-one onto the four stages in design §7.1.

---

## 7. Open items

Inherited from the design record — the stack does not resolve these:

1. CV in plain text to construct the scoring prompt (design §13.1).
2. Final scoring model, pending JSON-validity verification on 20 postings
   (design D8, §13.2).
3. Publication threshold calibration after one week (design D7, §13.3).

---

*End of document.*
