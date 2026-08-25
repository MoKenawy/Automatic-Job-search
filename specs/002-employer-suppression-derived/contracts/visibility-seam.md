# Contract: the visibility seam

**Module**: `app/src/app/db/visibility.py` *(new)*
**Feature**: [002-employer-suppression-derived](../spec.md) | **Implements**: FR-010, ADR-0015 §Decision 4

This project exposes no public API and no network contract — it is a local
single-operator tool. The contract that matters here is **internal**: the
agreement every read path over `postings` signs, and the one ADR-0015 identifies
as the place this whole decision can go wrong.

---

## Interface

```python
def not_suppressed() -> ColumnElement[bool]:
    """True for postings whose employer is not blacklisted."""
```

**Returns**: a SQLAlchemy boolean expression, correlated against the enclosing
statement's `postings` reference. Not a query, not a session-bound object — it
takes no arguments and holds no state, so it is safe to call once per statement
or once per `.where()` clause with no difference in behaviour.

**Usage** — drops into any statement that references `Posting`:

```python
select(func.count()).select_from(Posting).where(not_suppressed())
select(Posting, Employer).join(Employer, ...).where(*where, not_suppressed())
select(Posting.country_code).distinct().where(not_suppressed())
```

---

## Guarantees

| # | Guarantee | Why it is stated |
|---|---|---|
| G1 | **Composes with statements that do not join `employers`** | `totals` and `facets` select straight from `postings`. A seam requiring a join would force them to restructure, and a restructure is where a filter gets dropped |
| G2 | **Cannot change a row count on its own** | `EXISTS` is a boolean test; it can only remove rows, never multiply them. `list_postings` derives its `total` and its page from two separate statements — a filter with join-like cardinality effects could make them disagree, and the pager would then claim results the operator cannot reach |
| G3 | **Compiles identically under SQLite and PostgreSQL** | The suite runs on in-memory SQLite; production is PostgreSQL. A correlated `EXISTS` involves no JSON operators and no index-dependent semantics. Contrast `queries._has_source`, which needed a dialect split because SQLite's `JSON_QUOTE(NULL)` yields the string `'null'` and silently defeated an `IS NOT NULL` test |
| G4 | **Redundant application is free** | Safe to apply in statements that already join `Employer`. This is deliberate: one idiom everywhere beats two idioms plus a rule about which applies where |
| G5 | **Correctness does not depend on any index** | `ix_employers_suppressed` (partial, PostgreSQL) serves the subquery but is an optimisation. At NFR-1 volume the plan difference against a join is not measurable |

---

## The obligation

> Suppression is a property of an employer, never stamped on a posting, so every
> read of `postings` that must respect the blacklist applies this predicate. If
> you are writing a query over postings and not using it, that is a decision to
> be justified in a comment, not an omission.

This is stated in the module's own docstring, at the definition site, because
that is the one place a developer writing a new query is guaranteed to look. It
is FR-010 in prose.

**The failure mode this contract accepts.** ADR-0015 is explicit that centralising
does not eliminate the risk, it relocates it: the failure moves from "stale
data" to "missing filter", and a missing filter *resurfaces* a blacklisted
employer. This is the strongest argument against the chosen option and it is
accepted, not solved. Three things contain it:

1. **One definition** — there is exactly one thing to apply, so applying it is
   never a judgement call about which variant fits.
2. **A closed inventory** — [read-path-inventory.md](read-path-inventory.md)
   assigns a verdict to every existing query, so an unexamined path is visible
   as a gap in a table rather than invisible as an absence in code.
3. **Per-path tests** — one invisibility assertion per adopting path, so removing
   the filter from any single path fails the suite. Not one test in total; the
   suite's governing asymmetry applied to this feature.

---

## Opt-out protocol

A read path may decline the seam. It may not decline it silently.

An opt-out MUST carry an inline comment at the query stating (a) that it is
deliberate, (b) the reason, and (c) `ADR-0015`. Both current opt-outs are
requirements in their own right rather than concessions — FR-015 for posting
detail, FR-017 for the R3 source-overlap report — so each comment points at the
requirement it serves.

The distinction this protocol draws is the whole point: **an unexamined query is
the failure mode; an examined query that declines the filter is a decision.**

---

## Test contract

`app/tests/test_visibility.py` — the predicate in isolation:

| Case | Expectation |
|---|---|
| Normal employer's posting | Selected |
| Suppressed employer's posting | Rejected |
| **Suppressed employer's posting whose `status` is still `new`** | **Rejected** |

The third case is the keystone. It fails before the seam exists, for exactly the
right reason: under the old model, suppression was only visible *as* a status, so
a suppressed-but-`new` posting was a state the system could not represent. It is
the assertion this entire feature exists to make true.

Per-path invisibility tests live with their paths in `app/tests/test_blacklist.py`
— see the inventory's Verification column.

**Every per-path test must be two-sided.** Each fixture holds a suppressed
employer *and* a normal one, and each test asserts the suppressed posting is
absent **and** the normal posting is present. An absence-only suite passes
against a `not_suppressed()` that returns `false` and hides the entire corpus —
the seam would be catastrophically wrong and every test green. The predicate's
own case 1 guards this at unit level, but not through the query paths, which is
where the adoption could go wrong independently.

**Invisibility is not retention.** D9 requires suppressed postings to be retained,
never deleted (spec FR-014), and no invisibility assertion can distinguish "hidden"
from "gone". One test must assert the rows are still present after blacklisting,
or the requirement is uncovered.
