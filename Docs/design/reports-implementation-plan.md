# Reports — Implementation Plan

| | |
|---|---|
| **Author** | Mohammed |
| **Date** | 27 July 2026 |
| **Status** | Proposal |
| **Scope governed by** | [ADR-0008](../ADRs/0008-report-system-scope.md) |
| **Related** | [Design record](../job-discovery-pipeline-design.md) §4.3, §7.3.1, §7.4, D11, D13; [Data model](data-model.md); [Refactor plan](refactor-plan.md) §7.1 |

---

## 1. Scope

Six reports, admitted by the criteria in ADR-0008 §1: every input populated
today, no new collection, and a statable sampling bias.

| ID | Report | Answers |
|---|---|---|
| R1 | Employer hiring activity | Who is actually hiring, and who hires continuously rather than once |
| R2 | Posting longevity and repost detection | How long roles stay live, and which look like ghost postings |
| R3 | Source coverage and overlap | What each board contributes, and which surfaces a role first |
| R4 | Role demand by normalised title | Which roles appear most, and how that moves week to week |
| R5 | Collection health and decay | Whether the pipeline is quietly returning less than it did |
| R6 | Work arrangement mix | The remote, contract and country split of what is collected |

Everything considered and not admitted — skills demand, employer firmographics,
the triage funnel, score distribution, and salary benchmarking — is recorded in
ADR-0008 §3 and §4 with the condition that unblocks each. This plan does not
restate them.

## 2. Prerequisite — `last_seen_at` split into two columns

R2 reads `last_seen_at` as "when a board last surfaced this posting." It did
not mean that: `onupdate=func.now()` advanced it on **every** UPDATE against
the row — a triage transition, a description backfill, and (once stage 3
lands) a score write — each inflating the apparent lifetime of a posting no
board had re-surfaced. The docstring above `status_changed_at` already names
the adjacent form of this problem; it is why that column was split out of
this one already, once.

**Resolved at the schema level, not by a runtime filter.** An initial pass
removed only the `onupdate`, then added a heuristic in R2 to guess which
historical rows the now-corrected column had contaminated before the fix
landed. That heuristic worked but was solving a problem worth removing
instead: **[ADR-0012](../ADRs/0012-retrieval-date-column-split.md)** splits
the column into `updated_at` (the renamed original — generic "row last
modified" bookkeeping, `onupdate` restored, same meaning
`SearchProfile.updated_at` / `AppSetting.updated_at` already carry) and
`last_retrieved_at` (new, written only inside `observe()`, no `onupdate`,
no second writer to be confused with). R2 reads `last_retrieved_at`.

**A migration is required** — `cb39b32a6843` — since this is a real rename
plus an added column, not a model-only edit. It backfills every existing
row's `last_retrieved_at` from that row's own `first_seen_at`: a real,
already-recorded fact, not a migration-time guess. See ADR-0012 for why that
backfill choice, and why the two now-obsolete alternatives (a blanket `now()`
for every row, or leaving the column `NULL`) were rejected.

ADR-0009, which the heuristic above came from, is retained as a record of the
alternatives it compared — that comparison is still the right reference if a
future column is ever tempted to carry two meanings again — but its Decision
is superseded by ADR-0012.

## 3. Placement

Following refactor-plan §7.1, one module per resource:

| Path | Contents |
|---|---|
| `src/app/services/reports.py` | Aggregation. Dataclass per report, function per report. |
| `src/app/web/routes/reports.py` | `/reports` index and `/reports/{slug}` detail. |
| `src/app/web/templates/reports/` | `index.html`, one template per report, `_table.html` partial. |
| `tests/test_reports.py` | Service-level, no web client. |
| `tests/test_web_reports.py` | Route-level. |

`services/queries.py` is documented as "read models for the triage interface"
and is not extended: reports are a distinct concern with a different lifetime,
and folding six aggregations into it would obscure both. The two shared
helpers it already owns — `_has_source()` and `known_sites()` — are imported
rather than duplicated, and `_has_source` is promoted to `has_source` since it
gains a second caller.

`templates/reports/` is the first template subdirectory. Seven more files in
the flat directory would leave the triage templates hard to find; Jinja
resolves subdirectories without configuration.

**Split threshold.** If `reports.py` passes roughly 400 lines it becomes a
`reports/` package with a module per report. Not before — this project has
twice rejected structural elaboration ahead of the need (refactor-plan §1, §9),
and six aggregation functions do not justify a package.

## 4. Decisions that apply to every report

### 4.1 Computed per request; no caching, no summary tables

NFR-1 bounds the system at under a hundred postings a day. Every aggregation
here is a single GROUP BY or one pass over a few thousand rows. Materialised
summaries, a reporting schema, or a cache would each cost more in staleness
bugs than they save in milliseconds.

