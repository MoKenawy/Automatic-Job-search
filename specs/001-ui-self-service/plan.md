# Implementation Plan: Operator Self-Service (Triage & Configuration from the UI)

**Branch**: `001-ui-self-service` | **Date**: 21 July 2026 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-ui-self-service/spec.md`

## Summary

Extend the triage interface with four operator-facing capabilities, ordered by
value and independence: (P1) inline status change on the list page, (P2) bulk
status change via multi-select, (P2) a company blacklist that auto-rejects while
preserving postings, and (P3) UI-driven configuration — runtime-editable
operational settings plus database-backed, individually scheduled search profiles
that supersede the `SEARCHES` environment list.

The technical thrust is a shift in **where configuration and schedules live**:
from an immutable process-start singleton to database-backed state that the web
UI edits and the scheduler reloads. US1–US3 are small and self-contained; US4
carries the architectural change and is planned to depend on nothing from
US1–US3.

## Technical Context

**Language/Version**: Python 3.12 (existing)

**Primary Dependencies**: FastAPI, Jinja2, HTMX (existing UI stack); SQLAlchemy
2.0 + Alembic; APScheduler; pydantic-settings. No new runtime dependency
anticipated.

**Storage**: PostgreSQL 16 (+ pgvector). Two new tables (`search_profiles`,
`app_settings`); no new columns on existing tables — the blacklist reuses
`employers.suppressed`.

**Testing**: pytest against in-memory SQLite (existing pattern), plus
`fastapi.testclient`. New coverage per FR-021.

**Target Platform**: Single-machine Docker Compose (web + scheduler + postgres +
migrate).

**Project Type**: Web service (server-rendered) + background scheduler, one image.

**Performance Goals**: Daily triage under five minutes (design NFR-2). Bulk update
of a screenful (~100 rows) in a single request.

**Constraints**: Single operator, single surface (ADR-0004). No external service,
no auth. Runtime-editable settings exclude secrets and restart-only values.

**Scale/Scope**: Hundreds of postings, tens of employers, a handful of search
profiles. No concurrency beyond a single operator's browser tabs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is currently an
unfilled template, so there are no ratified machine-checkable gates. In its place
this plan is checked against the project's **established design principles** (from
the design record and ADRs), which function as the de facto constitution:

| Principle (source) | Compliant? | Note |
|---|---|---|
| Single triage surface (ADR-0004) | ✅ | All features are in the existing UI; none adds a second surface |
| Zero recurring cost / no external service (§9.1) | ✅ | All state is local; nothing leaves the machine |
| One language end to end (tech-stack) | ✅ | No new language or build step |
| Idempotent, re-runnable stages (§7.1) | ✅ | Blacklist suppression is an idempotent pass |
| Preserve, never delete (D9) | ✅ | Blacklist rejects and retains; no deletion of postings |
| Observability of runs (§7.4) | ⚠️ | Per-profile scheduling must keep per-run/per-source counts intact — tracked as a task |
| Decisions recorded (ADR discipline) | ⚠️ | Moving `SEARCHES` and settings into the DB supersedes prior config decisions → **new ADR required** (see Complexity Tracking) |

No violation blocks the plan. Two items are flagged as obligations, not
violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-ui-self-service/
├── spec.md              # Feature specification (done)
├── plan.md              # This file
├── research.md          # Open decisions / clarifications
├── data-model.md        # New and changed entities
├── quickstart.md        # (deferred — not required for planning)
├── contracts/           # (deferred — endpoints enumerated inline below)
└── tasks.md             # Task breakdown (speckit.tasks output)
```

### Source Code (repository root)

The application is a single package under `app/src/app`. This feature adds a
`config/` package (settings store + search profiles) and a `templates/` set, and
extends `web/`, `pipeline/`, and `db/`.

```text
app/src/app/
├── config.py               # extended: env becomes the SEED for DB-backed settings
├── db/
│   └── models.py           # + SearchProfile, AppSetting
├── settings_store/         # NEW: read/write runtime settings and profiles
│   ├── __init__.py
│   ├── store.py            # get/set operational settings (DB over env default)
│   └── profiles.py         # CRUD for search profiles
├── pipeline/
│   ├── collect_stage.py    # reads search profiles instead of settings.searches
│   └── suppress_stage.py   # NEW: apply employer blacklist -> reject postings
├── scheduler.py            # reschedules per enabled profile; reloads on change
└── web/
    ├── app.py              # + routes: bulk status, blacklist, settings, profiles
    ├── queries.py          # + suppression-aware queries, profile/settings reads
    └── templates/
        ├── postings.html          # + row status control, multi-select, bulk bar
        ├── _row_status.html       # NEW: inline list-row status control (HTMX)
        ├── blacklist.html         # NEW: blacklist management
        ├── settings.html          # NEW: operational settings form
        └── profiles.html          # NEW: search-profile CRUD + schedules

app/tests/
├── test_web_triage.py      # US1, US2
├── test_blacklist.py       # US3 (pipeline + web)
├── test_settings_store.py  # US4 settings precedence + validation
└── test_profiles.py        # US4 profile CRUD + scheduling read model
```

**Structure Decision**: Single-project web service, extending the existing
`app/src/app` package. A new `settings_store/` package isolates the
runtime-configuration concern from both the web layer (which edits it) and the
pipeline (which reads it), preserving the existing strict dependency direction
(web and pipeline depend on config/store, not each other).

## Complexity Tracking

> Filled because the Constitution Check raised obligations that must be justified.

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| New `app_settings` table + precedence layer over env | FR-014 requires runtime changes without restart; the current singleton is immutable | Re-reading `.env` and restarting per change fails FR-014 and defeats the point of UI config |
| New `search_profiles` table replacing `SEARCHES` env | FR-016/017 require per-profile CRUD and per-profile schedules from the UI | A JSON blob in `app_settings` cannot carry per-row schedule/enabled state or be scheduled individually without reinventing a table |
| Per-profile scheduling replaces the single daily job | FR-017 requires each profile to run on its own schedule | One global job cannot honour differing per-profile run times |
| **New ADR (0005)** superseding `SEARCHES`-in-env and static config | ADR discipline; this changes a standing decision | Not recording it would leave the design record inconsistent with the system (the failure mode already corrected once for Notion) |

**Sequencing note**: US1 → US2 share the list template and are done first. US3
(blacklist) is independent and can be built in parallel; it needs only the
suppression pass and `employers.suppressed`. US4 is the largest and is planned
last, gated behind ADR-0005 being accepted, because it changes configuration
semantics the other stories rely on implicitly (they read today's `settings`).
