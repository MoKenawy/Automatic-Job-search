# Implementation Plan: CLI Support

**Branch**: `CLI-Support-Feature` (spec directory `003-cli-support`) | **Date**: 13 August 2026 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-cli-support/spec.md`

**Design authority**: [Docs/CLI-Support.md](../../Docs/CLI-Support.md) is the
assessed design — command specifications, blocker decisions B1–B6, the
file-level change table, and the step ordering. This plan is the Spec Kit view
of it: the constitution gate, the structure decision, and the phase mapping. It
does not restate the design; where the two ever diverge, `Docs/CLI-Support.md`
is authoritative and this plan is the stale one.

## Summary

Promote the existing flat nine-command CLI (`app/src/app/__main__.py`) into a
grouped `app/cli/` adapter package beside `app/web/`, over the service layer both
share, and extend it with roughly twenty commands covering the operations that
are currently browser-only: triage transitions, employer suppression, search
profile CRUD, runtime settings, run health, and the two admitted reports.

This is a restructure and an expansion, not a greenfield build. Two findings from
the codebase assessment cut work out of the plan rather than adding it: no
business logic is trapped in the web controllers, so no controller refactoring is
needed; and there is no repository layer, so none is introduced.

The technical approach is a thin adapter package with three primitives — a
session provider, an exit-code translator, and an output formatter — under which
every command parses input, calls one service function, formats, and returns a
code. Two services gain a `patch()` counterpart so partial writes stay in the
service layer.

## Technical Context

**Language/Version**: Python 3.12 (`requires-python = ">=3.12,<3.13"`)

**Primary Dependencies**: Typer 0.27 on Click 8.4.2 — already a declared
dependency and already the project's CLI. SQLAlchemy 2.0, pydantic 2.7 /
pydantic-settings. **No new dependency is added by this feature.**

**Storage**: PostgreSQL via SQLAlchemy ORM; SQLite in-memory with `StaticPool` in
tests. **No schema change, no migration, no `alembic` run.**

**Testing**: pytest, plus `typer.testing.CliRunner` for the CLI layer. Baseline
is 224 tests, 0 of them CLI. Click 8.4.2 separates `result.stdout` and
`result.stderr` by default; the removed `mix_stderr` argument must not be passed.

**Target Platform**: Linux container (`python -m app web`, `python -m app serve`
under Docker Compose); developed on Windows.

**Project Type**: Single Python package, src-layout, with two adapters over one
service layer.

**Performance Goals**: None specified. Startup cost matters only insofar as the
existing deferred-import discipline is preserved, so `--help` stays cheap and a
root callback can still run before `app.db.session` is imported.

**Constraints**:
- The container command contract (`web`, `serve`) is frozen — FR-001.
- All 224 existing tests must pass unmodified — FR-003.
- Changes to shared service modules are additive; the single exception is a
  behaviour-preserving extraction inside `set_many`.
- No secret may be a command argument; the database is process-wide — FR-019,
  FR-020.

**Scale/Scope**: ~11 new modules under `app/src/app/cli/`, 9 commands ported
verbatim, ~20 commands added, 3 new service functions, 7 new test modules.
Single technical operator; no concurrency requirement.

## Constitution Check

*GATE: passed before Phase 0. Re-checked after Phase 1 design — still passing.*

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Adapters Are Thin** | **Pass**, with two recorded pre-existing exceptions | Every new command maps to one existing service function; where none expressed the operation, the service gains one (`profiles.patch`, `settings.patch`) rather than the adapter growing a merge loop. `cli/` is a leaf: nothing imports from it. Exceptions are logged in Complexity Tracking below. |
| **II. One Service Layer, No HTTP** | **Pass** | The CLI calls services directly. `uvicorn` appears only inside the pre-existing `web` command, which *starts* the server rather than calling it. No repository layer is introduced; services keep `Session` as their first argument, and no container or application factory is added. |
| **III. Exit Codes Are a Contract** | **Pass** | `Docs/CLI-Support.md` §3.4 fixes exactly the six codes the constitution names, and every command's specification states which it can return. `2` is left to Click rather than re-implemented. |
| **IV. Data on stdout, Diagnostics on stderr** | **Pass** | §3.5. Logging already defaults to stderr; `--output json` projects explicit dictionaries, never ORM rows. `--quiet` raises the log threshold rather than redirecting a stream. Asserted in tests, not merely intended. |
| **V. Destructive Ops Confirm** | **Pass** | §3.6 names four such commands. Prompts state the affected count; `--yes` bypasses; a non-TTY without `--yes` fails rather than hangs. `employers resweep` is specified and tested as idempotent. |
| **VI. Two-Level Testing** | **Pass** | §7. The three new service functions are proven in `test_profiles.py` / `test_settings.py`; CLI tests assert wiring, presentation, and exit codes only. §7.1 enumerates help, happy path, invalid arguments, and exit codes per command. |
| **Configuration and Secrets** | **Pass** | B1 fixes the database as process-wide with no per-command selection; B4 makes masking unconditional with no `--show-secrets`. ADR-0005 resolution order is untouched. |
| **Development Workflow** | **Pass** | Seven steps ordered so the suite is green after each; restructuring precedes new surface, read-only precedes writes, service additions precede the commands needing them. |

**No violation requires the plan to change.** Two entries in Complexity Tracking
record deviations that are *inherited and deliberately preserved*, not
introduced.

## Project Structure

### Documentation (this feature)

```text
specs/003-cli-support/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 — assessment findings and resolved unknowns
├── data-model.md        # Phase 1 — entities touched; no schema change
├── contracts/
│   └── cli-surface.md   # Phase 1 — command surface, exit codes, JSON shapes
├── checklists/
│   └── requirements.md  # Spec quality validation
└── tasks.md             # Phase 2 — created by /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── src/app/
│   ├── cli/                    # NEW — adapter package, beside web/
│   │   ├── __init__.py
│   │   ├── main.py             # root Typer app, group registration, root callback
│   │   ├── deps.py             # cli_session() — the session seam (B1)
│   │   ├── errors.py           # @handle_errors — exit-code translation (B5)
│   │   ├── output.py           # OutputFormat, emit() — table / JSON
│   │   ├── stages.py           # the nine existing commands, moved verbatim
│   │   ├── postings.py         # list · get · set-status
│   │   ├── employers.py        # blacklisted · blacklist · unblacklist · resweep
│   │   ├── profiles.py         # list · create · update · enable · disable · delete · run
│   │   ├── settings.py         # show · set
│   │   ├── runs.py             # list · health
│   │   └── reports.py          # employers · sources
│   ├── web/                    # unchanged — the other adapter
│   ├── services/               # +profiles.patch, +settings.patch, +settings.coerce_value
│   ├── pipeline/               # unchanged
│   ├── db/                     # unchanged
│   ├── config.py               # unchanged
│   └── __main__.py             # REDUCED to a shim importing cli.main:app
├── tests/
│   ├── conftest.py             # + shared SQLite StaticPool factory fixture
│   ├── test_cli_smoke.py       # NEW
│   ├── test_cli_errors.py      # NEW
│   ├── test_cli_postings.py    # NEW
│   ├── test_cli_employers.py   # NEW
│   ├── test_cli_profiles.py    # NEW
│   ├── test_cli_settings.py    # NEW
│   ├── test_cli_reports.py     # NEW
│   ├── test_profiles.py        # appended cases only
│   └── test_settings.py        # appended cases only
└── pyproject.toml              # one line: job-discovery = "app.cli.main:app"
```

**Structure Decision**: Single project, src-layout, **two adapters over one
service layer**. `app/cli/` is created as a top-level adapter package beside the
existing `app/web/`, mirroring its shape: `deps.py` is the CLI's counterpart to
`web/deps.py`, and the dependency rule that already forbids importing from
`web/` extends verbatim to `cli/`.

Hatchling's `packages = ["src/app"]` and pytest's `pythonpath = ["src"]` both
pick the new subpackage up with **no configuration change**; the only packaging
edit is the module path in the existing `[project.scripts]` entry.

The alternative — a separate top-level `cli/` distribution, or a CLI that drives
the system over HTTP — was rejected by Constitution §II and by the guideline's
own architectural principle: both entry points call the same services, and
introducing HTTP between them would add latency and couple the CLI to the web
surface for no gain.

## Phase Mapping

The seven steps in `Docs/CLI-Support.md` §5 map onto the Spec Kit phases as
follows. Ordering is load-bearing: the suite is green after each.

| Step | Phase | Delivers | Stories |
|---|---|---|---|
| 1 — Package skeleton, entry-point move | Foundational | `cli/` exists, `__main__.py` is a shim, logging moves off module scope | — (FR-001–003) |
| 2 — Adapter primitives | Foundational | Session seam (B1), exit codes (B5), output formatter | — (FR-012–015) |
| 3 — Port the nine commands verbatim | Foundational | Compose contract preserved under the new structure | — (FR-001) |
| 4 — Read-only groups | US1, US4, US5 | `postings list/get`, `employers blacklisted`, `profiles list`, `settings show`, `runs`, `reports` | P1, P3 |
| 5 — Close the service gaps | Foundational for US3, US4 | `profiles.patch`, `settings.patch`, `settings.coerce_value` | (FR-008, FR-009) |
| 6 — Mutating commands and confirmation | US1, US2, US3, US4 | `set-status`, blacklist group, profile CRUD + run, `settings set` | P1, P2, P3 |
| 7 — Documentation and operational polish *(optional)* | — | Docs level with the surface; optional `health`, `--version`, compose healthcheck | — |

Steps 1–3 carry no user-visible change whatsoever and exist to make steps 4–6
possible. Step 4 is the first that delivers an independently demonstrable user
story.

## Complexity Tracking

Two constitution deviations exist. Both are **inherited from the nine commands
being ported verbatim** and are preserved deliberately under FR-001; neither is
introduced by this feature.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `status` and `normalise` build their own `select(Run)` queries in the command body, rather than calling a service (Principle I) | FR-001 freezes these commands byte-identical. `docker-compose.yml`, the `Dockerfile`, and `development-guide.md` §6 all reference the existing surface; rewriting a command while relocating it makes a behaviour regression indistinguishable from a move | Refactoring `status` onto `queries.recent_runs` during step 3 would conflate "did the move break it?" with "did the rewrite break it?". It is listed instead as optional refactoring (§6.2), to be done after the port is proven green |
| `web` and `serve` start a server and a scheduler rather than calling a service (Principle I) | They are process entry points, not operations on data. `web` starts uvicorn; `serve` starts APScheduler. There is no service call to delegate to | Wrapping either in a service function would create a service whose only caller is the CLI and whose only behaviour is "block forever", which is worse than the honest exception |

## Phase 0 / Phase 1 Outputs

- **Phase 0 research** — [research.md](research.md). The assessment was
  performed against the working tree before this plan; all six unknowns (B1–B6)
  are resolved, none remain open.
- **Phase 1 data model** — [data-model.md](data-model.md). No new entity, no
  attribute change, no migration.
- **Phase 1 contracts** — [contracts/cli-surface.md](contracts/cli-surface.md).
  The command surface, the exit-code contract, and the JSON projections.
- **Phase 2 tasks** — produced by `/speckit-tasks` into `tasks.md`.