Revisit only if `postings` passes roughly 100,000 rows or a report exceeds
about a second — neither is reachable on the current collection rate within the
project's expected life.

### 4.2 JSON is aggregated in Python, not in SQL

`known_sites()` already records why JSON keys cannot be enumerated portably
across JSONB and SQLite's JSON, and `_has_source()` exists because the naive
`[key]` comparator silently matches everything under SQLite —
`JSON_QUOTE(NULL)` returns the string `'null'`, which satisfies `IS NOT NULL`.

R3 needs nested values (`sources[site]["first_seen"]`), which is worse than the
key test that trap applies to. Rather than extend the dialect split, R3 selects
`(id, sources)` and aggregates in Python. At this scale the cost is negligible
and the correctness risk drops to zero. The site vocabulary comes from
`known_sites()`, never from enumerating the JSON keys.

### 4.3 Every report displays its own bias, and a test asserts it

ADR-0008 criterion 3 admits these reports on the condition that their sampling
bias is stated with the output. A caveat that lives only in a design document
is not a control — it is absent at the moment of misreading.

Each report template renders a one-sentence caveat, and `test_web_reports.py`
asserts its presence. Without the test the caveat will be dropped in a future
layout change and nobody will notice.

The caveat common to R1, R2, R3, R4 and R6, from which each specialises:

> These figures describe the postings this system collected — two boards,
> matching your search profiles, within the `hours_old` window. They are not a
> measurement of the job market.

## 5. Report specifications

### R1 — Employer hiring activity

**Computes.** Grouped by employer: posting count, distinct `normalised_title`
count, earliest and latest `first_seen_at`, days since the most recent new
posting, and a status breakdown.

Because the fingerprint already collapses one real-world role to one row,
posting count *is* distinct-role count. The second metric is what makes the
report useful: an employer with twelve postings across three titles is
repeatedly filling the same three roles, which is a different signal from one
with twelve distinct titles. Present them as volume and breadth, adjacent.

**Query.** One GROUP BY over `postings` joined to `employers`; `employer_id`
is indexed.

**Suppressed employers** are excluded by default, with a toggle to include —
their postings are auto-rejected, but an excluded employer posting heavily is
worth being able to see.

**Caveat.** Counts are of roles matching your profiles, not the employer's
total hiring.

### R2 — Posting longevity and repost detection

**Depends on §2's migration having run first.**

**Computes.** Live span (`last_retrieved_at - first_seen_at`), collection lag
(`first_seen_at - date_posted`), the distribution of live span in buckets, and
a long-lived tail — postings still being re-observed well after first sight,
which is the ghost-posting candidate list. `last_retrieved_at` is written only
by `observe()` (ADR-0012), so no contamination-detection filter is needed —
every value the column holds means what R2 needs it to mean, including the
migration's backfilled rows, which read as "not yet re-observed since the
column was added" rather than as a value requiring suspicion. Computed in
Python over the fetched timestamp columns, not in dialect-branched SQL — see
[ADR-0010](../ADRs/0010-r2-span-computation-strategy.md) for why that is the
right call at this scale and what would change it.

**Three caveats, all mandatory.** This report is the easiest of the six to
misread:

1. A span of zero means *seen in a single run*, not *live for zero days*. Span
   resolution is bounded below by run cadence.
2. `hours_old` (default 72) truncates from above: once a posting ages out of
   the collection window it stops being re-observed regardless of whether it is
   still live. Every span is a lower bound.
3. `date_posted` is board-reported and is captured once, at creation —
   `observe()` deliberately does not update it — so collection lag is measured
   against first sight, not against any later repost.

**Deliberately excluded from v1: an observation count.** The number of times a
posting was re-observed would strengthen this report considerably, and is not
stored. Adding `observation_count` to `postings`, incremented in `observe()`,
is a small additive migration. It is excluded because historical rows would
start at 1 and understate for months, making early output misleading in exactly
the way §4.3 exists to prevent. Recorded here so the option is deliberate; add
it when a months-long forward series is worth more than the current backlog.

Detecting reposts through `date_posted` drift is likewise possible only via
`raw_postings`, since the posting keeps the first value observed. Left out of
v1 for the same reason.

### R3 — Source coverage and overlap

**Computes.** Per board: how many postings carry it in `sources`. Across
boards: Indeed-only, LinkedIn-only, and both. Per posting: which board recorded
the earliest `sources[site]["first_seen"]`.

**Ties are meaningful and must not be broken.** Every site processed within one
run shares a single `now` (`normalise_stage.py` computes it once per run), so
two boards surfacing a role in the same run record identical timestamps. That
is a genuine tie — "both boards had it at that collection" — not a sorting
problem. Report ties as a third category, never resolve them arbitrarily.

