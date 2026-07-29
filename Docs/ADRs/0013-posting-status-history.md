# ADR-0013: Transactional audit table for triage status transitions

| | |
|---|---|
| **Status** | Under review |
| **Date** | 29 July 2026 |
| **Decision maker** | Mohammed |
| **Related** | [ADR-0012](0012-retrieval-date-column-split.md); [db/models.py](../../app/src/app/db/models.py); [services/triage.py](../../app/src/app/services/triage.py); [services/blacklist.py](../../app/src/app/services/blacklist.py); migration `64c8f2ca9cfe` |

---

## Context

`postings.status` and `postings.status_changed_at` record only the *current*
triage state and *when it last changed* — the previous state, who or what
changed it, and why are all overwritten on every transition. That is enough
for the list/detail views, but not enough to answer "how did this posting get
to Rejected", audit an operator's bulk action after the fact, or distinguish
a manual triage decision from the suppression sweep's own rejections once
both have happened to the same row.

`Posting.transition_to()` is already the single place every status change
passes through (`triage.set_status`, `triage.set_status_bulk`,
`Posting.reject_for_suppression` via the suppression sweep and the
blacklist service) — refactor-plan.md §4.1 and ADR-0012 already established
that pattern for other invariants. Adding history at that one seam, rather
than at each caller, is the same shape of fix.

## Decision

**A new `posting_status_history` table, one row per transition, written in
the same session/transaction as the `postings` update it accompanies.**

`Posting.transition_to()` appends a `PostingStatusHistory` row to
`Posting.status_history` (an ORM relationship, `cascade="all, delete-orphan"`)
as part of the same call that mutates `status` / `status_changed_at` /
`published`. Because both the `postings` UPDATE and the
`posting_status_history` INSERT are emitted from the same SQLAlchemy
session and flushed together, a `session.commit()` failure rolls back both,
and a `session.rollback()` after a mid-transaction exception leaves neither
applied. There is no code path that changes `status` without a
corresponding history row, and no path that leaves a partial write —
correctness follows from *when* the row is appended (inside the mutating
method itself), not from callers remembering to log it separately.

Columns: `posting_id` (FK, `ondelete="CASCADE"`), `previous_status`
(nullable — see backfill below), `new_status`, `changed_at`, `actor`
(`'operator'` | `'system'` | `'migration'`), `reason` (nullable free text).
No `updated_at` — rows are never edited, only inserted; correcting a mistaken
transition means recording a further one.

**Invalid transitions never reach the table.** `transition_to()` validates
`status in STATUSES` before mutating anything or appending history, so an
unknown status raises `ValueError` (`UnknownStatusError` at the service
layer) with zero side effects — nothing to roll back because nothing was
written. The any-status-to-any-other business rule itself (Rejected is not
terminal — confirmed behaviour, refactor-plan.md §6.1) is unchanged; this
ADR only adds a record of each such transition, not a new restriction on
which ones are allowed.

**Concurrency: `SELECT ... FOR UPDATE`, ordered by id.** `triage.set_status`,
`triage.set_status_bulk`, and `blacklist.reject_employer_postings` all lock
the row(s) they are about to transition before reading `status`, so two
concurrent requests touching the same posting serialize instead of racing —
without the lock, both could read the same starting status and the later
commit would silently overwrite the earlier transition and its history row.
Bulk operations lock in `id` order specifically so two overlapping bulk
requests cannot deadlock by acquiring the same two rows in opposite order.
(SQLite, used under test, has no row-level locking and ignores the clause;
the lock is only meaningful — and only needed — under PostgreSQL, where
this application actually runs concurrent requests.)

**Backfill: one synthetic baseline row per existing posting.** Migration
`64c8f2ca9cfe` backfills `previous_status = NULL`, `new_status =
<the posting's current status>`, `changed_at = COALESCE(status_changed_at,
first_seen_at)`, `actor = 'migration'`. This is the same reasoning ADR-0012
already applied to `last_retrieved_at`: `NULL` previous-status is honest
(nothing before this table existed recorded what a posting transitioned
*from*), and `first_seen_at` as the timestamp floor is a real fact already
on hand rather than a claim that a transition happened at migration time.

## Consequences

*Favourable:*

- Every transition from this point forward carries who/what did it and, when
  supplied, why — answering questions the single-row `status_changed_at`
  column structurally cannot (multiple transitions between report runs, a
  transition later reversed, distinguishing operator action from the
  suppression sweep).
- Atomicity is structural, not procedural: because the history append lives
  inside `transition_to()` itself, no future caller of that method can
  forget to record history, and no future service method needs its own
  transaction-boundary reasoning beyond "call `transition_to()` and commit."
- `postings.status` / `status_changed_at` are untouched — every existing
  query, template, and report keeps working unchanged; this is additive.

*Unfavourable, and accepted:*

- A new table to maintain, and one more INSERT per transition (negligible at
  this project's scale — triage volume is operator-paced, not high-throughput).
- The backfilled baseline row's `previous_status` is `NULL` for every posting
  that predates this migration — a real gap in what is knowable, not a defect,
  but a caveat for anyone reading pre-migration history expecting a full chain.
- `FOR UPDATE` locking is inert under the SQLite test backend; the concurrency
  guarantee is verified structurally (same-session same-transaction) in tests
  rather than by exercising real lock contention, since this project's test
  suite does not run against PostgreSQL.

## Control

If a future feature needs to *revert* to a prior status programmatically
(not just record one), read the latest `posting_status_history` row for that
posting rather than reconstructing state from `postings.status_changed_at`
— the row already carries the exact previous value.
