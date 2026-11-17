---
description: "Task list for collect-stage relevance and experience filtering (spec 003)"
---

# Tasks: Collect-stage relevance and experience filtering

**Input**: Design documents from `/specs/003-collect-stage-filtering/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/filter-seam.md](contracts/filter-seam.md),
[quickstart.md](quickstart.md)

**Tests**: **Included, and not optional here.** The specification requires them by
name — SC-002 demands that the body of tests proving nothing is wrongly rejected be
*at least as large* as the body proving rejection works, which is the suite's
governing asymmetry (`CLAUDE.md`) restated for a filter. A false rejection conceals
a posting the operator cannot recover by looking harder; tests are the containment.

**Organization**: by the plan's six phases, with story labels on the tasks that
deliver each story. See the ordering note below — these phases are not freely
reorderable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (experience honoured, P1), US2 (off-topic titles stop arriving,
  P2), US3 (the operator can see and tune what the filter did, P3)
- Paths are repository-relative. Commands run from `app/`.

---

## ⚠️ Ordering is a safety property, not a convention

The template's usual promise — foundational work, then stories in parallel — holds
only partly here. Four constraints override it:

1. **Phase 2 (write the verdicts) must land before Phase 3 (enforce them).**
   Between them the filter is recorded but reads nowhere, which is the only window
   in which the criteria can be measured against the real corpus with no risk of
   hiding anything. `--dry-run` exists for that window. Reversing these phases means
   the first commit that can hide a posting is also the first one anybody has
   measured.

2. **Phase 3 is one commit, surfaces included.** The "Filtered out" bucket (T028)
   and the detail-page banner (T029) ship with the predicate, not after it. 002's
   detail-page opt-out is only defensible because the blacklist banner and lift
   control were already on that page; a commit that hides postings with nothing to
   explain where they went is the failure that precedent avoids.

3. **US1 and US2 are not independently deliverable, only independently testable.**
   They share one pure evaluator, one stage, one pair of verdict columns and one
   predicate. What is genuinely independent is their *criteria*: US1 needs a profile
   with an experience value, US2 needs a pattern, and either works with the other
   absent. The phases reflect the shared machinery; the story labels reflect which
   requirement each task serves.

4. **US3 is not last.** Its observability is what makes US1 and US2 safe to operate —
   a filter rejecting too much is otherwise indistinguishable from boards that have
   stopped returning results. Its recovery surfaces are therefore in Phase 3, and
   only the funnel display waits for Phase 4.

**The invariant every phase boundary preserves**: *there is no commit at which a
posting the operator should see is hidden, and no commit at which a posting is hidden
without a route to it.* Each boundary fails open — an absent or partial verdict is
NULL, and NULL is admitted — so a crash mid-stage under-filters rather than
over-filters.

---

## Phase 0: The pure core, imported by nothing

**Purpose**: all the criteria logic, with no database knowledge, so it is testable
without infrastructure (`CLAUDE.md`'s dependency rule; `Docs/development-guide.md`
§9 step 1).

- [ ] T001 Verify the baseline: `uv run pytest` green and `uv run ruff check src tests` clean on `003-collect-stage-filtering` before anything is added
- [ ] T002 [US1] Create `app/src/app/filters/levels.py`: a `Level` IntEnum ordered internship < entry < associate < mid_senior < director < executive **with no `UNKNOWN` member** (contract G3 — an unknown inside an orderable enum eventually meets a `<=`); `BOARD_LABELS` mapping the boards' controlled vocabulary onto it; `parse_level(label) -> Level | None` treating `None`, `""`, whitespace and `not applicable` as the same absence, case-insensitively (G2, citing `normalise/country.py`'s `parse_country` precedent); `parse_requested(text) -> Level | None` with a synonym table covering at least `fresh`, `fresher`, `graduate`, `grad`, `junior`, `jr`, `entry`, `entry level`, `intern`, `internship`, `associate`, `mid`, `mid-senior`, `senior`, `sr`, `lead`, `principal`, `staff`, `director`, `head`, `executive`, `vp`, `c-level`, returning `None` for anything unrecognised (FR-002, FR-002a); `level_from_title(normalised_title) -> Level | None`, word-boundary matching only and `None` when markers conflict (G9, FR-006); `merge_labels(labels) -> str | None` returning the minimum-seniority label with a lexicographic tie-break on the raw string (G8, FR-009, research R2); and `admits(requested, actual) -> bool | None` implementing the at-or-below band (FR-007)
- [ ] T003 [P] [US2] Create `app/src/app/filters/titles.py`: a frozen `TitleRules` with `compile(include, exclude)` that treats an empty or whitespace-only pattern as *criterion disabled* **before compiling** (G5, research R3 — `re.search("", title)` matches everything and both patterns ship empty), catches `re.error` into an `errors` tuple and disables only the offending pattern (G6, FR-008), and a `verdict(title) -> bool | None` matching case-insensitively against the **raw** title and returning `None` when both patterns are disabled (G4)
- [ ] T004 [US1] [US2] Create `app/src/app/filters/verdict.py`: frozen `Criteria` (title rules plus the requested levels of the profiles that surfaced a posting) and `Verdict` (`title_passed`, `experience_passed`, with derived `rejected` and `grounds` properties returning `'title' | 'experience' | 'both' | None`), and a pure `evaluate(*, title, normalised_title, job_level, criteria) -> Verdict` that combines per-profile experience results by **disjunction**, admits unconditionally for a profile-less contribution, falls back to `level_from_title` only where the board label is absent, and never raises (G7, research R1). Shape it on `normalise/fingerprint.py`'s `FingerprintParts` — a frozen value object carrying inputs alongside outcome
- [ ] T005 [US1] [US2] Create `app/src/app/filters/__init__.py` re-exporting the public surface (`Level`, `parse_level`, `parse_requested`, `level_from_title`, `merge_labels`, `admits`, `TitleRules`, `Criteria`, `Verdict`, `evaluate`) with an `__all__`, as `normalise/__init__.py` does
- [ ] T006 [P] [US1] Create `app/tests/test_filter_levels.py`: the scale's order; every board label in the live vocabulary parsed, as `# OBSERVED` strings (`mid-senior level`, `entry level`, `associate`, `not applicable`, `director`, plus `internship` and `executive` from the spec's vocabulary); all four spellings of unknown yielding `None`; the at-or-below band proved in both directions (entry admits internship/entry/associate, rejects mid-senior/director/executive); unrecognised requested text disabling rather than rejecting (FR-002a); the disjunction across two profiles with opposite requirements giving the same answer **in both orders** (research R1); `merge_labels` commutativity, idempotence and its tie-break; `level_from_title` word boundaries (`intern` must not match `internal`) and its refusal on conflicting markers
- [ ] T007 [P] [US2] Create `app/tests/test_filter_titles.py`: **an empty exclude pattern rejects nothing, named for SC-006**; an empty include pattern admits everything; include and exclude independently and together; a malformed pattern disabling its own criterion, reporting in `errors`, and not raising (FR-008, US2 scenario 4); case-insensitivity; a `None` or empty title admitted
- [ ] T008 [P] Correct the coverage record in `app/src/app/db/models.py`'s module docstring (FR-020): `job_level` and `company_industry` are present on 100% of LinkedIn rows and 0% of Indeed rows (67% overall, measured 16 November 2026 over 60 rows), not "never populated"; `job_function`, `listing_type`, `skills` and `experience_range` are confirmed at 0% and stay in the payload. State that `job_level` is promoted to a column by this feature and that the others are deliberately not (FR-019)
- [ ] T009 **Gate 0** — `uv run pytest` and `uv run ruff check src tests` green, **with no pre-existing test amended**. Nothing in the running system imports `filters/` yet, so a pre-existing test needing a change would mean this phase did more than it claims. Commit

