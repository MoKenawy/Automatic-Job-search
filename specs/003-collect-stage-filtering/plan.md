# Implementation Plan: Collect-stage relevance and experience filtering

**Branch**: `003-collect-stage-filtering` | **Date**: 16 November 2026 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-collect-stage-filtering/spec.md`

**Implements**: design D6 (coarse pre-filter on title), SRS FR-16, and the standing
intent of `SearchProfile.experience` · **Precedent**:
[ADR-0015](../../Docs/ADRs/0015-employer-level-suppression.md) · **Records**:
ADR-0016 *(written in Phase 5)*

## Summary

Give the pipeline its first rejection, and make it reversible.

A new pure package `app/src/app/filters/` decides two things about a posting — does
its title satisfy the operator's include/exclude rules (D6), and is its seniority at
or below what some profile asked for — and a new stage
`app/src/app/pipeline/filter_stage.py` records those two verdicts on the posting and
their totals on the run. The board's seniority label, until now kept only inside the
verbatim payload, is promoted to `postings.job_level` so the filter's primary input
is typed and inspectable.

Nothing is deleted and no triage state is touched. A rejected posting is withheld
**at read time** through one shared predicate, exactly as a blacklisted employer's
postings are (ADR-0015), so loosening the criteria and re-running the stage brings
the posting back with its history intact.

Three properties carry the design, and each is a test rather than an intention:

- **Unknown admits.** Absent, empty and `not applicable` are one thing — absence of
  evidence — and the verdict column stays NULL wherever a criterion did not apply.
- **The verdict is a pure function of stored state**, not of run order. It therefore
  converges, and re-applying it to unchanged data issues zero UPDATE statements.
- **Hiding is not rejection.** A posting the operator has shortlisted or applied to
  is never withdrawn from view by a later tightening of the criteria.

Work is ordered so that verdicts are written and measurable **before** anything is
capable of hiding, and so that the commit which first hides a posting is the same
commit that ships the route to it.

## Technical Context

**Language/Version**: Python 3.12 (pinned via `app/.python-version`)

**Primary Dependencies**: SQLAlchemy 2.x (ORM + Core `select`), FastAPI + Jinja2
(triage UI), Typer (CLI), Alembic (migrations), APScheduler. `re` from the standard
library is the whole of the title-matching machinery — D6 says regex, and SRS FR-16
confines it to the title.

**Storage**: PostgreSQL 16 in production (Docker Compose); in-memory SQLite with
`StaticPool` under test. Models declare `JSON` variants of `JSONB` columns so the
suite runs without Docker. Both new columns are plain scalars — `String(64)` and
`Boolean` — so nothing in this feature needs a dialect split of the kind
`queries._has_source` required.

**Testing**: pytest. Full suite runs with no external services. SC-002 sets the
sizing rule: the body of tests proving nothing is wrongly rejected must be **at
least as large** as the body proving rejection works — the suite's governing
asymmetry (`CLAUDE.md`), restated for a filter.

**Target Platform**: single local machine (Windows 11 host, Postgres in Docker); no
data leaves the machine.

**Project Type**: single project — Typer CLI plus a local FastAPI triage interface
over a shared SQLAlchemy model layer.

**Performance Goals**: SC-004 — re-applying the criteria to a thousand postings
completes within a minute and contacts no board. The stage is a batch read, a pure
evaluation per posting and a guarded write, so the cost is one query plus one
`re.search` per posting per pattern. The live corpus is 52 postings.

**Constraints**: dependency direction is load-bearing and enforced by review —
`pipeline/` must not import `services/`; `filters/` (like `normalise/` and
`collect/`) holds no database knowledge; `web/` never writes pipeline data; nothing
outside `config.py` reads `os.environ`. The read-time predicate must compile
identically under SQLite and PostgreSQL, and must be NULL-safe: see research R6.

**Scale/Scope**: 1 new package (3 modules), 2 new modules elsewhere
(`db/attribution.py`, `pipeline/filter_stage.py`) plus 2 Alembic revisions, ~11
existing source files amended, 3 new test modules plus 2 amended, 1 new ADR and 7
documents corrected.

**Measured baseline (16 November 2026, against the live database)**: 60 raw rows
across 2 runs, 52 postings, 3 search profiles. The spec's figures (32 runs, 1,092
rows, a "Backend Developer" profile recording `fresh`) describe an earlier state of
the database and are not reproducible here; see research R9. Field coverage, which
is what the design actually depends on, reproduces exactly:

| payload field | LinkedIn | Indeed | overall |
|---|---|---|---|
| `job_level` | 40/40 = 100% | 0/20 = 0% | 40/60 = 67% |
| `company_industry` | 40/40 = 100% | 0/20 = 0% | 40/60 = 67% |
| `job_function`, `listing_type`, `skills`, `experience_range` | 0% | 0% | 0% |

Observed `job_level` vocabulary, lowercased by the collector:
`mid-senior level` (22), *empty* (20), `not applicable` (8), `entry level` (7),
`associate` (2), `director` (1).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status: not operative.** `.specify/memory/constitution.md` is the unmodified Spec
Kit template — every principle is still a `[PRINCIPLE_N_NAME]` placeholder. There
are no ratified gates to evaluate against, so this check cannot pass or fail on its
own terms and is not treated as a blocker. This is the same verdict
[002's plan](../002-employer-suppression-derived/plan.md) recorded, reached the same
way.

In its place the plan is gated against the project's written, enforced constraints,
all three from `CLAUDE.md`:

| Constraint | Applies how | Verdict |
|---|---|---|
| **Dependency direction is strict and load-bearing** — `pipeline/` must not import `services/`; `normalise/` and `collect/` hold no database knowledge | The filter's criteria logic must be testable without infrastructure, and the stage needs a posting-to-profile traversal whose only existing implementation is in `services/reports.py` | **Pass** — the criteria live in a pure `filters/` package with no DB import; the traversal is re-sited in `db/attribution.py`, which `pipeline/` may import. Same reasoning that put `not_suppressed()` in `db/` (002 research R1), and the reason is the decision, not a convenience |
| **Assert non-merging at least as hard as merging** — a false merge conceals a posting | Restated for this feature, and already restated by the spec itself as SC-002: a false *rejection* conceals a posting, and unlike a false merge it cannot be found by looking harder | **Pass** — every criterion fails open (research R2); the admission body of tests is sized against the rejection body; the Phase 3 exit gate is that **no pre-existing test needs amending** |
| **Comments cite the decision they implement** (`design §7.3`, `D12`, `ADR-0004`) | Three places in this feature will read as arbitrary to a later reader: `.is_(False)` instead of `== False`, the `status == new` term inside the hide rule, and `merge_job_level`'s lowering-only merge where its neighbours fill gaps | **Pass** — each carries its reason at the definition site, and Phase 5 makes ADR-0016 a deliverable rather than a courtesy |

*Post-Phase 1 re-check*: unchanged. The design adds one pure package and two `db/`
modules, introduces no import in the prohibited direction, and adds no entry to
Complexity Tracking. The one structural novelty — a second predicate in
`db/visibility.py` — is an addition to an existing seam rather than a new one, and
[contracts/filter-seam.md](contracts/filter-seam.md) extends 002's read-path
inventory in place rather than starting a second table.

## Project Structure

### Documentation (this feature)

```text
specs/003-collect-stage-filtering/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output — the nine decisions and what was rejected
├── data-model.md        # Phase 1 output — what each column means, and who writes it
├── quickstart.md        # Phase 1 output — how to prove it works, gate by gate
├── contracts/
│   └── filter-seam.md   # The internal contract: the CLI surface, the predicate,
│                        # and the read-path obligation
├── checklists/
│   └── requirements.md  # Spec quality validation (closed out, iteration 2)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/src/app/
├── config.py                      # untouched — title patterns already present (D6)
├── __main__.py                    # MODIFY — `filter` command; counts in `status`, `run-all`
├── filters/                       # ADD — the pure core, no database knowledge
│   ├── __init__.py                #       public re-exports, as normalise/ does
│   ├── levels.py                  #       the ordered scale, the vocabularies, the fallback
│   ├── titles.py                  #       include/exclude compilation, empty means disabled
│   └── verdict.py                 #       Criteria + Verdict value objects, evaluate()
├── db/
│   ├── models.py                  # MODIFY — postings.job_level, experience_filter_passed,
│   │                              #          merge_job_level(); FR-020 docstring correction
│   ├── visibility.py              # MODIFY — filter_rejected(), hidden_by_filter()
│   └── attribution.py             # ADD — posting to run to profile traversal, one query
├── pipeline/
│   ├── __init__.py                # MODIFY — export run_filter
│   ├── filter_stage.py            # ADD — the stage: evaluate, guard, write, count
│   ├── normalise_stage.py         # MODIFY — promote job_level on create and on observe
│   └── runner.py                  # MODIFY — call the stage; counts in the completion log
├── services/
│   ├── queries.py                 # MODIFY — adopt the seam; the "filtered out" bucket
│   └── settings.py                # MODIFY — title keys PENDING to CONSUMED; regex validation
└── web/
    ├── routes/postings.py         # MODIFY — thread `verdict` through list, pager, bulk echo
    └── templates/
        ├── postings.html          # MODIFY — the bucket link, and its column
        ├── detail.html            # MODIFY — the withheld banner and the grounds
        ├── runs.html              # MODIFY — Passed / Rejected columns, colspans
        └── settings.html          # MODIFY — note the linkedin_fetch_description coupling

