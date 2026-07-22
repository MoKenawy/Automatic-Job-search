---
description: "Task list for Operator Self-Service (Triage & Configuration from the UI)"
---

# Tasks: Operator Self-Service (Triage & Configuration from the UI)

**Input**: Design documents from `/specs/001-ui-self-service/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: Included — the spec requires automated coverage for every new action
(FR-021), consistent with the existing suite.

**Organization**: Grouped by user story so each is independently implementable and
testable. Paths are relative to `app/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency)
- **[Story]**: US1–US4

---

## Phase 1: Setup

- [ ] T001 Create feature branch/worktree and confirm the suite is green as a baseline (`uv run pytest`).
- [ ] T002 [P] Confirm the running stack (web, scheduler, postgres, migrate) is healthy before changes.

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ Only the parts each story needs; US1/US2 need almost none.**

- [ ] T003 [P] Add a shared list-row selection + bulk-action-bar partial skeleton to `src/app/web/templates/postings.html` (no behaviour yet) — unblocks US1/US2 layout.
- [ ] T004 Record **ADR-0005** (`Docs/ADRs/0005-ui-config-and-db-search-profiles.md`): DB-backed settings and search profiles supersede `SEARCHES`/static config. **Gates US4 only.**

**Checkpoint**: US1, US2, US3 can proceed; US4 waits on T004.

---

## Phase 3: User Story 1 — Quick status change from the list (P1) 🎯 MVP

**Goal**: Inline status control on each list row, updating in place.

**Independent Test**: Change a row's status on `/postings`; row updates, no reload.

### Tests (write first, must fail)

- [ ] T005 [P] [US1] `tests/test_web_triage.py`: row status control renders per row on `/postings`.
- [ ] T006 [P] [US1] `tests/test_web_triage.py`: posting `POST /postings/{id}/status` from the list returns the updated row fragment (HTMX) and redirects without HTMX.

### Implementation

- [ ] T007 [US1] Create `src/app/web/templates/_row_status.html` — inline control mirroring `_status_control.html`, targeting the row.
- [ ] T008 [US1] Render `_row_status.html` in the status cell of `postings.html`; add `hx-target` on the row.
- [ ] T009 [US1] Extend `POST /postings/{id}/status` in `src/app/web/app.py` to return the row fragment when the request originates from the list (and redirect to `/postings` without HTMX).
- [ ] T010 [US1] Ensure filter counts on the list reflect the change (re-query or out-of-band swap).

**Checkpoint**: US1 fully functional and testable on its own.

---

## Phase 4: User Story 2 — Bulk status change via multi-select (P2)

**Goal**: Select multiple postings; apply one status in a single request.

**Independent Test**: Select three rows, apply Rejected; all three change at once.

### Tests (write first, must fail)

- [ ] T011 [P] [US2] `tests/test_web_triage.py`: `POST /postings/status` with a list of ids sets all to the given status.
- [ ] T012 [P] [US2] `tests/test_web_triage.py`: bulk endpoint rejects an unknown status (400) and an empty selection (no-op/400).

### Implementation

- [ ] T013 [US2] Add row checkboxes and a "select all in view" control to `postings.html`.
- [ ] T014 [US2] Add a bulk action bar (status choices + apply), disabled until ≥1 selected.
- [ ] T015 [US2] Add `POST /postings/status` in `src/app/web/app.py` accepting `ids[]` + `status`; validate status against `STATUSES`; update in one transaction.
- [ ] T016 [US2] Return the refreshed list (or affected rows) so the view reflects all changes at once.

**Checkpoint**: US1 + US2 both work independently.

---

## Phase 5: User Story 3 — Company blacklist (P2)

**Goal**: Blacklist an employer → all their postings auto-reject and are retained;
future postings auto-reject on collection.

**Independent Test**: Blacklist an employer with postings; run suppression; all
their postings Rejected and still present; a new one is created Rejected.

### Tests (write first, must fail)

- [ ] T017 [P] [US3] `tests/test_blacklist.py`: suppression pass sets `status='rejected'`, `published=false` for all postings of a suppressed employer, idempotently.
- [ ] T018 [P] [US3] `tests/test_blacklist.py`: a newly normalised posting for a suppressed employer is created Rejected and never published.
- [ ] T019 [P] [US3] `tests/test_blacklist.py`: blacklist/un-blacklist endpoints toggle `employers.suppressed`; un-blacklist does not reinstate prior rejections.

### Implementation

- [ ] T020 [US3] Create `src/app/pipeline/suppress_stage.py` — idempotent pass over suppressed employers' postings.
- [ ] T021 [US3] Call suppression in `run-all` (after normalise) and immediately when an employer is blacklisted.
- [ ] T022 [US3] In `normalise_stage.py`, mark a new posting Rejected if its employer is suppressed (catch mid-run additions).
- [ ] T023 [US3] Add a partial index on `employers(suppressed) WHERE suppressed` (Alembic migration).
- [ ] T024 [US3] Add routes in `app.py`: `POST /employers/{id}/blacklist`, `POST /employers/{id}/unblacklist`; blacklist action from a posting row/detail (FR-012).
- [ ] T025 [US3] Create `src/app/web/templates/blacklist.html` and a `/blacklist` route listing suppressed employers with remove actions; add nav link.
- [ ] T026 [US3] Exclude suppressed employers' postings from publication in the publish path/queries (FR-009).

