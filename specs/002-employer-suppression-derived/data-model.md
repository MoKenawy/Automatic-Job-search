# Data Model: Employer-level suppression, derived at read time

**Feature**: [002-employer-suppression-derived](spec.md) | **Date**: 13 August 2026

**No schema change.** Every table, column, and index below already exists. What
changes is *what they mean* and *who is allowed to write them* — which is the
entire content of this feature, and the reason a document that adds no columns is
still worth writing. Verification that the schema is genuinely untouched is a
plan deliverable (research R5), not an assumption.

---

## Entities

### `employers`

| Field | Type | Meaning after this change |
|---|---|---|
| `id` | int PK | — |
| `name`, `normalised_name` | str | — |
| `suppressed` | bool, not null, default false | **The single authoritative record of blacklist state.** Previously the source of truth for a value also copied onto every posting; now the only place it exists |

**Index**: `ix_employers_suppressed` — partial, `WHERE suppressed = true`. Already
present. Serves the seam's `EXISTS` subquery under PostgreSQL. A performance
aid only: at NFR-1 volume (under one hundred postings) correctness does not
depend on it, and SQLite ignores the partiality.

**Writers**: `services/blacklist.blacklist()` and `services/blacklist.lift()`,
each now a single-row flag flip — one row, one commit, atomically visible to
every reader by construction. The transaction-boundary problem ADR-0014 solved
becomes vacuous rather than solved.

**Invariant (ADR-0015 §Control)**: *suppression is a property of an employer, and
postings are filtered by it, never stamped with it.* If a future requirement
needs to know **when** an employer was blacklisted, that belongs here or on an
employer history table — never as a per-posting copy.

---

### `postings`

| Field | Type | Meaning after this change |
|---|---|---|
| `id` | int PK | — |
| `employer_id` | int FK → `employers.id`, not null | The link the seam correlates on. Non-nullable, so the `EXISTS` can never be indeterminate |
| `status` | str(16), not null, default `new`, indexed | **Operator judgement only** — `new`, `shortlist`, `applied`, `rejected`. Previously also carried "this employer is blacklisted" |
| `status_changed_at` | timestamptz, nullable | When `status` last changed **through an operator transition**. NULL now means only "never triaged" |
| `published` | bool, not null, default false, indexed | Unchanged as a column. No longer forced to `false` by suppression — a published posting of a newly blacklisted employer keeps `published = true` on the row and is hidden by the seam instead |
| `score`, `sources`, `country_code`, … | — | Untouched by this feature |

**Sole writer of `status`**: `services/triage.py`, via `Posting.transition_to()`.
This is the change stated as a rule. Before it, three call sites wrote `status`
on suppression grounds — `pipeline/suppress_stage.run_suppress`,
`services/blacklist._reject_employer_postings`, and `Posting.create` (which
birthed a posting `rejected` when its employer was already suppressed). All
three are removed.

**Removed method**: `Posting.reject_for_suppression()`. It was the only caller of
`transition_to(..., actor="system", reason="employer suppressed")`.

**Changed method**: `Posting.create()` always births `STATUS_NEW`. It no longer
consults `employer.suppressed`.

---

### `posting_status_history`

Schema unchanged; ADR-0013's contract stands intact. What changes is the
population.

| Field | Meaning after this change |
|---|---|
| `actor` | `'operator'` (web UI action) or `'migration'` (synthetic baseline row). **`'system'` stays a valid value with no writer** — it is reserved for future automated paths, and the suppression sweep that used to dominate it is gone |
| `reason` | Free text. `'employer suppressed'` no longer occurs |

This is ADR-0013's stated intent finally realised: the table becomes a record of
operator intent, uncontaminated by system rows restating a flag the employer row
already holds.

---

## The derived property

Not a column. Computed per read:

```
posting is employer-suppressed  ⟺  EXISTS (
    SELECT 1 FROM employers
    WHERE employers.id = postings.employer_id
      AND employers.suppressed = true
)
```

Expressed once, in `app/src/app/db/visibility.py` as `not_suppressed()`. See
[contracts/visibility-seam.md](contracts/visibility-seam.md) for the contract and
[contracts/read-path-inventory.md](contracts/read-path-inventory.md) for who
applies it.

---

## State transitions

**Before** — two actors writing one field, neither able to recover the other's
intent, because on disk the two cases are identical:

```
  operator ──set_status──────────────┐
                                     ├──▶ postings.status
  system   ──run_suppress─────────────┤        (contested)
           ──blacklist() sweep───────┘
           ──create(born rejected)───┘
```

**After** — one actor, one field; visibility is a separate axis computed at read
time:

```
  operator ──set_status──▶ postings.status   (uncontested)

  operator ──blacklist()/lift()──▶ employers.suppressed ──┐
                                                          ├──▶ visible?
                              postings.employer_id ───────┘   (per read)
```

### Consequences that fall out of the diagram

**Blacklist → lift is now reversible.** Nothing was overwritten, so nothing needs
restoring: a `shortlist` posting comes back as `shortlist`. This inverts 001's
FR-011 (spec FR-012).

**Suppression covers postings not yet collected, with no machinery.** A posting
stored tomorrow from a blacklisted employer is filtered on the day it appears,
because visibility is evaluated against `employers.suppressed` at read time and
never stamped at write time. The reconciliation pass that existed solely to catch
up on this requirement has nothing left to do (spec FR-003).

**Publication exclusion moves from write time to read time.** Previously
`transition_to` unconditionally cleared `published` on entering `rejected`, which
made FR-009 a side effect of the sweep. Nothing enters `rejected` on suppression
now, so the exclusion is the seam's job. This is latent today — stage 4 does not
exist and nothing sets `published = true` — but `list_postings(published_only=True)`
is a live filter, which is why it must adopt the seam, and why stage 4 must adopt
it both when selecting candidates and when writing `run.published_count`
(spec FR-009, FR-011).

---

## Validation rules

| Rule | Source | How it is checked |
|---|---|---|
| No write to `postings.status` may cite employer suppression as its reason | FR-002 | `posting_status_history` accumulates zero rows with `actor='system'` over a full blacklist/collect/lift cycle (SC-004) |
| A posting of a suppressed employer is absent from every adopting read path | FR-006 – FR-009 | One invisibility test per read path, so removing the filter from any single path fails the suite (SC-006) |
| Lifting restores prior status exactly | FR-012 | Round-trip test across all four statuses (SC-003) |
| Historical `rejected` rows are unmodified | FR-016 | No migration exists to modify them; verified by the empty autogenerate (research R5) |
| `employer_id` is never null | structural | Existing not-null constraint; the seam's correctness depends on it |
