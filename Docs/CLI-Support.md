# CLI Support — Implementation Plan

| | |
|---|---|
| **Author** | Mohammed |
| **Date** | 13 August 2026 |
| **Status** | Proposal |
| **Scope governed by** | [CLI Development Guideline](Implementation_guidelines/CLI-DEV-Guidlines.md) |
| **Related** | [System Architecture](design/system-architecture.md); [Development Guide](development-guide.md) §6; [ADR-0005](ADRs/0005-ui-config-and-db-search-profiles.md); [ADR-0008](ADRs/0008-report-system-scope.md) §1; [ADR-0014](ADRs/0014-status-transition-row-locking.md); [SRS](software-requirements-specification.md) IR-1 |
| **Assessed against** | branch `job-post-transitions`, 224 tests, 0 CLI tests |

---

## 1. Scope and headline finding

**This is not a greenfield CLI build.** The repository already ships a Typer
CLI — `app/src/app/__main__.py`, nine commands, 187 lines — and already
declares `[project.scripts] job-discovery = "app.__main__:app"`. Typer 0.27.0
on Click 8.4.2 is already a dependency, and `tech-stack.md` already names Typer
as the CLI. SRS **IR-1** already requires a command-line interface exposing each
stage, and that requirement is met today.

What this plan proposes is therefore a **restructure and an expansion**: promote
the flat `__main__.py` into a grouped `app/cli/` adapter package sitting beside
`app/web/`, over the service layer both already share, and add roughly twenty
commands to reach the parts of the system that are currently only operable
through a browser.

Two structural findings shape everything that follows, and both cut work out of
the plan rather than adding it:

- **No business logic is trapped in the API controllers.** Every route in
  `web/routes/` already delegates to a service. `services/triage.py` says so in
  its own docstring — extracted from route bodies "so the same transition logic
  is callable from a future CLI command, not only from an HTTP handler." No
  controller refactoring is required.
- **There is no repository layer, and none should be built.** The SQLAlchemy
  `Session` plus the module-level functions in `services/` *are* the data-access
  layer. Introducing repositories would be unrelated refactoring, explicitly out
  of scope.

Out of scope: stages 3 and 4 remain unimplemented, so `score` and `publish` stay
as stubs. No database, schema, migration, route, or Pydantic model changes.

---

## 2. Current architecture assessment

Everything below was read from the working tree, not inferred.

### 2.1 What exists

| Concern | Where it lives | Shape, and what it means for a CLI |
|---|---|---|
| Package layout | `app/src/app/` | src-layout. Hatchling wheel `packages = ["src/app"]`; pytest `pythonpath = ["src"]`. A new `app/cli/` subpackage is picked up by both with no configuration change. |
| **Existing CLI** | `src/app/__main__.py` | Typer 0.27, Click 8.4.2. Nine flat commands: `collect`, `normalise`, `score`, `publish`, `run-all`, `serve`, `web`, `status`, `config`. Stage imports are deferred into command bodies to keep startup cheap. |
| Packaging / entry point | `pyproject.toml` | `[project.scripts] job-discovery = "app.__main__:app"` **already exists**. Only the module path needs to move. |
| FastAPI entry points | `web/app.py`, `web/routes/*.py` | Module-level `app = FastAPI(...)` with five routers, a `/` dashboard and `/healthz`. Server-rendered Jinja; no JSON API and **no response schemas**. |
| Application services | `services/{queries,triage,blacklist,profiles,settings,reports}.py` | Plain module-level functions, `Session` as the first argument, returning ORM rows or dataclasses. No classes, no constructor injection. **Directly callable from a CLI as-is.** |
| Repositories | — none — | See §1. The `Session` and the service modules are the data-access layer. |
| Pipeline | `pipeline/{runner,collect_stage,normalise_stage,suppress_stage}.py` | `runner.run_all_profiles()` and `run_one_profile(id)` own their session and run tracking. Already the shared entry point for the CLI, the scheduler, and the web "run now". |
| Composition root | `web/deps.py::get_db` (web only) | The web has a seam; the CLI has none. `db/session.py` builds `engine` and `SessionFactory` at **import time** from `settings.database_url`. |
| Configuration | `config.py` | Three reusable tiers: the `Settings` pydantic-settings singleton (env + `.env`); `RunConfig.resolve(session)`, a frozen per-run snapshot; and `services/settings.py` for DB overrides. Resolution order DB → env → code default (ADR-0005). |
| Pydantic models | `config.py`, `services/settings.py::_EditableModel` | Used for **configuration and validation only**, never as request/response DTOs. There is no serialisation contract for a CLI to reuse — and none for it to break. |
| Exception handling | service modules | `ProfileError`, `EmployerNotFoundError`, `UnknownStatusError` all subclass `ValueError`, plus pydantic `ValidationError`. No shared base class and no not-found/invalid distinction. Routes translate these to `HTTPException` or a redirect carrying `?error=`. |
| Logging | `__main__.py` module scope | `logging.basicConfig(level=INFO)` runs at import. The default handler is stderr, so the log/stdout split is *already correct* — but it is global, unconditional, and fires merely on import. |
| Tests | `app/tests/` | 224 collected, no Docker required. Each module builds its own in-memory SQLite engine with `StaticPool`; web tests swap `app.dependency_overrides[get_db]`. `conftest.py` holds one autouse fixture neutering `time.sleep`. **Zero CLI tests.** |
| Scripts / management commands | `docker-compose.yml`, `Dockerfile` | No `scripts/` directory. Compose invokes `python -m app web` and `python -m app serve`; the one-shot `migrate` service runs `alembic upgrade head`. Dockerfile `CMD` is `python -m app --help`. |

### 2.2 Blockers

Only **B1** genuinely blocks integration. **B2** and **B3** are correctness traps
that would cause silent data loss if a CLI naively reused the existing service
signatures. **B4**–**B6** are defects the new surface must not inherit.

**B1–B4 are decided**; each carries its **Decision** inline below. **B5** and
**B6** are resolved in §3.4 and §3.2 respectively.

#### B1 — No session seam for the CLI, and the engine is built at import time

