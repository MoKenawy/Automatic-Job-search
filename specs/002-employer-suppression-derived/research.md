# Research: Employer-level suppression, derived at read time

**Feature**: [002-employer-suppression-derived](spec.md) | **Date**: 13 August 2026

The feature's *what* was settled by [ADR-0015](../../Docs/ADRs/0015-employer-level-suppression.md),
which chose derivation over materialisation after a
[concurrency review](../../Docs/design/suppression-concurrency-review.md) traced
a family of races to the redundancy rather than to a locking defect. This
document records the decisions the ADR deliberately left to implementation, and
what was rejected in each case.

There were no `NEEDS CLARIFICATION` markers carried in from the spec.

---

## R1 — Where the shared filter lives

**Decision**: A new module `app/src/app/db/visibility.py`.

**Rationale**: ADR-0015 §Decision 4 requires "a single filtered base query (or
view) that list, detail, publication, reports, and the future scoring stage all
start from", and names it as the place the decision can go wrong. Two of those
five consumers — stage 3 scoring and stage 4 publication — are `pipeline/`
modules that do not yet exist.

`CLAUDE.md` and `refactor-plan.md` §7.2 fix the dependency direction: `pipeline/`
must not import `services/`. So the obvious home, `services/queries.py`, is the
wrong one — a seam sited there is a seam the two named future consumers are
structurally forbidden to use, which guarantees the precise failure the ADR
warns about: a read path that silently forgets the filter, not through
carelessness but because the import is illegal.

`db/` is imported by both `services/` and `pipeline/` and prohibited to neither.
It is the only placement that makes the obligation satisfiable by every consumer
the ADR names.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| `services/queries.py` — today's read model | Unreachable from `pipeline/`. Stages 3 and 4 would each grow their own copy of the filter, which is the redundancy this feature exists to remove, reintroduced one layer up |
| A new top-level `visibility/` package | A single nine-line predicate over two ORM models is not a package. It would also need its own place in the dependency ordering, for no gain |
| Inside `db/models.py` | `models.py` is the schema's source of truth and is already large. A query-shaping helper there dilutes what the module is for, and the seam's docstring — which carries the obligation — would be buried |

---

## R2 — What shape the seam takes

**Decision**: A composable predicate, `not_suppressed() -> ColumnElement[bool]`,
implemented as a correlated `NOT EXISTS` over `employers`.

```python
def not_suppressed() -> ColumnElement[bool]:
    return ~(
        select(Employer.id)
        .where(Employer.id == Posting.employer_id, Employer.suppressed.is_(True))
        .exists()
    )
```

**Rationale**: three properties, each load-bearing.

1. **It composes with statements that do not join `employers`.** `totals` and
   `facets` select straight from `postings`. A base query forcing a join would
   require restructuring them; a predicate drops into their existing `.where()`.
2. **It cannot alter a row count on its own.** A join added purely to filter is
   a join that can silently multiply rows if a cardinality assumption ever
   changes. `EXISTS` is a boolean test — it can only ever remove rows.
   `list_postings` computes its `total` and its page from separate statements,
   so a filter that could affect cardinality differently between the two would
   make the pager lie.
3. **One idiom everywhere.** Applied even in queries that already join
   `Employer`, where it is redundant but free. The alternative — join condition
   where a join exists, `EXISTS` where it does not — is two idioms plus a rule
   about which applies when, and a rule like that is what a future reader gets
   wrong.

Dialect-portable by construction: a plain correlated `EXISTS`, with no
JSON operators and no index-dependent behaviour. This matters concretely —
`queries._has_source` already needed a SQLite/PostgreSQL split because
`JSON_QUOTE(NULL)` returns the *string* `'null'` and silently defeated an
`IS NOT NULL` filter. Nothing analogous applies here.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| A filtered base query (`select(Posting).where(...)`) that callers extend | Callers that need `select(func.count())` or `select(Posting.country_code).distinct()` cannot start from a `select(Posting)`. Either they opt out — defeating the point — or the module grows one base query per shape |
| A database view | Invisible to Alembic autogenerate, so it needs hand-written migrations in both directions; and it cannot be exercised under SQLite the way the rest of the suite is. It would move the seam outside the tests that protect it |
| A global `with_loader_criteria` event | Enforces by magic. The one query that must opt out (R3 source overlap) has to fight the framework to do so, and — decisively — nothing at any call site tells a reader the filter exists. That converts a stated obligation into a hidden one |
| A join with `Employer.suppressed.is_(False)` | Works where a join already exists; needs a new join elsewhere. See point 3 above |

---

## R3 — Which read paths opt out, and on what grounds

**Decision**: Two deliberate opt-outs, both commented at the site; one
pre-existing opt-out that keeps its behaviour but loses a now-false docstring.

**Rationale**: an unexamined query is the failure mode; an examined query that
declines the filter is a decision. The full verdict table is
[contracts/read-path-inventory.md](contracts/read-path-inventory.md). The two
that decline:

- **`queries.get_posting` (posting detail).** `detail.html` already renders the
  blacklist banner and the "Remove from blacklist" button — this page *is* the
  operator's route back out of a suppression. Filtering it would make lifting
  unreachable from the posting that prompted it, turning the filter into a
  one-way door. Spec FR-015 makes this a requirement rather than a concession.
- **`reports.source_overlap` (R3).** It measures what the *collector* returned,
  not what the operator should act on. Filtering would understate a board's
  coverage — the report would answer a different question than its title claims.
  Spec FR-017.

**A third case is a documentation fix, not a decision**: `reports.employer_activity`
(R1) already opts out knowingly, via an `include_suppressed` parameter at the
employer level. Its behaviour is correct and unchanged. Its docstring's claim
that suppressed employers' "postings are auto-rejected (D9)" simply becomes
false and must be reworded.

