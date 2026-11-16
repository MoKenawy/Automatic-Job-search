# Feature Specification: CLI Support — Operating the System Without a Browser

**Feature Directory**: `specs/003-cli-support`

**Git Branch**: `CLI-Support-Feature`

**Created**: 13 August 2026

**Status**: Draft

**Input**: User description: "Grouped CLI adapter package exposing triage, employers, profiles, settings, runs and reports over the existing service layer"

**Design authority**: [Docs/CLI-Support.md](../../Docs/CLI-Support.md) holds the
assessed architecture, the blocker decisions (B1–B6), and the file-level change
plan. This specification states *what* the operator gets and *how it is
verified*; that document states *how it is built*.

---

## Context (existing system)

Facts about the system as it stands, read from the working tree:

- A command-line interface **already exists** — nine flat commands in
  `app/src/app/__main__.py`, with a `job-discovery` console entry point already
  declared. SRS **IR-1** is already met.
- Two of those commands, `web` and `serve`, are **container entry points**:
  `docker-compose.yml` invokes them directly. They are a deployment contract.
- Roughly twenty operations are reachable **only through a browser** today:
  triage transitions, the employer blacklist, search-profile CRUD, runtime
  settings, run health, and both reports.
- Every web route already delegates to a service function; no business logic is
  trapped in an HTTP handler.
- The suite is at **224 tests with zero CLI coverage**, because no seam exists
  that lets a command run against a test database.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Triage the queue from a terminal (Priority: P1)

The operator reviews the morning queue and moves postings between triage states
without opening a browser: list under the same filters the web offers, read one
posting in full, and transition one or many in a single invocation.

**Why this priority**: This is the core daily action and the largest capability
currently locked behind the UI. It also delivers the first scriptable surface —
an operator can pipe a filtered list into a bulk transition.

**Independent Test**: Seed a database with postings across statuses, then list,
read, and transition them entirely through commands; verify state in the
database afterwards. Delivers value with no other story implemented.

**Acceptance Scenarios**:

1. **Given** a queue of postings, **When** the operator lists them filtered by
   status and country, **Then** the matching rows are printed with a position
   footer showing which page of how many is displayed, and the exit status is
   success even if the page is empty.
2. **Given** a posting id that exists, **When** the operator requests its
   detail, **Then** every stored field is shown including one line per source
   board that surfaced it.
3. **Given** a posting id that does not exist, **When** the operator requests
   its detail, **Then** a one-line "not found" message is printed to the error
   stream and the not-found exit code is returned.
4. **Given** several posting ids, **When** the operator transitions them to
   rejected without an automation flag on an interactive terminal, **Then** the
   command states how many rows it will affect and waits for confirmation.
5. **Given** the same command with the automation flag, **When** it runs with no
   terminal attached, **Then** it proceeds without prompting and reports how
   many of the requested postings were updated.

---

### User Story 2 — Suppress an employer and sweep their postings (Priority: P2)

The operator blacklists an employer whose postings are noise. Their existing
postings are rejected in the same transaction, and the operator can re-run that
sweep later without lifting and re-applying the blacklist.

**Why this priority**: A mass state change that is currently browser-only and
carries the widest blast radius of any operation in the system. Second because
it is used weekly, not hourly.

**Independent Test**: Blacklist a seeded employer, assert their postings become
rejected and the count is reported, then lift and confirm the rejections are
*not* reversed.

**Acceptance Scenarios**:

1. **Given** an employer with postings in the queue, **When** the operator
   blacklists them after confirming, **Then** the employer is suppressed, their
   postings are rejected in one transaction, and the affected count is printed.
2. **Given** a blacklisted employer, **When** the operator lifts the blacklist,
   **Then** the suppression ends but previously rejected postings stay rejected,
   and the command's output and help both state this.
3. **Given** an already-suppressed employer who has since acquired new postings,
   **When** the operator re-runs the sweep, **Then** the new postings are
   rejected; running it a second time rejects nothing and still succeeds.
4. **Given** an employer id that does not exist, **When** any of these commands
   runs, **Then** the not-found exit code is returned.

---

### User Story 3 — Manage search profiles and run one on demand (Priority: P2)

The operator creates, inspects, amends, enables, disables, and deletes the saved
search profiles that drive the scheduler, and can trigger a single profile's
full pipeline immediately.

**Why this priority**: Profiles govern what the system collects at all. Amending
one is the highest-frequency configuration action, and the on-demand run is what
makes the CLI usable from cron or CI.

**Independent Test**: Create a profile, change exactly one of its fields, and
assert every other field is untouched; then run it with the collector stubbed
and assert the run is recorded.

**Acceptance Scenarios**:

1. **Given** no profile named "Cairo DE", **When** the operator creates one with
   a name, role, and at least one board, **Then** it is saved and its id is
   reported.
