# Data Model: Collect-stage relevance and experience filtering

**Feature**: [003-collect-stage-filtering](spec.md) | **Date**: 16 November 2026

Two new columns, three columns that have existed since the initial migration and are
written for the first time, and one table whose meaning this feature deliberately
does **not** change. What each value means, and who is allowed to write it.

---

## Entities

### `postings`

| Field | Type | Meaning after this change |
|---|---|---|
| `job_level` | `String(64)`, nullable | **NEW.** The board's own seniority label, verbatim and lowercased as the collector delivers it (`mid-senior level`, `entry level`, `associate`, `not applicable`, `director`, `internship`, `executive`). Where several collected rows fold into one posting it is the **minimum** seniority among their labels, ties broken lexicographically (research R2). NULL means no contributing board supplied one. **Never holds an inference**: the title-derived fallback is computed at evaluation time and not stored (ADR-0012's lesson — a column named after a payload field must answer "what did the board say?") |
| `title_filter_passed` | `Boolean`, nullable | Exists since `ff6adc50ab28`; **written for the first time.** The verdict of the *title* criterion alone. Tri-state, see below |
| `experience_filter_passed` | `Boolean`, nullable | **NEW.** The verdict of the *experience* criterion alone. Same tri-state |
| `status` | `String(16)`, not null | **Untouched by this feature.** Operator judgement only, `services/triage.py` its sole writer (ADR-0015). A filter verdict is never written here, and a rejection never becomes `rejected` |
| `status_changed_at`, `last_retrieved_at` | timestamptz, nullable / not null | **Untouched.** The filter stage writes neither. `last_retrieved_at` moves only in `observe()`; a verdict is not an observation (ADR-0012) |
| `updated_at` | timestamptz, not null, `onupdate` | Moves when a verdict actually changes, and **not** when a re-apply recomputes the same verdict — writes are difference-guarded so a converged re-apply issues no UPDATE at all (research R5) |
| `normalised_title` | `String(512)`, not null | Unchanged as a column. Gains a second reader: the title-derived seniority fallback, which wants the lowercased, punctuation-free form that `normalise/title.py` already produces while deliberately retaining seniority words |
| `title` | `String(512)`, not null | Unchanged. The include/exclude patterns match against **this**, not the normalised form — the operator writes patterns after reading these strings (research R3) |

**The tri-state, which is load-bearing.** Both verdict columns mean exactly:

| Value | Meaning |
|---|---|
| `NULL` | The criterion was **not applied** — either the posting has never been filtered, or the criterion is disabled (empty pattern, absent or unrecognised requested experience, malformed pattern) |
| `TRUE` | Applied, and **admitted** — including admitted *because the input was unknown* (FR-005) |
| `FALSE` | Applied, and **rejected** |

Three consequences follow, and each is a requirement rather than a convenience:

- **SC-006 becomes literally true.** With no criteria set, no column changes at all,
  so installing the feature is observably a no-op.
- **The funnel stays honest.** With no criteria set, nothing is evaluated, so
  `filter_passed_count + filter_rejected_count` is zero and a pre-feature run stays
  distinguishable from a filtered one.
- **`detail.html:83` keeps working untouched.** Its existing three-way render
  (`passed` / `rejected` / `—`) already matches these semantics; it has simply never
  had a non-NULL value to show.

**Derived, not stored.** The overall verdict and the grounds for a rejection are
computed from the pair, never written:

```text
rejected  :=  title_filter_passed IS FALSE  OR  experience_filter_passed IS FALSE
grounds   :=  'title' | 'experience' | 'both'          (from which column is FALSE)
```

A stored reason string would be stale precisely when it matters most: FR-011 makes
criteria changes routine, and the operator reads the grounds *because* they are
about to loosen the rule that produced them. A derived explanation cannot go stale,
and the detail page can go further — it re-evaluates with current criteria and says
so when the stored verdict and the current rule disagree.

**Writers**: `pipeline/filter_stage.py` alone writes the two verdict columns.
`job_level` is written by `Posting.create` (first sighting) and
`Posting.merge_job_level` (a later sighting that supplies a lower label), both called
from `pipeline/normalise_stage.py`. Nothing in `web/` or `services/` writes any of
the four.

**Invariant**: *a filter verdict is a statement about criteria, and a status is a
statement about the operator's judgement; neither is ever written into the other.*
This is ADR-0015's invariant restated for a second kind of exclusion, and it is what
makes FR-013's recoverability free rather than engineered.

