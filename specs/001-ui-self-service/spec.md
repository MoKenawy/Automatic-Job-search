# Feature Specification: Operator Self-Service (Triage & Configuration from the UI)

**Feature Branch**: `001-ui-self-service`

**Created**: 21 July 2026

**Status**: Draft

**Input**: User description: "Quick status change in list page; multi-select status change in list page; configure the system from the UI (everything in the configuration file, saved schedules, own job-survey schedule incl. Role/Experience/Sites); blacklist companies so their postings auto-reject but are preserved."

---

## Context (existing system)

This feature extends the running triage interface (ADR-0004). Relevant facts about
the system as it stands:

- The posting list (`/postings`) shows triage status as a **read-only** pill.
- The detail page already has a working status control backed by
  `POST /postings/{id}/status`; the list page does not.
- Configuration is supplied by environment / `.env` and loaded into an **immutable
  module singleton** at process start (`settings = Settings()`). Nothing can be
  changed at runtime without editing `.env` and restarting.
- The daily schedule is a **single** global job (06:00) that runs every search in
  `SEARCHES`.
- `Employer.suppressed` **already exists in the schema but is read nowhere** — a
  dead column, and the natural seed for the blacklist.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Quick status change from the list (Priority: P1)

The operator triages the morning list without opening each posting. Each row
carries an inline control to set its status (Shortlist, Applied, Rejected). The
change is applied in place, without a full page reload.

**Why this priority**: This is the core daily action (Operations Guide §2), done
dozens of times a session. Removing the open-read-return round trip is the single
largest reduction in triage effort, and it is the smallest change — the endpoint
already exists.

**Independent Test**: On the list page, change a posting's status from a row and
confirm the row reflects the new status and the list filter counts update, with no
navigation to the detail page.

**Acceptance Scenarios**:

1. **Given** a list of postings, **When** the operator sets a row to Shortlist,
   **Then** the row shows Shortlist and no full page reload occurs.
2. **Given** a row set to Rejected, **When** the operator views the list filtered
   by "new", **Then** that row no longer appears.
3. **Given** client-side scripting is unavailable, **When** the operator submits a
   status change, **Then** it still succeeds and the list reflects it (progressive
   enhancement, consistent with the detail page).

---

### User Story 2 — Bulk status change via multi-select (Priority: P2)

The operator selects several postings at once and applies one status to all of
them — e.g. rejecting a batch of clearly irrelevant roles in one action.

**Why this priority**: Compounds US1's efficiency for the common case of clearing
noise. Depends on US1's row-level model but adds real value on top of it.

**Independent Test**: Select three postings, apply Rejected, and confirm all three
change and drop out of the default view in one action.

**Acceptance Scenarios**:

1. **Given** several rows are selected, **When** the operator applies Rejected,
   **Then** all selected postings become Rejected in a single operation.
2. **Given** no rows are selected, **When** the operator opens the bulk action bar,
   **Then** the apply action is unavailable until at least one row is selected.
3. **Given** a "select all" control, **When** it is toggled, **Then** every row in
   the current filtered view is selected.

---

### User Story 3 — Company blacklist with automatic rejection (Priority: P2)

The operator blacklists an employer. From then on, every posting from that
employer — existing and future — is automatically set to Rejected, but retained in
the database rather than deleted. The operator can view and remove blacklist
entries.

**Why this priority**: High value and low cost — the schema field exists but is
unused. It removes recurring noise from specific employers permanently, directly
serving the "signal quality" objective (design §2).

**Independent Test**: Blacklist an employer that has postings, run the pipeline (or
the suppression pass), and confirm all of that employer's postings are Rejected and
still present, and that a newly collected posting from them is auto-rejected.

**Acceptance Scenarios**:

1. **Given** an employer with active postings, **When** the operator blacklists
   them, **Then** all their postings become Rejected and remain in the database.
2. **Given** a blacklisted employer, **When** a new posting from them is collected,
   **Then** it is created already Rejected and is never published.
