# Phase 1 Data Model: CLI Support

**Date**: 13 August 2026 | **Plan**: [plan.md](plan.md)

## Headline: nothing changes

**No new entity, no new attribute, no relationship change, no migration.** This
feature adds an adapter over data that already exists. `db/models.py` is not
edited and `alembic` is not run.

This file exists to make that finding explicit and reviewable, and to record
which existing entities the new surface reads and writes — because the *write*
column is where the risk is.

## Entities touched

| Entity | Read by | Written by | Notes |
|---|---|---|---|
| **Posting** | `postings list`, `postings get`, `reports employers`, `reports sources` | `postings set-status`, `employers blacklist`, `employers resweep` | Status transitions go through `triage`, which owns the legal-transition rule (`Posting.transition_to`). The CLI never sets a status attribute directly. |
| **Employer** | `employers blacklisted`, `reports employers` | `employers blacklist`, `employers unblacklist` | `suppressed` is the blacklist flag. Suppression and the posting sweep happen in **one transaction** (ADR-0014). |
| **SearchProfile** | `profiles list` | `profiles create`, `profiles update`, `profiles enable`, `profiles disable`, `profiles delete` | The only entity the CLI creates and hard-deletes. `update` writes through the new `profiles.patch`, never through `update()` directly. |
| **Run** | `status`, `runs list`, `runs health`, `normalise` | `run-all`, `profiles run`, `collect` — indirectly, via `track_run` | The CLI never constructs a `Run`; the pipeline's `track_run` owns its lifecycle and terminal status. |
| **AppSetting** | `settings show` | `settings set` | Key-value overrides for the nine editable settings. See the write semantics below. |
| **RawPosting / posting sources** | `postings get` (per-board provenance), `reports sources` | — | Read-only from the CLI. |

## Write semantics worth stating

Three of these writes have a rule that is easy to get wrong, and each has a named
regression test.

### SearchProfile — partial update

`profiles update` must change **only** the fields named. The existing
`services.profiles.update()` is a full-record replace: `_clean()` supplies a
default for every absent key, so a naive single-field update would blank the
role, reset the country, empty the board list, reset the schedule, and disable
the profile.

- Written through **`profiles.patch()`** (new), which merges onto current values
  and delegates to `update()` so validation and the duplicate-name check are
  reused unchanged.
- `None` means "unspecified". Clearing a nullable field (`location`,
  `experience`) is done with an **empty string**, which `_clean` maps back to
  `None`.
- Guarded by: `test_cli_profiles.py` — a single-field update leaves every other
  field intact.

### AppSetting — single-key write preserves inheritance

The nine editable settings resolve **stored override → environment → code
default** (ADR-0005). Writing one key must not convert the other eight into
stored overrides.

- Written through **`settings.patch()`** (new): merge over `all_effective`,
  validate the whole set, write **only the changed keys**.
- A key with no `AppSetting` row is *inheriting*, and that state is meaningful —
  changing the environment still moves it. Pinning all nine on every write would
  destroy that silently.
- Guarded by: `test_cli_settings.py` — after setting one key, the other eight
  still resolve from the environment rather than from stored rows.

### Employer — suppression is a mass write

`employers blacklist` suppresses the employer **and** rejects every one of their
postings, in one transaction with row locking (ADR-0014).

- `employers unblacklist` lifts the suppression but does **not** reinstate
  already-rejected postings (FR-011 of the original SRS). Both the help text and
  the command output must say so.
- `employers resweep` re-runs only the rejection sweep and is **idempotent** — a
  second call rejects nothing and still succeeds.
- Guarded by: `test_cli_employers.py` — lift does not reinstate; resweep is
  idempotent on the second call.

## Deletion behaviour

`profiles delete` is a hard delete, and it is the only one the CLI performs. Run
history survives it: `runs.profile_id` is `ON DELETE SET NULL`, so past runs keep
their counts and lose only their profile attribution. The confirmation copy says
this, so the operator is not guessing about what they are destroying.

## Serialisation

JSON output projects **explicit dictionaries**, never serialised ORM rows. The
CLI's JSON is therefore a stable published contract that a schema change cannot
silently alter, and no new Pydantic model is introduced anywhere. The projections
are specified in [contracts/cli-surface.md](contracts/cli-surface.md).
