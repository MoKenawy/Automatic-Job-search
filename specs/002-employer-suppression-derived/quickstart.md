# Quickstart: validating employer-level suppression

**Feature**: [002-employer-suppression-derived](spec.md) | **Date**: 13 August 2026

How to prove this feature works, at each point where proof is meaningful. All
commands run from `app/`. The suite needs no Docker — web and pipeline tests use
in-memory SQLite with `StaticPool`.

---

## Prerequisites

```powershell
uv sync
```

Docker is needed only for the manual walkthrough at the end and for the
schema-neutrality check:

```powershell
docker compose up -d postgres
```

---

## Checkpoint gates

Each phase has a state the suite must be in. Running the suite at the wrong
moment and finding it green can mean the phase did nothing — the Phase 1 and
Phase 2 gates below are as much about what *fails* as what passes.

### Gate 0 — baseline

```powershell
uv run pytest
```

Green, behaviour unchanged. This is the ADR-0014 locking work landing on its own.

### Gate 1 — the seam exists, before anything is removed

The keystone test must fail **before** `db/visibility.py` exists, and for the
right reason:

```powershell
uv run pytest tests/test_visibility.py -q
```

Expected first run: a suppressed employer's posting with `status = 'new'` is
still selected. Under the old model that posting was a state the system could
not represent — suppression was only ever visible *as* a status. Seeing this
fail is the point; it is the assertion the whole feature exists to make true.

After adding the seam and adopting it:

```powershell
uv run pytest
```

Green. Suppression is now enforced **twice** — stamped and filtered. That
redundancy is deliberate: it is the only condition under which the new
enforcement can be proven on its own, without the old mechanism being what makes
the tests pass.

### Gate 2 — materialisation removed

```powershell
uv run pytest
```

**Expected to fail.** The failures are the tests that assert the old mechanism as
a behaviour — `run_suppress`, born-rejected, the endpoint's rejection sweep.
Failing here is the plan working. Anything failing that is *not* in that set is a
real defect.

### Gate 3 — tests rewritten

```powershell
uv run ruff check src tests --fix
uv run ruff format src tests
uv run pytest
```

Green. **This is the first point at which the change is complete and correct.**

### Gate 4 — schema neutrality, verified not assumed

```powershell
uv run alembic revision --autogenerate -m "verify adr-0015 is schema-neutral"
```

Open the generated file. `upgrade()` must be empty — then **delete the file**.

A non-empty body means the model comment sweep changed more than a comment. That
is a defect to fix at the source, not a migration to keep.

---

## Scenario checks

Each maps to a user story. Run individually while working the relevant phase.

### Story 1 — a blacklisted employer disappears completely

```powershell
uv run pytest tests/test_blacklist.py -q -k invisible
```

One assertion per read path — list rows, list `total`, the `published_only`
list, `totals.by_status`, and `facets.countries` when the suppressed posting is
its country's only one. Deliberately **not** one test covering all five: removing
the filter from any single path must fail the suite. This mirrors the project's
governing testing asymmetry — here the concealment risk runs toward
*resurfacing* a blacklisted employer, so the negative assertions carry the
weight.

### Story 2 — suppression covers postings not yet collected

```powershell
uv run pytest tests/test_blacklist.py -q -k born
```

A posting normalised for an already-blacklisted employer is born `new`, and is
invisible through the seam **with no pass having run**. This is the inverted
descendant of `test_new_posting_from_blacklisted_employer_is_born_rejected`, and
it proves ADR-0015 §Decision 1: the "covers postings not yet seen" requirement,
satisfied structurally rather than by a catch-up job.

### Story 3 — un-blacklisting restores what it hid

```powershell
uv run pytest tests/test_blacklist.py -q -k reinstate
```

The visible behaviour change. After blacklist-then-lift, postings are visible
again with prior status intact: `new` stays `new`, `shortlist` stays
`shortlist`. This inverts 001's FR-011.

### Story 4 — the way back out stays reachable

```powershell
uv run pytest tests/test_blacklist.py -q -k detail
```

A suppressed posting's detail page still loads, shows the blacklist banner, and
offers removal.

### The audit trail stays clean

```powershell
uv run pytest tests/test_posting_status_history.py -q
```

No `actor='system'` rows, no `reason='employer suppressed'` rows, across a full
blacklist/collect/lift cycle (SC-004). `'system'` remains a valid actor value for
future automated paths — it simply has no writer.

---

## Manual walkthrough

Needs a populated database.

```powershell
docker compose up -d postgres
uv run alembic upgrade head
uv run python -m app web --reload
```

1. Open the triage list. Note an employer with postings across several statuses,
   and the list's total.
2. Shortlist one of its postings, so there is real operator judgement to lose.
3. Blacklist the employer from the posting row (FR-012).
4. **Check**: its postings are gone from the list; the total dropped by exactly
   that many; the dashboard figures dropped correspondingly; if it was a
   country's only employer, that country is no longer offered as a filter.
5. Open the shortlisted posting's URL directly. **Check**: the page loads, shows
   the blacklist banner, and offers "Remove from blacklist" (FR-015) — this is
   the route back out.
6. Remove the blacklist from there.
7. **Check**: the postings are back, and the one you shortlisted is **still
   shortlisted** (FR-012). Under the old mechanism it would have returned as
   Rejected, with the shortlist decision destroyed.
8. Open the blacklist view. **Check**: it states that blacklists applied before
   this change do not restore on removal (FR-013).

Step 7 is the behaviour change worth seeing with your own eyes — everything else
is the absence of something.

---

## Not covered here

- **Publication (FR-009) end to end.** Stage 4 does not exist and nothing sets
  `published = true`, so read-time exclusion is proven against the
  `published_only` filter rather than a live publication flow.
- **Scoring (FR-011).** Stage 3 does not exist. Its obligation to adopt the seam
  is recorded in [contracts/read-path-inventory.md](contracts/read-path-inventory.md)
  rows 17–18 so it is inherited rather than rediscovered.
- **Historical `rejected` postings.** Deliberately untouched (research R4); there
  is nothing to run and nothing to verify beyond the empty migration at Gate 4.