**Checkpoint**: the criteria exist and are proved in isolation. Behaviour unchanged.

---

## Phase 1: Schema and data, but no verdicts

**Purpose**: promote the board's seniority label (FR-018, FR-019) so the filter's
primary input is typed, and add the verdict columns while nothing reads them.

- [ ] T010 In `app/src/app/db/models.py`, add `Posting.job_level` (`String(64)`, nullable) and `Posting.experience_filter_passed` (`Boolean`, nullable). Replace the `# Stage 3 — coarse title filter, then model evaluation` comment above `title_filter_passed` with the tri-state semantics from [data-model.md](data-model.md) — NULL = criterion not applied, True = applied and admitted (including because the input was unknown), False = applied and rejected — citing ADR-0016 and noting that this is what makes SC-006 checkable. No index (contract H6)
- [ ] T011 In `app/src/app/db/models.py`, add `job_level` as a keyword argument to `Posting.create` (defaulting to `None`, so existing call sites are unaffected) and add `Posting.merge_job_level(label)` beside `merge_description`. Its docstring must say **why it lowers rather than fills gaps** — the merged value must be a function of the set of contributing rows, and the minimum leans toward admission (FR-009, research R2) — or a reviewer will align it with the fill-gaps-only `merge_description` and `Employer.enrich_from`
- [ ] T012 In `app/src/app/pipeline/normalise_stage.py`, pass `job_level=payload.get("job_level")` through `Posting.create`, and call `posting.merge_job_level(payload.get("job_level"))` on the `observe()` branch so a later board's lower label wins. Note in a comment that the collector lowercases the label and yields `""` rather than null when LinkedIn descriptions are not fetched (research R8)
- [ ] T013 Create the DDL Alembic revision in `app/migrations/versions/` with `down_revision = "b2c3d4e5f6a7"`, adding both columns as nullable with **no server default** — `job_level` has 0% coverage on one working board, so a default would be a claim about absent data, and the verdict columns' NULL is load-bearing. Follow `e2494af987ca`'s "nullable and additive" shape and write the rationale into the docstring, as the existing revisions do
- [ ] T014 Create the data Alembic revision following T013, backfilling `postings.job_level` from each posting's contributing payloads through `raw_posting_normalizations`, **importing `app.filters.levels.merge_labels`** rather than restating the rule (the precedent set by `b2c3d4e5f6a7`, which imports `build_fingerprint`; research R7 — a restated rule can diverge and SC-007 would fail on day one). Batch as that revision does, log the row count, and give it a documented no-op downgrade. It must not write a verdict column: the spec forbids retroactive filtering on installation
- [ ] T015 [P] Create `app/tests/test_job_level_promotion.py` — its own module, because the promotion is stage 2 behaviour and the stage tests in T023 belong to a later phase: a first sighting storing the board's label; a second board supplying a lower label lowering it; a second board supplying a higher label leaving it alone; a second board supplying nothing leaving it alone; and the promotion never touching `last_retrieved_at` or `status`
- [ ] T016 **Gate 1** — `uv run alembic upgrade head`, `downgrade -1`, `upgrade head` all clean against the running PostgreSQL; then confirm with the quickstart's Gate 1 query that `job_level` is populated and **both verdict counts are zero**. A verdict at this point means a column is being written a phase early. Commit