`db/session.py` instantiates `create_engine(settings.database_url)` and
`SessionFactory` at module import (`session.py:11-18`). `session_scope()` takes
no arguments: it draws from that one module-level factory, so every call — from
the web, the scheduler, the pipeline, or a CLI command — reaches the same
database. There is no CLI analogue of `app.dependency_overrides[get_db]`, which
is why zero CLI tests exist today.

**Decision — per-command database selection is out of scope.**

*Not supported, and not proposed:* passing a session bound to a caller-chosen
database configuration into a CLI command. No command takes a session parameter,
no command takes a `--database-url`, and `cli_session()` is **not** an injection
point for arbitrary connection settings.

*Supported:* every command resolves its database from the process environment,
through `settings.database_url` — the single value `db/session.py` read at
import time. One process, one database, fixed before the process starts. This is
exactly how the web and the scheduler behave today, and what `docker-compose.yml`
already relies on.

`cli/deps.py::cli_session()` therefore exists for one reason: to give the CLI a
**single patchable name** so tests can redirect it to in-memory SQLite. It is a
test seam, not a production capability. That distinction must stay explicit in
the code, or the next reader will build a `--database-url` flag on top of it.

**Future work, deliberately not in this plan.** A command that selects the
database — most plausibly a root `--env-file` / `--db-profile` option that
adjusts `settings.database_url` before the engine exists — is a reasonable
extension. Two constraints bind it, and both must be honoured:

1. **It must run before `app.db.session` is imported.** Rebinding the variable
   after import does nothing: `engine` is already built from the old value. The
   existing deferred-import discipline makes this achievable — `__main__.py`
   imports stage modules *inside* command bodies, so a root `@app.callback()`
   still executes while `app.db.session` is unimported. Any such feature must
   preserve that discipline, or it silently no-ops against the wrong database.
2. **It must never accept a credential-bearing URL as an argument** (§3.6). The
   option names an env file or an alias; the URL itself stays in the
   environment.

**B1a — the pipeline owns its own sessions, and that does not change.**
`runner.run_all_profiles()` and `run_one_profile(profile_id)` take no session
parameter; each opens its own `session_scope()` internally (`runner.py:84`,
`runner.py:94`) because each must own the run-tracking transaction. A CLI-level
session provider cannot reach inside them.

Consequence for tests: `run-all` and `profiles run` are covered by patching
`app.pipeline.runner.session_scope`, not `app.cli.deps.session_scope`. Because
`runner.py` does `from app.db import session_scope`, that name is bound into the
runner's own namespace at import, so patching `app.db.session.session_scope`
afterwards has no effect. `tests/test_scheduler.py` already uses precisely this
pattern for `app.scheduler.session_scope`. Two seams, not one — designed for
here rather than discovered in step 6.

#### B2 — `services.profiles.update()` is a full-record replace, not a partial update

`_clean()` supplies a default for *every* absent key. So
`update(session, id, name="x")` would blank `term`, reset `country` to
`"egypt"`, empty `sites` (which then trips `ProfileError`), reset the schedule to
06:00, and set `enabled` to `False`.

This is safe for the web, whose form always posts every field, and unsafe for a
CLI, where an unspecified option must mean "leave alone".

**Decision — the service exposes a `patch()` method.** `update()` is the PUT and
keeps its semantics unchanged; `patch(session, profile_id, **changed)` is the
PATCH counterpart. Merging current values with the caller's changes is a
business rule and belongs in `services/`: doing it in the CLI adapter would
require the adapter to know the full field set and every default.

```python
# services/profiles.py — additive; update() is not touched
_FIELDS = (
    "name", "term", "location", "country", "is_remote",
    "sites", "experience", "schedule_hour", "schedule_minute", "enabled",
)

def patch(session: Session, profile_id: int, **changed) -> SearchProfile:
    """Update only the named fields. Omitted fields keep their current value."""
    profile = session.get(SearchProfile, profile_id)
    if profile is None:
        raise ProfileError("profile not found")
    unknown = set(changed) - set(_FIELDS)
    if unknown:
        raise ProfileError(f"unknown field(s): {', '.join(sorted(unknown))}")
    current = {k: getattr(profile, k) for k in _FIELDS}
    merged = current | {k: v for k, v in changed.items() if v is not None}
    return update(session, profile_id, **merged)
```

Delegating to `update()` is deliberate: `_clean`, `_validate`, the
duplicate-name check and the commit are all reused unchanged, so `patch` cannot
drift from `update`'s rules. The round-trip through `_clean` is safe for every
field — `_as_bool(True)` returns `True`, `sites` is already a list, and the two
nullable fields map `None → None`.

`None` means "unspecified", which is what a Typer option defaults to. Clearing a
nullable field is therefore `--location ""`: the empty string, which `_clean`
maps back to `None`. Stated in the command's help text.

#### B3 — `services.settings` has no single-key write, and `coerce_form` would discard DB overrides

`set_many()` validates through `_EditableModel`, whose nine fields are all
required; there is no partial write. Worse, `coerce_form()` fills every missing
key from the `Settings` singleton, i.e. from **env/code defaults**. A CLI
`settings set` built on `coerce_form` would therefore reset the other eight keys
to their env defaults, wiping stored overrides.

**Decision — the same shape as B2: the service exposes `patch()`, plus a
per-key coercion helper.** Read-modify-write is a business rule for exactly the
reason profile merging is, so it does not live in the CLI adapter.

**Scope of change: one service module, two new public functions, ~40 lines,
plus tests.**

| Change | Kind | Size | Alters existing behaviour |
|---|---|---|---|
| `settings.coerce_value(key, raw)` | New | ~20 lines | No |
| `settings.patch(session, changes)` | New | ~14 lines | No |
| `_upsert(session, key, value)`, extracted from `set_many`'s loop | Refactor | ~6 lines | No — `set_many` behaves identically |
| `__all__` | Edit | 2 entries | No |
| Cases in `tests/test_settings.py` | New | ~60 lines | No existing case modified |

Nothing else moves. `_EditableModel`, `EDITABLE_KEYS`, `get`, `all_effective`,
`set_many`'s signature and semantics, and `coerce_form` are all unchanged, so
the web settings page is unaffected. No schema change, no migration, and
`test_every_editable_key_is_consumed_or_pending` is untouched.