**No index.** Correctness does not depend on one (002's G5), and at NFR-1 volume —
under a hundred postings — the plan difference is not measurable. The existing
`ix_postings_triage_queue (published, status, score)` is unchanged.

---

### `runs`

| Field | Type | Meaning after this change |
|---|---|---|
| `filter_passed_count` | `Integer`, not null, default 0 | Exists since `ff6adc50ab28`; **written for the first time.** How many of this run's distinct postings the filter admitted |
| `filter_rejected_count` | `Integer`, not null, default 0 | Likewise, how many it rejected |
| `deduplicated_count` | `Integer`, not null, default 0 | Unchanged, and now the subject of an invariant: `filter_passed_count + filter_rejected_count == deduplicated_count` for any run the stage has processed. This is SC-003 made testable, and it forces the stage to scope itself to exactly the set `run_normalise` counted |
| `profile_id` | FK, nullable | Unchanged. **No longer the source of the experience criterion** — research R1 explains why reading it would make the verdict depend on run order. It remains attribution |

**Semantics of the counters.** They are *the verdict as of the last application*,
not an audit trail. `filter --run-id N` against an old run evaluates under **current**
criteria (FR-011 requires exactly that) and overwrites that run's figures. A reader
who treats the funnel as history will be wrong, which is why it is stated here.

`filter --all` writes **no** run counters. The counts in FR-015 belong to a run that
evaluated postings during an execution; writing a re-apply's totals onto some
arbitrary run would decouple them from that run's `collected_count` and break the sum
invariant above. `--all` reports to stdout and the log instead.

**Zero is ambiguous, and stays visible.** Both existing runs show `0 / 0` because the
stage did not exist when they ran. That is indistinguishable in the aggregate from a
filter that rejected everything, so two things keep them apart: the view renders a
structurally-zero pair as `—` rather than `0` (Phase 4), and the stage logs a warning
when `rejected == deduplicated_count > 0` — the spec's "every posting rejected" edge
case.

---

### `search_profiles`

| Field | Type | Meaning after this change |
|---|---|---|
| `experience` | `String(64)`, nullable, free text | **Unchanged as a column; effective for the first time.** Read through a synonym set, so values already stored (`entry level`, `fresh`) work without re-entry (FR-002). An unrecognised value disables the experience criterion for that profile and is reported, never rejecting anything (FR-002a). The model comment "advisory until wired into the scorer — a post-collection filter, not a board parameter" is the promise this feature keeps, and is updated to say so |

No migration touches this table. The profiles form is unchanged — that was the point
of resolving FR-002 toward free text.

---

### `raw_postings`, `raw_posting_normalizations`

**Untouched, and that is a requirement.** FR-012: filtering must not reduce, alter or
prevent what collection stores. Every row a board returns continues to be landed
verbatim whatever the verdict, which is what makes a criteria change re-appliable to
history rather than a reason to re-scrape.

`raw_posting_normalizations` gains one reader: `db/attribution.py`, which walks
posting → raw row → run → profile to assemble the set of profiles that have surfaced
each posting (research R1). It is the only path from a run to its postings, and the
same one `services/reports.py` already uses.

---

## Field promotion, and the record that justified leaving it alone

`db/models.py`'s module docstring states that column choices are grounded in the
measured JobSpy output of 20 July 2026, and lists `job_level` among fields
"LinkedIn-declared, never populated" that are therefore left in the payload. FR-020
requires that record corrected. Measured 16 November 2026 over 60 raw rows:

| payload field | LinkedIn | Indeed | overall | record |
|---|---|---|---|---|
| `job_level` | 100% | 0% | 67% | **false** — promoted by this feature |
| `company_industry` | 100% | 0% | 67% | **false** — stays in the payload (out of scope per FR-019/FR-020), but documented honestly |
| `job_function` | 0% | 0% | 0% | accurate; stays |
| `listing_type`, `skills`, `experience_range` | 0% | 0% | 0% | accurate; stays |
| salary block | — | — | 0% | accurate; D13 stands |

The collector's design made this cheap: `raw_postings` holds all 34 columns verbatim
specifically so that "a later decision to promote a field costs a backfill rather
than a re-scrape". This is the first time that promise has been called in.

One dependency travels with the promotion and is recorded in ADR-0016: the collector
populates `job_level` only when LinkedIn descriptions are fetched, so the
operator-editable `linkedin_fetch_description` is a hidden switch on the experience
criterion's primary input (research R8).

---

## Migrations

| Revision | Content |
|---|---|
| DDL, `down_revision = b2c3d4e5f6a7` | `postings.job_level` `String(64)` nullable; `postings.experience_filter_passed` `Boolean` nullable. No server default — `job_level` has 0% coverage on one working board, so any default would be a claim about absent data, and the verdict columns' NULL is load-bearing |
| Data, following it | Backfill `job_level` from each posting's contributing payloads, applying the min-wins rule **imported from `app.filters.levels`** rather than restated — the precedent set by `b2c3d4e5f6a7`, which imports `build_fingerprint`. Batched; documented no-op downgrade |

Neither revision touches a verdict column's data. The spec is explicit that existing
postings are not retroactively filtered on installation: whether to apply the filter
to already-collected postings is an operator action (`filter --all`), not an install
step.