3. **Given** a blacklisted employer, **When** the operator removes the blacklist,
   **Then** future postings are no longer auto-rejected (previously rejected ones
   are not automatically reinstated).
4. **Given** the blacklist management view, **When** the operator opens it, **Then**
   every blacklisted employer is listed with an option to remove each.

---

### User Story 4 — Configure the system from the UI (Priority: P3)

The operator changes system configuration through the interface rather than by
editing `.env` and restarting: operational settings (results per search, request
delay, publish threshold, scoring model, LinkedIn description fetch), and
**saved search schedules** — each a named job-survey profile with its own role,
experience, location, sites, and run time — which can be individually enabled,
disabled, edited, and run on demand.

**Why this priority**: The largest change and the one with architectural
implications (runtime-mutable configuration; per-profile scheduling). It is
valuable but not on the critical path to daily triage, and it should follow the
smaller, self-contained stories.

**Independent Test**: Change the publish threshold in the UI, confirm it takes
effect on the next scoring pass without a restart; create a named search profile
with its own schedule, confirm it appears in the schedule list and runs at its
configured time.

**Acceptance Scenarios**:

1. **Given** the settings view, **When** the operator changes the publish threshold
   and saves, **Then** the new value is used by subsequent runs without a process
   restart.
2. **Given** the schedules view, **When** the operator creates a search profile
   (role, experience, location, sites, run time), **Then** it is saved, listed, and
   scheduled.
3. **Given** a saved profile, **When** the operator disables it, **Then** it no
   longer runs on its schedule but is retained for re-enabling.
4. **Given** a saved profile, **When** the operator triggers "run now", **Then** a
   run executes for that profile immediately.
5. **Given** an invalid setting (e.g. threshold above 100), **When** the operator
   saves, **Then** the change is rejected with a message and the prior value stands.

---

### Edge Cases

- **Concurrent status change** on the same posting from two tabs — last write wins;
  no error surfaced.
- **Blacklisting an employer mid-run** — suppression is applied idempotently on the
  next stage; a posting created during the run is caught by the suppression pass.
- **A setting that requires a restart to take effect** (e.g. the database URL) must
  be either excluded from the UI or clearly marked as restart-required — see
  [NEEDS CLARIFICATION] in requirements.
- **Removing a blacklist** does not reinstate previously auto-rejected postings;
  this is deliberate and must be stated in the UI.
- **A search profile with no enabled sites** must be rejected at save time.
- **Deleting the last remaining search profile** — the pipeline then collects
  nothing; this is allowed but surfaced as a warning.

---

## Requirements *(mandatory)*

### Functional Requirements

**Triage — quick and bulk**

- **FR-001**: The posting list MUST provide an inline control to change each
  posting's triage status without navigating to the detail page.
- **FR-002**: A status change from the list MUST update the row in place and MUST
  function without client-side scripting (progressive enhancement).
- **FR-003**: The list MUST allow selecting multiple postings and applying one
  status to all selected in a single operation.
- **FR-004**: The bulk operation MUST be unavailable when no postings are selected.
- **FR-005**: A "select all in current view" control MUST be provided.

**Company blacklist**

- **FR-006**: The operator MUST be able to blacklist and un-blacklist an employer.
- **FR-007**: While an employer is blacklisted, the system MUST set every posting
  from that employer to Rejected, for both existing and newly collected postings.
- **FR-008**: Auto-rejected postings MUST be retained, never deleted (design D9).
- **FR-009**: A blacklisted employer's postings MUST never be published.
- **FR-010**: The system MUST provide a view listing all blacklisted employers with
  the ability to remove each.
- **FR-011**: Removing a blacklist MUST stop future auto-rejection but MUST NOT
  automatically reinstate previously rejected postings.
- **FR-012**: The operator MUST be able to blacklist an employer directly from a
  posting (list row or detail).

**Configuration from the UI**

