# Development Guide
## Automated Job Discovery Pipeline

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 21 July 2026 |
| **Audience** | Developer |
| **Related** | [System Architecture](design/system-architecture.md), [Data Model](design/data-model.md) |

---

## 1. Purpose

This guide covers working on the code: setting up a local environment, the
project layout, the conventions to follow, how to run and test, and how to change
the schema. It assumes familiarity with Python.

---

## 2. Environment setup

The project uses [uv](https://docs.astral.sh/uv/) for the interpreter, the
virtual environment, dependency locking, and running. The interpreter is pinned
to 3.12 in `.python-version`.

```powershell
# From app/
uv python install 3.12      # if not already present
uv sync                     # creates .venv, installs from uv.lock
```

`uv sync` installs the exact locked graph, including dev tools (Ruff, pytest).
Run any command in the environment with `uv run`, e.g. `uv run pytest`.

The database is expected at `localhost:5432`; start it with
`docker compose up -d postgres` (see the [Deployment Guide](deployment-guide.md)).
The unit test suite does **not** require a database (§4).

---

## 3. Project layout

```
src/app/
├── __main__.py       Typer CLI — the single entry point wiring stages together
├── config.py         Typed settings (pydantic-settings); one source of truth
├── scheduler.py      APScheduler daily trigger
├── collect/          Stage 1: query boards via JobSpy
├── normalise/        Pure fingerprint logic (country, employer, title)
├── pipeline/         Stage orchestration + persistence (run, collect, normalise)
├── db/               SQLAlchemy models and session
└── web/              FastAPI interface (app, queries, templates/)
```

**Dependency direction is strict and load-bearing:**

- `normalise/` and `collect/` know nothing of the database. They are pure
  transforms and can be tested without infrastructure.
- `pipeline/` composes `collect` and `normalise` and is the only place that
  persists.
- `web/` reads the database and never writes pipeline data (only triage status).
- `config.py` depends on nothing; everything depends on it.

Keep this direction. If normalisation starts importing the database, the property
that makes the fingerprint logic trivially testable is lost.

---

## 4. Testing

```powershell
uv run pytest              # full suite
uv run pytest -q           # quiet
uv run pytest tests/test_fingerprint.py   # one file
```

The suite runs **without Docker**. Web tests use an in-memory SQLite database
with a `StaticPool` (a single shared connection, so the schema persists across
sessions). The models declare a `JSON` variant of their `JSONB` columns for
exactly this reason — production uses `JSONB`, tests fall back to `JSON`.

**Testing conventions:**

- **Fixtures marked `OBSERVED` are real strings captured from live boards.** They
  are the reason the normalisation rules exist; do not "tidy" them. For example,
  `القاهرة, C, EG` and `Cairo, Egypt` are the same city from two boards and must
  fingerprint identically.
- **Assert non-merging at least as hard as merging.** The governing asymmetry
  (design §7.3) is that a false merge conceals a posting. Tests must prove that
  seniority and discipline variants stay *distinct*, not only that cosmetic
  variants collapse.
- Deduplication is covered by `test_fingerprint.py`, `test_employer.py`,
  `test_country.py`; collection failure shapes by `test_collect.py`; the
  interface by `test_web.py`.

When the normalisation logic changes, validate against real captured output, not
only handcrafted fixtures.

---

## 5. Code style

```powershell
uv run ruff check src tests          # lint
uv run ruff check src tests --fix    # autofix
uv run ruff format src tests         # format
```

Ruff is configured in `pyproject.toml` (line length 100; rule sets E, F, I, UP,
B, SIM). Dependency-injection defaults (`Depends`, `Form`, `typer.Option`) are
whitelisted from B008 there — they are the intended FastAPI/Typer idiom, not
mutable-default bugs.

**Comment convention.** Comments explain *why*, and cite the design decision they
implement (`design §7.3`, `D12`, `ADR-0004`). This keeps the code traceable to
the reasoning. Match the surrounding density; do not narrate *what* the code
plainly does.

---

## 6. The CLI

Every capability is a Typer subcommand, so any stage runs independently against
the stored data (design §7.1).

```powershell
uv run python -m app --help
```

| Command | Does |
|---|---|
| `collect` | Stage 1: collect and land raw postings |
| `normalise [--run-id N]` | Stage 2: fingerprint and deduplicate (latest run by default) |
| `score` | Stage 3: title filter + model scoring *(planned)* |
| `publish` | Stage 4: mark above-threshold published *(planned)* |
| `run-all` | Every stage in order, recording per-stage counts |
| `serve` | Run the scheduler in the foreground |
| `web` | Serve the triage interface |
| `status` | Recent runs and their per-stage counts |
| `config` | Print effective configuration, secrets masked |

Develop the web interface with autoreload:

```powershell
uv run python -m app web --reload
```

---

## 7. Changing the schema

The schema is managed by Alembic; models are the source of truth. To change it:

1. Edit the models in `src/app/db/models.py`.
2. Generate a migration against a running database:

   ```powershell
   uv run alembic revision --autogenerate -m "describe the change"
   ```

3. **Review the generated migration.** Autogenerate is a starting point, not an
   authority. In particular:
   - It does **not** detect data migrations, extension creation, or `CREATE
     EXTENSION`. The `vector` extension was added by hand for this reason.
   - **A new `NOT NULL` column on a populated table needs a `server_default`**
     for the backfill, dropped immediately afterward so the schema matches the
     model. Both existing migrations demonstrate the pattern.
   - Carry data across before dropping a column it lived in (the Notion→status
     migration moves `suppressed` into `status = 'rejected'` before dropping it).
4. Apply and verify:

   ```powershell
   uv run alembic upgrade head
   uv run alembic downgrade -1   # confirm the downgrade works, then upgrade again
   uv run alembic upgrade head
   ```

Alembic reads the database URL from `app.config.settings`, not from
`alembic.ini`, so there is one source of truth. `alembic.ini` is set to prepend
`src` to the path so `app` imports.

---

## 8. Configuration in code

Add settings to the `Settings` class in `config.py`. They are read from the
environment or `.env`, validated by pydantic at startup, and exposed as
`settings.<name>`. Complex values (like `SEARCHES`) are accepted as JSON strings
via a validator. Never read `os.environ` directly elsewhere; go through
`settings`.

---

## 9. Extending the pipeline

To implement a new stage (e.g. stage 3, scoring):

1. Put the pure logic in its own package (`app.score`), free of database
   concerns, with its own tests.
2. Add a persistence function in `app.pipeline` that reads from the database,
   calls the pure logic, and writes results — following `normalise_stage.py`.
3. Wire it into `__main__.py` as a subcommand and into `run-all`.
4. Update `runs` counts so the stage is observable (design §7.4).
5. Validate against real stored postings before trusting output — for scoring,
   design §12 item 9 requires checking a sample by hand first.

Keep stages idempotent: re-running against the same input must converge on the
same state.

*End of document.*
