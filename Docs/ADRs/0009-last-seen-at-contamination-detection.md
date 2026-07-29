# ADR-0009: Detecting `last_seen_at` contamination for R2

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 27 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | Refines [Reports implementation plan](../design/reports-implementation-plan.md) §2, which proposed one option without comparing it against alternatives |
| **Related** | [ADR-0008](0008-report-system-scope.md) R2; [ADR-0012](0012-retrieval-date-column-split.md), which supersedes this record's Decision; [db/models.py](../../app/src/app/db/models.py) `Posting.observe`, `Posting.transition_to`; [pipeline/normalise_stage.py](../../app/src/app/pipeline/normalise_stage.py) |

---

> **Superseded by [ADR-0012](0012-retrieval-date-column-split.md).** This
> record's Decision (§ below) was never implemented: before
> `posting_longevity()` was built, the column itself was split into
> `updated_at` and `last_retrieved_at`, which removes the need for a
> detection heuristic entirely rather than refining one. Everything from
> **Decision** onward — including the "no migration, no new column" line
> under Consequences — describes that abandoned approach and does **not**
> reflect the current schema; a migration and a new column are exactly what
> ADR-0012 adds instead. Kept unedited, per this project's immutable-once-accepted
> convention for ADRs, because the **Context** and **Options considered**
> sections below remain the correct reference for comparing "detect
> after the fact" against "redesign the column" the next time a column is
> tempted to carry two meanings at once. Reading them: every `last_seen_at`
> below is the single, still-overloaded column as it stood at the time this
> was written — the observation-tracking half of what it meant is now
> `last_retrieved_at`; the generic any-write half is now `updated_at`.

> **Erratum — Option B's central safety claim does not hold.** The Decision
> below states "a false positive is not possible" and "cannot over-trust a
> contaminated row." That is wrong, independent of being superseded, and the
> error is worth recording since this file is kept as a reference.
>
> `status_changed_at` is written from `datetime.now(UTC)` — an application-process
> clock reading, taken in `triage.py` before commit. `last_seen_at`'s
> `onupdate=func.now()` compiles to PostgreSQL's own `NOW()`, evaluated by the
> *database* process at UPDATE time. Per `docker-compose.yml`, `postgres` and
> `web`/`scheduler` are separate services — two independently clocked
> machines, not one. "Near equality within a few seconds" is a claim about
> clock agreement between them that nothing in this system establishes or
> guarantees; container and VM clock drift routinely exceeds a few seconds
> without either host being considered broken.
>
> The consequence is exactly backwards from what Decision claims: under
> skew, a row that **is** genuinely contaminated — both fields written in the
> one buggy transaction, no re-observation since — can show an apparent gap
> *larger* than the window purely because the two clocks disagree, causing B
> to clear it as clean. That is over-trusting a contaminated row, the one
> failure Decision calls impossible.
>
> This does not extend to R3's same-run tie handling: `normalise_stage.py`
> computes one `now = datetime.now(UTC)` and writes that single Python value
> into every provenance entry touched in that call, so R3 compares one clock
> reading against copies of itself, never two independently sampled clocks.
> Option D above is less exposed than B but not immune either: its lower
> bound (`runs.started_at`) shares `last_seen_at`'s database-clock source
> exactly, but its upper bound (`runs.finished_at`) is written by
> `datetime.now(UTC)` in `runner.py` — application-clock, the same mismatch
> as B, confined to one edge of a window normally wide enough to absorb it.
> None of this changes ADR-0012's outcome, which was already correct for an
> independent reason — a column written from exactly one place needs no
> timestamp inference at all — but a future reader should not treat B as a
> safe fallback for a different problem without re-deriving both compared
> timestamps from the same clock first.

## Context

`Posting.last_seen_at` carried `onupdate=func.now()` until this session, which
meant SQLAlchemy added `last_seen_at = now()` to the SET clause of every UPDATE
against the row — not only the collector's own writes. Confirmed empirically:
a posting inserted with `last_seen_at = 2020-01-01`, then moved through
`transition_to()`, came back stamped with the current time. The existing test
that appeared to guard this (`test_transition_to_stamps_status_changed_at_but_not_last_seen_at`)
asserts against a detached `Posting()` with no session attached, so no UPDATE was
ever emitted and the defect never fired inside the test. It passed while the
column was broken.

The column has been corrected — `onupdate` removed, `observe()` retains its
explicit assignment — so no *new* contamination can occur. But rows written
before the fix landed may already hold a `last_seen_at` that reflects an
operator's triage action rather than a board's last re-observation, and that
history cannot be edited back into correctness after the fact: the true value
was never recorded anywhere once the buggy write overwrote it in place.

R2 (posting longevity and repost detection) is built directly on
`last_seen_at - first_seen_at`. Reported without correction, a contaminated
row's span is not just noisy but wrong in a specific direction — inflated
toward "still live" for a role that may have stopped being observed weeks
earlier, which is precisely the ghost-posting signal R2 exists to surface. An
undetected contaminated row produces the opposite of the report's purpose.

The reports plan's §2 proposed one detection rule — exclude any row where
`status_changed_at` is non-null — and flagged it as imprecise without
comparing it to alternatives. This ADR does that comparison.

