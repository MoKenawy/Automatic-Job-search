# Implementation Plan: Employer-level suppression, derived at read time

**Branch**: `job-post-transitions` | **Date**: 13 August 2026 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-employer-suppression-derived/spec.md`

**Source documents**: [ADR-0015](../../Docs/ADRs/0015-employer-level-suppression.md) ·
[engineering plan](../../Docs/design/IMPLEMENTATION_PLAN_ADR-0015-Employer-level.md) ·
[concurrency review](../../Docs/design/suppression-concurrency-review.md)

## Summary

Stop materialising employer blacklist state onto postings. `postings.status`
reverts to operator judgement only, with `services/triage.py` as its sole
writer; whether a posting is out of play because of its employer is answered at
read time from `employers.suppressed` through **one predicate every read path
applies**.

The predicate lives in a new `app/src/app/db/visibility.py` as
`not_suppressed()`, a correlated `NOT EXISTS` over `employers`. Siting it in
`db/` rather than `services/` is the plan's one architectural decision: `db/` is
the only package both `services/` and `pipeline/` may import, and the future
scoring and publication stages are `pipeline/` modules that ADR-0015 names as
seam consumers. `pipeline/suppress_stage.py` is deleted; `blacklist()` and
`lift()` become single-row flag flips.

Work is ordered so the new enforcement is in place and tested **before** the old
enforcement is removed. There is no commit in the sequence at which a
blacklisted employer's postings are visible.

## Technical Context

**Language/Version**: Python 3.12 (pinned via `app/.python-version`)

**Primary Dependencies**: SQLAlchemy 2.x (ORM + Core `select`), FastAPI +
Jinja2 (triage UI), Typer (CLI), Alembic (migrations), APScheduler

**Storage**: PostgreSQL 16 in production (Docker Compose); in-memory SQLite with
`StaticPool` under test. Models declare `JSON` variants of `JSONB` columns
specifically so the suite runs without Docker.

**Testing**: pytest. Full suite runs with no external services.

**Target Platform**: single local machine (Windows 11 host, Postgres in Docker);
no data leaves the machine

**Project Type**: single project — Typer CLI plus a local FastAPI web interface
over a shared SQLAlchemy model layer

**Performance Goals**: NFR-1 — a daily run completes within a few minutes at an
expected volume below one hundred postings. At that scale the predicate's plan
shape is not a measurable factor; the partial index `ix_employers_suppressed` is
an optimisation, not a correctness dependency.

**Constraints**: dependency direction is load-bearing and enforced by review —
`pipeline/` must not import `services/`; `normalise/` and `collect/` hold no
database knowledge; `web/` never writes pipeline data; nothing outside
`config.py` reads `os.environ`. The suppression predicate must compile
identically under SQLite and PostgreSQL — no dialect split, unlike
`queries._has_source`.

**Scale/Scope**: ~11 source files touched, 1 deleted, 1 added; ~7 test files
amended; 1 new test module; 8 specification/design documents corrected. No
schema change expected — to be *verified*, not assumed (see Phase 4).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status: not operative.** `.specify/memory/constitution.md` is the unmodified
Spec Kit template — every principle is still a `[PRINCIPLE_N_NAME]` placeholder.
There are no ratified gates to evaluate against, so this check cannot pass or
fail on its own terms and is not treated as a blocker.

In its place, the plan is gated against the project's two written, enforced
constraints, both from `CLAUDE.md`:

| Constraint | Applies how | Verdict |
|---|---|---|
| **Dependency direction is strict and load-bearing** — `pipeline/` must not import `services/`; `config.py` depends on nothing | The seam must be reachable from both `services/` (list, dashboard, facets) and `pipeline/` (future stages 3–4). Siting it in `services/` would put it structurally out of reach of the stages ADR-0015 names as consumers | **Pass** — seam sited in `db/`, which both may import. This is the reason for the decision, not a convenience |
| **Assert non-merging at least as hard as merging** — the suite's governing asymmetry, because a false merge conceals a posting | Restated for this feature: a *missing filter* resurfaces a blacklisted employer. The concealment risk runs toward exposure, so the negative assertions carry the weight — one invisibility test per adopting read path, not one in total | **Pass** — encoded as SC-006 and Phase 1.5 |
| Comments cite the decision they implement (`ADR-0004`, `design §7.3`, `D12`) | Every seam adoption and every opt-out cites ADR-0015 | **Pass** — Phase 1.4 makes the opt-out comments a deliverable, not a courtesy |

*Post-Phase 1 re-check*: unchanged. The design adds one module in `db/`, imports
it from `services/` and (later) `pipeline/`, and introduces no new dependency
edge in the prohibited direction. No entry in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/002-employer-suppression-derived/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output — the four decisions and what was rejected
├── data-model.md        # Phase 1 output — what each field means after the change
├── quickstart.md        # Phase 1 output — how to prove it works
├── contracts/
│   ├── visibility-seam.md      # The internal contract every read path signs
│   └── read-path-inventory.md  # Every query over postings, and its verdict
├── checklists/
│   └── requirements.md  # Spec quality validation
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/src/app/
├── config.py                    # untouched
├── __main__.py                  # MODIFY — drop `suppressed=` from the run-all output line
├── db/
│   ├── models.py                # MODIFY — delete reject_for_suppression; Posting.create
│   │                            #          always births STATUS_NEW; comment sweep
│   └── visibility.py            # ADD — the seam: not_suppressed()
├── pipeline/
│   ├── __init__.py              # MODIFY — drop run_suppress import and __all__ entry
│   ├── runner.py                # MODIFY — drop import, call, and "suppressed" result key
│   └── suppress_stage.py        # DELETE
├── services/
│   ├── blacklist.py             # MODIFY — reduce to two flag flips
│   ├── queries.py               # MODIFY — adopt the seam (list, totals, facets);
│   │                            #          comment the get_posting opt-out
│   ├── reports.py               # MODIFY — comments only; R1 docstring is now false,
│   │                            #          R3 opt-out needs stating
│   └── triage.py                # untouched — survives ADR-0015 unchanged
└── web/routes/employers.py      # MODIFY — docstrings only; both promise rejection

app/tests/
├── test_visibility.py           # ADD — the predicate in isolation
├── test_blacklist.py            # MODIFY — delete 4 sweep tests, invert 3, add per-seam
│                                #          invisibility tests
├── test_models.py               # MODIFY — invert born-rejected; delete 3 tests
└── test_posting_status_history.py  # MODIFY — delete the suppression-reason assertion
```

