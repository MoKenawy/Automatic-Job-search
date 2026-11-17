# Contract: the filter seam

> **Amended by [ADR-0018](../../../Docs/ADRs/0018-per-profile-title-rules.md), 17 November 2026.** The contracts below describe `Criteria` with one global
> `TitleRules` and a `requested_levels` tuple. `Criteria` now carries `contributors` —
> one record per contributing profile holding its requested level **and** its own
> title rules — and the title verdict is `all_of(global, any_of(profiles))`.
> `requested_levels` survives as a derived property. The experience-criterion
> contract, including the disjunction paragraph below, is unchanged.

**Modules**: `app/src/app/filters/` *(new, pure)* · `app/src/app/db/visibility.py`
*(extended)* · `app/src/app/pipeline/filter_stage.py` *(new)*
**Feature**: [003-collect-stage-filtering](../spec.md) | **Implements**: FR-004…FR-011,
FR-016, FR-017 | **Precedent**: [ADR-0015](../../../Docs/ADRs/0015-employer-level-suppression.md)

This project exposes no public API and no network contract — it is a local
single-operator tool. Three internal contracts matter here: what the pure evaluator
promises, what the read-time predicates promise, and what the CLI promises. The
second is the one that can go wrong silently, which is why it has 002's seam
treatment.

---

## 1. The pure evaluator

```python
# app/src/app/filters/levels.py
class Level(IntEnum):            # ordered: internship < entry < associate
    ...                          #        < mid_senior < director < executive

def parse_level(label: str | None) -> Level | None
def parse_requested(text: str | None) -> Level | None
def level_from_title(normalised_title: str | None) -> Level | None
def merge_labels(labels: Iterable[str | None]) -> str | None

# app/src/app/filters/titles.py
class TitleRules:                # compiled, or deliberately disabled
    @classmethod
    def compile(cls, include: str, exclude: str) -> "TitleRules"
    errors: tuple[str, ...]
    def verdict(self, title: str | None) -> bool | None

# app/src/app/filters/verdict.py
@dataclass(frozen=True)
class Criteria:                  # title rules + the requested levels of the
    ...                          # profiles that surfaced the posting
@dataclass(frozen=True)
class Verdict:
    title_passed: bool | None
    experience_passed: bool | None
    @property
    def rejected(self) -> bool
    @property
    def grounds(self) -> str | None      # 'title' | 'experience' | 'both' | None

def evaluate(*, title, normalised_title, job_level, criteria) -> Verdict
```

### Guarantees

| # | Guarantee | Why it is stated |
|---|---|---|
| G1 | **No database knowledge.** Nothing in `filters/` imports `app.db`, a `Session`, or `app.config` | The dependency rule `CLAUDE.md` makes load-bearing, and what lets the whole criteria layer be tested without infrastructure. `normalise/` and `collect/` hold the same line |
| G2 | **`None` is returned, never guessed.** `parse_level` maps `None`, `""`, whitespace and `not applicable` to the same `None`, case-insensitively | These are four spellings of one fact: absence of information. The collector lowercases the label and yields `""` rather than null when descriptions are not fetched, so all four occur in practice. Precedent: `normalise/country.py`'s `parse_country()` |
| G3 | **`Level` contains no `UNKNOWN` member.** Unknown is the absence of a `Level`, outside the type | An `UNKNOWN` inside an orderable enum eventually meets a `<=` and silently admits or rejects everything. Keeping it out makes that unrepresentable rather than guarded |
| G4 | **A disabled criterion returns `None`, not `True`.** Empty pattern, absent or unrecognised requested experience, malformed pattern | FR-005 and SC-006: "not applied" and "applied and admitted" are different facts, and only the first makes installation a no-op ([data-model.md](../data-model.md)) |
| G5 | **An empty pattern is disabled before compiling.** Emptiness is decided on the string, not on a match result | `re.search("", title)` matches everything, and both patterns ship empty. Compiling first puts the whole corpus one forgotten branch away from rejection (research R3) |
| G6 | **A malformed pattern disables its criterion and reports.** `re.error` is caught at compile time, recorded in `errors`, and never raised through the stage | FR-008 and US2 scenario 4: the run completes, the fault is reported, no posting is rejected on the strength of an unusable rule |
| G7 | **`evaluate` is total and order-free.** Same inputs, same `Verdict`, with no dependence on evaluation order, wall clock, or how many times it has run | FR-010 and SC-007 reduce to this plus "nothing is timestamped" |
| G8 | **`merge_labels` is commutative, associative and idempotent** — minimum seniority, ties broken lexicographically on the raw label | FR-009 asks for a verdict *defined* for the merged posting, not merely stable. Minimum also leans toward admission, which is the governing asymmetry (research R2) |
| G9 | **`level_from_title` is conservative.** Word-boundary matching only, and conflicting markers yield `None` | FR-006's fallback is the feature's chief false-rejection risk. `intern` must not match `internal`; "Senior Internship Programme" must not resolve to a level at all |

