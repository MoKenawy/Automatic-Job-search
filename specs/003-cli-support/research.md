# Phase 0 Research: CLI Support

**Date**: 13 August 2026 | **Plan**: [plan.md](plan.md)

The full assessment lives in [Docs/CLI-Support.md](../../Docs/CLI-Support.md) §2
and was read from the working tree, not inferred. This file records the
**decisions** that came out of it: what was unknown, what was chosen, and what
was rejected. Six unknowns were raised; all six are resolved and none remain
open.

---

## D1 — How does a CLI command get a database session?

**Unknown**: `db/session.py` builds `engine` and `SessionFactory` at *module
import* from `settings.database_url`. `session_scope()` takes no arguments. There
is no CLI analogue of `app.dependency_overrides[get_db]`, which is why zero CLI
tests exist today.

**Decision**: A single parameterless `cli_session()` context manager in
`cli/deps.py`, wrapping `session_scope()`. Per-command database selection is
**explicitly not supported**: no command takes a session parameter and none takes
a `--database-url`. Every command resolves the one process-wide database, exactly
as the web and the scheduler do.

`cli_session()` exists to give tests a single patchable name — a test seam, not a
production capability. The docstring must say so, or the next reader builds a
`--database-url` flag on top of it.

**Rejected**:
- *Parameterising `session_scope()` or rebuilding the engine per command* —
  changes a module the web and the scheduler both depend on, for a capability
  nothing asked for.
- *A `--database-url` option* — Constitution: no secret may be a command
  argument; arguments land in shell history and `ps` output.

**Deferred**: a root `--env-file` / `--db-profile` option that adjusts the
environment *before* `app.db.session` is imported. Feasible only because the
existing CLI defers stage imports into command bodies, so a root callback still
runs while `app.db.session` is unimported. Recorded as future work, not built.

---

## D2 — Can a session provider reach inside the pipeline runner?

**Unknown**: whether `run-all` and `profiles run` can be tested through the same
seam as every other command.

**Finding**: No. `runner.run_all_profiles()` and `run_one_profile(profile_id)`
take no session parameter — each opens its own `session_scope()` internally
(`pipeline/runner.py:84`, `:94`) because each must own the run-tracking
transaction.

**Decision**: **Two seams, not one.** Service-backed commands are tested by
patching `app.cli.deps.session_scope`; the two pipeline-backed commands are
tested by patching `app.pipeline.runner.session_scope`.

The distinction is not stylistic. `runner.py` does `from app.db import
session_scope`, so the name is bound into the runner's own module namespace at
import — patching `app.db.session.session_scope` afterwards has **no effect**.
`tests/test_scheduler.py` already uses precisely this pattern for
`app.scheduler.session_scope`, so the approach is proven in-repo rather than
novel.

**Consequence if ignored**: a CLI test that patches only `cli.deps` would assert
happily on argument parsing while the runner beneath it connects to the real
database. This is the single most likely way to write a silently wrong test here.

---

## D3 — How is a partial profile update expressed?

**Unknown**: `services.profiles.update()` looked like a partial update but is a
full-record replace. `_clean()` supplies a default for *every* absent key, so
`update(session, id, name="x")` blanks the role, resets the country, empties the
board list (which then trips `ProfileError`), resets the schedule to 06:00, and
disables the profile.

This is correct for the web, whose form always posts every field. It is silent
data loss for a CLI, where an unspecified option means "leave alone".

**Decision**: the service gains a `patch()` counterpart. `update()` remains the
PUT and is not touched; `patch(session, profile_id, **changed)` merges the named
fields onto current values and **delegates to `update()`**, so `_clean`,
`_validate`, the duplicate-name check, and the commit are reused rather than
duplicated — `patch` cannot drift from `update`'s rules.

**Rejected**: *merging in the CLI adapter.* Constitution §I — merging partial
input onto existing state is a business rule, and the adapter would have to know
the full field set and every default to do it.

---

## D4 — How is a single setting written?

**Unknown**: `set_many()` validates through `_EditableModel`, whose nine fields
are all required, so there is no partial write. Worse, `coerce_form()` fills
every missing key from the `Settings` singleton — i.e. from env/code defaults —
so a `settings set` built on it would reset the other eight keys to their
environment values, wiping stored overrides.

