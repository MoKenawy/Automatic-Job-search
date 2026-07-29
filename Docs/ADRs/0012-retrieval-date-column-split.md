# ADR-0012: Split `last_seen_at` into `updated_at` and `last_retrieved_at`

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 27 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | [ADR-0009](0009-last-seen-at-contamination-detection.md)'s Decision — the detection heuristic it adopted solves a problem this record removes at the schema level instead. ADR-0009's comparison of alternatives is retained as a record of what was considered. |
| **Related** | [ADR-0008](0008-report-system-scope.md) R2; [ADR-0010](0010-r2-span-computation-strategy.md); [db/models.py](../../app/src/app/db/models.py); migration `cb39b32a6843` |

---

## Context

ADR-0009 detected — after the fact, by heuristic — which historical rows of a
single `last_seen_at` column held a board's last observation and which held a
triage transition's timestamp instead. It worked, but it was solving a problem
this project had already solved once before by different means:
`status_changed_at` exists precisely because an earlier version of this same
column tried to carry two meanings at once and made `transition_to()` unable
to say honestly what it had stamped (refactor-plan.md §5). ADR-0009 accepted
that same conflation as a fact to be worked around rather than a defect to be
removed, on the (unstated) assumption that removing it would mean editing
history.

It does not. The two meanings a single column was carrying —
*a board last confirmed this posting exists* and *this row was last written
to, for any reason* — are genuinely different facts about a posting, and nothing
requires them to share a column. Splitting them removes the need for a
detection heuristic at all: a column written from exactly one place needs no
inference about what wrote it.

## Decision

**Two columns, not one.**

`updated_at` — the renamed original column, `onupdate=func.now()` restored
exactly as it always ran. Its history is untouched: every value already
written under the name `last_seen_at` keeps its meaning and simply moves with
the rename. This is the same "row last modified" bookkeeping
`SearchProfile.updated_at` and `AppSetting.updated_at` already provide
elsewhere in this schema — naming it consistently was the fix, not changing
what it does.

`last_retrieved_at` — new, nullable at no point, written only inside
`Posting.observe()`. No `onupdate`. Nothing else may write it, by
construction rather than by convention, which is what makes ADR-0009's
heuristic unnecessary: there is no second writer for it to be confused with.

**Backfill, not a guess.** Migration `cb39b32a6843` sets every existing row's
`last_retrieved_at` to that row's own `first_seen_at` — not to the
migration's run time, and not left `NULL`. Both alternatives were considered
and rejected:

- A single `now()` for every historical row would assert every posting in the
  table was re-observed at the moment of migration, which is not a fact this
  system has and would be worse than the defect being fixed.
- `NULL` is honest but pushes the "what do we actually know" question into
  every reader of the column instead of answering it once, in the migration,
  from a fact already on hand.

`first_seen_at` is a real, already-recorded fact: every row was retrieved at
least once, at that moment. Stating that as the floor is not a guess in the
sense §4.3 warns against — it is the most recent thing actually known, stated
as exactly that and no more, which is the same shape as R2's own "every span
is a lower bound" caveat already planned for the report this column feeds.

## Consequences

*Favourable:*

- ADR-0009's excluded-row bookkeeping — the near-equality window, the
  "excluded count" the report had to surface, the note that its accuracy
  should be watched over time — is no longer needed. A schema fix beats a
  runtime heuristic wherever both are available, because the heuristic has to
  be re-verified as correct while the schema fix is simply true.
- `last_retrieved_at` reads unambiguously as of the day this migration ships.
  No future contributor can repeat this session's original mistake against
  it, because nothing but `observe()` has ever written to it.
- The rename costs nothing in lost history — `updated_at` carries forward
  every value `last_seen_at` ever held, under its accurate name.

*Unfavourable, and accepted:*

- A real migration, where the prior attempt needed none. `ALTER TABLE ...
  RENAME` plus an added column is inexpensive on a table at this project's
  current and near-term scale, so the cost is real but small.
- `last_retrieved_at`'s backfilled values are, for every pre-migration row,
  identical to `first_seen_at` until that row is next re-observed — a
  temporary flat floor across historical data, not a defect, but worth
  knowing when reading early R2 output: the "how long has this been live"
  question is uninformative for any row that has not yet been seen again
  since this migration.
- Any code, dashboard, or export outside this repository that referenced the
  column as `last_seen_at` breaks silently rather than loudly. Confined
  in-repo to `Posting.observe()` and one template line, both updated with this
  change; nothing external is known to exist, since the web UI has been the
  system's only surface since ADR-0004.

## Control

ADR-0009's alternatives (A/C/D) remain the correct reference if a future
column is ever tempted to carry two meanings again. Its erratum records a
further reason B specifically should not be reached for: it compared a
timestamp written by the application process (`status_changed_at`, Python's
`datetime.now(UTC)`) against one written by the database server
(`last_seen_at`'s `onupdate=func.now()`, PostgreSQL's `NOW()`) — two
independently clocked services per `docker-compose.yml`, not one clock with
jitter. That mismatch let a genuinely contaminated row read as clean under
ordinary clock skew, the opposite of what the option claimed. Any row-level
heuristic revisited later needs both compared timestamps sourced from the
same clock, which this schema-level fix sidesteps entirely by removing the
comparison rather than trying to make it safe.
