# ADR-0014: `SELECT ... FOR UPDATE` for concurrent status transitions

* Status: under review
* Deciders: Mohammed
* Date: 29 July 2026

Technical Story: [ADR-0013](0013-posting-status-history.md) added a
transactional history table for triage transitions; this record captures the
concurrency analysis behind the locking (and, on revision, the
transaction-boundary fix) that accompanied it —
`app/src/app/services/triage.py`, `app/src/app/services/blacklist.py`.

## Context and Problem Statement

Every triage transition is a read-modify-write: read `posting.status`,
compute the new state, write `status` + `status_changed_at` + a
`posting_status_history` row whose `previous_status` is whatever was just
read. Plain SQLAlchemy reads (`session.get`, `session.scalars(select(...))`)
take no lock, so two transactions that read the same posting before either
writes can each compute a transition from the same stale state. How should
concurrent writers to the same posting be serialized, so that no transition
and no history row is silently lost, and no reader ever observes a
part-applied change?

**Out of scope: two operators working the same queue.** This is a
single-operator tool (one person runs their own triage queue); genuine
multi-operator contention on the *same posting at the same instant* is not a
scenario this system needs to design for, and is not a driver for this
decision.

## Decision Drivers

* **No silently lost transitions**, for the concurrency that *does* occur in
  this system: a single operator's own retried/duplicate request (a
  double-click, two tabs on the same posting), racing the automated
  suppression sweep.
* **History must stay honest** — a race must not let a
  `posting_status_history` row record a `previous_status` that was already
  stale by the time it was written.
* **The suppression sweep must be linearizable.** "Suppress this employer and
  reject all its postings" is one operator-visible action; any concurrent
  reader must see either its full before-state or its full after-state,
  never a state where the employer is already suppressed but some of its
  postings have not caught up. Locking rows *for other writers* is not
  sufficient to guarantee this — a reader (the list view) takes no lock at
  all, so an intermediate state is only unobservable if it never exists on
  disk as a committed fact in the first place.
* **No deadlocks** between the call paths that do lock multiple rows
  (`set_status_bulk`, the suppression sweep).
* **Must degrade safely under the SQLite test backend**, which has no
  row-level locking.
* **Minimal footprint** — proportionate to a low-traffic, single-operator
  tool; no retry loops, version columns, or external coordinators unless the
  actual risk warrants them.

## Considered Options

* Option A: No locking — accept last-write-wins
* Option B: `SELECT ... FOR UPDATE` alone, as the mechanism for every
  concurrency case including sweep-vs-operator
* Option C: Query-level visibility filtering — hide a suppressed employer's
  postings from list/detail views for the duration of the sweep
* Option D: Row locking for same-row write/write races (double-click, sweep
  racing a direct write to the same posting), **plus** making the sweep
  itself a single atomic transaction so there is no partially-applied state
  for any reader to observe, locked or not

## Decision Outcome

Chosen option: **"Option D"**. The two remaining concurrency cases in this
system's actual scope need two different mechanisms, not one:

1. **A single operator's duplicate request on the same posting**
   (double-click, two tabs) is a genuine write/write race between two
   transactions that both intend to mutate the same row. `SELECT ... FOR
   UPDATE` is the right tool here: the second transaction blocks until the
   first commits, then reads the post-transition state, so its history row
   correctly reports the first transition's outcome as its own
   `previous_status`.

2. **The suppression sweep vs. any reader or writer of the affected
   postings** is not actually a write/write race in the same sense — the
   sweep needs to be *invisible until complete*, not merely serialized
   against. A lock only constrains other **writers**; it does nothing for a
   **reader** (the list view, `queries.list_postings`), which takes no lock
   and would simply read whatever is currently committed. If the sweep
   commits the employer's `suppressed` flag and then, in a second
   transaction, rejects each posting — as `blacklist()` originally did — a
   reader in the gap between those two commits sees a real, committed,
   inconsistent state: an employer already suppressed whose postings still
   read `new`. No lock prevents that, because a plain read was never
   blocked by the writer's lock to begin with.

   The fix is therefore not a lock but a transaction boundary:
   `blacklist()` now flips `employer.suppressed` and rejects every one of
   its postings inside **one** transaction, **one** `commit()`. Under
   PostgreSQL's default READ COMMITTED isolation, no other transaction can
   ever see this operation's intermediate state — only its state before the
   commit, or its state after. "Postings not shown until the sweep
   finishes" falls directly out of that: there is no window in which they
   could be shown half-swept, because that state is never durable. This is
   what makes the operation linearizable — it appears to every observer as
   a single, indivisible point in time, not because of an added visibility
   filter, but because it truly is one atomic write.

   `FOR UPDATE` is still taken inside that transaction (`id`-ascending, see
   below) — not to protect against a reader, but for the same reason as
   case 1: it protects against a concurrent *write* to one of the same
   posting rows, e.g. an operator's direct `set_status` call landing on a
   posting the sweep is simultaneously rejecting.

