# Implementation Plan — ADR-0015: Employer-level suppression, derived at read time

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 13 August 2026 |
| **Status** | Ready to implement |
| **Implements** | [ADR-0015](../ADRs/0015-employer-level-suppression.md) |
| **Related** | [ADR-0013](../ADRs/0013-posting-status-history.md), [ADR-0014](../ADRs/0014-status-transition-row-locking.md), [suppression-concurrency-review.md](suppression-concurrency-review.md) |
| **Branch** | `job-post-transitions` |

---

## 1. What this changes, in one paragraph

`postings.status` stops carrying employer-ban state. Nothing writes `rejected`
on account of a blacklist any more — not the pipeline, not `blacklist()`, not
`Posting.create`. Whether a posting is out of play because of its employer is
answered at read time from `employers.suppressed`, through **one predicate that
every read path applies**. `blacklist()` and `lift()` become single-row flag
flips. `pipeline/suppress_stage.py` is deleted.

The work is deliberately ordered so the new enforcement is in place and tested
**before** the old enforcement is removed. There is no commit in the sequence at
which a blacklisted employer's postings are visible.

---

## 2. The seam — the one decision this plan makes

ADR-0015 §Decision 4 requires "a single filtered base query (or view) that list,
detail, publication, reports, and the future scoring stage all start from", and
names it as the place the decision can go wrong. Two questions follow: where the
seam lives, and what shape it takes.

### 2.1 It lives in `db/`, not `services/`

The obvious home is `services/queries.py`, since that is today's read model. It
is the wrong one. `CLAUDE.md` and `refactor-plan.md` §7.2 fix the dependency
direction: `pipeline/` must not import `services/`. Stage 3 (scoring) and
stage 4 (publication) are `pipeline/` modules and are both named by ADR-0015 as
seam consumers — publication explicitly, in §Decision 5. A seam in `services/`
is a seam those two stages structurally cannot use, which guarantees the exact
failure ADR-0015 warns about: a read path that silently forgets the filter.

`db/` is depended on by both `services/` and `pipeline/`, and by neither's
prohibition. The seam goes in a new `app/src/app/db/visibility.py`.

### 2.2 It is a predicate, not a base query

```python
"""The single point at which employer suppression is enforced (ADR-0015).

Suppression is a property of an employer, never stamped on a posting, so every
read of `postings` that must respect the blacklist applies this predicate. If
you are writing a query over postings and not using it, that is a decision to
be justified in a comment, not an omission.
"""

from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Employer, Posting


def not_suppressed() -> ColumnElement[bool]:
    """True for postings whose employer is not blacklisted.

    A correlated NOT EXISTS rather than a join, so it composes with statements
    that do not already join `employers` (`totals`, `facets`) and cannot alter a
    row count on its own — a join added purely to filter is a join that can
    silently multiply rows if the cardinality assumption ever changes. The
    partial index `ix_employers_suppressed` serves the subquery; at NFR-1 scale
    the plan difference against a join is not measurable.
    """
    return ~(
        select(Employer.id)
        .where(Employer.id == Posting.employer_id, Employer.suppressed.is_(True))
        .exists()
    )
```

One idiom everywhere, including in the queries that already join `Employer` —
where it is redundant but free, and where using the join condition instead would
mean two idioms and a rule about which applies when.

**Rejected alternatives.** A database view: invisible to Alembic autogenerate,
needs hand-written migrations, and cannot be tested under SQLite the way the
rest of the suite is. A global `with_loader_criteria` event: enforces by magic,
so the one query that needs to opt out (reports) has to fight the framework, and
nothing in the code tells a reader the filter exists.

---

## 3. Read-path inventory

Every current query over `postings`, and what it does. **The opt-outs are as
much a part of this plan as the adoptions** — an unexamined query is the failure
mode, an examined one that declines the filter is a decision.

