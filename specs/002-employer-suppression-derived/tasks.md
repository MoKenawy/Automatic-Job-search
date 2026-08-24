---
description: "Task list for employer-level suppression, derived at read time (ADR-0015)"
---

# Tasks: Employer-level suppression, derived at read time

**Input**: Design documents from `/specs/002-employer-suppression-derived/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: **Included, and not optional here.** The specification requires them by
name — SC-006 demands one invisibility assertion *per read path* so that removing
the filter from any single path fails the suite, and the whole feature's accepted
failure mode (per ADR-0015) is a read path that silently forgets the filter.
Tests are the containment.

**Organization**: Grouped by user story, but see the ordering note below — this
feature's phases are not freely reorderable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Paths are repository-relative. Commands run from `app/`.

---

## ⚠️ Ordering is a safety property, not a convention

The template's usual promise — foundational work, then stories in parallel —
holds only partly here. Three constraints override it:

1. **Phase 3 (adopt the seam) must land before Phase 5 (remove the sweep).**
   Between them, suppression is enforced *twice* — stamped and filtered. That
   redundancy is the point: it is the only window in which the new enforcement
   can be proven on its own, and it guarantees there is no commit at which a
   blacklisted employer's postings are visible. Reversing these phases opens
   exactly that gap.

2. **US2 and US3 are blocked by Phase 5**, and cannot be parallelised with US1.
   Their acceptance criteria (a posting *born* `new`; a lift that *restores*
   prior status) are unreachable while `Posting.create` still births `rejected`
   and `blacklist()` still overwrites status. This is stated rather than papered
   over: the stories are independently *testable*, not independently
   *deliverable*.

3. **Within Phase 5, the test-import cleanup (T023) comes first**, before any
   symbol it imports is deleted. See the note on T023 — this is a
   collection-time failure, not a test failure, and the two are not equivalent.

**US1 alone is a coherent, shippable increment** — it delivers the full
visibility guarantee. US2 and US3 deliver reversibility and the removal of the
catch-up pass.

---

## Phase 1: Setup — land the ADR-0014 baseline

**Purpose**: The working tree held two ADR-0014 fixes with opposite fates. Only
one is committed; see research R6.

> **`services/blacklist.py`'s sweep-atomicity fix is stashed, not committed.**
> Every line of it is deleted by Phase 5, so landing it would add
> add-then-delete churn to the breaking commit for a record that ADR-0014 and
> [the concurrency review](../../Docs/design/suppression-concurrency-review.md)
> already carry better. Phase 5 therefore edits `blacklist.py` **as it stands on
> `main`** — there is no `_reject_employer_postings`, and `blacklist()` still
> commits twice.

- [X] T001 Commit the row-locking and `actor="operator"` changes in `app/src/app/services/triage.py` (`FOR UPDATE`, `ORDER BY id`) — the only part of the ADR-0014 work that survives ADR-0015. The double-click / two-tabs race it guards is orthogonal to suppression and stays real
- [X] T002 [P] Set status to *Accepted* in `Docs/ADRs/0013-posting-status-history.md`
- [X] T003 [P] Set status to *Accepted, partly superseded by ADR-0015* in `Docs/ADRs/0014-status-transition-row-locking.md`, copying the surviving/moot split from ADR-0015 §Relationship into its header. **State explicitly that case 2 was superseded before it was committed** — its single-transaction `blacklist()` fix has no implementation in `main`'s history, and a reader who searches for one needs to know none exists rather than assume they have missed it (research R6)
- [X] T004 Verify baseline: `uv run pytest` green, behaviour unchanged

**Checkpoint**: Commits 1–2 of the sequence at the foot of this file are in place.

---

## Phase 2: Foundational — the visibility seam

**Purpose**: Create the single predicate every read path will apply.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Create `app/tests/test_visibility.py` with the three cases from [contracts/visibility-seam.md](contracts/visibility-seam.md) — normal employer's posting selected; suppressed employer's posting rejected; **suppressed employer's posting whose `status` is still `new`** rejected. Run it and confirm the third case FAILS — it is the assertion this whole feature exists to make true, and it must be seen failing before the seam exists
- [X] T006 Create `app/src/app/db/visibility.py` with `not_suppressed() -> ColumnElement[bool]` as a correlated `NOT EXISTS` over `Employer`, per [contracts/visibility-seam.md](contracts/visibility-seam.md). The module docstring carries the FR-010 obligation — it is the deliverable, not decoration
- [X] T007 Verify `uv run pytest tests/test_visibility.py` green

**Checkpoint**: The seam exists and is proven in isolation. Nothing uses it yet.

---

## Phase 3: User Story 1 — a blacklisted employer disappears completely (Priority: P1) 🎯 MVP

**Goal**: Postings of a blacklisted employer are absent from every operator-facing
view — list, list total, published filter, dashboard figures, filter options —
while remaining in the database.

**Independent Test**: Blacklist an employer with postings across several statuses
and countries; check every view. Absent from all, the list's total matches the
rows shown, and the rows are still on disk.

### Tests for User Story 1 ⚠️

> Write these FIRST and confirm they FAIL. All live in `app/tests/test_blacklist.py`,
> so they are sequential edits to one file — no `[P]`. They are separate *tasks*
> deliberately: SC-006 requires one assertion per path, not one in total, so that
> dropping the filter from any single path fails the suite.
>
> **Every one of these is two-sided.** Each fixture holds a suppressed employer
> *and* a normal one, and each test asserts the suppressed posting is absent
> **and the normal posting is present**. Absence-only tests would all pass
> against a `not_suppressed()` that returned `false` and hid the entire corpus —
> the seam would be catastrophically wrong and the suite would be green.

- [X] T008 [US1] Test in `app/tests/test_blacklist.py`: a suppressed employer's `status='new'` posting is absent from `queries.list_postings` rows **and** from `Page.total`, while a normal employer's posting is present in both. Asserted together, because a total that disagrees with the page makes the pager claim results the operator cannot reach
- [X] T009 [US1] Test in `app/tests/test_blacklist.py`: a `published=True` posting of a suppressed employer is absent from `list_postings(published_only=True)`, while a normal employer's published posting is present — this is FR-009's enforcement now
- [X] T010 [US1] Test in `app/tests/test_blacklist.py`: a suppressed employer's postings are excluded from `queries.totals` `postings`, `published`, `scored`, and every `by_status` bucket, while a normal employer's postings are still counted in each
- [X] T011 [US1] Test in `app/tests/test_blacklist.py`: a blacklisted employer is excluded from `queries.totals().employers`, while a non-blacklisted employer is still counted
- [X] T012 [US1] Test in `app/tests/test_blacklist.py`: a country whose only posting belongs to a suppressed employer is absent from `queries.facets().countries`, a country with a normal employer's posting is still offered, and `unknown_country` is False when only suppressed postings lack a country
- [X] T013 [US1] Test in `app/tests/test_blacklist.py`: after blacklisting, the employer's postings are absent from the list **but still present in the `postings` table** (FR-014, design D9). This is the direct successor to `test_postings_are_preserved_not_deleted`, which T023 removes — invisibility is not retention, and without this task the suite would accept a future change that deleted suppressed postings outright

### Implementation for User Story 1

> All in `app/src/app/services/queries.py` — sequential, no `[P]`. Verdicts and
> line references: [contracts/read-path-inventory.md](contracts/read-path-inventory.md).

- [X] T014 [US1] Apply `not_suppressed()` to both `list_postings` statements — the count (`queries.py:184-189`) and the page (`queries.py:193-200`). Both, or the pager lies
- [X] T015 [US1] Apply `not_suppressed()` to all four posting figures in `queries.totals` — `postings`, `published`, `scored`, and the `by_status` grouping (`queries.py:37-50`)
- [X] T016 [US1] Apply `Employer.suppressed.is_(False)` — **not** `not_suppressed()` — to the employer count in `queries.totals` (`queries.py:52`); the predicate is over `postings` and does not apply to a count of employers
- [X] T017 [US1] Apply `not_suppressed()` to both `queries.facets` statements — the country `distinct` and the unknown-country count (`queries.py:225-235`)
- [X] T018 [US1] Run `uv run pytest` — green

**Checkpoint**: US1 complete and shippable. Suppression is now enforced **twice**
— stamped *and* filtered. This is commit 3 (`feat(db): add the suppression read
seam`).

---

## Phase 4: User Story 4 — the way back out stays reachable (Priority: P3)

**Goal**: A suppressed posting's detail page still loads and offers the removal
action; both deliberate opt-outs are commented so a later reader sees a decision,
not an oversight.

**Independent Test**: Note a posting's URL, blacklist its employer, open the URL.
The page loads, shows the blacklist state, offers removal.

> **Sequenced here despite being P3.** It needs no removal work, and the opt-out
> comments belong in the same commit as the adoptions — an inventory that lists
> adoptions in one commit and exemptions in another is, in between, an inventory
> with unexplained gaps.

- [X] T019 [US4] Test in `app/tests/test_blacklist.py`: the detail route for a posting whose employer is suppressed returns 200 and renders the blacklist banner and the "Remove from blacklist" control
- [X] T020 [US4] Comment the deliberate opt-out at `queries.get_posting` (`app/src/app/services/queries.py:261`) citing ADR-0015 and FR-015 — this page is the operator's route back out, so filtering it would make lifting unreachable from the posting that prompted it
- [X] T021 [US4] Comment the deliberate opt-out at `reports.source_overlap` (`app/src/app/services/reports.py:193`) citing ADR-0015 and FR-017 — it measures what the collector returned, so filtering would understate a board's coverage
- [X] T022 [US4] Reword the `reports.employer_activity` docstring (`app/src/app/services/reports.py:83-112`) — its "their postings are auto-rejected (D9)" becomes false. Behaviour and the `include_suppressed` opt-out are unchanged; only the claim is wrong

**Checkpoint**: [contracts/read-path-inventory.md](contracts/read-path-inventory.md)
is discharged for all inventoried paths — SC-005 satisfied.

---

## Phase 5: Foundational — remove the materialisation

**Purpose**: Delete the sweep and everything that writes suppression onto a
posting. **Blocking prerequisite for US2 and US3.**

**⚠️ Must not land before Phase 3.** Removing the stamp while the filter is
absent is the one sequence that exposes blacklisted employers.

- [X] T023 **First in this phase, before any symbol it imports is deleted.** In `app/tests/test_blacklist.py`: drop the `run_suppress` and `reject_employer_postings` imports (`:24-25`), delete the four `run_suppress` tests (`:65-96`) and `test_suppress_employer_targeted` (`:177`), and rewrite the module docstring. These are module-level imports of symbols T024 and T028 delete — run in the other order and the file fails to **collect**, which is not the same as failing: a collection error silently takes every other test in the file with it, and Phase 5's checkpoint then cannot distinguish expected failures from real defects. Successors: T008–T012 for the invisibility assertions, **T013 for the retention assertion**
- [X] T024 Delete `app/src/app/pipeline/suppress_stage.py`
- [X] T025 Drop the `run_suppress` import and its `__all__` entry from `app/src/app/pipeline/__init__.py`
- [X] T026 Drop the import, the `run_suppress(session)` call, and the `"suppressed"` result key from `_run` in `app/src/app/pipeline/runner.py`
- [X] T027 Drop `suppressed={result['suppressed']}` from the `run-all` echo in `app/src/app/__main__.py:81`, which would otherwise `KeyError` after T026
- [X] T028 Rewrite `app/src/app/services/blacklist.py` — **as it stands on `main`**, since the ADR-0014 atomicity work was stashed rather than committed (research R6). Delete `reject_employer_postings` (`:24-38`) and reduce `blacklist()` to a flag flip returning `None`. **Four pieces of prose must go with the code, or they survive as false claims** — the same class of drift T030 sweeps in `models.py`, and easier to miss here because the function around them is being deleted rather than edited:
  - the module docstring (`:1-7`), which points at `suppress_stage.run_suppress` as "the bulk sweep" and describes blacklisting's "immediate sweep"
  - `blacklist()`'s docstring (`:42-46`) — *"immediately reject their postings"*, *"Returns the number of postings newly rejected"*. Nothing is rejected and the return becomes `None`
  - **`lift()`'s docstring (`:56-61`)** — *"Future postings are no longer auto-rejected; previously rejected postings are NOT reinstated (US3, FR-011)"*. **Both clauses invert.** Nothing was auto-rejected, and postings **are** reinstated with their prior status. This is the service-layer twin of the `Employer.lift_blacklist` docstring T030 fixes, and it is the one a caller actually reads. Reword against spec FR-012
  - the `log.info("suppression: rejected %d posting(s)…")` call — nothing is rejected

  Ruff (T042) will catch the imports the deletion orphans (`datetime`, `UTC`, `select`, `STATUS_REJECTED`, `Posting`); it will not catch any of the above
- [X] T029 In `app/src/app/db/models.py`: delete `Posting.reject_for_suppression` (`:394-403`) and make `Posting.create` (`:329`) always birth `STATUS_NEW`, dropping the born-Rejected rationale from its docstring
- [X] T030 Comment sweep in `app/src/app/db/models.py` — five sites now assert something false: `STATUS_REJECTED`'s "doubles as the D9 suppression signal" (`:46`); `Posting.status`'s "suppression-driven rejection" note (`:252-256`); `transition_to`'s suppression-sweep parenthetical (`:369`); `Employer.lift_blacklist`'s FR-011 docstring (`:116-119`, now **inverted** — postings *do* return); `PostingStatusHistory.actor`'s "'system' (suppression sweep)" (`:436`). `'system'` stays a valid actor value for future automated paths; it simply has no writer today
- [X] T031 Reword `_ordering`'s docstring in `app/src/app/services/queries.py:104-122` — no posting is born Rejected any more, so the NULL `status_changed_at` case survives only for rows predating this change. Reword rather than delete: the `nullslast()` is still load-bearing for them
- [X] T032 Update both route docstrings in `app/src/app/web/routes/employers.py:30,49` — both currently promise rejection and non-reinstatement. The `blacklist()` return value was already ignored, so no call-site change is needed

**Checkpoint**: `uv run pytest` **fails here by design** — the failures are the
tests asserting the old mechanism as behaviour. Anything failing that is *not* in
that set is a real defect. T023 having run first is what makes that distinction
readable.

---

## Phase 6: User Story 2 — suppression covers postings not yet collected (Priority: P2)

**Goal**: A posting collected from an already-blacklisted employer is stored with
the ordinary starting status and is invisible from that moment, with no pass
having run.

**Independent Test**: Blacklist an employer, normalise a raw posting from it,
confirm the posting is `new`, invisible through the seam, and that no
system-authored history row was written.

- [X] T033 [US2] Invert `test_new_posting_from_blacklisted_employer_is_born_rejected` at `app/tests/test_blacklist.py:102` — the posting is born `new` and is invisible through the seam **with no pass having run**. This is the test that proves ADR-0015 §Decision 1: "covers postings not yet seen", satisfied structurally
- [X] T034 [P] [US2] Invert the born-rejected assertion at `app/tests/test_models.py:52` to born-`new`
- [X] T035 [P] [US2] Delete the three `reject_for_suppression` tests at `app/tests/test_models.py:176-185` and `:226-231` — target method is gone
- [X] T036 [P] [US2] In `app/tests/test_posting_status_history.py`: delete the `reason == "employer suppressed"` assertion and its test (`:216`), and fix the module docstring's reference to `blacklist.reject_employer_postings`. ADR-0013's history contract is otherwise untouched
- [X] T037 [US2] Add a test asserting `posting_status_history` gains **zero** `actor='system'` rows across a full blacklist → collect → lift cycle (SC-004), in `app/tests/test_posting_status_history.py`

**Checkpoint**: US2 complete. The catch-up pass is gone and nothing needs it.

---

## Phase 7: User Story 3 — un-blacklisting restores what it hid (Priority: P2)

**Goal**: Removing a blacklist returns the employer's postings to visibility with
each posting's prior triage status intact.

**Independent Test**: Record statuses, blacklist, un-blacklist, confirm every
posting is visible again carrying its original status.

- [X] T038 [US3] Invert `test_blacklist_endpoint_suppresses_and_rejects` at `app/tests/test_blacklist.py:149` — the endpoint sets the flag and the postings' statuses are **untouched**, while being invisible
- [X] T039 [US3] Invert `test_unblacklist_stops_future_but_does_not_reinstate` at `app/tests/test_blacklist.py:160` — **this is the visible behaviour change**: after blacklist-then-lift, postings are visible again with prior status intact across all four statuses (`new` stays `new`, `shortlist` stays `shortlist`, an operator-rejected posting stays `rejected`). Rename to match. Covers FR-012 and SC-003
- [X] T040 [US3] Add the FR-013 standing note to `app/src/app/web/templates/blacklist.html` — blacklists applied before this change do not restore their postings on removal. A view-level note, not a per-posting distinction, which is not recoverable
- [X] T041 [US3] Test in `app/tests/test_blacklist.py` that `/blacklist` renders the FR-013 note
- [X] T042 [US3] Run `uv run ruff check src tests --fix`, then `uv run ruff format src tests`, then `uv run pytest`

**Checkpoint**: **Suite green. First point at which the change is complete and
correct.** This is commit 4 — the breaking one, carrying a `BREAKING CHANGE:`
trailer naming the FR-011 inversion.

---

## Phase 8: Polish & Cross-Cutting — record the reversal

**Purpose**: ADR-0015 exists because the *previous* reversal went unrecorded.
Leaving these as drift repeats precisely the failure the ADR was written about,
so this phase is not optional tidying.

### Verification

- [ ] T043 **Blocked.** Run `uv run alembic revision --autogenerate -m "verify adr-0015 is schema-neutral"`. An empty `upgrade()` confirms schema neutrality — then **delete the generated file**. A non-empty body means T029/T030 changed more than a comment: fix at the source, do not keep the migration. *The dev Postgres container's `alembic_version` is stamped to a revision (`b2c3d4e5f6a7`) absent from any committed migration file — likely left over from an abandoned branch. It holds 466 real postings, so this needs the developer's own judgement rather than an automated fix; resolve that mismatch first, then run this check.*
- [ ] T044 **Blocked on T043** — same DB. Walk [quickstart.md](quickstart.md)'s manual scenario against a populated database, especially step 7 — the shortlisted posting returns *still shortlisted*

### Carry the obligation forward

- [X] T045 Record the FR-011 seam obligation for the unbuilt stages in `Docs/design/system-architecture.md`: stage 3 (scoring) and stage 4 (publication) must apply `db.visibility.not_suppressed()` when selecting postings to work on and when writing their run counts, and stage 4 is where FR-009 now lives. Without this the obligation exists only in `specs/002-*/contracts/`, which a future stage-3 author has no reason to open — and inheriting it by accident is the failure ADR-0015 names as permanent

### Specification corrections

- [X] T046 [P] Rewrite FR-007, FR-009, FR-011 in `specs/001-ui-self-service/spec.md` against ADR-0015, per the mapping table in [spec.md](spec.md#superseded-requirements-from-001-ui-self-service). FR-011 becomes the display decision
- [X] T047 [P] Annotate `specs/001-ui-self-service/data-model.md:113-125` as superseded, linking ADR-0015 — this is the passage that introduced the materialisation without an ADR
- [X] T048 [P] Mark superseded (do not delete) in `specs/001-ui-self-service/`: research.md D-A and D-B; plan.md:105,109 (the `suppress_stage.py` tree entry); tasks.md **001's** T020-T022 and T026 (that feature's IDs, not this one's). 001's T026 note "satisfied at the write layer" is now specifically wrong and is worth correcting in place rather than only flagging
- [X] T049 [P] Update FR-011 and any suppression-pass language in `Docs/software-requirements-specification.md`

### Design records

- [X] T050 [P] Add a superseded header to `Docs/design/status-transition-concurrency.md` pointing at ADR-0015, rather than editing its sweep sequence diagrams — they describe deleted code but remain the record of *why*
- [X] T051 [P] Tick §8's next steps as done in `Docs/design/suppression-concurrency-review.md`
- [X] T052 [P] Sweep `Docs/design/data-model.md`, `Docs/development-guide.md`, and `CLAUDE.md`'s architecture tree for suppression-stage references (`Docs/design/system-architecture.md` is covered by T045)
- [X] T053 Draft `Docs/design/System-modeling.md` from review §6, revised: the liveness property ("every posting of a suppressed employer *eventually* reaches suppressed, bounded by the next pipeline run") is replaced by a **safety** property ("no posting of a suppressed employer is ever visible"). Nothing converges any more, so nothing needs a convergence bound

**Checkpoint**: Commit 5 (`docs: record the ADR-0015 reversal across specs and
design records`).

---

## Dependencies & Execution Order

### Phase dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational — the seam)     ← blocks everything
    ↓
Phase 3 (US1, P1)  🎯 MVP             ← shippable alone
    ↓
Phase 4 (US4, P3)                     ← no removal needed; same commit as Phase 3
    ↓
Phase 5 (Foundational — removal)      ← MUST follow Phase 3; T023 first within it
    ↓
    ├── Phase 6 (US2, P2)  ─┐
    └── Phase 7 (US3, P2)  ─┴─ genuinely parallel with each other
              ↓
Phase 8 (Polish)
```