2. **Given** an existing profile, **When** the operator changes only its role,
   **Then** the role changes and its location, country, boards, schedule, and
   enabled state are all unchanged. *(This is the primary regression guard for
   the partial-update decision — see B2.)*
3. **Given** an existing profile, **When** the operator supplies an empty value
   for a clearable field, **Then** that field is cleared rather than left alone.
4. **Given** a profile name already in use, **When** the operator creates or
   renames another profile to it, **Then** the business-failure exit code is
   returned and nothing is written.
5. **Given** a profile, **When** the operator deletes it after confirming,
   **Then** it is removed and the historical runs it triggered survive.
6. **Given** a profile, **When** the operator runs it on demand, **Then**
   progress appears on the diagnostic stream, final counts on the data stream,
   and a run collecting zero postings is called out as a warning.

---

### User Story 4 — Inspect and change operational settings safely (Priority: P3)

The operator reads the effective operational settings — resolved across stored
overrides, environment, and code defaults — and overrides exactly one of them
without disturbing the others.

**Why this priority**: Lower frequency than triage, but the highest consequence
per invocation: these values change behaviour for the scheduler and every other
process.

**Independent Test**: Store an override for one key, then set a different key
and assert the first override survives and the remaining keys still resolve from
the environment rather than becoming pinned.

**Acceptance Scenarios**:

1. **Given** a stored override, **When** the operator shows the settings,
   **Then** each key is listed with its effective value and which tier it came
   from.
2. **Given** any settings output, **When** it is printed, **Then** it contains
   neither the proxy credential nor the database password, in any output format.
   *(Regression guard for B4.)*
3. **Given** nine editable settings, **When** the operator changes one, **Then**
   the before and after values are echoed, and the other eight are neither
   altered nor converted into stored overrides. *(Regression guard for B3.)*
4. **Given** a value that fails validation, **When** the operator submits it,
   **Then** the business-failure exit code is returned and every prior value
   still stands.
5. **Given** a key that is not editable, **When** the operator names it, **Then**
   the invalid-usage exit code is returned.

---

### User Story 5 — Observe pipeline health and reporting (Priority: P3)

The operator inspects recent runs, per-board collection counts over time, and
the two admitted reports, in a form a monitor or a spreadsheet can consume.

**Why this priority**: Diagnostic rather than operational — but the per-board
count series is the system's decay signal, and it is currently visible only in a
browser, where nothing can alert on it.

**Independent Test**: Seed several runs across boards, then assert the health
series is emitted in machine-readable form with one entry per board per run.

**Acceptance Scenarios**:

1. **Given** recent runs, **When** the operator lists them, **Then** each is
   shown with the profile that triggered it.
2. **Given** runs across several boards, **When** the operator requests health,
   **Then** a per-board series is produced that a monitor could alert on.
3. **Given** either report, **When** it is produced in any output format,
   **Then** the sampling-bias caveat that admitted the report is carried with
   it. *(Condition of ADR-0008 §1.)*

---

### Edge Cases

- **An empty result is not an error.** A filter matching nothing, a page beyond
  the last, and a report over an empty corpus all succeed.
- **The database is unreachable.** Any command that needs it fails with the
  infrastructure exit code and a one-line message — distinguishable from a
  missing row, which is what makes the CLI scriptable.
- **A destructive command is piped.** With no terminal attached and no
  automation flag, it fails loudly rather than blocking forever on a prompt that
  nobody can answer.
- **Unimplemented stages.** The scoring and publication stages do not exist yet;
  their commands report that and fail rather than pretending to succeed.
- **Machine-readable output while logging is on.** Services log at INFO during a
  command; the data stream must stay parseable regardless.
- **A profile is deleted while its runs exist.** The run history survives with
  its profile attribution nulled.
- **A bulk transition partially applies.** The operator is told how many of the
  requested ids were actually updated, not merely that the command finished.

---

## Requirements *(mandatory)*

### Functional Requirements

**Preservation**

- **FR-001**: Every one of the nine existing commands MUST keep its exact name,
  options, defaults, output text, and exit codes. `web` and `serve` are invoked
  by the container orchestration and a change to either is a breaking deployment
  change.
- **FR-002**: The existing module invocation path and the existing console entry
  point MUST both continue to resolve.
- **FR-003**: All 224 existing tests MUST pass unmodified. Edits to existing test
  files are limited to appended cases.

**New operator surface**

- **FR-004**: The operator MUST be able to page the triage queue under the
  filters the web list offers, and to read one posting in full including its
  per-board provenance.
- **FR-005**: The operator MUST be able to transition one or many postings
  between triage states in a single invocation.
- **FR-006**: The operator MUST be able to list suppressed employers, suppress
  one, lift a suppression, and re-run the rejection sweep independently.
- **FR-007**: The operator MUST be able to list, create, amend, enable, disable,
  and delete search profiles, and to run one profile's pipeline on demand.
- **FR-008**: Amending a profile MUST change only the fields named, leaving every
  unspecified field at its current value.