**Checkpoint**: US3 works independently of US1/US2.

---

## Phase 6: User Story 4 — Configure the system from the UI (P3)

**Prerequisite**: T004 (ADR-0005) accepted.

**Goal**: Runtime-editable operational settings + DB-backed, individually
scheduled search profiles, all from the UI.

**Independent Test**: Change publish threshold in UI → next run uses it, no
restart; create a profile with its own schedule → it lists and runs.

### Tests (write first, must fail)

- [ ] T027 [P] [US4] `tests/test_settings_store.py`: resolution order DB → env → code default; setting a value overrides env.
- [ ] T028 [P] [US4] `tests/test_settings_store.py`: invalid value (e.g. threshold > 100) rejected; prior value retained.
- [ ] T029 [P] [US4] `tests/test_profiles.py`: profile CRUD; validation (non-empty sites, valid schedule, unique name).
- [ ] T030 [P] [US4] `tests/test_profiles.py`: scheduler read model returns one job per enabled profile; disabled profiles excluded.

### Implementation — settings store

- [ ] T031 [US4] Create `db/models.py` entities `AppSetting` and `SearchProfile` (+ `runs.profile_id` nullable FK).
- [ ] T032 [US4] Alembic migrations: create tables, seed `search_profiles` from current `SEARCHES`, add `runs.profile_id`.
- [ ] T033 [US4] Create `settings_store/store.py`: typed get/set over `app_settings` with DB→env→default resolution, validated through pydantic.
- [ ] T034 [US4] Route operational reads (`results_per_search`, `publish_threshold`, `request_delay_seconds`, `scoring_model`, `linkedin_fetch_description`, title patterns, `hours_old`, `proxies`) through the store.

### Implementation — search profiles & scheduling

- [ ] T035 [US4] Create `settings_store/profiles.py`: CRUD + validation.
- [ ] T036 [US4] Change `collect_stage.py` to read enabled profiles instead of `settings.searches`.
- [ ] T037 [US4] Rework `scheduler.py`: one APScheduler job per enabled profile at its time; reload on profile change; preserve per-run/per-source counts (§7.4).
- [ ] T038 [US4] Add "run now" per profile (full pipeline for that profile), reusing `run-all` for a single profile.

### Implementation — UI

- [ ] T039 [P] [US4] `src/app/web/templates/settings.html` + `/settings` GET/POST: editable operational settings, restart-only shown read-only, `database_url` hidden.
- [ ] T040 [P] [US4] `src/app/web/templates/profiles.html` + `/profiles` routes: list/create/edit/enable/disable/delete + run-now.
- [ ] T041 [US4] Add nav links (Settings, Schedules); validation messages on save (FR-015).

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & cross-cutting

- [ ] T042 [P] Update docs: `Docs/operations-guide.md` (blacklist, settings, schedules), `Docs/design/data-model.md` (+2 tables), `Docs/software-requirements-specification.md` (traceability), app `README.md`.
- [ ] T043 [P] Deprecate `SEARCHES`/editable keys in `.env.example` with pointers to the UI (keep as seed).
- [ ] T044 Full suite green (`uv run pytest`), lint clean (`uv run ruff check`), rebuild image, verify all four services healthy and each story end-to-end.

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)**: T004 gates US4 only.
- **US1 (P1)**: after T003. MVP.
- **US2 (P2)**: after US1 (shares list template).
- **US3 (P2)**: independent of US1/US2 — can run in parallel with them.
- **US4 (P3)**: after T004 (ADR-0005). Largest; changes config semantics.
- **Polish (P7)**: after the desired stories.

### Parallel opportunities

- US3 can be built alongside US1/US2 (disjoint files: pipeline + blacklist template vs. list template).
- Within US4, settings-store tasks (T031–T034) and profile/UI tasks split across files marked [P].
- All test tasks marked [P] within a story can be written together first.

---

## Implementation Strategy

**MVP** = Phase 1 + T003 + US1. Ship inline status change first; validate the
five-minute triage target holds. Then US2 and US3 (parallelisable) as the next
increment. US4 last, behind ADR-0005, as it is the architectural change.

## Notes

- No new columns on existing tables except the additive nullable `runs.profile_id`.
- Blacklist reuses `employers.suppressed` (currently dead) — no new blacklist table.
- Preserve every existing design decision (D1–D15); ADR-0005 records the one this supersedes.
- Keep stages idempotent; keep per-run/per-source counts intact under per-profile scheduling.