### User story dependencies

- **US1 (P1)**: needs Phase 2 only. Independently deliverable.
- **US4 (P3)**: needs Phase 2 only. Sequenced with US1 for commit coherence.
- **US2 (P2)**: **blocked by Phase 5** — cannot be born `new` while `Posting.create` births `rejected`.
- **US3 (P2)**: **blocked by Phase 5** — cannot restore prior status while `blacklist()` overwrites it.

US2 and US3 touch disjoint tests and can be worked in parallel with each other.

### Intra-phase ordering that is not optional

- **T023 before T024 and T028.** Module-level imports of deleted symbols. See T023.
- **T027 after T026.** `__main__.py` reads the `"suppressed"` key T026 removes.
- **T013 before T023.** The retention successor should exist before the test it succeeds is deleted, so FR-014 is never uncovered — not even for one commit.

### Parallel opportunities

- **T002, T003** — different ADR files
- **T034, T035, T036** — `test_models.py` and `test_posting_status_history.py`, disjoint
- **T046–T052** — seven documentation files, no overlap
- **Phases 6 and 7** — different test targets, both unblocked by Phase 5

**Not parallel, despite appearances**: T008–T013 all edit `app/tests/test_blacklist.py`;
T014–T017 all edit `app/src/app/services/queries.py`. Separate tasks for
traceability against SC-006 and the read-path inventory, but sequential edits to
one file each.