**Caveat, specialised and important.** A role's absence from a board may mean
the board did not have it, *or* that no search profile queried that board.
`SearchProfile.sites` is per-profile, so coverage is confounded by
configuration. Display the report alongside which sites were actually queried
in the period, from `Run.counts_by_site`.

### R4 — Role demand by normalised title

**Computes.** Count by `normalised_title`, ranked, with a per-period series
(weekly buckets). Use `date_posted` where present and `first_seen_at`
otherwise, and state on the report which basis each row used rather than
silently mixing them.

**Caveats.** Two, both load-bearing:

1. Titles are normalised for *fingerprinting*, not for reporting.
   `normalise/title.py` exists to make duplicate detection work; it may merge
   titles a demand analysis would separate, or vice versa. Read the ranking as
   approximate.
2. A title can only appear if a search profile's `term` surfaced it. This
   measures demand within your search scope, and is silent about everything
   outside it.

### R5 — Collection health and decay

**Extends what exists.** `queries.source_health()` already provides the §7.4
per-site trend. This adds: per-stage funnel drop-off
(`collected_count` → `deduplicated_count`), run duration
(`finished_at - started_at`), success/failure rate, and profile attribution via
`runs.profile_id`.

**A decay flag** compares the latest run's per-site count against the trailing
median of recent runs. §7.4's stated failure mode is a run that succeeds while
returning progressively less, which no single run's status reveals.

**Mark the stage-3 counters as not-yet-applicable, do not display them as
zero.** `filter_passed_count`, `filter_rejected_count`, `scored_count` and
`published_count` are structurally zero because the stages that write them do
not exist. Rendering them as zeros in a health view manufactures a false alarm
on a working pipeline.

### R6 — Work arrangement mix

**Computes.** Cross-tab of `is_remote` × `job_type` × `country_code`, with the
unresolved-country bucket shown explicitly rather than dropped — `parse_country`
returns None rather than guessing, and `queries.COUNTRY_UNKNOWN` already exists
for exactly this.

**`job_type` needs no normaliser.** This section originally predicted spelling
and case variants (`fulltime` vs `Full-time`) and made enumerating production
data a prerequisite. That prediction was checked against the `python-jobspy`
source rather than against a database, and was wrong: JobSpy collapses every
board's locale-specific string onto a closed ten-member vocabulary
(`fulltime`, `parttime`, `contract`, `temporary`, `internship`, `perdiem`,
`nights`, `other`, `summer`, `volunteer`) before the row is ever built, so what
lands in `Posting.job_type` is already canonical. The only real variation is a
comma-joined combination string for a posting tagged more than one type, and
`None` when a board declared none. See
[ADR-0011](../ADRs/0011-job-type-taxonomy-for-arrangement-mix.md) for the
evidence and for why no code under `normalise/` is warranted.

**Caveats.** `is_remote` is partly a *search parameter* — `SearchSpec.is_remote`
determines what gets requested — so the remote share reflects profile
configuration as much as market conditions. Country is close to constant for
Egypt-focused profiles, and city is deliberately not comparable across boards
(§7.3.1), so no city breakdown is offered.

## 6. Phased task list

Format follows `specs/001-ui-self-service/tasks.md`: `[ID] [P?] Description`,
where **[P]** marks tasks that touch different files and may run in parallel.
Paths are relative to `app/`.

### Phase 0 — Prerequisite (blocks R2 only)

- [x] T001 Split `Posting.last_seen_at` into `updated_at` (renamed, `onupdate` restored) and `last_retrieved_at` (new, written only by `observe()`) in `src/app/db/models.py`; migration `cb39b32a6843` renames the column, adds the new one, and backfills it from `first_seen_at` (ADR-0012).
- [x] T002 `tests/test_models.py`: a status transition does **not** advance `last_retrieved_at` but **does** advance `updated_at`; `observe()` advances `last_retrieved_at`. Both directions are tested — a filter that silently stopped writing either column would pass a one-sided check.

**Checkpoint**: R2 can proceed. Phases 1 and 2 do not depend on this.

### Phase 1 — Foundation

- [ ] T003 Create `src/app/services/reports.py` with the module docstring and shared period-window helper.
- [ ] T004 Promote `queries._has_source` to `queries.has_source`; update its existing caller in `list_postings`.
- [ ] T005 [P] Create `src/app/web/routes/reports.py` with a `/reports` index route; register the router in `src/app/web/app.py`.
- [ ] T006 [P] Create `src/app/web/templates/reports/index.html` and `_table.html`, reusing the existing `.panel` / `.cards` styles from `base.html`.
- [ ] T007 [P] Add a `Reports` nav entry to `src/app/web/templates/base.html` between `Postings` and `Runs`, with the `active` flag.
- [ ] T008 [P] Create `tests/test_reports.py` and `tests/test_web_reports.py` with the session fixtures used by `tests/test_web.py`.

**Checkpoint**: `/reports` renders and is reachable; no report content yet.