**Decision**: the same shape as D3 — `settings.patch(session, changes)` plus a
per-key `coerce_value(key, raw)` helper. `patch` merges over `all_effective`,
validates the **whole** set through `_EditableModel`, then writes **only the
changed keys**.

**The write-only-what-changed detail is the point.** Delegating to
`set_many(merged)` would be shorter and is what the web already does, but it
upserts all nine rows: after a single `settings set hours_old 48`, the other
eight keys become explicit database overrides, permanently pinned against the
environment. That silently breaks the ADR-0005 resolution order for keys the
operator never mentioned. Writing only the changed keys costs one extracted
private `_upsert()` helper and preserves inheritance.

**Rejected**: *reusing `coerce_form`'s nested `_as_list`* — it splits on newlines
for a textarea, while the CLI splits the proxy list on commas. Widening the
web's parser to serve the CLI would change web behaviour to save six lines.

---

## D5 — What exit codes does the CLI use?

**Unknown**: the existing CLI returns `1` both for "stage not implemented" and
for "no run found". Nothing distinguishes a missing row from a database outage,
so the CLI is not scriptable.

**Decision**: six codes — `0` success, `1` business failure, `2` invalid usage,
`3` not found, `4` infrastructure failure, `70` unexpected internal error
(`EX_SOFTWARE`). This extends the guideline's `0/1/2` compatibly rather than
redefining it, and is now fixed in the Constitution.

Implemented as a `@handle_errors` decorator, **not** a `main()` wrapper —
specifically so `CliRunner` exercises the translation in tests. `2` is left
entirely to Click and never re-implemented.

**Precision worth noting**: mapping `ProfileError` to `3` for
`set_enabled`/`delete` and to `1` for `create`/`update` is exact, not a
heuristic — those two functions raise it for no other reason than "not found". A
`ProfileNotFoundError` subclass would express this in the type system and is
recorded as optional refactoring.

---

## D6 — Two name collisions

**Unknown**: `status` already exists as a top-level command meaning "recent
runs", while a natural `postings status` would mean triage state. And a
`settings` command group would sit alongside both `app.config.settings` and
`app.services.settings`.

**Decision**:
- The *module* collision is a non-issue — Python 3 absolute imports mean
  `app/cli/settings.py` shadows neither.
- `status` keeps its name and behaviour (FR-001); the richer listing lives at
  `runs list`. Making `status` delegate to it is optional refactoring, deferred
  until after the verbatim port is proven green.
- `settings show` does **not** replace `config` and is not aliased to it. They
  answer different questions: `config` reads the environment only and needs no
  database, which is exactly what an operator wants during an outage;
  `settings show` reads database-resolved effective values. Both state the
  distinction in their help.

---

## Supporting technical findings

| Finding | Source | Consequence |
|---|---|---|
| Click is 8.4.2, so `CliRunner` separates `result.stdout` and `result.stderr` by default | dependency lock | Do **not** pass the removed `mix_stderr` argument. This separation is what lets tests assert logs never contaminate JSON. |
| `logging.basicConfig` currently runs at `__main__.py` module scope | `__main__.py:15` | Importing the CLI reconfigures global logging as a side effect. Moves into a root `@app.callback()`. The stderr default is already correct and is preserved. |
| Stage imports are deferred into command bodies | `__main__.py:27, 44, 95` | Keeps `--help` cheap, and is the precondition that would make a future `--env-file` option workable. Preserve it during the port. |
| `packages = ["src/app"]` and `pythonpath = ["src"]` | `pyproject.toml` | A new `app/cli/` subpackage is picked up by both the wheel build and pytest with no configuration change. |
| `[project.scripts] job-discovery` already exists | `pyproject.toml` | Packaging is already correct; only the module path moves. |
| `blacklist.reject_employer_postings` is public and documented as a targeted re-sweep, but is called only from tests | `services/blacklist.py` | `employers resweep` is the missing production caller, not a new capability. |
| `tests/test_web_reports.py` already asserts the sampling-bias caveat for the templates | test suite | The CLI must assert the same for table and JSON output — "a caveat nothing tests is a caveat that disappears in the next layout change". |
| Each test module builds its own in-memory SQLite engine with `StaticPool` | `app/tests/` | The house pattern. A shared factory fixture is added to `conftest.py` for the seven new modules; existing modules keep their local fixtures untouched. |