---

## Parallel Example: Phase 8 documentation

```bash
Task: "Rewrite FR-007/009/011 in specs/001-ui-self-service/spec.md"
Task: "Annotate specs/001-ui-self-service/data-model.md:113-125 as superseded"
Task: "Mark superseded: 001 research.md D-A/D-B, plan.md:105,109, tasks.md T020-T022/T026"
Task: "Update FR-011 in Docs/software-requirements-specification.md"
Task: "Add superseded header to Docs/design/status-transition-concurrency.md"
Task: "Tick §8 next steps in Docs/design/suppression-concurrency-review.md"
Task: "Sweep Docs/design/data-model.md, Docs/development-guide.md, CLAUDE.md"
```

---

## Implementation Strategy

### MVP (US1 only)

1. Phase 1 — baseline committed
2. Phase 2 — seam exists and is proven in isolation
3. Phase 3 — every read path adopts it
4. **STOP and VALIDATE**: a blacklisted employer is invisible everywhere, and still on disk

At this point suppression is enforced twice. That is a legitimate resting state —
correct, if redundant — and safe to sit on indefinitely. It is *not* the finished
feature: the reversibility (US3) and the removal of the catch-up pass (US2) are
what the ADR was actually written for.

### Incremental delivery

1. Phases 1–2 → foundation
2. Phase 3 + Phase 4 → **commit 3**: seam adopted, inventory discharged (MVP)
3. Phases 5–7 → **commit 4**: breaking. Materialisation gone, FR-011 inverted
4. Phase 8 → **commit 5**: the reversal recorded