### The at-or-below rule

```text
experience_passed(requested, actual):
    requested is None  ->  None          # criterion disabled for this profile
    actual    is None  ->  True          # unknown admits (FR-005)
    otherwise          ->  actual <= requested
```

Deliberately asymmetric (FR-007): a request for entry level admits internship,
entry and associate, and rejects mid-senior, director and executive. A role below
the requested level is worth the operator's glance; one well above it is not.

Across several profiles the per-profile results are combined by **disjunction** —
admitted if any profile admits, `None` if every profile's criterion is disabled, and
a profile-less contribution admits unconditionally (research R1). Disjunction is why
the verdict does not depend on which run last touched the posting.

---

## 2. The read-time predicates

```python
# app/src/app/db/visibility.py
def filter_rejected() -> ColumnElement[bool]:
    """True for postings a filter criterion rejected, whatever their status."""

def hidden_by_filter() -> ColumnElement[bool]:
    """True for postings the filter is withholding from the operator's views."""
```

```python
filter_rejected()   ==  Posting.title_filter_passed.is_(False) | Posting.experience_filter_passed.is_(False)
hidden_by_filter()  ==  filter_rejected() & (Posting.status == STATUS_NEW)
```

Read paths adopt `~hidden_by_filter()`, alongside the existing `not_suppressed()`.

### Guarantees