- **FR-013**: The operator MUST be able to view and change operational settings
  from the UI: results per search, request delay, hours-old window, publish
  threshold, scoring model, LinkedIn description fetch, title filter patterns.
- **FR-014**: Changed operational settings MUST take effect on subsequent runs
  without a process restart.
- **FR-015**: Settings changes MUST be validated; invalid values MUST be rejected
  with a message and the prior value retained.
- **FR-016**: The operator MUST be able to create, edit, enable, disable, and
  delete **search profiles**, each carrying at least: name, role/term, location,
  country, sites, remote flag, and experience. **Resolved (research Q1):**
  experience is a post-collection filter stored on the profile that also feeds the
  stage-3 scoring prompt; it is not a board parameter.
- **FR-017**: Each search profile MUST carry its own schedule (run time), and the
  system MUST run each enabled profile on its schedule.
- **FR-018**: The operator MUST be able to trigger any profile to "run now".
- **FR-019**: Configuration that requires a restart to apply (e.g. database
  connection, bind host/port) MUST NOT be presented as live-editable, or MUST be
  clearly marked restart-required. **Resolved (research Q2):** editable =
  results_per_search, hours_old, request_delay_seconds, publish_threshold,
  scoring_model, linkedin_fetch_description, title patterns, proxies; read-only =
  timezone, web host/port; hidden = database_url.
- **FR-020**: Secrets MUST remain outside the UI-editable set and continue to be
  sourced from the environment. **Resolved (research Q2):** none of the editable
  settings is a secret (after ADR-0004 there are no delivery credentials);
  `database_url` is the only sensitive value and stays env-only and hidden.

**General**

- **FR-021**: All new interface actions MUST be covered by automated tests,
  consistent with the existing suite.
- **FR-022**: Existing behaviour (design decisions D1–D15) MUST be preserved;
  where this feature supersedes a prior decision (e.g. `SEARCHES` in `.env` moving
  to the database), it MUST be recorded in a new ADR.

### Key Entities

- **Employer (existing, extended in use)**: gains active use of its `suppressed`
  flag as the blacklist mechanism. No new column required.
- **Posting (existing)**: `status` is the target of quick, bulk, and automatic
  transitions. No new column required.
- **Search Profile (new)**: a named, saved job-survey definition — role/term,
  location, country, sites, remote, experience, schedule (run time), enabled flag.
  Supersedes the `SEARCHES` environment list.
- **App Setting (new)**: runtime-editable operational configuration, seeded from
  environment defaults, overriding them at runtime. Excludes secrets and
  restart-only settings.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can triage a posting's status from the list in a single
  action, with no page navigation.
- **SC-002**: An operator can reject a batch of N postings in one action rather than
  N actions.
- **SC-003**: After blacklisting an employer, 100% of that employer's postings —
  existing and subsequently collected — are Rejected and remain retrievable in the
  database.
- **SC-004**: An operational setting changed in the UI is reflected in the next run
  with zero restarts.
- **SC-005**: An operator can define a job-survey schedule (role, experience,
  location, sites, time) entirely from the UI, with no file editing.
- **SC-006**: Daily triage effort remains under five minutes (design §2.1 NFR),
  now including quick/bulk actions.
- **SC-007**: The test suite continues to pass with new coverage for every added
  action; no regression in existing tests.

---

## Assumptions

- The interface remains the single operator surface (ADR-0004); these features do
  not introduce a second surface or external service.
- Single operator, single machine; no authentication or multi-user concerns are in
  scope (consistent with SRS §2.4).
- Runtime-editable settings are limited to non-secret operational values; database
  connection and bind settings remain environment-sourced.
- Moving `SEARCHES` from `.env` into database-backed search profiles supersedes
  that part of D14/configuration and will be recorded in a new ADR.
- Per-profile scheduling replaces the single global daily job; the scheduler will
  read profiles from the database and reschedule when they change.
- "Preserved" for blacklisted postings means retained with status Rejected, which
  already carries the D9 "never resurfaces" guarantee.
