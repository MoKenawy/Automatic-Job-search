# Quickstart: validating collect-stage filtering

**Feature**: [003-collect-stage-filtering](spec.md) | **Date**: 16 November 2026

How to prove this feature works, at each point where proof is meaningful. All
commands run from `app/`. The suite needs no Docker — the filter's pure core and the
stage both run against in-memory SQLite with `StaticPool`.

---

## Prerequisites

```powershell
uv sync
```

Docker is needed for the migration round-trip (Gate 1) and for any measurement
against the real corpus:

```powershell
docker compose up -d postgres
```

---

## Checkpoint gates

Each phase has a state the suite must be in. Running the suite at the wrong moment
and finding it green can mean the phase did nothing — Gate 0 and Gate 3 below are as
much about what *does not* change as about what passes.

### Gate 0 — the pure core, before anything imports it

```powershell
uv run pytest tests/test_filter_levels.py tests/test_filter_titles.py
uv run pytest
```

Both green, and — the part that matters — **no existing test was amended to get
there**. Phase 0 adds a package nothing imports, so any pre-existing test needing a
change would mean the phase did more than it claims.

Two tests in this gate carry more weight than the rest:

- an empty exclude pattern rejects **nothing** (SC-006; the pattern ships empty, and
  `re.search("", title)` matches everything);
- an absent, empty or `not applicable` label yields no level rather than a guess
  (FR-005).

### Gate 1 — the schema, with no verdicts in it

```powershell
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Clean in all three directions, against the real PostgreSQL. Then confirm the
backfill landed and that nothing has been judged yet:

```powershell
docker exec job-discovery-db psql -U jobs -d jobs -c "
  SELECT count(*) AS postings,
         count(job_level) AS with_level,
         count(title_filter_passed) AS title_verdicts,
         count(experience_filter_passed) AS experience_verdicts
  FROM postings;"
```

`with_level` should be non-zero (the board supplies the label on every LinkedIn row);
**both verdict counts must be zero.** A verdict at this point means a column is being
written a phase early.

### Gate 2 — the stage, measured before it can hide anything

This is the gate the phase ordering exists for. Verdicts are being written and
nothing reads them, so the criteria can be measured against the real corpus at no
risk.

```powershell
uv run python -m app filter --all --dry-run
```

Read the reported counts against the criteria now in force. With no title patterns
set and one profile recording `entry level`, the rejections should be the mid-senior,
director and executive postings that profile surfaced, and nothing else.

Then apply it, and read the funnel back:

```powershell
uv run python -m app filter --all
uv run python -m app status
```

And the property SC-007 actually asserts:

```powershell
uv run python -m app filter --all
```

The second application must report **zero changes**. Writes are difference-guarded,
so a converged re-apply issues no UPDATE at all — which also means `updated_at` has
not moved on any row. To check that directly:

```powershell
docker exec job-discovery-db psql -U jobs -d jobs -c "
  SELECT max(updated_at) FROM postings;"
```

Run it before and after the second `filter --all`; the two values must be identical.

The per-run invariant (SC-003, contract C1):

```powershell
docker exec job-discovery-db psql -U jobs -d jobs -c "
  SELECT id, deduplicated_count, filter_passed_count, filter_rejected_count,
         filter_passed_count + filter_rejected_count = deduplicated_count AS balances
  FROM runs ORDER BY id;"
```

`balances` must be true for every run the stage has processed. Runs that predate the
stage show `0 / 0` and are expected not to balance — that is what Gate 4's `—`
rendering is for.

### Gate 3 — enforcement, and the route back in

```powershell
uv run pytest
```

Green, **with no pre-existing test amended except `tests/test_settings.py`** (whose
consumption partition genuinely moved, because the title patterns now have a
consumer). Any other test needing a change means the predicate is hiding something
SC-006 forbids — the gate is the diff, not the exit code.

The keystone, which must fail before `hidden_by_filter()` exists and for the right
reason:

```powershell
uv run pytest tests/test_visibility.py -k keystone -v
```

A posting rejected on experience grounds whose status is still `new` is invisible;
the same posting once shortlisted is visible; a posting with NULL verdicts is
visible. The third case is the one that fails catastrophically if the predicate is
written `== False` instead of `.is_(False)` — under three-valued logic that spelling
hides the entire corpus, and every absence-only test stays green.

Then by hand:

```powershell
uv run python -m app web --reload
```

- `/postings` — the queue no longer contains the rejected, untriaged postings.
- `/postings?verdict=rejected` — the "Filtered out" bucket contains them, **and**
  any posting that was rejected after the operator had already shortlisted it. That
  overlap with the normal list is deliberate (contract §2).
- a rejected posting's detail page — reachable, with a banner naming the criterion
  that withheld it and its triage controls intact.
- shortlist a rejected posting, then reload `/postings` — it is visible there, and
  still in the bucket.

### Gate 4 — the funnel is legible

```powershell
uv run python -m app status
```

Passed and Rejected columns present. The two historical runs read `—`, not `0`: a
structurally-zero pair is not the same claim as "the filter rejected nothing", and
rendering it as zero manufactures a false alarm on a working pipeline
(`reports-implementation-plan.md`).

At `/runs`, the same two columns, with the table's empty-state and error-row
colspans still correct — add a column and forget a colspan and the error row silently
misaligns.

### Gate 5 — the record matches the mechanism

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

Then read `Docs/ADRs/0016-collect-stage-filter-verdicts.md` and confirm it names, as
decisions with their rejected alternatives: the disjunction over profiles, the
min-wins merge, the NULL/TRUE/FALSE semantics, the `status == new` term in the hide
rule, and the `linkedin_fetch_description` coupling. ADR-0015 exists because a
previous reversal went unrecorded; an undocumented decision here would repeat that.

---

## Proving the spec's success criteria

| # | Criterion | How it is checked |
|---|---|---|
| SC-001 | 90% of a profile's queue at or below its requested level | Gate 2's `--dry-run` on the real corpus, then the `/postings` queue for that profile's postings. Note the spec's 24% baseline came from an earlier database (research R9) |
| SC-002 | Zero false rejections; the admission tests at least as large as the rejection tests | Gates 0 and 3, and the diff itself — the sizing rule is reviewable, not merely intended |
| SC-003 | Counts sum to the postings evaluated | Gate 2's `balances` query |
| SC-004 | A criteria change visible on collected postings, no board contacted, under a minute for a thousand postings | Edit the patterns at `/settings`, run `filter --all`, watch the bucket change. Nothing in the stage touches the network |
| SC-005 | One interaction to see that the filter withheld a posting and which criterion did | Gate 3's detail page, reached from the bucket |
| SC-006 | Installing without setting criteria changes nothing | Gates 0, 1 and 3's "no test amended" conditions, plus the empty-pattern test by name. With no criteria, every verdict stays NULL |
| SC-007 | Re-applying to unchanged data is identical | Gate 2's second `filter --all` reporting zero changes, and `max(updated_at)` unmoved |

---

## Known blast radius on this installation

SC-006 is a statement about "no criteria set", not about this machine. The
`AI Engineer` profile already records `experience = entry level`, and FR-002
deliberately makes stored values effective without re-entry — so the first
application of the filter **will** withhold mid-senior and director postings that
profile surfaced. That is the feature working, not a defect, and it is why Gate 2
exists as a separate, measurable, write-only step before Gate 3 makes anything
invisible.

If the effect is not wanted, blank the profile's experience field at `/profiles` and
re-run `filter --all`: the verdicts return to NULL and the postings come back, with
their triage status intact.