```python
def patch(session: Session, changes: dict[str, Any]) -> dict[str, Any]:
    """Write some editable settings; the rest keep their current resolution."""
    unknown = set(changes) - set(EDITABLE_KEYS)
    if unknown:
        raise ValueError(f"not an editable setting: {', '.join(sorted(unknown))}")
    merged = all_effective(session) | changes
    validated = _EditableModel(**merged).model_dump()   # whole-set validation
    for key in changes:                                 # write only what changed
        _upsert(session, key, validated[key])
    session.commit()
    return validated
```

**One semantic decision sits inside that snippet.** Validation runs over the
whole merged set, so `_EditableModel`'s rules — and any future cross-field rule
— keep working. But only the *changed* keys are written. The shorter
alternative, delegating to `set_many(merged)`, is what the web already does and
upserts all nine rows: after a single `settings set hours_old 48`, the other
eight keys would become explicit DB overrides, permanently pinned against the
environment. That silently breaks the ADR-0005 resolution order for keys the
operator never mentioned, so the `_upsert` extraction earns its six lines.

`coerce_value` parses one string into the type `_EditableModel` declares for
that key. It deliberately does **not** reuse `coerce_form`'s nested `_as_list`,
which splits on newlines for a textarea; the CLI splits `proxies` on commas.
Six lines of divergence beats widening the web's parser.

#### B4 — The existing `config` command does not mask `proxies`

`_mask()` is applied to `database_url` only. `settings.proxies` legitimately
carries `http://user:pass@host` credentials and is printed nowhere today — but a
`settings show` command reading `all_effective()` would print it verbatim.

**Decision — accepted, and unconditional.** Every new command that can print a
settings value masks both `proxies` and `database_url`. There is no
`--show-secrets` flag and no per-invocation override (§3.6). Applied in step 4
and regression-tested in `test_cli_settings.py`, which asserts the output
carries neither the proxy credential nor the database password. Masking the
`proxies` textarea in the *web* settings template stays optional (§6.2): it is a
pre-existing exposure, not one this plan introduces.

#### B5 — No exit-code convention

`_unimplemented()` returns `1`; "no run found" also exits `1`. Nothing
distinguishes a not-found id from a database outage. A convention has to be
fixed before roughly twenty commands are written against it, or the CLI is not
scriptable.

#### B6 — Two name collisions to resolve deliberately

`status` already exists as a top-level command meaning "recent runs", while a
natural `postings status` would mean triage state. And a `settings` command
group sits alongside `app.config.settings` and `app.services.settings`. The
*module* name is safe — Python 3 absolute imports mean `app/cli/settings.py`
shadows neither — but the command naming needs a decision, taken in §3.

### 2.3 Not blockers, recorded so they are not "fixed"

Every route in `web/routes/` already delegates: `employers.py` calls
`blacklist_service`, `postings.py` calls `triage_service` and `queries`,
`profiles.py` calls `profile_store`. What remains in the routes —
`_render_list()`'s pager URLs, `_multi_form()`'s checkbox flattening — is
genuinely presentational and must **not** be pulled into services.

---

## 3. Proposed CLI design

Two rules shape the hierarchy. First, **every existing top-level command keeps
its exact name and behaviour** — `docker-compose.yml` runs `python -m app web`
and `python -m app serve`, the Dockerfile's `CMD` is `python -m app --help`, and
[development-guide.md](development-guide.md) §6 tabulates all nine. Second,
**every new command maps to a service function that already exists**; where one
does not, the command is not proposed.

### 3.1 Command hierarchy

```
job-discovery                     (= python -m app)
│
│  global: --log-level  --quiet/-q  --traceback  --version
│
├── collect                       stage 1                    [existing, unchanged]
├── normalise [--run-id N]        stage 2                    [existing, unchanged]
├── score                         stage 3 stub → exit 1      [existing, unchanged]
├── publish                       stage 4 stub → exit 1      [existing, unchanged]
├── run-all                       every stage in order       [existing, unchanged]
├── serve                         scheduler, foreground      [existing — compose depends]
├── web  [--host --port --reload] triage interface           [existing — compose depends]
├── status [--limit]              recent runs                [existing, unchanged]
├── config                        env-resolved config        [existing, unchanged]
│
├── postings    list · get · set-status
├── employers   blacklisted · blacklist · unblacklist · resweep
├── profiles    list · create · update · enable · disable · delete · run
├── settings    show · set
├── runs        list · health
└── reports     employers · sources
```

### 3.2 Command specifications

Every command takes `--output/-o table|json` unless noted. All are
non-interactive by default; the commands marked **confirm** prompt on a TTY and
accept `--yes/-y` for automation.

#### `postings` — the triage surface (US1, US2)

| Command | Purpose | Arguments / options | Service | Output | Exit / errors | Confirm |
|---|---|---|---|---|---|---|
| `postings list` | Page the triage queue under the same filters the web list offers | `--status` (Choice of `STATUSES`), `--q`, `--published/--no-published`, `--country` (incl. `unknown`), `--remote/--on-site`, `--source`, `--page`, `--per-page` | `queries.list_postings` | id · status · score · employer · title · country, plus an `n–m of T (page p/P)` footer built from `Page` | 0 always; an empty page is not an error | no |
| `postings get` | Full detail for one posting, including per-board provenance | `POSTING_ID` | `queries.get_posting` | Field block; `sources` expanded one board per line | **3** when it returns `None` | no |
| `postings set-status` | Transition one or many postings | `POSTING_IDS...` (variadic), `--status` (required, Choice), `--reason` (single id only), `--yes` | `triage.set_status` for one; `triage.set_status_bulk` for many | `Set posting 42 → shortlist`, or `Updated 7 of 9 posting(s) → rejected` | **2** on a bad status (Click `Choice`); **3** when a single id is absent | **yes**, when >1 id or status is `rejected` |

`set_status_bulk` takes no `reason`, so `--reason` is accepted for the
single-id form only. That asymmetry is pre-existing and is surfaced in help text
rather than papered over.

#### `employers` — blacklist (US3)