**Checkpoint**: the filter's input is a typed column, backfilled over history. No
posting can be hidden by anything in this commit.

---

## Phase 2: The stage, write-only

**Purpose**: compute and record verdicts, and the run funnel, while nothing reads
them — the only window in which the criteria can be measured against real data at
zero risk (plan's Phase 2/3 boundary).

- [ ] T017 Create `app/src/app/db/attribution.py`: `posting_ids_for_run(session, run) -> list[int]` (the only path from a run to its postings — `Posting` → `raw_posting_normalizations` → `raw_postings` → `run_id`, the same one `services/reports.py` uses) and `requested_levels_by_posting(session, posting_ids) -> dict[int, list[Level | None]]`, assembling for each posting the requested level of every profile that has surfaced it, with `None` standing for a profile-less contribution (research R1). **One grouped query, not one per posting** (`refactor-plan.md` §4.3; the batching shape at `normalise_stage.py:43-76`). Sited in `db/` because `pipeline/` may not import `services/` — the same constraint that put `not_suppressed()` there (002 research R1); say so in the module docstring and note that `services/reports.py` could adopt it later
- [ ] T018 [US1] [US2] Create `app/src/app/pipeline/filter_stage.py` with `run_filter(session, run, config, *, dry_run=False) -> tuple[int, int]` and `filter_all(session, config, *, dry_run=False) -> tuple[int, int]`, sharing one private evaluator. Batch-load the postings in scope and their profile levels, evaluate each with `app.filters.evaluate`, and write each verdict **only when it differs from what is stored** (contract C3, research R5 — `updated_at` carries `onupdate`, so blind writes would move every row's timestamp and break SC-007). Write `run.filter_passed_count` / `filter_rejected_count` from the evaluated set (C1), commit once, and log `filter stage complete: …` — **not** "stage 2.5"; research R10 keeps the design's stage numbering intact — including the number of verdicts **changed** (so contract C3's zero-change property is observable rather than merely true), the count of unrecognised experience values, and any pattern error (C6, FR-002a, FR-008 — the `unresolved_country` precedent). Record any unusable criterion on `run.error` as well, the way `run_collect` records a non-fatal board failure, so the fault reaches the operator at `/runs` and not only the log — both FR-002a and FR-008 say "reported to the operator". Never write `status`, `status_changed_at`, `last_retrieved_at` or any raw row (C5, FR-012, FR-014). `filter_all` writes **no** run counters (C2). `dry_run` writes nothing at all (C4). Log a warning when `rejected == deduplicated_count > 0` (C7 — the spec's "every posting rejected" edge case, which the aggregate counts cannot distinguish from a dead board)
- [ ] T019 Export `run_filter` (and `filter_all`) from `app/src/app/pipeline/__init__.py`, which is where `__main__.py` imports stages from
- [ ] T020 [US3] Add the command to `app/src/app/__main__.py` as `@app.command("filter")` over `def filter_(...)` — the `@app.command("run-all")` / `def run_all()` precedent, and it avoids shadowing the builtin — taking `--run-id` (defaulting to the latest run, following `normalise`'s idiom), `--all` and `--dry-run`, echoing passed/rejected counts, **the number of verdicts changed** (zero on a converged re-apply, which is how the quickstart's Gate 2 checks SC-007) and any reported fault. `--all` and `--run-id` are mutually exclusive; say so rather than silently preferring one
- [ ] T021 In `app/src/app/pipeline/runner.py`, call the stage from `_run()` after `run_normalise` — which covers the CLI `run-all`, the scheduler and the web "run now" in one place — add `passed` and `rejected` to the returned dict, and add both counts to `track_run`'s completion log line
- [ ] T022 In `app/src/app/services/settings.py`, move `title_include_pattern` and `title_exclude_pattern` from `PENDING_KEYS` to `CONSUMED_KEYS` with the consumer named (`pipeline.filter_stage -> app.filters.titles`), and add `re.compile` validation to `_EditableModel` so a malformed pattern is refused at the form with a readable message instead of being stored (today `coerce_form` casts with bare `str()`). A refused save leaves the prior values standing, as `set_many`'s docstring already promises
- [ ] T023 [US1] [US2] Create `app/tests/test_filter_stage.py` (or extend it from T015): the sum invariant `filter_passed_count + filter_rejected_count == deduplicated_count` (SC-003, C1); a posting the board labelled above the requested level rejected and one at or below it admitted (US1 scenarios 1–2); an unlabelled posting admitted (US1 scenario 3); a profile with no experience rejecting nothing (US1 scenario 4); an excluded title rejected and a non-matching one admitted (US2 scenarios 1–3); convergence over repeated application (FR-010); **a converged re-apply issuing zero UPDATEs** (SC-007, C3); `--dry-run` writing nothing (C4); `status`, `status_changed_at`, `last_retrieved_at` and raw rows untouched (C5, FR-012/FR-014); the whole-haul warning (C7); and a malformed pattern completing the run while rejecting nothing (FR-008, US2 scenario 4)
- [ ] T024 [P] Amend `app/tests/test_settings.py` for the partition move in T022 — `test_every_editable_key_is_consumed_or_pending` must now see both title keys as consumed — and add a test that a malformed regex is refused by `set_many` and leaves the prior value standing
- [ ] T025 **Gate 2** — `uv run pytest` green; `uv run python -m app filter --all --dry-run` against the live database reporting counts consistent with the criteria in force; then `filter --all` twice, the second reporting zero changes and leaving `max(updated_at)` unmoved; then the quickstart's `balances` query true for every run the stage touched. Time `filter --all` and record the per-posting cost: SC-004 bounds a thousand postings at a minute, and the live corpus is 52, so the figure is an extrapolation and must be reported as one. Commit

**Checkpoint**: verdicts and the funnel are recorded and measurable. Nothing reads
them, so nothing is hidden.

---

## Phase 3: Enforcement and recovery, in one commit

**Purpose**: withhold rejected postings from the queue (US1, US2) **and** ship the
route to them (US3). One commit, because a commit that hides without explaining is
the failure 002's precedent avoids.

- [ ] T026 [US1] [US2] In `app/src/app/db/visibility.py`, add `filter_rejected()` (the pure verdict, no status term) and `hidden_by_filter()` (`filter_rejected() & (Posting.status == STATUS_NEW)`). Both written with **`.is_(False)`, never `== False`** — state the three-valued-logic hazard at the definition site: every verdict is NULL today, `NOT (NULL = FALSE)` is NULL, and a row whose clause evaluates to NULL is not selected, so the obvious spelling hides the entire corpus while an absence-only suite stays green (contract H1, research R6). Extend the module docstring with the second obligation, parallel in wording to the suppression one, and point at [contracts/filter-seam.md](contracts/filter-seam.md). Explain the `status == new` term: a tightening must never withdraw a posting the operator has already acted on (H7)
- [ ] T027 [US1] [US2] [US3] In `app/src/app/services/queries.py`, append `~hidden_by_filter()` to `list_postings`'s shared `where` list (so it reaches **both** the count and the page statement, or the pager lies), and to every figure in `totals` and both statements in `facets`. Add a `verdict: str | None = None` parameter to `list_postings` selecting the review bucket with `filter_rejected()` instead — **not** the complement of the hide rule, so a posting rejected after being shortlisted still appears (FR-017, SC-002, contract §2). Extend the `get_posting()` opt-out comment to cover the filter, citing ADR-0016 and FR-013/FR-016: this page is the route to a withheld posting and the place its grounds are shown
- [ ] T028 [US3] In `app/src/app/web/routes/postings.py`, thread `verdict` through the list route signature, `_render_list`'s `active` dict (so `page_url` keeps the bucket across pages), the template context, **and** the bulk-status route's hidden-input echo — miss the last and a bulk action from the bucket bounces the operator back to the unfiltered list
- [ ] T029 [US3] In `app/src/app/web/templates/postings.html`, add a "Filtered out" link beside the status filters (active-state styled like them), and a conditional column showing the grounds when that bucket is selected, following the `{% if status == 'rejected' %}` precedent already in the table — including its `colspan` on the empty state
- [ ] T030 [US3] In `app/src/app/web/templates/detail.html`, add a banner — shaped on the existing blacklist banner, which is why the detail-page opt-out is defensible — stating that the filter is withholding this posting and which criterion did it, and extend the existing `Filter` row to show both verdicts. Where the verdict re-evaluated under current criteria disagrees with the stored one, say *"criteria changed since the filter was last applied — re-apply to update"*: the one thing a stored reason column could not do (data-model.md)
- [ ] T031 [US1] [US2] [US3] Extend `app/tests/test_visibility.py` with the new predicates beside `not_suppressed()` (one module per seam file keeps both discoverable): the **keystone** — a posting rejected on experience grounds whose status is still `new` is invisible, the same posting once shortlisted is visible, a NULL-verdict posting is visible, a both-TRUE posting is visible; per-path two-sided tests over a corpus holding NULL × True × False verdicts crossed with all four statuses, asserting the rejected row absent **and** the admitted row present for `list_postings` (page and count), `totals` and `facets`; the partition test `|hidden| + |visible| == |all|` naming the deliberate overlap; and that a rejected posting's row still exists with its triage status intact — hiding is not deletion (FR-013, FR-014)
- [ ] T032 [US3] Add web-level tests to `app/tests/test_web_triage.py` (or `test_web.py`, matching where the list-view tests already live): the queue omitting a rejected untriaged posting, the bucket containing it, the bucket also containing a rejected-then-shortlisted posting, and the detail page remaining reachable with its banner
- [ ] T033 Extend the read-path inventory at `specs/002-employer-suppression-derived/contracts/read-path-inventory.md` **in place** with a second verdict column rather than cloning it — a second table is a second thing to forget (contract §2) — giving every existing query a filter verdict and restating the maintenance rule
- [ ] T034 **Gate 3** — `uv run pytest` green **with no pre-existing test amended except `test_settings.py`** (T024, whose partition genuinely moved). Any other pre-existing test needing a change means the predicate hides something SC-006 forbids: inspect the diff, not just the exit code. Then the quickstart's Gate 3 walkthrough by hand. Commit

**Checkpoint**: US1 and US2 are delivered end to end, and every withheld posting is
reachable and explained.

---

## Phase 4: The funnel becomes visible

**Purpose**: complete US3's observability (FR-015). Read-only additions over a
hiding rule that is already correct — they can reveal, never hide.

- [ ] T035 [US3] In `app/src/app/web/templates/runs.html`, add Passed and Rejected columns to the History table and move **both** colspans — the empty state's and the error row's. Render a structurally-zero pair (both counts zero while `deduplicated_count > 0`) as `—` rather than `0`: zero is a claim the filter rejected nothing, and the two historical runs predate the stage
- [ ] T036 [US3] In `app/src/app/__main__.py`, add passed/rejected columns to the `status` table (the weekly review surface, design §7.4) with the same `—` rule, and extend `run-all`'s echo with both counts
- [ ] T037 [P] [US3] Revise `Docs/design/reports-implementation-plan.md`'s instruction that `filter_passed_count` / `filter_rejected_count` must not be rendered as zero: they now have a writer, so the rule narrows to runs that predate the stage, which is what the `—` rendering expresses. Note that `scored_count` and `published_count` are still structurally zero and still bare in `runs.html`
- [ ] T038 **Gate 4** — `uv run python -m app status` and `/runs` both legible: the two historical runs read `—`, a filtered run reads its counts, and the error row still aligns. Commit

**Checkpoint**: the per-stage funnel the counts were designed to expose is no longer
flat.

---

## Phase 5: Record the decisions

**Purpose**: ADR-0015 exists because a previous reversal went unrecorded. Leaving
drift here would repeat precisely that failure, so this is a phase rather than an
afterthought.

- [ ] T039 Write `Docs/ADRs/0016-collect-stage-filter-verdicts.md` (next free number; bullet header style, as 0015 uses), recording with their rejected alternatives: the disjunction over contributing profiles and why `run.profile_id` is wrong (research R1), the min-wins merge (R2), the NULL/TRUE/FALSE semantics and why a NOT NULL default would break SC-006 (data-model.md), the `status == new` term in the hide rule (R4), the derived grounds instead of a reason column, and the `linkedin_fetch_description` coupling (R8). State the relationship to ADR-0007 §O3 — this implements D6's regex gate rather than settling O3, and makes O3's drop-rate measurement possible for the first time (R10) — and to ADR-0015, whose read-time-derivation invariant it extends to a second kind of exclusion
- [ ] T040 [P] Update `Docs/design/data-model.md`: the two new columns and the verdict tri-state in the ERD and §3.4; that `title_filter_passed` is written by the filter step rather than by stage 3; that the run counters are "verdict as of last application", not an audit trail; and correct §3.4's claim that `status` doubles as the suppression mechanism, which ADR-0015 already falsified and this feature's separation of verdict from status makes conspicuous
- [ ] T041 [P] Update `Docs/design/system-architecture.md` §5.3: the coarse title filter is now a prior step whose verdict the scoring stage consumes, with stage numbering unchanged (research R10). Add the seam obligation for the new predicate alongside the suppression one, and fix the stale "read models live in `app.web.queries`" line while in the file
- [ ] T042 [P] Update `Docs/development-guide.md` §6's CLI table and §9's "extending the pipeline" steps, and `CLAUDE.md`'s CLI list and architecture tree, for the `filter` subcommand and the `filters/` package. `CLAUDE.md`'s architecture block also still names `pipeline/run.py`, which is now `runner.py`
- [ ] T043 [P] Update `Docs/operations-guide.md`: the `filter` command in §3 and §10, the title criteria and the `linkedin_fetch_description` coupling in §6a, and how to recover a wrongly withheld posting (loosen the criteria, re-run `filter --all`; the triage status is intact). State the blast radius plainly — a profile that already records an experience value starts filtering on the first run
- [ ] T044 [P] Update `Docs/README.md`: the ADR index gains 0016, and the project tree gains `filters/`, `db/attribution.py` and `pipeline/filter_stage.py`
- [ ] T045 [P] [US3] Add a note to the title-pattern fields in `app/src/app/web/templates/settings.html` that they apply to the posting title only (D6, SRS FR-16) and that seniority filtering depends on `linkedin_fetch_description` staying on (research R8)
- [ ] T046 **Gate 5** — `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run pytest`, and a read-through of ADR-0016 against the quickstart's Gate 5 checklist. Commit

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 0** has no dependencies and can start immediately. It imports nothing and
  is imported by nothing.
- **Phase 1** depends on Phase 0 — the data revision imports `filters/levels.py`
  (T014 needs T002).
- **Phase 2** depends on Phase 1: the stage reads `postings.job_level` and writes
  both verdict columns.
- **Phase 3** depends on Phase 2 and **must not precede it** (ordering note 1).
- **Phase 4** depends on Phase 2 for the counts; it is independent of Phase 3 in code
  but is sequenced after it so the first visible funnel describes an enforced filter.
- **Phase 5** depends on everything, because documentation cannot be wrong about a
  mechanism that is not yet final.

### Within phases

- T002 and T003 are independent (different files); T004 needs both; T005 needs T004.
- T006 depends on T002; T007 on T003; T008 is independent of all of them.
- T010 and T011 touch the same file and are sequential; T012 needs T011; T013 needs
  T010; T014 needs T013 **and** T002.
- T017 is independent of T018 but needed by it; T019–T021 need T018; T022 and T024
  are independent of the stage.
- T026 must precede T027; T028 before T029; T031 needs T026 and T027; T032 needs
  T028–T030.

### Parallel opportunities

```bash
# Phase 0 — two pure modules and the docstring fix, three files, no shared state
Task: "T003 filters/titles.py"
Task: "T008 FR-020 docstring correction in db/models.py"

# Phase 0 tests, once their modules exist
Task: "T006 tests/test_filter_levels.py"
Task: "T007 tests/test_filter_titles.py"

# Phase 5 — six documents, no code
Task: "T040 Docs/design/data-model.md"
Task: "T041 Docs/design/system-architecture.md"
Task: "T042 Docs/development-guide.md + CLAUDE.md"
Task: "T043 Docs/operations-guide.md"
Task: "T044 Docs/README.md"
Task: "T045 web/templates/settings.html"
```

Phases 1–3 offer little genuine parallelism: they are a short chain of files that
read each other, and the gates between them are the point.

---

## Implementation strategy

### The smallest honest increment

Phases 0 → 1 → 2 is a coherent, shippable increment on its own: the criteria exist,
the board label is promoted and backfilled, verdicts and the funnel are recorded, and
**nothing is hidden**. It delivers SC-003 and the measurement SC-001 needs, and it is
where an operator should sit for a day with `--dry-run` before going further. That is
the MVP, and it is deliberately not "US1 end to end" — hiding postings is the part
that deserves to be entered on purpose.

### Then

Phase 3 delivers US1 and US2 as the operator experiences them, together with US3's
recovery surfaces. Phase 4 completes US3. Phase 5 records why any of it is shaped the
way it is.

### Notes

- `[P]` tasks touch different files and depend on nothing incomplete.
- Commit at each gate, not at each task: the gates are the boundaries that carry the
  safety property.
- Every gate that says "no pre-existing test amended" is a statement about the diff.
  A green suite with an amended test is a failed gate.
- Fixtures for seniority labels and titles are captured strings marked `# OBSERVED`,
  per the suite's convention: they are the reason the rules exist and must not be
  tidied.