**Alternative considered — filter everything, with no opt-outs.** Rejected on
both cases above: it makes an applied blacklist irreversible from the posting
that motivated it, and it silently changes what a collector-coverage report
measures. The uniformity is not worth either.

---

## R4 — What to do with postings already stamped `rejected`

**Decision**: Nothing. Leave them exactly as they are.

**Rationale**: which historical rejections were suppression-driven and which were
the operator's own is **not recoverable**. `posting_status_history` post-dates
the old mechanism (ADR-0013) and its backfill writes one synthetic baseline row
per posting with `previous_status = NULL`, so it cannot attribute pre-existing
rejections. Rewriting them would risk resurfacing postings the operator
genuinely rejected — destroying real judgement in order to tidy up ambiguous
judgement.

Leaving them is safe and loses nothing: those postings are already hidden, and
the pre-change FR-011 already promised that lifting a blacklist would not
reinstate them. So no existing promise is broken by inaction.

The consequence, accepted in ADR-0015 and made visible by spec FR-013:
**historical and future blacklists behave differently on lift.** Postings
suppressed before this change stay rejected; postings suppressed after it
reappear with operator status intact. This is an honest artefact of intent that
was destroyed before it could be recorded — not a design inconsistency going
forward.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Reset to `new` every `rejected` posting whose employer is currently suppressed | Cannot distinguish an operator's rejection from a sweep's. Silently discards real decisions |
| Reset only where history shows `actor='system'`, `reason='employer suppressed'` | Recovers only rejections made after ADR-0013 landed — a small, arbitrary slice. Produces a *third* behaviour class on top of the two the ADR already accepts, making the asymmetry harder to explain rather than easier |
| Add a column recording why a posting was rejected | Reintroduces a per-posting copy of employer state. This is exactly the invariant ADR-0015 §Control forbids |

---

## R5 — Whether a migration is needed

**Decision**: Expect none. **Verify it rather than assume it.**

**Rationale**: ADR-0015 §Migration calls the change "schema-only, no data
rewrite". On inspection there is no schema half either — `employers.suppressed`
and its partial index `ix_employers_suppressed` already exist; no column is
added, dropped, or altered. `ix_postings_triage_queue` stays useful for the
list's `published`/`status`/`score` ordering, so it is not dropped either. The
Phase 2 changes to `db/models.py` are a method deletion and comment edits,
neither of which Alembic sees.

But "expected to be empty" is a claim about a generator's output, and the project
convention (`CLAUDE.md`) is that autogenerated migrations are reviewed by hand
because autogenerate misses things. So the plan runs autogenerate as a
**verification step** after Phase 2 and asserts the `upgrade()` body is empty,
then deletes the generated file. A non-empty body is a defect signal — it means
the model sweep changed more than a comment — and is fixed at the source rather
than committed as a migration.

**Alternative considered — skip the check entirely.** Rejected: it is one command,
and it converts an assumption at the centre of the plan into a checked fact. The
failure it catches (an accidental column or constraint change during the comment
sweep) is silent otherwise, and would surface as a production/test schema drift
long after the commit that caused it.

---

## R6 — What to do with the uncommitted ADR-0014 sweep-atomicity work

**Decision**: **Stashed, not committed.** The working tree held an unmerged fix to
`services/blacklist.py` — extracting a non-committing `_reject_employer_postings`,
adding `ORDER BY id` + `FOR UPDATE` to match `triage.set_status_bulk`'s lock
order, and collapsing `blacklist()`'s two commits into one so no reader could
observe the sweep half-applied. It is set aside rather than landed.

**Rationale**: the fix was correct for the model it defended, and **every line of
it is deleted by this feature.** Unlike the sibling change to `services/triage.py`
— whose `FOR UPDATE` guards the double-click / two-tabs race, which is orthogonal
to suppression and survives untouched — nothing in `blacklist.py` outlives the
removal of the sweep. Committing it would add a file to the breaking commit's
diff purely to delete code that was never used, never merged, and never released.

The counter-argument considered at length: ADR-0014 is already accepted, so
deleting the code without ever committing it appears to leave the ADR documenting
an implementation that never existed. **It does not.** ADR-0014's header is
amended to *"Accepted, partly superseded by ADR-0015"* with an explicit
surviving/moot split, and its surviving half — the `triage.py` locking — **is**
committed. Its moot half is ADR-0014's case 2 in full, which ADR-0015 makes
vacuous rather than solved. The ADR ends up recording one fix that landed and one
that was overtaken before landing, which is exactly what happened.

The record does not depend on the code in any case.
[suppression-concurrency-review.md](../../Docs/design/suppression-concurrency-review.md)
traces the race family in far more detail than the implementation expresses, and
it is committed regardless. An uncommitted working tree is not history — no
decision to ship was ever made — so setting it aside retracts no claim.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Commit it, then delete it in the breaking commit | Adds ~30 lines of add-then-delete churn to the one commit that most needs to be reviewable, for a record two committed documents already carry better |
| `git restore` — discard outright | Loses the work irrecoverably. Stashing costs nothing and returns it if ADR-0015 is itself ever reversed |
| Keep it on a throwaway branch or tag | A branch nobody will look at, holding code nobody can use, requiring a note explaining why it exists. The stash entry carries the same information with no repository surface |

**Consequence to record**: ADR-0014's case-2 fix has **no implementation in
`main`'s history**. Someone reading that section and searching for the code will
find nothing. The amended ADR-0014 header must say so directly — not merely that
case 2 is superseded, but that it was superseded before it was committed.