| Command | Purpose | Arguments / options | Service | Output | Exit / errors | Confirm |
|---|---|---|---|---|---|---|
| `employers blacklisted` | List suppressed employers with their posting counts | — | `queries.blacklisted_employers` | id · name · postings | 0 | no |
| `employers blacklist` | Suppress an employer and reject their postings in one transaction (ADR-0014) | `EMPLOYER_ID`, `--yes` | `blacklist.blacklist` | `Blacklisted PwC (id 3). Rejected 12 posting(s).` | **3** on `EmployerNotFoundError` | **yes** — mass state change |
| `employers unblacklist` | Lift a blacklist | `EMPLOYER_ID` | `blacklist.lift` | Help and output must both state that already-rejected postings are **not** reinstated (FR-011) | **3** on `EmployerNotFoundError` | no |
| `employers resweep` | Re-run the rejection sweep for one already-suppressed employer | `EMPLOYER_ID` | `blacklist.reject_employer_postings` | `Rejected N posting(s).` Idempotent — a second call rejects nothing | **3** if the employer is absent | no |

`reject_employer_postings` is public, documented as "safe to call as a targeted
re-sweep, independently of `blacklist()`", and is currently reachable only from
`tests/test_blacklist.py`. `employers resweep` is that missing production
caller, not a new capability.

#### `profiles` — search profiles (US4, ADR-0005)

| Command | Purpose | Arguments / options | Service | Output | Exit / errors | Confirm |
|---|---|---|---|---|---|---|
| `profiles list` | All saved profiles and their schedules | — | `profiles.list_all` | id · name · enabled · term · location · country · remote · sites · `HH:MM` | 0 | no |
| `profiles create` | Define a new profile | `--name`\*, `--term`\*, `--location`, `--country`, `--remote/--no-remote`, `--site` (repeatable), `--experience`, `--hour`, `--minute`, `--enabled/--disabled` | `profiles.create` — **unchanged**; `_clean()` already accepts typed values | `Created profile 'Cairo DE' (id 4).` | **1** on `ProfileError` (blank name/term, no sites, unsupported site, duplicate name, hour/minute out of range); **2** on a non-integer `--hour` | no |
| `profiles update` | Change named fields only; unspecified options are left alone. `--location ""` clears a nullable field | `PROFILE_ID` + every `create` option, all defaulting to `None` | `profiles.patch` **(new)** — see B2 | `Updated profile 4: term, sites.` | **1** on validation; **3** when absent | no |
| `profiles enable` / `disable` | Toggle whether the scheduler picks the profile up | `PROFILE_ID` | `profiles.set_enabled` | `Profile 4 enabled.` The scheduler re-registers within 5 minutes via its `updated_at` poll | **3** — `ProfileError` here can only mean "not found" | no |
| `profiles delete` | Remove a profile permanently | `PROFILE_ID`, `--yes` | `profiles.delete` | Confirmation copy should note that run history survives — `runs.profile_id` is `ON DELETE SET NULL` | **3** when absent | **yes** — hard delete |
| `profiles run` | Run one profile's full pipeline now, as the web "run now" button does | `PROFILE_ID` | `pipeline.runner.run_one_profile` | Progress to stderr; final counts to stdout. Warn when `collected == 0` — that is the design §7.4 decay signal | **3** on `ValueError("profile … not found")`; **4** if the database is unreachable. Collector failures are recorded on `run.error`, not raised, so they stay exit 0 | no — long-running automation target |

`profiles create` needs **no service change**: `_clean()` coerces via
`str(v).lower()` and `int(...)`, so Typer's already-typed `True` and `6` pass
through correctly.

#### `settings` — runtime-editable operational settings (ADR-0005)

| Command | Purpose | Arguments / options | Service | Output | Exit / errors | Confirm |
|---|---|---|---|---|---|---|
| `settings show` | Effective values resolved DB → env → code default | — | `settings.all_effective` + `READONLY_KEYS` | key · value · source. **Masks `proxies` and `database_url`** (B4) | **4** if the database is unreachable | no |
| `settings set` | Override one editable key | `KEY` (Choice of `EDITABLE_KEYS`), `VALUE` | `settings.coerce_value` → `settings.patch` **(both new)** — see B3 | `results_per_search: 50 → 100` | **2** on an unknown key (Choice); **1** on `ValidationError` — prior values stand (FR-015) | no |

**`settings show` does not replace `config`, and `config` is not aliased to it.**
The two answer different questions: `config` reads the environment only and needs
no database, which is exactly what an operator wants during an outage;
`settings show` reads the DB-resolved effective values. Both keep their own help
text stating the distinction. This resolves the second half of B6.

`settings.patch` performs a read-modify-write across the nine keys to validate,
even though it writes only the one. The race that implies is acceptable here —
the SRS scopes the system to a single technical operator — and the command
echoes the before → after value so the change is visible in a CI log.

#### `runs` and `reports` — observability

| Command | Purpose | Arguments / options | Service | Output | Exit | Confirm |
|---|---|---|---|---|---|---|
| `runs list` | Recent runs with the profile that triggered each | `--limit` (default 30) | `queries.recent_runs` | Richer than the existing `status`, which issues its own query and cannot show the profile name | 0 | no |
| `runs health` | Per-source counts across recent runs — the design §7.4 decay surface | `--limit` (default 14) | `queries.source_health` | One row per board, one column per run. `--output json` earns its place here: this is the series a monitor would alert on, and it is currently visible only in the browser | 0 | no |
| `reports employers` | Employers ranked by distinct roles surfaced (R1) | `--limit`, `--include-suppressed` | `reports.employer_activity` | See the caveat requirement below | 0 | no |
| `reports sources` | Board coverage, overlap, and first-surfacer counts (R3) | — | `reports.source_overlap` | See the caveat requirement below | 0 | no |

**Both report commands must carry the ADR-0008 §1 sampling-bias caveat with
their output.** That is the condition on which each report was admitted, and
`tests/test_web_reports.py` already asserts it for the templates — "a caveat
nothing tests is a caveat that disappears in the next layout change". For the
CLI: a footer line in table output, a `caveat` field in JSON, and a test
asserting both.

`status` is kept unchanged rather than removed, since §6 of the development
guide documents it. Making it delegate to `runs list` is listed as optional
refactoring in §6.2.

### 3.3 One design call worth recording

