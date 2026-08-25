# ADR-0015: Employer-level suppression, derived at read time

* Status: accepted
* Deciders: Mohammed
* Date: 11 August 2026

Technical Story: a concurrency review of the triage/suppression paths
(`Docs/design/suppression-concurrency-review.md`) traced a family of races —
sweep atomicity, lost transitions, a corrupted audit trail, an unrecoverable
`lift()` — to a single modelling decision rather than to a locking defect.
This record reverses that decision. Supersedes parts of
[ADR-0014](0014-status-transition-row-locking.md); see *Relationship to
ADR-0013 and ADR-0014* below.

## Context and Problem Statement

`postings.status` currently carries two independent facts:

| Fact | Owner | Nature |
|---|---|---|
| "What does the operator think of this posting?" | Operator | Primary — exists nowhere else |
| "Is this posting's employer blacklisted?" | System | **Derived** — already fully determined by `employers.suppressed` |

The second is a materialised copy. `employers.suppressed` is the source of
truth, and a sweep pushes that fact down into every one of the employer's
posting rows as `status = 'rejected'`. Two copies of one fact, in two tables,
that can disagree.

Every problem the concurrency review found is a consequence of that
redundancy, not of insufficient locking:

- **Sweeps exist at all** — a materialised copy must be propagated
  (`blacklist()`) and repaired when it drifts (`run_suppress`).
- **The sweep must be transactionally atomic** — propagating to N rows
  alongside the flag flip is a multi-row write a reader can otherwise catch
  half-applied.
- **Operator writes race system writes** — both write the same column, so an
  operator can silently overwrite a suppression they were never shown, and the
  sweep can silently revert a deliberate operator decision on the next run.
  Neither party can recover the other's intent, because on disk the two cases
  are identical.
- **The propagation is destructive** — it overwrites the operator's judgement,
  so there is no inverse operation and `lift()` cannot restore it.

**This was not the original design.** `Docs/job-discovery-pipeline-design.md`
§8.1 (D15) states:

> Rejected is the suppression mechanism required by D9 [...] so a separate
> suppression flag on the posting is unnecessary. **Employer-level suppression
> remains distinct, since it must exclude every posting from that employer
> including ones not yet seen.**

The materialisation was introduced later, in
`specs/001-ui-self-service/data-model.md`, on the grounds that `rejected`
"already carries the 'never resurfaces' guarantee (D9)" and therefore required
**no schema change and no read-path change**. No ADR recorded the reversal.

That justification does not survive inspection: deriving requires *zero* new
columns — `employers.suppressed` already existed and, per that same spec, was
"column exists, read nowhere." The actual driver was avoiding changes to read
paths. The unpriced cost was the reconciliation machinery: `run_suppress`, the
sweep's transaction boundary, row locking, ADR-0013, ADR-0014, and this record.

Note also that §8.1's own justification for keeping the mechanisms distinct —
suppression must cover postings *not yet seen* — is exactly why `run_suppress`
must exist. A materialised flag can only apply to rows that already exist, so
something must run after every collection to catch up. The reconciliation pass
is a patch for the precise mismatch the design record identified in advance.

## Decision Drivers

* **Eliminate a class of races rather than patch instances of it.** Three ADRs
  and a full review have gone into defending a redundancy that need not exist.
* **Restore the design record's §8.1 intent** — employer-level suppression as a
  mechanism distinct from operator triage.
* **Keep `posting_status_history` a pure record of operator intent** (ADR-0013).
  It is currently polluted with `actor='system'` suppression rows that answer a
  question the employer row already answers.
* **Preserve D9** — rejected postings retained indefinitely, never resurfacing.
* **Proportionate to a single-operator, low-traffic tool.** No retry loops, no
  version columns, no coordinators.
* **Migration must not destroy operator intent** that cannot be recovered.

## Considered Options

* **Option A** — Status quo: materialised copy, defended by row locking and a
  one-transaction sweep (ADR-0014 as implemented).
* **Option B** — A distinct `suppressed` status the operator's write refuses to
  overwrite, guarded on `employer.suppressed`.
* **Option C** — `postings.suppressed` boolean, orthogonal to `status`.
* **Option D** — Suppression lives only on `employers.suppressed`, derived at
  read time by joining. **(chosen)**

## Decision Outcome

Chosen option: **Option D**.

`postings.status` reverts to operator judgement only — `new`, `shortlist`,
`applied`, `rejected` — with `services/triage.py` as its sole writer.
Suppression is never written to a posting. Whether a posting is out of play
because of its employer is answered at read time from `employers.suppressed`.

Consequently:

1. **`pipeline/suppress_stage.run_suppress` is deleted.** There is no
   materialised copy to reconcile, so there is no reconciliation pass. The
   "covers postings not yet seen" requirement is satisfied structurally: a
   posting collected tomorrow from a blacklisted employer is filtered on the
   day it appears, with nothing needing to run.