### Phase 2 — MVP (R1, R3)

Both are pure aggregation over fully populated fields and share no code, so
they can be built in parallel.

- [ ] T009 [P] `services/reports.py`: `employer_activity()` → dataclass with volume, breadth, span, days-quiet, status breakdown (§5 R1).
- [ ] T010 [P] `services/reports.py`: `source_overlap()` → per-board counts, the three-way overlap, and first-surfacer **with ties as a category** (§5 R3).
- [ ] T011 `tests/test_reports.py`: R1 — breadth and volume differ for an employer with repeated titles; suppressed employers excluded by default.
- [ ] T012 `tests/test_reports.py`: R3 — a posting surfaced by both boards in one run reports a tie, not a winner. This is the assertion most likely to be got wrong.
- [ ] T013 [P] `templates/reports/employers.html` + route, including the R1 caveat.
- [ ] T014 [P] `templates/reports/sources.html` + route, including the R3 configuration caveat and the queried-sites context from `Run.counts_by_site`.
- [ ] T015 `tests/test_web_reports.py`: both pages render, and both caveat strings are present (§4.3).

**Checkpoint**: two reports usable end to end.

### Phase 3 — R2 (requires Phase 0)

- [ ] T016 `services/reports.py`: `posting_longevity()` → span buckets, collection lag, long-lived tail over `last_retrieved_at`, computed in Python per ADR-0010. No exclusion filter needed (ADR-0012) — every row's `last_retrieved_at` is trustworthy by construction.
- [ ] T017 `tests/test_reports.py`: a single-observation posting reports span zero and is **not** counted as short-lived; a posting triaged one or more times still reports the span its `last_retrieved_at` actually holds — triage history must not affect the number at all, which is the whole point of ADR-0012 over ADR-0009's runtime filter.
- [ ] T018 `templates/reports/longevity.html` + route, rendering all three §5 R2 caveats.
- [ ] T019 `tests/test_web_reports.py`: the three caveats render.

### Phase 4 — R4, R6

- [ ] T020 [P] `tests/test_reports.py`: pin `python-jobspy`'s `JobType` enum to the ten expected `value[0]` tokens (ADR-0011 drift guard) — fails loudly if a future dependency bump renames the taxonomy underneath the report.
- [ ] T021 [P] `services/reports.py`: `title_demand()` with weekly buckets and an explicit per-row date basis (§5 R4).
- [ ] T022 [P] `services/reports.py`: `arrangement_mix()` treating `job_type` as the closed vocabulary confirmed in ADR-0011 (no normaliser); includes the `COUNTRY_UNKNOWN` bucket (§5 R6).
- [ ] T023 [P] `templates/reports/demand.html` + route + caveats.
- [ ] T024 [P] `templates/reports/arrangement.html` + route + caveats.
- [ ] T025 `tests/test_reports.py` + `tests/test_web_reports.py` for both.

### Phase 5 — R5

- [ ] T026 `services/reports.py`: `collection_health()` — funnel drop-off, duration, success rate, profile attribution, decay flag against trailing median (§5 R5).
- [ ] T027 `tests/test_reports.py`: stage-3 counters are reported as not-applicable, **not** as zero, while no scoring stage exists.
- [ ] T028 `templates/reports/health.html` + route; link it from `/runs` and from the dashboard.
- [ ] T029 Update `Docs/README.md` (project structure, document table) and `Docs/operations-guide.md` (how to read the decay flag).

## 7. Testing

The suite convention is service-level tests without a web client, plus
route-level tests for rendering — `services/queries.py` is documented as
existing partly so the querying is testable that way, and reports follow it.

Three assertions matter more than coverage percentage, because each guards a
conclusion that would otherwise be silently wrong:

1. **T002** — a status change must not move `last_retrieved_at`, and must still move `updated_at`. Guards the whole of R2, in both directions.
2. **T012** — same-run boards tie. Guards R3's first-surfacer from becoming an artefact of dict ordering.
3. **T015 / T019** — caveat text renders. Guards ADR-0008's admission condition from being lost in a layout change.

Fixtures build postings directly through `Posting.create` and `observe()` rather
than through the collector, so the tests exercise the same provenance and
timestamp paths the pipeline uses without needing JobSpy mocks.

## 8. Out of scope

- Any report deferred or rejected in ADR-0008 §3–§4.
- Export in any format. If it is wanted later, CSV from the same dataclasses is
  a small addition; it is not assumed here.
- Charting libraries. `base.html` loads only HTMX and has no build step; the
  existing tables and CSS bars cover everything specified above. A charting
  dependency would be the first front-end build decision this project has had
  to make and should not be smuggled in through a report.
- Scheduled or emailed report delivery. The operator opens the interface daily
  already (design §2.1 criterion 2); a second delivery channel adds a habit the
  design explicitly set out to avoid.