**`postings list` drops the web's `country=remote` sentinel.**
`routes/postings.py::_render_list` overloads one `country` selector to carry the
remote axis, because an HTML form had a single dropdown to spend.
`queries.list_postings` already exposes `remote` as a real tri-state parameter,
so the CLI takes `--remote/--on-site` and leaves the sentinel where it belongs —
in the web form.

### 3.4 Exit codes

| Code | Meaning | Raised by |
|---|---|---|
| `0` | Success | Normal return. An empty result set is success. |
| `1` | Business / application failure | `ProfileError` on create/update, `ValidationError` from `set_many`, the `score`/`publish` stubs. |
| `2` | Invalid CLI usage | Click's own default — bad option, bad `Choice`, missing argument. Comes free; do not re-implement it. |
| `3` | Not found | `EmployerNotFoundError`; `get_posting`/`set_status` returning `None`; `ProfileError` from `set_enabled`/`delete`, where "not found" is its only cause. |
| `4` | Infrastructure failure | `sqlalchemy.exc.OperationalError` / `DBAPIError` — database unreachable, schema not migrated. |
| `70` | Unexpected internal error | Anything else. One-line message; traceback only behind `--traceback`. `70` is `EX_SOFTWARE` from `sysexits.h`. |

Mapping `ProfileError` to 3 for `set_enabled`/`delete` and to 1 for
`create`/`update` is exact, not a heuristic: those two functions raise it for no
other reason. A `ProfileNotFoundError(ProfileError)` subclass would express this
in the type system and is listed as optional refactoring in §6.2.

### 3.5 Output and logging

Human-readable tables on **stdout** via `typer.echo`, hand-formatted in the
column style `__main__.py::status` already uses — no new dependency, and stable
column output for scripting. Application logging stays on **stderr**, which
`logging.basicConfig`'s default handler already does, so `--output json` yields
clean, pipeable stdout even while services log at INFO. `--quiet` raises the log
threshold to `WARNING` rather than redirecting anything.

JSON output projects **explicit dictionaries**, never serialised ORM rows. That
keeps the CLI's JSON a stable contract a schema change cannot silently alter,
and it means no new Pydantic models are needed anywhere.

### 3.6 Security

- **No secret is ever a CLI argument.** `DATABASE_URL` stays env-only; no
  `--database-url` flag is proposed. Arguments land in shell history and in `ps`
  output. This is the security half of the B1 decision: the database is chosen
  by the environment before the process starts, never by a command argument. If
  the future `--env-file` option is ever built, it names a file, never a URL.
- **No `--show-secrets` escape hatch.** `settings show` masks `proxies` and
  `database_url` unconditionally. Anyone entitled to the raw values can read
  `.env`.
- **Four destructive or administrative commands** — `profiles delete` (hard
  delete), `employers blacklist` (mass rejection and un-publication),
  `postings set-status` in bulk or to `rejected`, and `settings set` (changes
  behaviour for the scheduler and every other process). The first three confirm
  on a TTY and take `--yes`; `settings set` echoes before → after.
- **Pre-existing, out of scope, recorded here:** the web settings page renders
  `proxies` unmasked in a textarea.

---

## 4. Target architecture

Two adapters, one service layer, no HTTP between them. `cli/` becomes a
top-level adapter package beside `web/`, and the dependency rule in
[CLAUDE.md](../CLAUDE.md) extends by one clause: **nothing may import from
`cli/`**, exactly as nothing imports from `web/`.

```mermaid
flowchart TB
    CLI["Typer CLI<br/>app/cli/*.py"]
    API["FastAPI<br/>app/web/routes/*.py"]

    CLIA["CLI adapter<br/>cli/deps.py · session provider<br/>cli/errors.py · exit codes<br/>cli/output.py · table / json"]
    APIA["API adapter<br/>web/deps.py · get_db<br/>Jinja2 templates"]

    SVC["Application services<br/>queries · triage · blacklist<br/>profiles · settings · reports"]
    PIPE["Pipeline<br/>runner · collect · normalise · suppress"]
    DB[("SQLAlchemy Session<br/>db/models.py → PostgreSQL")]
    CFG["config.py<br/>Settings · RunConfig"]

    CLI --> CLIA
    API --> APIA
    CLIA --> SVC
    APIA --> SVC
    CLIA --> PIPE
    PIPE --> SVC
    SVC --> DB
    PIPE --> DB
    CFG -.-> CLIA
    CFG -.-> APIA
    CFG -.-> SVC
    CFG -.-> PIPE
```

The `CLIA → PIPE` edge is real and pre-existing: `run-all`, `collect`,
`normalise` and `profiles run` drive pipeline stages, not services. The
`PIPE → SVC` edge is likewise already there — `pipeline/runner.py` imports
`services.profiles` to resolve enabled specs. Neither is introduced here.

### 4.1 Where dependencies come from

**No DI container, and no application factory.** Services are module-level
functions whose only dependency is a `Session` passed as the first argument —
there is nothing to construct and nothing to wire. The composition root is
therefore exactly one thing: a session provider.

```python
# app/cli/deps.py — the CLI's counterpart to web/deps.py::get_db

@contextmanager
def cli_session() -> Iterator[Session]:
    """Session for one CLI command, against the process's configured database.

    The database comes from settings.database_url, resolved once at import in
    db/session.py. This is NOT an injection point for per-command connection
    settings (B1) — it takes no parameters by design. It exists so tests can
    patch one name, as the web patches app.dependency_overrides[get_db].
    """
    with session_scope() as session:
        yield session
```

One indirection, patchable at `app.cli.deps.session_scope`, and `db/session.py`
is left untouched — changing it would put the web and the scheduler at risk for
no gain. The provider takes no arguments, and per-command database selection is
out of scope (B1). Commands that reach `pipeline.runner` keep owning their own
session inside it (B1a) and are tested by patching
`app.pipeline.runner.session_scope`.

---

## 5. Implementation plan

Seven steps, ordered so the suite is green after each. Steps 1–3 are pure
restructuring with no behaviour change; step 4 is read-only; the two service
additions in step 5 land before the writes in step 6 that need them.

### Step 1 — Package skeleton and entry-point move

