# Design Document — System Guarantees for Triage and Suppression

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 14 August 2026 |
| **Status** | Approved |
| **Related** | [ADR-0013](../ADRs/0013-posting-status-history.md), [ADR-0014](../ADRs/0014-status-transition-row-locking.md), [ADR-0015](../ADRs/0015-employer-level-suppression.md), [suppression-concurrency-review.md](suppression-concurrency-review.md) §6, [db/visibility.py](../../app/src/app/db/visibility.py) |

---

## 1. Purpose

Formalises the guarantees the triage/suppression system makes, as scoped by
[suppression-concurrency-review.md](suppression-concurrency-review.md) §6 and
revised for the model [ADR-0015](../ADRs/0015-employer-level-suppression.md)
implemented: suppression derived at read time from `employers.suppressed`,
never materialised onto `postings`.

The review's original §6 stated a **liveness** property for the materialised
model — "every posting of a suppressed employer eventually reaches
`suppressed`, bounded by the next pipeline run." That property does not
survive the reversal, and it is not replaced by a different liveness claim.
It is replaced by a **safety** property, because nothing converges any more:
there is no window, bounded or otherwise, in which a blacklisted employer's
posting is visible. It just never is.

---

## 2. Safety — nothing bad happens

- **No posting of a suppressed employer is ever visible through an adopting
  read path.** Not "eventually excluded" — never included, at any point after
  its employer is blacklisted, including a posting collected after the
  blacklist was applied and before any pass has run over it. This holds
  because visibility is computed from `employers.suppressed` at the moment of
  each read, not propagated onto the posting at some later moment.
- **No operator transition writes suppression as its reason.**
  `posting_status_history.actor` accumulates zero `'system'` rows over a full
  blacklist → collect → lift cycle (SC-004) — there is no sweep to write them.
- **Blacklisting and un-blacklisting each take effect as a single indivisible
  change.** Both are one-row flag flips, one commit; no reader can observe a
  partially-applied blacklist, because there is no second write to be
  partially applied against.
- **Every `status` change has exactly one history row, written in the same
  transaction as the row it accompanies** (ADR-0013, unchanged).
- **Invalid statuses produce zero side effects** — `transition_to` validates
  before mutating anything (ADR-0013, unchanged).
- **A single operator's duplicate request on the same posting cannot lose a
  transition.** `SELECT ... FOR UPDATE` in `triage.set_status` /
  `set_status_bulk` serializes it (ADR-0014's surviving half).

## 3. Explicitly not guaranteed

- **Read paths that decline the seam are not covered by these guarantees on
  purpose.** `queries.get_posting` (FR-015) and `reports.source_overlap`
  (FR-017) are deliberate, commented opt-outs — see
  [contracts/visibility-seam.md](../../specs/002-employer-suppression-derived/contracts/visibility-seam.md).
  A future read path that adds a query over `postings` without a row in
  [contracts/read-path-inventory.md](../../specs/002-employer-suppression-derived/contracts/read-path-inventory.md)
  is *not* covered — that is the one obligation ADR-0015 accepts as
  permanent, not something this document can discharge for it.
- **No read-your-writes across separate requests** (unchanged from the
  review).
- **Lock waits have no timeout** (accepted, ADR-0014).
- **SQLite tests exercise lock shape, never real blocking** (unchanged).
- **Historical postings rejected by the pre-ADR-0015 sweep carry irrecoverable
  ambiguity.** Which past `rejected` rows were operator decisions and which
  were sweep artefacts is not knowable (ADR-0015 §Migration, spec FR-016).
  These rows are left exactly as they are; lifting the employer's blacklist
  today does not distinguish them from an operator's own rejection, and
  cannot.

---

## 4. What changed from the pre-ADR-0015 model

| | Materialised (before) | Derived (after) |
|---|---|---|
| Where suppression lives | Copied onto `postings.status` | Only on `employers.suppressed` |
| How a new suppressed posting becomes invisible | A reconciliation pass must run and catch it | Never visible — nothing to catch |
| Bound on "the operator can no longer see it" | Next pipeline run (liveness, bounded) | None needed — it never appears (safety) |
| Failure mode if the mechanism is broken | Stale data — a posting the sweep missed | Missing filter — a read path that forgot the seam |

The last row is why §3 above calls out the seam's opt-out protocol explicitly:
centralising the filter does not eliminate the risk of this design, it
relocates it. This document records the guarantee the relocation buys, not a
claim that the risk is zero.