**Structure Decision**: The existing single-project layout under `app/src/app/`
is unchanged. This feature adds exactly one module, `db/visibility.py`, and
deletes exactly one, `pipeline/suppress_stage.py`. The placement of the added
module is the whole architectural content of the plan and is argued in
[research.md](research.md) R1.

## Implementation phases

Full step-level detail lives in the
[engineering plan](../../Docs/design/IMPLEMENTATION_PLAN_ADR-0015-Employer-level.md);
`/speckit-tasks` expands these into `tasks.md`.

### Phase 0 — Land the ADR-0014 baseline

The working tree held two ADR-0014 fixes with opposite fates, and they are
treated differently (research R6):

- **`services/triage.py` — committed.** Its `FOR UPDATE` and `ORDER BY id` guard
  the single-operator duplicate-request race (double-click, two tabs), which is
  orthogonal to suppression and survives ADR-0015 untouched.
- **`services/blacklist.py` — stashed, not committed.** The sweep-atomicity fix
  was correct for the model it defended, and every line of it is deleted by this
  feature. Landing it would add add-then-delete churn to the breaking commit for
  a record that ADR-0014 and the concurrency review already carry.

Committing them separately — rather than as one "ADR-0014 baseline" — is what
lets history separate "we hardened the transitions" from "we removed the thing
that needed hardening".

Then accept ADR-0013, and mark ADR-0014 partly superseded. Its amended header
must state that case 2 was superseded **before it was committed**, so a reader
searching for that implementation knows there is none rather than assuming they
have missed it.

*Exit: suite green, behaviour unchanged.*

### Phase 1 — Add the seam while the old mechanism still stands

Nothing is removed. Suppression ends up enforced twice — stamped *and* filtered
— which is precisely the condition under which the new enforcement can be proven
on its own. Add `db/visibility.py`; adopt it in `list_postings` (page **and**
count), `totals` (all five figures), `facets`; comment the two opt-outs; write
one invisibility test per adopting seam.

The keystone test: a suppressed employer's posting **whose status is still
`new`** is invisible. It fails before the seam exists, for exactly the right
reason.

*Exit: suite green. Suppression enforced by both mechanisms.*

### Phase 2 — Remove the materialisation

Delete `suppress_stage.py` and its wiring; reduce `blacklist()`/`lift()` to flag
flips; delete `Posting.reject_for_suppression`; sweep the model comments that
now assert something false.

*Exit: the Phase 3 tests fail here by design.*

### Phase 3 — Rewrite the tests the change invalidates

Each invalidated test is inverted or replaced, never deleted quietly, so the
suite keeps covering the *requirement* rather than the *mechanism*. Only the
four `run_suppress` tests go outright, and Phase 1's invisibility tests are their
named successors.

*Exit: suite green. First point at which the change is complete and correct.*

### Phase 4 — Record the reversal, and verify schema neutrality

ADR-0015 exists because the *previous* reversal went unrecorded; leaving drift
would repeat the exact failure. Correct 001's spec, data-model, research, plan,
and tasks; the SRS; and the design records.

Then verify the no-op migration rather than assuming it:

```powershell
uv run alembic revision --autogenerate -m "verify adr-0015 is schema-neutral"
```

An empty `upgrade()` confirms it — **delete the generated file**. A non-empty one
means the Phase 2 model sweep changed more than a comment, and is a defect to
fix, not a migration to keep.

## Risks

| Risk | Mitigation |
|---|---|
| A read path forgets the filter — the failure mode ADR-0015 accepts as permanent | [contracts/read-path-inventory.md](contracts/read-path-inventory.md) forces a verdict on every current query; opt-outs carry comments so a later reader sees a choice, not an oversight; the seam's own docstring states the obligation at the definition site |
| A future `pipeline/` stage cannot reach the seam | Resolved by siting it in `db/` (research R1) |
| Test deletion quietly drops requirement coverage | Phase 3 inverts wherever a requirement survives the mechanism; the only outright deletions are the four `run_suppress` tests, whose successors are named in Phase 1 |
| SQLite/PostgreSQL divergence in the `NOT EXISTS` | Plain correlated EXISTS — no dialect-specific JSON or index behaviour, unlike `_has_source`, which needed a split. Suite exercises it under SQLite; the partial index is a PostgreSQL optimisation only |
| Phase 2 lands without Phase 1 | Separate commits in that order. Between them suppression is enforced twice; never zero times |
| The restored back catalogue surprises the operator on lift | Stated plainly in spec FR-012/FR-013 and surfaced on the blacklist view. Any hide-on-lift affordance is explicitly out of scope, not silently assumed |

## Complexity Tracking

No entries. The design removes a module, a pipeline stage, two service
functions, and a model method, and adds one nine-line predicate. Net complexity
is negative.