| | |
|---|---|
| **Objective** | Create `app/cli/` and make `__main__.py` a shim, with no user-visible change whatsoever. |
| **Files** | *New:* `src/app/cli/__init__.py`, `cli/main.py`. *Modified:* `src/app/__main__.py`, `pyproject.toml`. |
| **Changes** | `cli/main.py` holds `app = typer.Typer(add_completion=False, help=…)`. `__main__.py` reduces to `from app.cli.main import app` plus the `if __name__ == "__main__": app()` guard, preserving `python -m app`. `[project.scripts]` becomes `job-discovery = "app.cli.main:app"`. Move `logging.basicConfig` out of module scope into a root `@app.callback()` so importing the CLI no longer reconfigures global logging. |
| **Tests** | New `tests/test_cli_smoke.py`: `--help` exits 0 and lists all nine existing commands. The existing 224 must stay green, untouched. |
| **Risk** | Low, but the blast radius is wide if wrong. Verify `python -m app --help`, `python -m app web --help`, `python -m app serve --help` and `uv run job-discovery --help` all still resolve before moving on. |

### Step 2 — CLI adapter primitives

| | |
|---|---|
| **Objective** | Build the session seam (B1), the exit-code translator (B5), and the output formatter once, before any command depends on them. |
| **Files** | *New:* `cli/deps.py`, `cli/errors.py`, `cli/output.py`. |
| **Changes** | `deps.py`: the `cli_session()` context manager from §4.1. `errors.py`: a `@handle_errors` decorator mapping `EmployerNotFoundError` and `None` returns to 3, `ProfileError` and `ValidationError` to 1, `OperationalError`/`DBAPIError` to 4, and anything else to 70 — message on stderr, traceback only under `--traceback`. A decorator rather than a `main()` wrapper specifically so `CliRunner` exercises it. `output.py`: `OutputFormat` enum plus `emit(rows, columns, fmt)` over explicit dict projections. |
| **Tests** | Direct unit tests of the decorator: one raise per branch, asserting each exit code and that no traceback reaches stderr without the flag. |
| **Risk** | Low — nothing calls it yet. |

### Step 3 — Port the nine existing commands verbatim

| | |
|---|---|
| **Objective** | Relocate the existing command bodies into `cli/stages.py` with names, options, output text, and exit codes byte-identical. |
| **Files** | *New:* `cli/stages.py`. *Modified:* `cli/main.py` registers it. |
| **Changes** | Move `collect`, `normalise`, `score`, `publish`, `run-all`, `serve`, `web`, `status`, `config` unchanged, keeping the deferred imports. Registered at the root, not in a group. Optional while here: correct `normalise`'s `run_id` annotation from `int` to `int \| None`. |
| **Tests** | Extend the smoke test to assert every command still resolves and `config` still masks the database password. `web` and `serve` are covered at `--help` level only — invoking them starts servers. |
| **Risk** | **Medium — the compose contract.** `web` and `serve` are container commands; a rename or a changed default breaks deployment silently. Diff the help output before and after. |

### Step 4 — Read-only groups

| | |
|---|---|
| **Objective** | Ship every command that cannot mutate state, proving the session seam and the output layer against real services. |
| **Files** | *New:* `cli/postings.py` (`list`, `get`), `cli/employers.py` (`blacklisted`), `cli/profiles.py` (`list`), `cli/settings.py` (`show`), `cli/runs.py`, `cli/reports.py`. |
| **Changes** | Thin adapters over `queries` and `reports`. Apply the `proxies` mask in `settings show` (B4). Attach the ADR-0008 caveat to both report commands. |
| **Tests** | Per group: table output, `--output json` parses and carries the expected keys, filters narrow the result, `get` on a missing id exits 3, and the reports caveat is present in both formats. |
| **Risk** | Low — no writes. The one thing to get right is that `settings show` never prints a credential. |

### Step 5 — Close the two service gaps

| | |
|---|---|
| **Objective** | Give both services a PATCH counterpart, so partial profile updates and single-key setting writes are expressible without duplicating business rules in the CLI (B2, B3). |
| **Files** | *Modified:* `services/profiles.py`, `services/settings.py`. |
| **Changes** | `profiles.patch(session, profile_id, **changed)`: load the profile, merge `changed` onto its current values, then delegate to `update()` so `_clean`, `_validate`, the duplicate-name check and the commit are all reused. `update()` itself is not touched. `settings.coerce_value(key, raw)`: parse one string to the type `_EditableModel` declares for that key (comma-splitting for `proxies`). `settings.patch(session, changes)`: merge over `all_effective`, validate the whole set through `_EditableModel`, write only the changed keys via a private `_upsert()` extracted from `set_many`'s loop. Add the three public names to `__all__`. |
| **Tests** | New cases appended to `tests/test_profiles.py` and `tests/test_settings.py`: a partial profile update leaves other fields intact and still rejects a duplicate name; `settings.patch` changes one key, leaves the other eight resolving as before, and rejects an unknown key; `coerce_value` round-trips each of the nine keys and raises on garbage. **No existing test is modified.** |
| **Risk** | **Medium** — the only step touching shared service modules. Everything is additive except the `_upsert` extraction, which is a pure move of `set_many`'s upsert loop with no behaviour change; `set_many`, `update()` and `coerce_form()` keep their signatures and semantics, which is what holds the web constant. `tests/test_settings.py::test_every_editable_key_is_consumed_or_pending` must still pass. |

### Step 6 — Mutating commands and confirmation

| | |
|---|---|
| **Objective** | Complete the four write-capable groups with interactive safety and an automation bypass. |
| **Files** | *Modified:* `cli/postings.py`, `cli/employers.py`, `cli/profiles.py`, `cli/settings.py`. |
| **Changes** | Add `set-status`; `blacklist`, `unblacklist`, `resweep`; `create`, `update`, `enable`, `disable`, `delete`, `run`; `settings set`. Confirmation via `typer.confirm` guarded by `--yes`, skipped when stdin is not a TTY so a piped invocation fails loudly rather than hanging. |
| **Tests** | Per command: success path and its exit code; not-found → 3; validation failure → 1; bad `Choice` → 2; confirmation declined leaves state unchanged and exits non-zero; `--yes` proceeds without a prompt. |
| **Risk** | **Medium** — these write. `employers blacklist` in particular mass-rejects and un-publishes in one transaction (ADR-0014); its confirmation prompt should state the posting count it is about to affect. |