### Commit sequence

Five commits, matching the engineering plan's
[§8 sequence](../../Docs/design/IMPLEMENTATION_PLAN_ADR-0015-Employer-level.md#8-commit-sequence).
Its commit 1 covered both `triage.py` and `blacklist.py`; here it covers
`triage.py` alone, because `blacklist.py`'s ADR-0014 work is stashed rather than
committed (research R6).

| # | Message | Tasks |
|---|---|---|
| 1 | `fix(triage): lock rows during status transitions (ADR-0014)` | T001 |
| 2 | `docs(adr): accept ADR-0013, mark ADR-0014 partly superseded` | T002–T003 |
| 3 | `feat(db): add the suppression read seam (ADR-0015)` | T005–T022 |
| 4 | `refactor(suppression)!: derive suppression from employer, drop the sweep (ADR-0015)` | T023–T042 |
| 5 | `docs: record the ADR-0015 reversal across specs and design records` | T043–T053 |

Commit 4 is the breaking one. The `!` and a `BREAKING CHANGE:` trailer naming the
FR-011 inversion belong on it.

---

## Notes

- `[P]` = different files, no dependencies
- Verify tests fail before implementing — especially T005, whose failure *is* the
  feature's thesis, and Phase 5's checkpoint, whose failures are the plan working
- Every US1 test is two-sided (suppressed absent **and** normal present); an
  absence-only suite passes against a seam that hides everything
- Phase 5 edits `blacklist.py` as it stands on `main`, not as the stashed
  working tree left it (research R6)
- The suite runs without Docker; only T043 and T044 need PostgreSQL
- Comments cite the decision they implement (`ADR-0015`, `FR-xxx`) per `CLAUDE.md`