2. **`blacklist()` and `lift()` become single-row flag flips.** One row, one
   commit, atomically visible to every reader by construction. The
   transaction-boundary problem ADR-0014 solved becomes vacuous rather than
   solved.
3. **`_reject_employer_postings` and `reject_employer_postings` are removed.**
4. **Read paths filter through one shared seam**, not per-query discipline —
   a single filtered base query (or view) that list, detail, publication,
   reports, and the future scoring stage all start from. This is the real cost
   of the decision and the place it can go wrong; it is contained deliberately
   in one place.
5. **Publication (FR-009) becomes a derived filter too.** The sweep previously
   forced `published = false`; that condition moves into the same seam.

### Migration: a deliberate no-op on existing rows

Postings already set to `rejected` by a past sweep are **left as they are**.
Which historical rejections were suppression-driven is not recoverable:
`posting_status_history` is new (ADR-0013) and its backfill writes a single
synthetic baseline row per posting with `previous_status = NULL`, so it cannot
attribute pre-existing rejections. Rewriting them would risk resurfacing
postings the operator genuinely rejected.

Leaving them is safe and loses nothing: those postings are already hidden, and
FR-011 already states that lifting a blacklist does not reinstate previously
rejected postings. The migration is therefore schema-only — no data rewrite,
no risk, no downgrade hazard.

The consequence to accept: **historical and future blacklists behave
differently on lift.** Postings suppressed before this change stay rejected
after a lift; postings suppressed after it reappear with their operator status
intact. This is an honest artefact of intent that was destroyed before it could
be recorded, not a design inconsistency going forward.

### FR-011 becomes a display decision

FR-011 ("previously rejected postings are NOT reinstated") was, under
materialisation, a statement about data that had been overwritten. Under
derivation nothing is overwritten, so lifting a blacklist restores the
employer's postings to visibility with their prior triage status. If dumping a
back catalogue into the queue is unwanted, that is now a **UI choice made with
full information** — default-hide on lift with an explicit restore action, or a
date filter — rather than an irreversible mutation. The SRS wording needs
updating to match; this ADR does not silently redefine it.

## Consequences

*Favourable:*

- The race class disappears rather than being defended. Case B — an operator
  unknowingly reversing their own standing instruction — becomes structurally
  impossible, because operator and system no longer write the same field.
- `posting_status_history` becomes what ADR-0013 intended: a record of operator
  intent, uncontaminated by system rows restating the employer's flag.
- `blacklist()`/`lift()` are trivially atomic and trivially reversible.
- The deadlock-ordering convention has only one remaining multi-row locker
  (`set_status_bulk`), so the ordering constraint is satisfied by a single
  call site rather than a convention three paths must remember.
- Suppression applies to postings not yet collected with no machinery at all.

*Unfavourable, and accepted:*

- Every read path must go through the filtered seam. Forgetting it silently
  resurfaces blacklisted employers — the failure mode moves from "stale data"
  to "missing filter." Mitigated by centralising it, but it is a real,
  permanent obligation and the strongest argument against this option.
- Reports and any future direct database consumer must apply the same filter or
  knowingly opt out.
- Historical postings carry irrecoverable ambiguity between operator rejection
  and sweep rejection (see migration above).
- FR-011 and the §8.1/`001-ui-self-service` documents need updating; the
  reversal must be recorded rather than left as drift, which is the purpose of
  this ADR.

## Relationship to ADR-0013 and ADR-0014

**ADR-0013 (status history) stands, and improves.** The history table, its
transactional coupling to `transition_to()`, and its `actor`/`reason` columns
are unchanged. With suppression removed from the status vocabulary, `actor`
distinguishes operator paths from future automated ones without the sweep
dominating the table.

**ADR-0014 is partly superseded.** What survives:

- `SELECT ... FOR UPDATE` in `triage.set_status` — the single-operator
  duplicate-request race (double-click, two tabs) is unaffected by this ADR and
  remains real.
- `FOR UPDATE ... ORDER BY id` in `triage.set_status_bulk`.

What becomes moot:

- ADR-0014's case 2 in full — the suppression sweep's linearizability, the
  reader-visibility gap, and the single-transaction fix for `blacklist()`. With
  no rows to propagate to, a one-row flag flip is atomic without argument.
- The `id`-ascending lock-ordering convention as a *multi-path* agreement.
- The unreviewed gap in `pipeline/suppress_stage.run_suppress`, which had
  neither lock nor ordering: the file is deleted.

## Control

If a future requirement needs to know *when* an employer was blacklisted, or to
report on suppression over time, add that to the employer record or an employer
history table — do not reintroduce a per-posting copy. The invariant this ADR
establishes is that **suppression is a property of an employer, and postings
are filtered by it, never stamped with it.**