| Read path | File | Action |
|---|---|---|
| Triage list — page query and its count | [queries.py:184-200](../../app/src/app/services/queries.py#L184-L200) | **Adopt.** Both statements; the count must match the page or the pager lies |
| `published_only` filter | [queries.py:166](../../app/src/app/services/queries.py#L166) | **Adopt** (same statement). This is now FR-009's enforcement — see §6 |
| Dashboard totals — postings, published, scored, by_status | [queries.py:37-54](../../app/src/app/services/queries.py#L37-L54) | **Adopt** on each of the four |
| Dashboard totals — employers | [queries.py:52](../../app/src/app/services/queries.py#L52) | **Adopt**, but as `Employer.suppressed.is_(False)` — the predicate is over `postings` and does not apply to a count of employers |
| Facets — countries, unknown-country | [queries.py:224-240](../../app/src/app/services/queries.py#L224-L240) | **Adopt.** A facet derived from suppressed postings offers a filter that can only return an empty list |
| Posting detail | [queries.py:261](../../app/src/app/services/queries.py#L261) | **Deliberate opt-out.** [detail.html:14](../../app/src/app/web/templates/detail.html#L14) already renders the blacklist banner and the "Remove from blacklist" button — this page *is* the operator's route back out of a suppression, so filtering it would make lifting unreachable from the posting. Comment it as such |
| Blacklisted employers | [queries.py:269](../../app/src/app/services/queries.py#L269) | **No change** — selects suppressed employers by definition |
| R1 employer activity | [reports.py:83-112](../../app/src/app/services/reports.py#L83-L112) | **Already opts out knowingly**, via `include_suppressed` at the employer level. No code change; the docstring's "their postings are auto-rejected (D9)" becomes false and must be reworded |
| R3 source overlap | [reports.py:193](../../app/src/app/services/reports.py#L193) | **Deliberate opt-out.** It measures what the *collector* returned, not what the operator should see; filtering would understate a board's coverage. Comment it |
| Stage 3 scoring | not yet built | Must adopt — scoring a blacklisted employer's postings is wasted model time. Note it in the stage's plan |
| Stage 4 publication | not yet built | Must adopt — this is where FR-009 now lives |

---

## 4. Phases

### Phase 0 — Land the ADR-0014 baseline

The working tree holds the locking and `actor` fixes. Commit them first, on
their own, so history separates "we hardened the transitions" from "we removed
the thing that needed hardening".

- [ ] **0.1** Commit [triage.py](../../app/src/app/services/triage.py) — `FOR UPDATE`, `ORDER BY id`, `actor="operator"`. Survives ADR-0015 unchanged.
- [ ] **0.2** Commit [blacklist.py](../../app/src/app/services/blacklist.py) — the single-transaction sweep. Phase 2 deletes it; committing it anyway keeps the branch an honest record of a fix that was real when it was made, and avoids rewriting the working tree to pretend otherwise.
- [ ] **0.3** ADR-0013 → *Accepted*. ADR-0014 → *Accepted, partly superseded by ADR-0015*, with the surviving/moot split from ADR-0015 §Relationship copied into its header.

*Checkpoint: `uv run pytest` green, unchanged behaviour.*

### Phase 1 — Add the seam, while the old mechanism is still in place

Nothing is removed in this phase. Suppression ends up enforced twice — stamped
*and* filtered — which is exactly the condition under which the new enforcement
can be proven on its own.

- [ ] **1.1** Create [db/visibility.py](../../app/src/app/db/visibility.py) with `not_suppressed()` as in §2.2.
- [ ] **1.2** New `tests/test_visibility.py`: the predicate selects a normal employer's posting, rejects a suppressed employer's posting, and — the case that matters — **rejects a suppressed employer's posting whose `status` is still `new`**. That test fails today for the right reason: it is the assertion the whole change exists to make true.
- [ ] **1.3** Apply to `queries.list_postings` (page + count), `queries.totals` (all five), `queries.facets`.
- [ ] **1.4** Comment the two opt-outs (`get_posting`, `reports.source_overlap`) with the reason, citing ADR-0015.
- [ ] **1.5** Per-read-path invisibility tests in `tests/test_blacklist.py` — one per adopting seam, asserting a suppressed employer's `new`-status posting is absent from: the list, the list's `total`, the `published_only` list, `totals.by_status`, and `facets.countries` when it is that country's only posting.

> Point 1.5 is the analogue of the suite's governing asymmetry — *assert
> non-merging at least as hard as merging*. Here the concealment risk runs the
> other way: a missing filter silently **resurfaces** a blacklisted employer, so
> the invisibility assertions carry the weight, one per seam, not one in total.

*Checkpoint: `uv run pytest` green. Suppression enforced by both mechanisms.*

### Phase 2 — Remove the materialisation

- [ ] **2.1** Delete [pipeline/suppress_stage.py](../../app/src/app/pipeline/suppress_stage.py).
- [ ] **2.2** [pipeline/__init__.py:6,11](../../app/src/app/pipeline/__init__.py#L6) — drop the import and the `__all__` entry.
- [ ] **2.3** [pipeline/runner.py:23,72,78](../../app/src/app/pipeline/runner.py#L72) — drop the import, the `run_suppress` call, and the `"suppressed"` result key.
- [ ] **2.4** [__main__.py:81](../../app/src/app/__main__.py#L81) — drop `suppressed={...}` from the `run-all` line, which would otherwise `KeyError`.
- [ ] **2.5** [services/blacklist.py](../../app/src/app/services/blacklist.py) — delete `_reject_employer_postings` and `reject_employer_postings`; reduce `blacklist()` to a flag flip returning `None`; rewrite the module docstring, which currently points at `suppress_stage.run_suppress` as "the bulk sweep".
- [ ] **2.6** [routes/employers.py:36](../../app/src/app/web/routes/employers.py#L36) — the return value is already ignored; update the docstrings on both routes, which promise rejection and non-reinstatement.
- [ ] **2.7** [db/models.py](../../app/src/app/db/models.py) — delete `Posting.reject_for_suppression` (394-403); `Posting.create` (329) always births `STATUS_NEW`, and its docstring loses the born-Rejected rationale.
- [ ] **2.8** `db/models.py` comment sweep — every one of these now asserts something false: the `STATUS_REJECTED` "doubles as the D9 suppression signal" note (46), `Posting.status`'s "suppression-driven rejection" comment (252-256), `transition_to`'s suppression-sweep parenthetical (369), `Employer.lift_blacklist`'s FR-011 docstring (116-119, now inverted — postings *do* return), and `PostingStatusHistory.actor`'s "'system' (suppression sweep)" (436). `system` stays a valid actor value for future automated paths; it simply has no writer today.
- [ ] **2.9** [queries.py:104-122](../../app/src/app/services/queries.py#L104-L122) — `_ordering`'s docstring explains a NULL `status_changed_at` as "postings born Rejected because their employer was already suppressed". No posting is born Rejected any more; the NULL case survives only for rows predating this change. Reword rather than delete — the `nullslast()` is still load-bearing for them.

*Checkpoint: `uv run pytest` — the tests in Phase 3 fail here by design.*

### Phase 3 — Rewrite the tests the change invalidates

Several existing tests assert the materialisation as a behaviour. They do not
get deleted quietly; each is either inverted or replaced by the derived-model
equivalent, so the suite keeps covering the requirement rather than the
mechanism.

- [ ] **3.1** [test_blacklist.py:65-96](../../app/tests/test_blacklist.py#L65-L96) — four `run_suppress` tests. Delete; the invisibility tests from 1.5 are their successors. Drop the `run_suppress` and `reject_employer_postings` imports (24-25) and rewrite the module docstring.
- [ ] **3.2** [test_blacklist.py:102](../../app/tests/test_blacklist.py#L102) `..._is_born_rejected` → **invert**: a posting normalised for a blacklisted employer is born `new`, and is invisible through the seam **with no pass having run**. This is the test that proves ADR-0015 §Decision 1 — the "covers postings not yet seen" requirement satisfied structurally.
- [ ] **3.3** [test_blacklist.py:149](../../app/tests/test_blacklist.py#L149) `..._suppresses_and_rejects` → the endpoint sets the flag and the postings' statuses are **untouched**, while being invisible.
- [ ] **3.4** [test_blacklist.py:160](../../app/tests/test_blacklist.py#L160) `..._does_not_reinstate` → **inverts, and is the visible behaviour change**: after blacklist-then-lift, postings are visible again with their prior status intact (`new` stays `new`, `shortlist` stays `shortlist`). See §6 for the FR-011 rewording this requires.
- [ ] **3.5** [test_blacklist.py:177](../../app/tests/test_blacklist.py#L177) — delete, target function is gone.
- [ ] **3.6** [test_models.py:52](../../app/tests/test_models.py#L52) invert to born-`new`; delete the three `reject_for_suppression` tests (176-185, 226-231).
- [ ] **3.7** [test_posting_status_history.py:216](../../app/tests/test_posting_status_history.py#L216) — delete the `reason == "employer suppressed"` assertion and its test; fix the module docstring's reference to `blacklist.reject_employer_postings`. ADR-0013's history contract is otherwise untouched.
- [ ] **3.8** `uv run ruff check src tests --fix && uv run ruff format src tests`, then full suite.

*Checkpoint: `uv run pytest` green. This is the first point at which the change is complete and correct.*

### Phase 4 — Record the reversal

ADR-0015 exists because the *previous* reversal went unrecorded. Leaving these
as drift would repeat precisely the failure the ADR was written about.

- [ ] **4.1** `specs/001-ui-self-service/spec.md` — FR-007 (blacklist sets every posting Rejected), FR-009 (publication exclusion), FR-011 (no reinstatement) all restate the materialised model. Rewrite against ADR-0015; FR-011 becomes the display decision described in §6.
- [ ] **4.2** `specs/001-ui-self-service/data-model.md:113-125` — the passage that introduced the materialisation without an ADR. Annotate it as superseded, linking ADR-0015.
- [ ] **4.3** `specs/001-ui-self-service/research.md` D-A, D-B; `plan.md:105,109` (the `suppress_stage.py` tree entry); `tasks.md` T020-T022, T026 — mark superseded rather than deleting. T026's note ("satisfied at the write layer") is now specifically wrong and is worth correcting in place.
- [ ] **4.4** `Docs/software-requirements-specification.md` — FR-011 and any suppression-pass language.
- [ ] **4.5** [status-transition-concurrency.md](status-transition-concurrency.md) — the sweep sequence diagrams describe deleted code; add a superseded header pointing at ADR-0015 rather than editing the diagrams, since they remain the record of why.
- [ ] **4.6** [suppression-concurrency-review.md](suppression-concurrency-review.md) §8 — tick the next steps as done.
- [ ] **4.7** Check `Docs/design/system-architecture.md`, `Docs/design/data-model.md`, `Docs/development-guide.md`, and `CLAUDE.md`'s architecture tree for suppression-stage references.
- [ ] **4.8** Draft `System-modeling.md` from review §6, revised: the liveness property ("every posting of a suppressed employer *eventually* reaches suppressed, bounded by the next pipeline run") is replaced by a safety property ("no posting of a suppressed employer is ever visible"). Nothing converges any more, so nothing needs a convergence bound.

---

## 5. Migration

**Expect none.** ADR-0015 §Migration calls it "schema-only, no data rewrite" —
and on inspection there is no schema half either. `employers.suppressed` and its
partial index `ix_employers_suppressed` already exist; no column is added,
dropped, or altered. `ix_postings_triage_queue` stays useful for the list's
`published`/`status`/`score` ordering.

Verify rather than assume, after Phase 2:

```powershell
uv run alembic revision --autogenerate -m "verify adr-0015 is schema-neutral"
```

An empty `upgrade()` confirms it — **delete the generated file**. If it is not
empty, something in the model sweep (2.7/2.8) changed more than a comment.

Existing rows stamped `rejected` by a past sweep are left exactly as they are,
per ADR-0015: which historical rejections were suppression-driven is not
recoverable, and rewriting them would risk resurfacing postings the operator
genuinely rejected.

---

## 6. Two behaviour changes worth stating plainly

**FR-011 inverts.** Today lifting a blacklist leaves the back catalogue
rejected, because the sweep destroyed the operator's judgement on the way in.
Under derivation nothing was destroyed, so lifting restores those postings to
visibility with their prior status — a `shortlist` posting comes back as
`shortlist`. If a back catalogue arriving in the queue is unwanted, that is now
a UI choice made with full information (default-hide with an explicit restore, a
date filter), not an irreversible mutation. **It is not silently in scope here:**
this plan implements the reversal and rewords FR-011 to match; any hide-on-lift
affordance is a separate task on the SRS's terms.

Note the resulting asymmetry, accepted in ADR-0015: postings suppressed *before*
this change stay rejected after a lift, postings suppressed *after* it reappear.
Worth surfacing on the blacklist page.

**FR-009 moves from write time to read time.** Today publication exclusion is a
side effect — `transition_to` unconditionally clears `published` when entering
Rejected, which `tasks.md` T026 records as satisfying FR-009 "at the write
layer". After this change nothing enters Rejected on suppression, so a published
posting of a newly blacklisted employer keeps `published = true` on the row and
is hidden by the seam instead. This is latent today, since stage 4 does not
exist and nothing sets `published = true` — but `list_postings(published_only=
True)` is a live filter, which is why 1.3 must cover it, and why stage 4 must
adopt the seam when it selects candidates and when it writes `run.published_count`.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| A read path forgets the filter — the failure mode ADR-0015 accepts as permanent | §3 inventories every current query and forces a decision on each; the opt-outs carry comments so a later reader sees a choice, not an oversight. `db/visibility.py`'s docstring states the obligation at the definition site |
| A future stage in `pipeline/` cannot reach the seam | Resolved by siting it in `db/` (§2.1) rather than `services/` |
| Test deletion quietly drops requirement coverage | Phase 3 inverts rather than deletes wherever a requirement survives the mechanism; only the four `run_suppress` tests go, and 1.5 replaces them |
| SQLite/Postgres divergence in the NOT EXISTS | Plain correlated EXISTS, no dialect-specific JSON or index behaviour — unlike `_has_source`, which needed the split. The suite runs it under SQLite; the partial index is a Postgres-only optimisation, not a correctness dependency |
| Phase 2 lands without Phase 1 | Phases 1 and 2 are separate commits in that order; between them suppression is enforced twice, never zero times |

---

## 8. Commit sequence

1. `fix(triage): lock rows during status transitions (ADR-0014)` — Phase 0.1-0.2
2. `docs(adr): accept ADR-0013, mark ADR-0014 partly superseded` — Phase 0.3
3. `feat(db): add the suppression read seam (ADR-0015)` — Phase 1
4. `refactor(suppression)!: derive suppression from employer, drop the sweep (ADR-0015)` — Phases 2-3
5. `docs: record the ADR-0015 reversal across specs and design records` — Phase 4

Commit 4 is the breaking one and carries the behaviour changes in §6; the `!`
and a `BREAKING CHANGE:` trailer naming the FR-011 inversion belong on it.