3. **Deadlock avoidance between multi-row lockers.** `set_status_bulk` and
   the sweep's row selection (`blacklist._reject_employer_postings`) both
   lock in `id`-ascending order, so two such operations can never acquire
   the same two rows in opposite order and cycle.

4. **Behavior under the SQLite test backend.** `.with_for_update()` compiles
   to a no-op under SQLite; the atomicity half of the fix (case 2) does not
   depend on it — a single `session.commit()` is one transaction under any
   backend, including SQLite, so the linearizability guarantee is exercised
   correctly in tests even though real row-level blocking is not.

### Consequences

* Good, because the suppression sweep is now linearizable for the reason
  that actually matters for a reader: it is one transaction, so no
  intermediate state is ever committed for anyone to observe. This closes a
  real gap — `blacklist()` previously committed the `suppressed` flag and
  the postings' rejection separately.
* Good, because the remaining, narrower same-row write/write race
  (double-click; sweep vs. a direct concurrent write to one of its own
  postings) is still covered by `FOR UPDATE`, with `id`-ascending order
  removing deadlock risk between the two multi-row lockers.
* Good, because dropping "two operators on the same queue" as a design
  driver keeps the fix proportionate — no version columns, no retry
  handling, no cross-process coordinator, for a race this system does not
  actually need to survive.
* Bad, because `FOR UPDATE`-held locks still have no timeout — a stalled
  transaction blocks another writer to the same row for the stall's
  duration. Accepted: rare and short-lived in a single-operator, request-scoped
  application.
* Bad, because SQLite's lack of row locking means case 1 and the
  writer-vs-writer half of case 2 are exercised for shape/regressions only,
  not for real blocking behaviour, under this project's test suite.

## Pros and Cons of the Options

### Option A: No locking

* Good, because it's the simplest possible implementation.
* Bad, because it reintroduces both remaining races: a lost transition on
  double-click, and — separately — does nothing about the sweep's
  transaction-boundary gap, which isn't a locking problem at all.

### Option B: `FOR UPDATE` alone, relied on for every case including the sweep

* Bad, because it doesn't actually solve the sweep's visibility problem —
  the original two-commit `blacklist()` could have every row-level lock in
  the world and a reader would still observe the gap between commit one and
  commit two, since reads take no lock. This was the option first reached
  for, and the flaw only became visible on rechecking what a *reader*
  (not another writer) can observe.

### Option C: Query-level visibility filtering

* Good, because it would also hide a mid-sweep employer's postings from the
  list view.
* Bad, because it treats the symptom rather than the cause: it would need
  every current and future read path (list, detail, totals, facets,
  reports) to remember to apply the same filter, whereas making the sweep
  one transaction removes the inconsistent state at its source — nothing
  downstream needs to know this case exists at all.
* Bad, because it does nothing for direct reads of `posting.status` itself
  (e.g. a future API or report) unless *that* path also applies the filter
  — the atomicity fix has no such gap since there is no inconsistent row
  to read, filtered or not.

### Option D: Row locking for writer/writer races + one-transaction sweep (chosen)

* Good, because each mechanism is applied to the case it actually solves —
  locking for write/write races, a single commit for reader-visible
  atomicity — rather than stretching one mechanism to cover both.
* Good, because the sweep's guarantee holds for *every* reader, present and
  future, with no per-query opt-in required.
* Neutral, because it is two changes instead of one, but each is small: a
  lock-order convention already established, and collapsing two existing
  `commit()` calls into one.