### Step 7 — Documentation and operational polish *(optional)*

| | |
|---|---|
| **Objective** | Bring the docs level with the surface, and spend the new CLI where it pays operationally. |
| **Files** | `Docs/development-guide.md` §6, `Docs/README.md`, `Docs/design/system-architecture.md`, `CLAUDE.md`; `docker-compose.yml`. |
| **Changes** | Extend the §6 command table to the groups. Add `cli/` to the architecture listings with the rule that nothing imports from it. Optionally add a root `health` command (`SELECT 1`, the same probe as `/healthz`) and give the `scheduler` service the healthcheck it currently lacks — the one addition motivated by operations rather than by an existing service function, hence optional. A root `--version` from `importlib.metadata` is likewise cheap and optional. |
| **Tests** | `health` exits 0 against the test database and 4 against a closed engine. |
| **Risk** | Low. The compose healthcheck is additive; leave the `web` service's existing check alone. |

---

## 6. File-level change plan

Paths are relative to `app/`. Only files that actually require changes are
listed.

| File | Change | Reason | Risk |
|---|---|---|---|
| `src/app/cli/__init__.py` | **New** — empty package marker | Makes `cli/` a top-level adapter beside `web/` | Low |
| `src/app/cli/main.py` | **New** — root Typer app, group registration, root callback for `--log-level`/`--quiet`/`--traceback`/`--version` | Single entry point; moves `basicConfig` off module scope | Low |
| `src/app/cli/deps.py` | **New** — `cli_session()`, no parameters | The CLI's `get_db`. Resolves **B1** and makes CLI tests possible; not a per-command DB selector | Low |
| `src/app/cli/errors.py` | **New** — `@handle_errors` + exit-code constants | Resolves **B5**; keeps tracebacks off the operator's screen | Low |
| `src/app/cli/output.py` | **New** — `OutputFormat`, `emit()` | One table/JSON implementation; explicit projections decouple JSON from the ORM | Low |
| `src/app/cli/stages.py` | **New** — the nine existing commands, moved verbatim | Preserves the compose and docs contract while emptying `__main__.py` | Medium |
| `src/app/cli/postings.py` | **New** — `list`, `get`, `set-status` | Over `queries` and `triage` | Low |
| `src/app/cli/employers.py` | **New** — `blacklisted`, `blacklist`, `unblacklist`, `resweep` | Over `blacklist` and `queries`; gives `reject_employer_postings` a production caller | Low |
| `src/app/cli/profiles.py` | **New** — full CRUD + `run` | Over `profiles` and `pipeline.runner` | Low |
| `src/app/cli/settings.py` | **New** — `show`, `set` | Over `services.settings`. Module name is safe under absolute imports | Low |
| `src/app/cli/runs.py` | **New** — `list`, `health` | Puts the design §7.4 decay surface on a scriptable interface | Low |
| `src/app/cli/reports.py` | **New** — `employers`, `sources` | Over `services.reports`, carrying the ADR-0008 caveat | Low |
| `src/app/__main__.py` | **Reduce** to a two-line shim importing `cli.main:app` | `python -m app` is the container invocation path and must not change | Medium |
| `pyproject.toml` | **Edit one line:** `job-discovery = "app.cli.main:app"` | Console script follows the module. No new dependency — `typer>=0.12` already present | Low |
| `src/app/services/profiles.py` | **Add** `patch()` + `_FIELDS` — additive only | Resolves **B2**. `update()` untouched, so the web is unaffected | Medium |
| `src/app/services/settings.py` | **Add** `patch()`, `coerce_value()`, `__all__` entries; **extract** `_upsert()` from `set_many` | Resolves **B3**. `set_many()`/`coerce_form()` keep identical behaviour | Medium |
| `tests/conftest.py` | **Add** a shared SQLite `StaticPool` factory fixture | Every CLI test module needs one; existing modules keep their local fixtures and are not edited | Low |
| `tests/test_cli_*.py` | **New** — six modules | See §7 | Low |
| `tests/test_profiles.py`, `tests/test_settings.py` | **Append** cases for the two new service functions | Service behaviour is proven at the service level, not only through the CLI | Low |
| `Docs/development-guide.md` | **Edit** the §6 command table | §6 currently documents exactly the nine commands and would go stale | Low |
| `Docs/README.md`, `Docs/design/system-architecture.md`, `CLAUDE.md` | **Edit** the structure tree / component table *(optional)* | All three list `__main__.py` as the CLI; add `cli/` and the no-inbound-imports rule | Low |
| `docker-compose.yml` | **Add** a `scheduler` healthcheck *(optional)* | Only if the optional root `health` command is built; that service has no healthcheck today | Low |

### 6.1 Required

The eleven new `cli/` modules, the `__main__.py` shim, the `pyproject.toml`
entry-point line, the three new service functions (`profiles.patch`,
`settings.patch`, `settings.coerce_value`) and the `_upsert` extraction, the
conftest fixture, the CLI tests, and the `development-guide.md` §6 table.

### 6.2 Optional refactoring, explicitly off the critical path

- A `ProfileNotFoundError(ProfileError)` subclass, so not-found is distinguished
  from invalid by type rather than by which command raised it (§3.4).
- Making `status` delegate to `runs list`, removing the duplicate query.
- Correcting `normalise`'s `run_id` annotation to `int | None`.
- The root `health` and `--version` commands, and the compose healthcheck.
- Masking `proxies` in the web settings template.
- A root `--env-file` / `--db-profile` option for selecting the database before
  `app.db.session` is imported — the B1 future-work item, subject to the two
  constraints recorded there.

### 6.3 Backward compatibility

No route, response, or redirect changes. No Pydantic model changes —
`SearchSpec`, `Settings`, `RunConfig`, and `_EditableModel` are untouched. No
behavioural change to `update()`, `set_many()`, `coerce_form()`, or any other
existing service function; the three additions are new names. The one edit to an
existing function body is mechanical: `set_many`'s upsert loop moves into a
private `_upsert()` that `settings.patch` also calls, leaving `set_many`'s
signature, validation, commit, and log line exactly as they are. No
`db/models.py` edit, no migration, no `alembic` run. Configuration semantics are
unchanged: the CLI reads the same `Settings` singleton, resolves its database
from the same `settings.database_url` as the web and the scheduler (B1), and
follows the same DB → env → default order, introducing no configuration system
of its own. All 224 existing tests are expected to pass unmodified; the only
edits to existing test files are appended cases.