- **FR-009**: The operator MUST be able to view effective settings and to
  override a single editable setting without altering the resolution of any
  other.
- **FR-010**: The operator MUST be able to list recent runs with their
  triggering profile, view per-board collection counts across recent runs, and
  produce both admitted reports.
- **FR-011**: Both reports MUST carry their sampling-bias caveat in every output
  format.

**Behaviour and contract**

- **FR-012**: Every command MUST return an exit code from the fixed set —
  success, business failure, invalid usage, not found, infrastructure failure,
  unexpected internal error — and the code each command can return MUST be
  stated in its help or specification.
- **FR-013**: Results MUST be written to the data stream and all logging,
  progress, and error messages to the diagnostic stream, such that
  machine-readable output stays parseable while services log.
- **FR-014**: A machine-readable output format MUST be available for the
  commands where automation benefits, and its structure MUST be an explicit
  projection that a database schema change cannot silently alter.
- **FR-015**: Errors MUST be reported as actionable one-line messages. A stack
  trace MUST appear only when explicitly requested.
- **FR-016**: Destructive or system-wide commands MUST confirm on an interactive
  terminal, MUST accept an explicit automation flag to skip the prompt, and MUST
  fail rather than hang when neither applies.
- **FR-017**: A confirmation prompt MUST state the number of records it is about
  to affect.
- **FR-018**: The rejection sweep MUST be idempotent — re-running it against an
  unchanged employer MUST reject nothing and still succeed.

**Configuration and secrets**

- **FR-019**: No secret may be accepted as a command argument. The database
  connection is resolved from the process environment only.
- **FR-020**: Per-command database selection is NOT supported; every command
  resolves the same process-wide database, as the web and scheduler do. *(B1.)*
- **FR-021**: Any command that can print a configuration value MUST mask both
  the proxy list and the database URL unconditionally, with no override. *(B4.)*
- **FR-022**: The environment-only configuration command and the
  database-resolved settings view MUST remain distinct commands, each stating
  the distinction in its help — the former must stay usable during a database
  outage.

**Layering**

- **FR-023**: No business rule, default, or validation may originate in the CLI
  layer. Where a partial write is needed and no service function expresses it,
  the service gains one.
- **FR-024**: Nothing in the system may import from the CLI package.
- **FR-025**: The CLI MUST NOT reach the system through its own HTTP API.

### Key Entities

- **Posting**: A job advert in the triage queue, carrying a status, a score, an
  employer, a country, a remote flag, and the set of boards that surfaced it.
- **Employer**: The hiring organisation; may be suppressed, which auto-rejects
  their postings while preserving them.
- **Search Profile**: A saved search — role, location, country, remote, boards,
  experience — with a daily schedule and an enabled flag. Drives the scheduler.
- **Run**: One execution of the pipeline, tracked to a terminal status, carrying
  per-board counts and an optional triggering profile.
- **Editable Setting**: One of nine operational values resolvable across stored
  override, environment, and code default.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every operation currently reachable only through the browser —
  triage transitions, employer suppression, profile management, settings
  override, run health, and both reports — is reachable from the command line.
- **SC-002**: Deployment is unaffected: the container commands and the console
  entry point behave identically before and after, verified by diffing their
  help output.
- **SC-003**: An operator can distinguish a missing record from an unreachable
  database purely from the exit code, without reading the message.
- **SC-004**: A morning triage pass — filter the queue, then reject a set of
  postings — is completable in a single non-interactive pipeline with no browser
  and no prompt.
- **SC-005**: Machine-readable output parses cleanly while the application logs
  at INFO, with zero log lines in the parsed stream.
- **SC-006**: No settings output, in any format, contains a credential.
- **SC-007**: Changing one setting leaves the other eight resolving exactly as
  they did before the change.
- **SC-008**: Every command has automated coverage for help, one success path,
  invalid arguments, and its documented failure exit codes; the suite is green
  at every step of delivery.

---

## Assumptions

- **The operator is a single technical user** with shell access to the deployment
  host, per the SRS scope. Read-modify-write races on settings are therefore
  acceptable and no locking is specified.
- **The command-line surface is a first-class adapter**, not a wrapper over the
  web API. Command-line arguments are the integration pattern for a tool, so
  naming commands and options is in scope for this specification while remaining
  free of implementation detail.
- **The scoring and publication stages stay unimplemented.** Their commands
  remain stubs that fail with a message; expanding them is a separate feature.
- **No schema change is required.** Every new capability maps to a service
  function that already exists, or to a partial-write counterpart of one.
- **The existing service layer is the data-access layer.** No repository layer
  exists and none is introduced (Constitution §II).
- **Terminal detection is sufficient for confirmation.** Whether stdin is
  interactive is the signal used to decide between prompting and failing; no
  additional automation-detection heuristic is specified.
- **Reports keep their admitted scope.** The two existing reports are exposed as
  they are, with their caveat; no new report is defined here.
