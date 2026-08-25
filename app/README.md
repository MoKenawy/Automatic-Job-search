# app/ — the Python project

This directory holds the application: `pyproject.toml`, `src/app/`, `tests/`,
the Dockerfile, the Compose file, and the Alembic migrations. **All development
commands run from here.**

The project's front page is the [repository README](../README.md) — what the
system is, the architecture, the dependency direction, and the quick start.
This file exists only so the directory is not silently undocumented; the
canonical content is one level up, and it is deliberately not repeated here.

## The commands, in short

```bash
uv sync                              # install the locked dependency graph
docker compose up -d postgres        # database only, for host-side development
uv run pytest                        # full suite — no Docker required
uv run ruff check src tests          # lint
uv run ruff format src tests         # format
uv run python -m app --help          # the CLI entry point
uv run python -m app web --reload    # triage UI with autoreload
```

## Where to read next

- [Repository README](../README.md) — architecture, structure, quick start
- [CONTRIBUTING](../CONTRIBUTING.md) — conventions and review rules
- [Development guide](../Docs/development-guide.md) — the fuller treatment
- [Deployment guide](../Docs/deployment-guide.md) — standing the system up
- [Documentation index](../Docs/README.md) — everything else