## Options considered

**A — Exclude on `status_changed_at IS NOT NULL`** (the plan's original
proposal). Any row ever triaged is treated as suspect, permanently.

*Rejected.* Once a posting is triaged even once, it never returns to the
report, whether or not that triage actually damaged the row. Since the
operator is expected to triage most published postings, the excluded fraction
grows toward the whole table over time — the report would shrink in exact
proportion to how much the system gets used, which is backwards for a report
meant to run indefinitely.

**B — Near-equality of `last_seen_at` and `status_changed_at`.** Flag a row as
contaminated when the two timestamps fall within a short window (a few
seconds) of each other, since the bug wrote both from the same `now()` inside
one transaction.

*Correctly handles the case Option A gets wrong:* if a genuine re-observation
occurred after a (buggy) triage write, `observe()` always assigns
`last_seen_at` explicitly, so the two columns diverge again and the row
correctly reads as clean — the contamination self-heals the moment a real
observation lands on top of it, without needing to know when the code fix
shipped.

*Two failure modes, both narrow.* A false negative: a row triaged exactly once
and never re-observed since, where the operator's action coincidentally lands
within the same window as a genuine same-run collection write — the same class
of race the R3 tie-handling already exists to treat honestly rather than paper
over. A false positive is not possible in the other direction: two independent
real events landing within seconds of each other still describes a real state,
so flagging it merely under-counts rather than mis-reports.

**C — Deploy-time cutoff.** A literal constant recording when the fix shipped;
exclude rows whose `status_changed_at` predates it.

*Rejected as the primary rule, on the same failure this ADR checked B
against:* a row triaged before the fix but genuinely re-observed afterward is
clean — `observe()`'s explicit assignment overwrote the buggy stamp — yet a
pure date cutoff has no way to see that and would exclude it anyway. Coarser
than B for no accuracy gain. This project already uses literal measured-date
constants freely elsewhere (`WORKING_SITES`, D13's 20 July measurement), so
the pattern itself is not the objection — only using it as the sole test here,
where a more precise signal already exists.

**D — Cross-reference against `runs`.** `last_seen_at` can only be
legitimately written from inside `observe()`, which runs only inside
`normalise_stage.run_normalise`, itself only invoked from a pipeline run. A
row's timestamp is therefore ground-truth-clean only if it falls within some
recorded run's `[started_at, finished_at]` window; a value outside every
known window could only have been written by a non-collection code path.

*The most rigorous option, and the most expensive.* It needs a range-membership
test against `runs` per posting rather than a same-row comparison, and
`normalise_stage`'s internal `now()` is computed after `run_collect` finishes
within the same run, so the window must be `[started_at, finished_at]` rather
than a point — collection can take a noticeable slice of a run's duration, and
treating the window as a single instant would manufacture false positives
against genuinely clean rows.

## Decision

**B, with D as a defensive cross-check available if B's judgement is ever
challenged, not run by default.**

B is adopted as the sole automatic filter in `posting_longevity()`. It is
self-limiting in the way A is not — the excluded set does not grow with
operator usage, only with actual contamination — and it is exact in the one
case that matters most: a row corrected by a real subsequent observation is
never wrongly excluded, since the fix already guarantees `observe()` always
writes the timestamp explicitly regardless of what a prior buggy transition
left behind.

D is recorded rather than built now because it answers a question B does not
need answered for the report to be honest: B can under-count (exclude a
handful of coincidental same-second rows) but cannot over-trust a contaminated
row, which is the only direction of error R2 cannot tolerate. D is the tool to
reach for if that assumption is ever doubted — e.g. spot-checking a specific
employer's numbers — not a second filter run on every request.

**Implementation.** `posting_longevity()` computes
`abs(last_seen_at - status_changed_at) < CONTAMINATION_WINDOW` (proposed: 5
seconds — generous against clock and transaction-commit jitter, tight against
any real gap between two independent events) only for rows where
`status_changed_at` is not null, and reports the excluded count alongside the
included ones rather than silently dropping it, consistent with ADR-0008 §1's
bias-must-be-shown criterion.

## Consequences

*Favourable:*

- The report stays viable indefinitely under normal operator use, which
  Option A did not.
- No migration, no new column, no backfill — the whole fix is a comparison
  inside the aggregation function.
- The excluded-count figure doubles as a decaying indicator of how much
  pre-fix contamination remains in the table, without any separate tracking.

*Unfavourable, and accepted:*

- The rare same-second coincidental race is undercounted rather than shown.
  Accepted for the same reason the R3 tie category is accepted: an honest
  "we can't tell" is preferable to an arbitrary tiebreak, and the cost here is
  a handful of rows missing from a report, not a wrong number.
- Nothing repairs the historical rows; B only decides which ones to trust for
  display. If a specific employer's longevity numbers are ever load-bearing
  for a decision, run D against it by hand rather than trusting the aggregate
  blindly.

## Control

Reviewed if the excluded-row count fails to trend toward zero over a few
weeks of normal triage — that would mean B's window is systematically missing
cases, and D should be built as the default check rather than the fallback.
