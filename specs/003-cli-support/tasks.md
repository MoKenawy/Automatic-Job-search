---
description: "Task list for CLI Support — operating the system without a browser"
---

# Tasks: CLI Support

**Input**: Design documents from `/specs/003-cli-support/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli-surface.md](contracts/cli-surface.md)

**Design authority**: [Docs/CLI-Support.md](../../Docs/CLI-Support.md) — §3.2 holds the per-command specification each task implements against.

**Tests**: Included. The specification requires automated coverage for every command (SC-008) and the constitution makes it non-negotiable (Principle VI).

**Organization**: Grouped by user story so each is independently implementable and testable. **Paths are relative to `app/`.**

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency
- **[Story]**: US1–US5, or blank for foundational work

## Reconciliation with `Docs/CLI-Support.md` §5

The design document orders work in seven linear steps. This file regroups the
same work by user story, which changes two things and nothing else:

- **Step 4 (read-only) and Step 6 (mutating) are split across story phases.** A
  story owns both its read and its write commands, so it can be demonstrated on
  its own.
- **Step 5 (the service gaps) is distributed to the stories that need it.**
  `profiles.patch` lands in Phase 5 (US3), `settings.patch` and
  `coerce_value` in Phase 6 (US4). Service-before-command still holds inside
  each phase.

Steps 1–3 map onto Phase 2 unchanged, and their ordering is load-bearing.

---

## Phase 1: Setup

**Purpose**: Establish the baseline that FR-001 and FR-003 are measured against.

- [ ] **T001** Run the suite and record the baseline: `uv run pytest` from `app/` must collect **224 passing tests**. Any pre-existing failure is resolved or documented before proceeding — the plan's central claim is that this number does not move.
- [ ] **T002** [P] Capture the current help output of all nine commands to a scratch file (`--help` for root, `collect`, `normalise`, `score`, `publish`, `run-all`, `serve`, `web`, `status`, `config`). This is the artefact T018 diffs against; without it, "byte-identical" is an assertion rather than a check.
- [ ] **T003** [P] Confirm both invocation paths resolve today: `python -m app --help` and `uv run job-discovery --help`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The package skeleton, the three adapter primitives, and the verbatim port. Carries **no user-visible change whatsoever**.

**⚠️ CRITICAL**: No user story work can begin until Phase 2 is complete and the suite is green.

### Step 1 — Package skeleton and entry-point move

- [ ] **T004** Create `src/app/cli/__init__.py` as an empty package marker.
- [ ] **T005** Create `src/app/cli/main.py`: `app = typer.Typer(add_completion=False, help=…)` plus a root `@app.callback()` carrying `--log-level`, `--quiet/-q`, and `--traceback`. **Move `logging.basicConfig` out of module scope into that callback** so importing the CLI no longer reconfigures global logging as a side effect. Keep the stderr default handler — the stream split is already correct.
- [ ] **T006** Reduce `src/app/__main__.py` to a shim: `from app.cli.main import app` plus the `if __name__ == "__main__": app()` guard. `python -m app` is the container invocation path and must keep working.
- [ ] **T007** Edit one line in `pyproject.toml`: `[project.scripts] job-discovery = "app.cli.main:app"`. No dependency is added — Typer is already present.
- [ ] **T008** New `tests/test_cli_smoke.py`: root `--help` exits 0 and lists all nine existing commands.
- [ ] **T009** Verify `python -m app --help`, `python -m app web --help`, `python -m app serve --help`, and `uv run job-discovery --help` all still resolve. **Do not proceed past this task if any does not** — the blast radius is the whole deployment.

### Step 2 — Adapter primitives

- [ ] **T010** [P] Create `src/app/cli/deps.py` with the parameterless `cli_session()` context manager (plan §4.1). Its docstring must state that it is **not** an injection point for per-command connection settings (B1/D1) — that sentence is what stops the next reader building a `--database-url` flag on it.
- [ ] **T011** [P] Create `src/app/cli/errors.py`: exit-code constants and a `@handle_errors` decorator mapping `EmployerNotFoundError` and `None` returns → 3, `ProfileError`/`ValidationError` → 1, `OperationalError`/`DBAPIError` → 4, anything else → 70. Message on stderr; traceback only under `--traceback`. **A decorator, not a `main()` wrapper** — specifically so `CliRunner` exercises it.
- [ ] **T012** [P] Create `src/app/cli/output.py`: an `OutputFormat` enum and `emit(rows, columns, fmt)` over **explicit dict projections**, never serialised ORM rows. Table style follows the existing `__main__.py::status` column formatting; no new dependency.
- [ ] **T013** Add a shared in-memory SQLite `StaticPool` session-factory fixture to `tests/conftest.py`. Existing test modules keep their local fixtures and are **not** edited.
- [ ] **T014** New `tests/test_cli_errors.py`: one raise per branch of `@handle_errors`, asserting each exit code, that no traceback reaches stderr without the flag, and that it does with it.

### Step 3 — Port the nine existing commands verbatim

- [ ] **T015** Create `src/app/cli/stages.py` and move `collect`, `normalise`, `score`, `publish`, `run-all`, `serve`, `web`, `status`, `config` into it **unchanged** — names, options, defaults, output text, and exit codes byte-identical. Keep the deferred imports inside command bodies; they keep `--help` cheap and are the precondition for any future `--env-file` option. Register at the root, not in a group.
- [ ] **T016** Register `stages.py` in `cli/main.py`.
- [ ] **T017** Extend `tests/test_cli_smoke.py`: every command resolves, `config` still masks the database password, and the `score`/`publish` stubs exit 1 with a message on **stderr**. `web` and `serve` are covered at `--help` level only — invoking them starts servers.
- [ ] **T018** **Gate:** diff the help output of all nine commands against the T002 capture. Any difference is a deployment-contract break (FR-001) and must be reverted, not accepted.
- [ ] **T019** Run the suite. It must still be **224 passing plus the new CLI tests**, with no existing test modified.

**Checkpoint**: `app/cli/` exists, the three primitives are tested, the nine commands behave identically, and the container contract is proven intact. User story work can begin.

---

## Phase 3: User Story 1 — Triage the queue from a terminal (Priority: P1) 🎯 MVP

**Goal**: List, read, and transition postings entirely from the command line.

**Independent Test**: Seed postings across statuses, then list under filters, read one, and transition one and several — verifying database state afterwards.

### Tests for User Story 1

> Write these first and confirm they fail. All live in one file, so they are sequential.

- [ ] **T020** [US1] New `tests/test_cli_postings.py`: `list` under each filter (`--status`, `--q`, `--published/--no-published`, `--country` including the unknown bucket, `--remote/--on-site`, `--source`, `--page`, `--per-page`), asserting the `n–m of T (page p/P)` footer and that an **empty page exits 0**.
- [ ] **T021** [US1] Add to `test_cli_postings.py`: `get` on an existing id shows the full field block with one line per source board; `get` on a missing id exits **3** with the message on stderr.
- [ ] **T022** [US1] Add to `test_cli_postings.py`: `set-status` single and bulk; a bad status exits **2** via Click's `Choice`; confirmation declined leaves status unchanged and exits non-zero; `--yes` proceeds unprompted; a non-TTY stdin without `--yes` **fails rather than hangs**.
- [ ] **T023** [US1] Add to `test_cli_postings.py`: `--output json` parses while services log at INFO, carries the keys fixed in [contracts/cli-surface.md](contracts/cli-surface.md) §3, and **stdout contains no log lines**.

### Implementation for User Story 1

- [ ] **T024** [US1] Create `src/app/cli/postings.py` with `list`, over `queries.list_postings`. Project `queries.Page` into the footer — `total`/`number` are fields, `pages`/`first`/`last` are properties.
- [ ] **T025** [US1] Add `get`, over `queries.get_posting`, which returns `tuple[Posting, Employer] | None`; the `None` is the exit-3 path.
- [ ] **T026** [US1] Add `set-status`: `triage.set_status` for a single id, `triage.set_status_bulk` for many. `--reason` is accepted **for the single-id form only** — `set_status_bulk` takes no reason, and the asymmetry is surfaced in help text rather than papered over.
- [ ] **T027** [US1] Add confirmation to `set-status` when more than one id is given or the target status is `rejected`: prompt states the affected count, `--yes` bypasses, non-TTY without `--yes` fails loudly.
- [ ] **T028** [US1] Register the `postings` group in `cli/main.py`.
- [ ] **T029** [US1] Confirm `--remote/--on-site` is wired to `list_postings`'s real tri-state `remote` parameter and that **the web's `country=remote` sentinel is not carried over** (design §3.3).

**Checkpoint**: US1 is fully functional and demonstrable on its own — a filtered list piped into a bulk transition, with no browser and no prompt.

---

## Phase 4: User Story 2 — Suppress an employer and sweep their postings (Priority: P2)

**Goal**: Blacklist, lift, and re-sweep from the command line, with the mass-write blast radius stated before it happens.

**Independent Test**: Blacklist a seeded employer, assert their postings are rejected and the count reported; lift and confirm the rejections are not reversed.

### Tests for User Story 2

- [ ] **T030** [US2] New `tests/test_cli_employers.py`: `blacklisted` lists suppressed employers with posting counts; `blacklist` rejects the employer's postings and reports the count; a missing id exits **3** on `EmployerNotFoundError`.
- [ ] **T031** [US2] Add to `test_cli_employers.py`: `unblacklist` lifts suppression and **does not reinstate previously rejected postings** (FR-011); `resweep` is **idempotent** — a second call rejects nothing and still exits 0.
- [ ] **T032** [US2] Add to `test_cli_employers.py`: confirmation on `blacklist` — declined leaves the employer unsuppressed and their postings untouched; `--yes` proceeds; the prompt states the posting count it is about to affect.

### Implementation for User Story 2

- [ ] **T033** [US2] Create `src/app/cli/employers.py` with `blacklisted`, over `queries.blacklisted_employers` (returns `list[tuple[Employer, int]]`).
- [ ] **T034** [US2] Add `blacklist`, over `blacklist.blacklist` — suppression and the posting sweep are **one transaction with row locking** (ADR-0014), so the command must not split them.
- [ ] **T035** [US2] Add `unblacklist`, over `blacklist.lift`. Both the **help text and the output** must state that already-rejected postings are not reinstated.
- [ ] **T036** [US2] Add `resweep`, over `blacklist.reject_employer_postings` — a public, documented function currently reachable only from tests. This command is its missing production caller, not a new capability.
- [ ] **T037** [US2] Register the `employers` group in `cli/main.py`.

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 5: User Story 3 — Manage search profiles and run one on demand (Priority: P2)

**Goal**: Full profile CRUD plus an on-demand pipeline run, with partial updates that do not destroy unspecified fields.

**Independent Test**: Create a profile, change exactly one field, assert every other field is untouched; then run it with the collector stubbed.

### Service gap first (B2 / D3)

- [ ] **T038** [US3] Add `patch()` and `_FIELDS` to `src/app/services/profiles.py` — **additive; `update()` is not touched**. Load the profile, reject unknown field names, merge non-`None` changes onto current values, then delegate to `update()` so `_clean`, `_validate`, the duplicate-name check, and the commit are reused. Implementation is given in `Docs/CLI-Support.md` §2.2 B2.
- [ ] **T039** [US3] Append cases to `tests/test_profiles.py`: a partial update leaves every other field intact; it still rejects a duplicate name; it raises on an unknown field; an empty string clears a nullable field. **No existing case is modified.**

### Tests for User Story 3

- [ ] **T040** [US3] New `tests/test_cli_profiles.py`: `create` success, and each `ProfileError` path exits **1** (blank name, blank term, no sites, unsupported site, duplicate name, hour/minute out of range); a non-integer `--hour` exits **2**.
- [ ] **T041** [US3] Add to `test_cli_profiles.py`: **`update` leaves unspecified fields untouched** — the direct regression test for B2 — and `--location ""` clears a nullable field.
- [ ] **T042** [US3] Add to `test_cli_profiles.py`: `enable`/`disable`; `delete` with confirmation declined and with `--yes`; a missing id exits **3** for all three.
- [ ] **T043** [US3] Add to `test_cli_profiles.py`: `run` with `collect_all` **stubbed so no test touches the network**, patching `app.pipeline.runner.session_scope` — **not** `app.cli.deps.session_scope` (B1a/D2). A test that patches only `cli.deps` here would silently hit the real database.

### Implementation for User Story 3

- [ ] **T044** [US3] Create `src/app/cli/profiles.py` with `list`, over `profiles.list_all`. Project `schedule_hour`/`schedule_minute` into one `HH:MM` field.
- [ ] **T045** [US3] Add `create`, over `profiles.create` — **no service change needed**: `_clean()` coerces via `str(v).lower()` and `int(...)`, so Typer's already-typed values pass through correctly.
- [ ] **T046** [US3] Add `update`, over the new `profiles.patch`. Every option defaults to `None` meaning "unspecified"; the help text states that an empty string clears a nullable field.
- [ ] **T047** [US3] Add `enable` and `disable`, over `profiles.set_enabled`. `ProfileError` here can only mean "not found", so it maps to **3**. Note in help that the scheduler re-registers within 5 minutes via its `updated_at` poll.
- [ ] **T048** [US3] Add `delete`, over `profiles.delete`, with confirmation. The prompt states that **run history survives** — `runs.profile_id` is `ON DELETE SET NULL`.
- [ ] **T049** [US3] Add `run`, over `pipeline.runner.run_one_profile`. Progress to stderr, final counts to stdout. **Warn when `collected == 0`** — that is the design §7.4 decay signal. Exit **3** on `ValueError("profile … not found")`, **4** if the database is unreachable; collector failures are recorded on `run.error` rather than raised, so they stay exit 0.
- [ ] **T050** [US3] Register the `profiles` group in `cli/main.py`.

**Checkpoint**: US1–US3 all work independently. Profiles are manageable and runnable from cron or CI.

---

## Phase 6: User Story 4 — Inspect and change operational settings safely (Priority: P3)

**Goal**: Read effective settings with credentials masked, and override exactly one key without disturbing the inheritance of the other eight.

**Independent Test**: Store an override for one key, set a different key, assert the first survives and the rest still resolve from the environment rather than becoming pinned.

### Service gap first (B3 / D4)

- [ ] **T051** [US4] Extract the upsert loop from `set_many` into a private `_upsert(session, key, value)` in `src/app/services/settings.py`. **Pure move — `set_many`'s signature, validation, commit, and log line are unchanged**, and its existing tests are the proof.
- [ ] **T052** [US4] Add `patch(session, changes)`: reject unknown keys, merge over `all_effective`, validate the **whole** set through `_EditableModel`, then write **only the changed keys** via `_upsert`. Writing all nine would pin the untouched keys as database overrides and silently break the ADR-0005 resolution order — see [research.md](research.md) D4.
- [ ] **T053** [US4] Add `coerce_value(key, raw)`: parse one string into the type `_EditableModel` declares for that key, **comma-splitting for `proxies`**. Do not reuse `coerce_form`'s nested `_as_list`, which splits on newlines for a textarea. Add all three public names to `__all__`.
- [ ] **T054** [US4] Append cases to `tests/test_settings.py`: `patch` changes one key and leaves the other eight resolving from the environment; `patch` rejects an unknown key; an invalid value leaves every prior value standing (FR-015); `coerce_value` round-trips each of the nine keys and raises on garbage. **`test_every_editable_key_is_consumed_or_pending` must still pass.**

### Tests for User Story 4

- [ ] **T055** [US4] New `tests/test_cli_settings.py`: `show` resolves database over environment and labels the source of each key.
- [ ] **T056** [US4] Add to `test_cli_settings.py`: **output contains neither the proxy credential nor the database password, in table or JSON** — the regression test for B4.
- [ ] **T057** [US4] Add to `test_cli_settings.py`: `set` changes one key and **leaves the other eight untouched and still inheriting** — the regression test for B3; an invalid value exits **1** with prior values intact; an unknown key exits **2**.

### Implementation for User Story 4

- [ ] **T058** [US4] Create `src/app/cli/settings.py` with `show`, over `settings.all_effective` plus `READONLY_KEYS`. **Mask `proxies` and `database_url` unconditionally** — no `--show-secrets` flag exists (B4, FR-021). The module name is safe under Python 3 absolute imports and shadows neither `app.config.settings` nor `app.services.settings`.
- [ ] **T059** [US4] Add `set`, over `coerce_value` → `patch`. Echo the before → after value so the change is visible in a CI log.
- [ ] **T060** [US4] Ensure `show`'s help states that it is **not** a replacement for `config`: `config` reads the environment only and needs no database, which is what an operator wants during an outage. Update `config`'s help with the reciprocal sentence.
- [ ] **T061** [US4] Register the `settings` group in `cli/main.py`.

**Checkpoint**: US1–US4 all work independently. No settings output can leak a credential.

---

## Phase 7: User Story 5 — Observe pipeline health and reporting (Priority: P3)

**Goal**: Put the decay signal and both reports on a scriptable interface.

**Independent Test**: Seed runs across boards, assert the health series is emitted machine-readably with one entry per board per run.

### Tests for User Story 5

- [ ] **T062** [US5] New `tests/test_cli_runs.py`: `list` shows each run with its triggering profile name; `health` emits a per-board series; both exit 0 over an empty database.
- [ ] **T063** [US5] New `tests/test_cli_reports.py`: both report commands against the seeded corpus, and **the ADR-0008 §1 sampling-bias caveat appears in table output and in the JSON payload** — mirroring what `tests/test_web_reports.py` already asserts for the templates.

### Implementation for User Story 5

- [ ] **T064** [US5] Create `src/app/cli/runs.py` with `list`, over `queries.recent_runs` — richer than the existing `status`, which issues its own query and cannot show the profile name.
- [ ] **T065** [US5] Add `health`, over `queries.source_health`, which returns `(datetime, int)` tuples oldest-first. **Name both members in the JSON projection** rather than emitting positional pairs — this is the series a monitor alerts on.
- [ ] **T066** [US5] Create `src/app/cli/reports.py` with `employers`, over `reports.employer_activity` (`--limit`, `--include-suppressed`).
- [ ] **T067** [US5] Add `sources`, over `reports.source_overlap`. Name the members of `combinations`, which is `list[tuple[tuple[str, ...], int]]`.
- [ ] **T068** [US5] Attach the ADR-0008 caveat to both: a footer line in table output, a `caveat` field in JSON. **This is the condition on which each report was admitted** — a caveat nothing tests is a caveat that disappears in the next layout change.
- [ ] **T069** [US5] Register the `runs` and `reports` groups in `cli/main.py`.

**Checkpoint**: every story is independently functional. SC-001 is met — nothing is browser-only any more.

---

## Phase 8: Polish and Cross-Cutting Concerns

- [ ] **T070** Extend the `Docs/development-guide.md` §6 command table to the new groups. It currently documents exactly the nine commands and would otherwise go stale immediately.
- [ ] **T071** [P] Add `cli/` to the structure tree and component table in `Docs/README.md` and `Docs/design/system-architecture.md`, with the rule that **nothing imports from it** — the same clause that already covers `web/`.
- [ ] **T072** [P] Verify FR-024 mechanically: no module outside `app/cli/` imports from `app.cli`.
- [ ] **T073** Full-suite gate: 224 original tests still passing **unmodified**, plus the seven new CLI modules and the appended service cases. Re-run the T018 help diff one final time.
- [ ] **T074** Set `Docs/CLI-Support.md` status from **Proposal** to **Implemented**, and update its "Assessed against" row to the delivered branch and final test count.

### Optional — explicitly off the critical path (design §6.2)

- [ ] **T075** [P] A `ProfileNotFoundError(ProfileError)` subclass, so not-found is distinguished from invalid by type rather than by which command raised it.
- [ ] **T076** [P] Make `status` delegate to `runs list`, removing the duplicate query. **Only after T018 has proven the verbatim port green** — doing it during Step 3 would conflate a move with a rewrite.
- [ ] **T077** [P] Correct `normalise`'s `run_id` annotation from `int` to `int | None`.
- [ ] **T078** [P] A root `health` command (`SELECT 1`, the same probe as `/healthz`) exiting 0 against the test database and 4 against a closed engine, plus a root `--version` from `importlib.metadata`, plus the `scheduler` healthcheck that `docker-compose.yml` currently lacks. Leave the `web` service's existing check alone.
- [ ] **T079** [P] Mask `proxies` in the web settings template — a pre-existing exposure this plan does not introduce but does document.

---

## Dependencies and Execution Order

### Phase dependencies

- **Phase 1 (Setup)** — no dependencies.
- **Phase 2 (Foundational)** — depends on Phase 1. **Blocks every user story.** Its three steps are internally ordered: skeleton → primitives → port.
- **Phases 3–7 (Stories)** — all depend on Phase 2. Once it is done they can proceed in parallel or in priority order P1 → P2 → P2 → P3 → P3.
- **Phase 8 (Polish)** — depends on the stories being complete.

### Within each story

- Service gaps before the commands that need them (T038 before T046; T051–T053 before T059).
- Tests written and failing before implementation.
- Group registration last, so a half-built group is never reachable.

### Parallel opportunities

- T002 and T003 together.
- T010, T011, T012 together — three new files, no dependency between them.
- Once Phase 2 closes, Phases 3–7 are independent: each touches its own `cli/*.py` and its own `tests/test_cli_*.py`. The only shared file is `cli/main.py`, touched once per story by a one-line registration.
- T071, T072 together; the entire optional block T075–T079 in parallel.

### Sequential by necessity

- Everything in Phase 2 — a shared, ordered spine.
- Tasks writing to the same test module (T020–T023, T030–T032, T040–T043, T055–T057).
- T051 before T052 — `patch` calls the helper T051 extracts.

---

## Implementation Strategy

### MVP first

1. Phase 1 → Phase 2 → **Phase 3 (US1)**.
2. **Stop and validate**: triage a seeded queue end to end from the command line.
3. That alone retires the largest browser-only workflow in the system.

### Incremental delivery

Phase 2 → US1 (P1) → US2 (P2) → US3 (P2) → US4 (P3) → US5 (P3) → Polish. Each
story adds a group without touching another story's files, so none can break a
previous one.

---

## Notes

- **[P] means different files.** Tasks appending to the same test module are
  sequential even where they test unrelated things.
- **Two seams, not one.** Service-backed commands are tested by patching
  `app.cli.deps.session_scope`; `run-all` and `profiles run` by patching
  `app.pipeline.runner.session_scope`. Getting this wrong is the most likely way
  to write a CLI test that silently talks to the real database ([research.md](research.md) D2).
- **Click is 8.4.2**, so `CliRunner` separates `result.stdout` and
  `result.stderr` by default — do not pass the removed `mix_stderr` argument.
- **Additive by default.** The only edit to an existing function body in the
  whole plan is T051, and it is a pure move.
- Commit after each task or logical group; the suite is green at every commit.