---

## 7. Testing strategy

`typer.testing.CliRunner`, following the house pattern: in-memory SQLite with
`StaticPool`, seeded per module, no Docker. The CLI equivalent of
`app.dependency_overrides[get_db]` is monkeypatching
`app.cli.deps.session_scope` to the test factory. Monkeypatching is the *only*
way a test redirects the database — no command accepts a connection argument
(B1), so a test that forgets to patch runs against `settings.database_url`.

**Two seams, not one.** Commands that call services go through `cli.deps`.
Commands that call `pipeline.runner` — `run-all` and `profiles run` — open their
own session internally (B1a) and are tested by patching
`app.pipeline.runner.session_scope`, with `collect_all` stubbed so no test
touches the network. Getting this wrong is the most likely way to write a CLI
test that silently talks to the real database.

Click is 8.4.2, so `CliRunner` separates `result.stdout` and `result.stderr` by
default — do not pass the removed `mix_stderr` argument. That separation is what
lets the tests assert log output never contaminates JSON.

| Module | Covers |
|---|---|
| `test_cli_smoke.py` | Root `--help` exits 0 and lists every group; `--help` for each group and each command; all nine legacy commands still resolve; `config` masks the password; the `score`/`publish` stubs exit 1 with a message on stderr. |
| `test_cli_errors.py` | The `@handle_errors` decorator per branch: not-found → 3, business error → 1, `OperationalError` → 4, unexpected → 70; no traceback on stderr without `--traceback`, traceback present with it. |
| `test_cli_postings.py` | `list` under each filter and its pager footer; `get` success and missing → 3; `set-status` single and bulk; bad status → 2; bulk confirmation declined leaves status unchanged; `--yes` proceeds unprompted; `--output json` parses and carries the expected keys. |
| `test_cli_employers.py` | `blacklisted` listing; `blacklist` rejects the employer's postings and reports the count; missing id → 3; `unblacklist` does **not** reinstate previously rejected postings (FR-011); `resweep` is idempotent on a second call; confirmation behaviour. |
| `test_cli_profiles.py` | `create` success and each `ProfileError` path → 1; non-integer `--hour` → 2; **`update` leaves unspecified fields untouched** — the direct regression test for B2; `enable`/`disable`; `delete` confirmation and `--yes`; `run` with `collect_all` stubbed. |
| `test_cli_settings.py` | `show` resolves DB over env; **output contains neither the proxy credential nor the database password** — the regression test for B4; `set` changes one key and **leaves the other eight untouched, still resolving from env rather than pinned as overrides** — the regression test for B3; invalid value → 1 with prior values intact; unknown key → 2. |
| `test_cli_reports.py` | Both report commands against the seeded corpus; **the ADR-0008 sampling-bias caveat appears in table output and in the JSON payload**, mirroring what `test_web_reports.py` asserts for the templates. |

### 7.1 Required coverage

| Requirement | Where it is met |
|---|---|
| `--help` | `test_cli_smoke.py` — root, every group, every command |
| Successful commands | At least one happy path per command across the six modules |
| Invalid arguments | Bad `Choice`, non-integer option, missing required argument — all asserted at exit 2 |
| Business / application failures | `ProfileError` and `ValidationError` paths at exit 1, with the message on stderr |
| Exit codes | `test_cli_errors.py` covers every branch of the mapping directly |
| Confirmation behaviour | Declining leaves state unchanged, for all four confirming commands |
| Non-interactive execution | `--yes` proceeds without a prompt; a non-TTY stdin without `--yes` fails rather than hangs |
| Output formatting | Table headers and column order asserted; JSON parsed and keyed; stdout confirmed free of log lines |

Service behaviour is **not** re-tested through the CLI. The two new service
functions get their own cases in `test_profiles.py` and `test_settings.py`; the
CLI tests assert wiring, presentation, and exit codes.

---

## 8. Final decisions

| | |
|---|---|
| **Framework** | Typer — already a dependency at 0.27.0 on Click 8.4.2, already the declared CLI in `tech-stack.md`. No framework is added. |
| **Architecture** | CLI as a first-class application adapter: `app/cli/` beside `app/web/`, both over the same services. Nothing imports from `cli/`. |
| **Business logic** | Shared application services in `app/services/`, unchanged except for three new functions — `profiles.patch`, `settings.patch`, `settings.coerce_value`. Merging partial input is a service concern, not an adapter one (B2, B3). Commands parse, resolve a session, call one service, format, return a code. |
| **HTTP dependency** | None. The CLI never calls the FastAPI app; `uvicorn` appears only inside the pre-existing `web` command, which starts the server rather than calling it. |
| **Validation** | Typer type hints and `Choice` for CLI input, exiting 2 via Click. Business rules stay in `services/` — `_validate`, `_EditableModel`, `Posting.transition_to` — and surface as exit 1. |
| **Dependency injection** | No container and no application factory. Services take a `Session`; the composition root is the single parameterless `cli_session()` provider, mirroring `web/deps.py::get_db`. |
| **Database selection** | Process-wide, from `settings.database_url` in the environment, fixed before the process starts — as for the web and the scheduler. Per-command database configuration is **not supported** and no command accepts a connection argument (B1). A root `--env-file` option is recorded as future work in §6.2. |
| **Configuration** | The existing system, unchanged: `app.config.settings` plus the ADR-0005 DB → env → default order. No CLI-specific configuration, no secrets as arguments. |
| **Output** | Human-readable tables on stdout by default; `--output json` where automation benefits, projected from explicit dicts. Logging stays on stderr. |
| **Testing** | `typer.testing.CliRunner` over in-memory SQLite with `StaticPool`, matching the existing suite. Existing application tests are extended, never rewritten. |
| **Packaging** | The project's existing mechanism — hatchling with `packages = ["src/app"]` and the `[project.scripts]` console entry point that already exists. One line changes: the module path. |