app/migrations/versions/
├── <ddl>_filter_verdicts_and_job_level.py       # ADD — two nullable columns
└── <data>_backfill_job_level.py                 # ADD — min-wins backfill from payloads

app/tests/
├── test_filter_levels.py          # ADD — the scale, the vocabularies, the fallback
├── test_filter_titles.py          # ADD — compilation, empty means disabled, malformed
├── test_filter_stage.py           # ADD — the stage: counts, convergence, no-op re-apply
├── test_visibility.py             # MODIFY — the new predicates beside not_suppressed()
└── test_settings.py               # MODIFY — the consumption partition moves
```

**Structure Decision**: the existing single-project layout is unchanged. The feature
adds one pure package, mirroring `normalise/`, and follows
`Docs/development-guide.md` §9's five-step recipe for extending the pipeline
verbatim: pure logic in its own package with its own tests, a persistence function
in `pipeline/` shaped like `normalise_stage.py`, wired into `__main__.py` and
`run-all`, with `runs` counts updated so the stage is observable.

## Implementation phases

The invariant, stated the way 002 stated its own:

> **There is no commit at which a posting the operator should see is hidden, and no
> commit at which a posting is hidden without a route to it.**

Every phase boundary fails open. An absent or partial verdict is NULL, NULL is
admitted, so a crash in the middle of the stage under-filters rather than
over-filters.

### Phase 0 — the pure core, imported by nothing

`filters/levels.py`, `filters/titles.py`, `filters/verdict.py` and their two test
modules. No column, no query, no stage; nothing in the running system imports the
package yet. The FR-020 docstring correction at `db/models.py` lands here too, since
it is documentation and has no behaviour.

*Exit: suite green with **no existing test amended**. Behaviour unchanged.*

### Phase 1 — schema and data, but no verdicts

Two Alembic revisions (research R7): a DDL revision adding `postings.job_level` and
`postings.experience_filter_passed`, both nullable, then a data revision backfilling
`job_level` from the contributing payloads using the same min-wins rule the stage
uses — imported from `filters/levels.py`, not restated. Then `Posting.create` and
`Posting.observe` promote the label at stage 2.

`job_level` is *data*, not a verdict. Both verdict columns are NULL on every row and
read by nothing, so no posting can be hidden by anything in this commit.

*Exit: `upgrade head` → `downgrade -1` → `upgrade head` clean against PostgreSQL.
`job_level` coverage on the real corpus measured and recorded.*

### Phase 2 — the stage, write-only

`db/attribution.py`, `pipeline/filter_stage.py`, the `filter` command with
`--run-id` / `--all` / `--dry-run`, the wiring into `runner._run()` — which covers
the CLI, the scheduler and the web "run now" in one place — the run counters, and
the two settings keys moving from `PENDING_KEYS` to `CONSUMED_KEYS` with regex
validation at the form.

**Verdicts are recorded but enforced nowhere.** This is the mirror of 002's Phase 1
("add the seam while the old mechanism still stands"): the only phase in which the
filter can be run against the real corpus, and SC-001 checked, at zero risk of
hiding anything. `--dry-run` exists for exactly this moment.

*Exit: `filter --all --dry-run` reports sane numbers on live data;
`filter_passed_count + filter_rejected_count == deduplicated_count` for every run
the stage touched; a second `filter --all` issues zero UPDATEs.*

### Phase 3 — enforcement and recovery, in one commit

`filter_rejected()` and `hidden_by_filter()` in `db/visibility.py`; adoption in
`list_postings` (page **and** count), `totals` and `facets`; the `get_posting()`
opt-out comment; and — in the same commit — the "Filtered out" bucket and the
`detail.html` banner that says which criterion withheld the posting.

Splitting the surfaces out into a later phase would leave commits at which postings
are hidden with nothing to explain where they went. 002's detail opt-out is only
defensible because the blacklist banner and lift control were already on that page;
this reproduces that structure rather than assuming it.

*Exit: the entire pre-existing suite passes with no amendment except
`test_settings.py`. Any other test needing a change means the predicate hides
something SC-006 forbids.*

### Phase 4 — the funnel becomes visible

`runs.html` gains Passed and Rejected columns (and both colspans move); `status` and
`run-all` print the counts; `_run()`'s result dict carries them. Read-only additions
over a hiding rule that is already correct: they can reveal, never hide.

### Phase 5 — record the decisions

ADR-0016, then the documents that now describe something false: `db/models.py`'s
coverage claim (already corrected in Phase 0), `data-model.md`,
`system-architecture.md` §5.3, `development-guide.md` §6 and §9, `CLAUDE.md`'s CLI
list and architecture tree, `operations-guide.md` §6a and §10,
`reports-implementation-plan.md`'s "do not render the counters as zero" instruction,
and `Docs/README.md`'s tree.

ADR-0015 exists because a previous reversal went unrecorded. Leaving drift here
would repeat that failure, so this is a phase rather than an afterthought.

## Risks

| Risk | Mitigation |
|---|---|
| **Three-valued logic inverts the predicate** and hides the entire corpus while an absence-only suite stays green — the catastrophe 002's contract names explicitly | `.is_(False)`, never `== False` or `~(… == True)`; the hazard stated at the definition site; two-sided tests over a corpus holding NULL, True **and** False verdicts crossed with all four statuses (research R6) |
| **An empty exclude pattern matches everything**, so the shipped default rejects the whole corpus | Empty or whitespace means *criterion disabled*, decided **before** compiling, with a test named for SC-006 (research R3). Phase 2's write-only boundary means even this bug could not hide a posting before Phase 3 |
| **The verdict depends on which run last touched the posting** — a posting surfaced by two profiles with opposite requirements would flip, breaking FR-010 and SC-007 | The experience verdict is a disjunction over every profile that has surfaced the posting, which is order-independent by construction (research R1). Tested by filtering the same corpus in both orders |
| **`updated_at` churn** makes a converged re-apply observably non-identical (SC-007 says byte-identical) | Difference-guarded writes; a converged `filter --all` issues zero UPDATEs, which is checkable by diffing a table dump (research R5) |
| **A read path forgets the predicate** — and there are now two obligations where there was one | 002's read-path inventory is **extended in place** with a second verdict column rather than cloned: a second table is a second thing to forget. Opt-outs carry comments; the seam's docstring states the obligation where a developer writing a new query will look |
| **The bucket and the hide rule drift**, so "Filtered out" is not the set missing from the queue | They are deliberately different sets (research R4). A partition test over every (verdict × status) pair asserts `hidden + visible == all` and names the overlap |
| **Installation is not behaviour-neutral on this machine.** SC-006 holds under "no criteria set"; the `AI Engineer` profile already stores `entry level`, and FR-002 deliberately makes that effective | Blast radius stated here rather than discovered: the first filtered run withholds mid-senior and director postings for that profile. `--dry-run` and the Phase 2/3 boundary are the mitigation, and `operations-guide.md` says so |
| **`linkedin_fetch_description = false` silently zeroes the filter's primary input** — the collector only populates `job_level` when descriptions are fetched | ADR-0016 records the coupling; the `/settings` field carries a note. It fails open, which is the right direction, but silently, which is not (research R8) |
| **The title-derived fallback is the chief source of false rejection**, and the repository holds no seniority vocabulary to build it from | Conservative by construction: word-boundary matching, and conflicting markers yield "unknown" rather than a guess. Fixtures are `OBSERVED` strings. The board label always wins where present, and min-wins runs with the asymmetry (research R2) |
| **The backfill and the stage disagree**, so installation and the first re-apply differ | The data revision imports `filters/levels.py` — the precedent set by `b2c3d4e5f6a7`, which imports `build_fingerprint` rather than restating it. One test asserts the backfilled value equals a fresh evaluation |
| **Historical runs read as a dead filter** — two runs showing `0 / 0` look like a filter that rejects everything | Phase 4 decides the "—" rule for counts that are structurally zero and revises `reports-implementation-plan.md` to match. A run whose whole haul is rejected logs a warning, so that case stays distinguishable from a board that stopped responding |
| Only SQLite exercises the predicate in CI | Same posture as 002: plain boolean columns, no JSON operators, no index dependence. The migration round-trip is run against the real PostgreSQL (quickstart Gate 1) |

## Complexity Tracking

No entries. The feature adds one pure package of three small modules, one traversal
helper, one stage, one CLI command and two nullable columns; it adds a second
predicate to an existing seam rather than a second seam, and it introduces no new
dependency edge. The one thing it deliberately does **not** add — a per-profile
verdict table, which would be the fully correct model of a per-profile criterion —
is rejected in research R1 for a structural reason rather than a budgetary one.