| # | Guarantee | Why it is stated |
|---|---|---|
| H1 | **NULL-safe.** Written with `.is_(False)`, never `== False` or `~(… == True)` | Under three-valued logic `NOT (NULL = FALSE)` is NULL and the row is dropped. Every verdict is NULL today, so the obvious spelling hides the entire corpus — while an absence-only suite stays green, the exact catastrophe [002's contract](../../002-employer-suppression-derived/contracts/visibility-seam.md) names |
| H2 | **Composes with statements that join nothing.** Both are plain boolean expressions over `postings` columns, with no subquery | `totals` and `facets` select straight from `postings`. A predicate requiring a join would force them to restructure, and a restructure is where a filter gets dropped (002's G1) |
| H3 | **Cannot change a row count on its own.** No join, no subquery, so no cardinality effect | `list_postings` derives its page and its total from two statements; a predicate with join-like effects would make them disagree and the pager would claim rows the operator cannot reach (002's G2) |
| H4 | **Compiles identically under SQLite and PostgreSQL.** `IS FALSE` on a plain `Boolean`, no JSON operators | The suite runs on SQLite, production is PostgreSQL. Contrast `queries._has_source`, which needed a dialect split because SQLite's `JSON_QUOTE(NULL)` is the string `'null'` — the strongest concrete argument for promoting `job_level` to a column instead of reading it from JSONB (002's G3) |
| H5 | **Redundant application is free.** Idempotent boolean conjunction | One idiom everywhere beats two idioms plus a rule about which applies where (002's G4) |
| H6 | **Correctness does not depend on any index.** None is added | At NFR-1 volume the plan difference is not measurable (002's G5) |
| H7 | **Triaged postings are never withheld.** The `status == new` term is inside `hidden_by_filter()` and absent from `filter_rejected()` | The spec's edge case: a posting the operator has shortlisted or applied to must not be removed from view by a later tightening. The verdict must stay status-free or FR-016 cannot answer for a triaged posting |

### The obligation

> A filter verdict is a statement about criteria, never about the operator's
> judgement, so every read of `postings` that must respect the filter applies
> `~hidden_by_filter()`. If you are writing a query over postings and not using it,
> that is a decision to be justified in a comment, not an omission.

Stated in the module's own docstring, at the definition site, because that is the one
place a developer writing a new query is guaranteed to look. It is FR-004 and FR-017
in prose, and it is deliberately word-for-word parallel to the suppression
obligation already there: a reader who has internalised one has internalised both.

**The failure mode this contract accepts.** Centralising does not remove the risk,
it relocates it — a missing predicate *resurfaces* a filtered posting, which is the
harmless direction, but it also makes the "Filtered out" bucket disagree with the
queue, which is not. Three things contain it:

1. **One definition per fact** — two expressions, each with one meaning, so applying
   the right one is never a judgement call.
2. **A closed inventory** — [002's read-path inventory](../../002-employer-suppression-derived/contracts/read-path-inventory.md)
   is **extended in place** with a second verdict column rather than cloned. A second
   table would be a second thing to forget, and the whole value of the artefact is
   that an unexamined path shows up as a missing row a reviewer can see.
3. **Per-path two-sided tests** — removing the predicate from any single path fails
   the suite.

### Opt-out protocol

A read path may decline the predicate. It may not decline it silently. An opt-out
carries an inline comment stating (a) that it is deliberate, (b) the reason, and
(c) `ADR-0016`.

| Path | Verdict | Reason |
|---|---|---|
| `queries.get_posting` | **Deliberate opt-out** | FR-013 and FR-016: the detail page is the operator's route to a withheld posting and the place the grounds are shown. Filtering it would make a rejected posting unreachable — the same argument that already exempts it from `not_suppressed()`. Conditional on the banner shipping in the same commit |
| The "Filtered out" bucket | **Inverted deliberately** | FR-017: it selects `filter_rejected()`, so it shows triaged-and-rejected postings too. That overlap with the normal list is the point — see below |

### The bucket is not the complement

`filter_rejected()` and `hidden_by_filter()` are different sets, and their difference
— *rejected but no longer `new`* — appears **both** in the normal list and in the
bucket. This is deliberate: FR-017 and SC-002 exist to make false rejections
discoverable, and the strongest evidence of one is a posting the operator shortlisted
that the current criteria reject. A bucket defined as "everything hidden" would
conceal exactly that.

Because the two can drift apart silently, a partition test over every
(verdict × status) pair asserts `|hidden| + |visible| == |all|` and names the overlap
set explicitly.

---

## 3. The CLI surface

```text
uv run python -m app filter [--run-id N] [--all] [--dry-run]
```

| Form | Scope | Run counters |
|---|---|---|
| `filter` | the latest run's distinct postings | written to that run |
| `filter --run-id N` | run N's distinct postings, under **current** criteria | written to run N, overwriting its previous figures |
| `filter --all` | every posting in the database | **none** — see below |
| `… --dry-run` | as above | none; nothing is written at all |

`--all` and `--run-id` are mutually exclusive, and saying so beats silently
preferring one. Behind the command sit two entry points sharing one evaluator:

```python
# app/src/app/pipeline/filter_stage.py
def run_filter(session, run, config, *, dry_run=False) -> tuple[int, int]
def filter_all(session, config, *, dry_run=False) -> tuple[int, int]
```

`run_filter` also runs as part of `run-all`, wired into `pipeline/runner._run()`
after normalise, which covers the CLI, the scheduler and the web "run now" in one
place.

### Guarantees

| # | Guarantee | Why it is stated |
|---|---|---|
| C1 | **`filter_passed_count + filter_rejected_count == deduplicated_count`** for any run the stage processed | SC-003 made testable, and it pins the stage's scope to exactly the set `run_normalise` counted — distinct postings reached through `raw_posting_normalizations` |
| C2 | **`--all` writes no run counters** | FR-015's counts belong to a run that evaluated postings during an execution. Writing a re-apply's totals onto a past run would decouple them from its `collected_count` and break C1 |
| C3 | **A converged re-apply issues zero UPDATE statements**, and **says so** — the number of verdicts changed is reported | SC-007 literally: `updated_at` carries `onupdate`, so blind writes would move a thousand timestamps for no change (research R5). Writes are difference-guarded, and the changed count is what makes the property observable rather than merely true |
| C4 | **`--dry-run` writes nothing** — no verdict, no counter, no `updated_at` | The only safe way to measure the criteria against the real corpus before anything can be hidden, which is what the Phase 2/3 boundary exists for |
| C5 | **Never writes `status`, `status_changed_at`, `last_retrieved_at`, or any raw row** | FR-012 and FR-014. Rejection and operator judgement are separate facts; a verdict is not an observation (ADR-0012) |
| C6 | **Reports what it could not interpret** — the count of unrecognised experience values and any pattern error, in the log, in the command's output, **and on `run.error`** | FR-002a and FR-008 require the fault to reach *the operator*, whose surface is the triage interface: `run.error` is rendered at `/runs`. Precedents: `run_normalise`'s `unresolved_country` in its completion log, and `run_collect` recording a non-fatal board failure on `run.error` |
| C7 | **Warns when it rejects a whole haul** — `rejected == deduplicated_count > 0` | The spec's edge case: in the aggregate this is indistinguishable from a board that stopped responding, and the two must stay distinguishable |

---

## 4. Test contract

| Module | Covers |
|---|---|
| `app/tests/test_filter_levels.py` | The scale and both vocabularies; `OBSERVED` board labels; `None` for all four spellings of unknown; the at-or-below band in both directions; the disjunction across profiles **in both orders**; `merge_labels` commutativity and the tie-break; the title fallback's word boundaries and its ambiguity refusal |
| `app/tests/test_filter_titles.py` | Empty pattern disabled (named for SC-006); include and exclude independently and together; malformed pattern disables and reports without raising; case-insensitivity; `None`/empty title |
| `app/tests/test_filter_stage.py` | C1's sum invariant; convergence; **zero UPDATEs on a converged re-apply** (C3); `--dry-run` writing nothing; status and raw rows untouched; the whole-haul warning; the unrecognised-experience report |
| `app/tests/test_visibility.py` *(extended)* | The predicates in isolation, beside `not_suppressed()` — one module per seam file keeps both discoverable together |

**The keystone test**, mirroring 002's:

| Case | Expectation |
|---|---|
| Posting rejected on experience grounds, status still `new` | **Invisible** |
| The same posting once `shortlist` | **Visible** — a tightening never withdraws the operator's own judgement |
| Posting with NULL verdicts | **Visible** |
| Posting with both verdicts `TRUE` | **Visible** |

The third case is the one that fails catastrophically under the wrong spelling of the
predicate (H1), and it is the reason the corpus must contain NULL verdicts rather
than only `TRUE` and `FALSE`.

**Every per-path test is two-sided.** Each fixture holds a rejected posting *and* an
admitted one, and each test asserts the rejected one is absent **and** the admitted
one is present. An absence-only suite passes against a predicate that hides
everything.

**Hiding is not deletion.** No invisibility assertion can distinguish "withheld" from
"gone", so one test asserts the rows are still present, with their triage status
intact, after being rejected — FR-013 and FR-014, and the thing that makes a criteria
change reversible.

**SC-002's sizing rule.** The body of tests proving nothing is wrongly rejected must
be at least as large as the body proving rejection works. The spec states it; this
contract makes it a reviewable property of the diff rather than an intention.
