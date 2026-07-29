# ADR-0010: Where R2's span arithmetic runs — Python, SQL, or the write path

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 27 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | Refines [Reports implementation plan](../design/reports-implementation-plan.md) §4.2, §5 R2, which assumed a Python-side computation without recording alternatives |
| **Related** | [ADR-0008](0008-report-system-scope.md) R2; [ADR-0012](0012-retrieval-date-column-split.md); [services/queries.py](../../app/src/app/services/queries.py) `_has_source`, `_ordering` |

---

## Context

R2 needs, per posting: live span (`last_retrieved_at - first_seen_at`),
collection lag (`first_seen_at - date_posted`), a bucketed distribution of
both, and a long-lived tail. (`last_retrieved_at` is ADR-0012's name for this
column; at the time this record was drafted it was still the overloaded
`last_seen_at` — the computation-strategy question below is unaffected by
which column supplies the timestamp.) The reports plan defaulted to computing
these in Python —
consistent with how R3 was built (design plan §4.2) — but R3's reason for that
choice does not transfer cleanly: R3 aggregates *JSON*, which is genuinely
unportable across JSONB and SQLite's JSON in the way `queries._has_source`
documents. R2's inputs are two plain `DateTime` columns, where the portability
problem is different in kind — date arithmetic, not JSON semantics — and the
codebase already has a working precedent for handling exactly that kind of
dialect split (`_has_source` itself, and `_ordering`'s conditional column
selection), so the choice deserves its own comparison rather than inheriting
R3's answer by proximity.

## Options considered

**A — Python, as originally planned.** Select the four timestamp columns per
posting, compute spans and buckets in the aggregation function.

*Simplest to write and to test*, and correctness is dialect-independent since
`datetime` subtraction is the same operation regardless of what produced the
values. Cost scales linearly with rows fetched, which is bounded well under
NFR-1's scale.

**B — Dialect-conditional SQL date-diff expression**, mirroring
`_has_source`'s existing split: SQLite's `julianday(a) - julianday(b)` against
PostgreSQL's native interval subtraction or `EXTRACT(EPOCH FROM a - b)`.

*Follows house precedent* — this project already accepts a dialect branch as
the right shape for a portability problem, rather than avoiding SQL
differences by pushing everything to Python. It also opens the door to
`percentile_cont` for the bucket boundaries under PostgreSQL, which Python
would otherwise have to reimplement.

*Cost:* two code paths to keep in sync, and the SQLite path exists only to keep
the test suite portable — production always runs PostgreSQL (`database_url`
default), so the branch that matters in production is exercised by a test
suite that never runs it.

**C — A SQL view, created by migration**, exposing `span_days` and
`collection_lag_days` as real columns other tools can query directly —
`psql`, a future BI connection, an ad hoc audit — not only the web report.

*Turns the computation into a durable artefact* rather than logic private to
one Python function, which has standalone value given this project's stated
secondary goal of being a portfolio piece (design §2.1 criterion 5). *Cost:*
a migration, a second thing to keep in sync with the ORM model if `Posting`'s
columns ever change, and machinery disproportionate to a report used by one
operator.

**D — Incrementally maintained columns**, written at pipeline time instead of
computed at read time: `observe()` gains an `observation_count` increment and
a running `max_gap_days` update on every re-observation.

*Moves cost to the write path*, which is the wrong direction for this system —
`normalise_stage` already runs against NFR-1's time budget, and R2's read-time
cost is a few thousand row subtractions, immeasurably cheaper than adding
write-path work to shave it further. Also reopens a question ADR-0008 §3
deliberately deferred: an `observation_count` column was already considered
there for the same report and set aside specifically because historical rows
would start at 1 and understate for months, misleading exactly where §4.3
requires honesty. Nothing about reaching the same column from the write-path
angle changes that objection.

## Decision

**A.** Python-side computation, exactly as the reports plan already specified,
now recorded as a compared decision rather than an inherited default.

The deciding fact is scale: NFR-1 bounds the whole pipeline to under a hundred
postings a day, and `services/reports.py` already states the governing rule —
compute per request, no caching, no summary tables, revisit only past roughly
100,000 rows or a report exceeding about a second. Four `DateTime` columns
across a few thousand rows is not in that territory, so B's dialect-branch
complexity, C's migration, and D's write-path cost are all being spent to
solve a performance problem that does not exist yet.

B is the one worth revisiting first if the situation changes — it needs no
schema change, only a query rewrite — and is explicitly the fallback named
below rather than a rejected option.

## Consequences

*Favourable:*

- One code path, no dialect branch to keep in sync, consistent with how the
  rest of `reports.py` is written.
- Nothing here forecloses B later: switching the internals of
  `posting_longevity()` from a Python loop to a dialect-branched query is a
  contained change behind an unchanged function signature.

*Unfavourable, and accepted:*

- Every call re-fetches and re-subtracts the same columns; acceptable at
  current and foreseeable scale per the stated 100,000-row / one-second
  trigger.
- PostgreSQL's native percentile functions go unused for now, so bucket
  boundaries are computed by hand in Python rather than requested from the
  database. Revisit under B if bucket logic grows more elaborate than simple
  fixed-width buckets.

## Control

Revisit if `postings` approaches 100,000 rows, or if R2 is ever observed to
take noticeably longer than the other reports on production data — either
signal points at B first, not at C or D.
