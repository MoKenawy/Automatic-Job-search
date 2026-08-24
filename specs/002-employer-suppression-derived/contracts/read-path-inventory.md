# Contract: read-path inventory

**Feature**: [002-employer-suppression-derived](../spec.md) | **Implements**: FR-010, SC-005

Every current query over `postings`, and its verdict. **The opt-outs are as much
a part of this contract as the adoptions** — an unexamined query is the failure
mode; an examined query that declines the filter is a decision.

This table is the closed set. A new query over `postings` that appears without a
row here is a defect against FR-010, regardless of whether it happens to behave
correctly.

---

## Verdicts

| # | Read path | Location | Verdict | Verification |
|---|---|---|---|---|
| 1 | Triage list — page statement | [queries.py:193-200](../../../app/src/app/services/queries.py#L193-L200) | **Adopt** | Suppressed employer's `new` posting absent from the list |
| 2 | Triage list — count statement | [queries.py:184-189](../../../app/src/app/services/queries.py#L184-L189) | **Adopt** | Absent from `Page.total`. Must match #1 or the pager lies |
| 3 | `published_only` filter | [queries.py:165-166](../../../app/src/app/services/queries.py#L165-L166) | **Adopt** (same statement as #1/#2) | A `published=True` posting of a suppressed employer is absent. **This is now FR-009's enforcement** |
| 4 | Dashboard — total postings | [queries.py:44](../../../app/src/app/services/queries.py#L44) | **Adopt** | Excluded from the count |
| 5 | Dashboard — published count | [queries.py:45-47](../../../app/src/app/services/queries.py#L45-L47) | **Adopt** | Excluded from the count |
| 6 | Dashboard — scored count | [queries.py:48-50](../../../app/src/app/services/queries.py#L48-L50) | **Adopt** | Excluded from the count |
| 7 | Dashboard — `by_status` grouping | [queries.py:37-41](../../../app/src/app/services/queries.py#L37-L41) | **Adopt** | Suppressed employer's postings absent from every bucket |
| 8 | Dashboard — employer count | [queries.py:52](../../../app/src/app/services/queries.py#L52) | **Adopt, differently** — `Employer.suppressed.is_(False)`, **not** `not_suppressed()`. The predicate is over `postings` and does not apply to a count of employers | Blacklisted employer excluded from the figure |
| 9 | Facets — countries | [queries.py:225-232](../../../app/src/app/services/queries.py#L225-L232) | **Adopt** | A country whose only posting is suppressed is not offered |
| 10 | Facets — unknown-country flag | [queries.py:233-235](../../../app/src/app/services/queries.py#L233-L235) | **Adopt** | Flag false when only suppressed postings lack a country |
| 11 | Facets — sources | [queries.py:243-258](../../../app/src/app/services/queries.py#L243-L258) | **No change** — reads `runs.counts_by_site` and `WORKING_SITES`, never `postings` | n/a |
| 12 | Posting detail | [queries.py:261-266](../../../app/src/app/services/queries.py#L261-L266) | **Deliberate opt-out** | Detail page of a suppressed posting still loads |
| 13 | Blacklisted employers list | [queries.py:269-274](../../../app/src/app/services/queries.py#L269-L274) | **No change** — selects suppressed employers by definition; the filter would empty the page it exists to fill | Page lists the blacklisted employer |
| 14 | R1 employer activity | [reports.py:83-112](../../../app/src/app/services/reports.py#L83-L112) | **Already opts out knowingly**, via `include_suppressed` at the employer level. No code change — but its docstring's "their postings are auto-rejected (D9)" becomes false and must be reworded | Existing report tests unchanged |
| 15 | R1 status breakdown — second pass | [reports.py:105-110](../../../app/src/app/services/reports.py#L105-L110) | **No change** — scoped by `employer_id IN (…)` to the employers #14 already selected, so it inherits #14's decision | Covered by #14 |
| 16 | R3 source overlap | [reports.py:193](../../../app/src/app/services/reports.py#L193) | **Deliberate opt-out** | Suppressed employer's postings still counted |
| 17 | Stage 3 — scoring | not yet built | **Must adopt.** Scoring a blacklisted employer's postings is wasted model time | Deferred; recorded in the stage's own plan |
| 18 | Stage 4 — publication | not yet built | **Must adopt**, both when selecting candidates and when writing `run.published_count`. **This is where FR-009 now lives** | Deferred; recorded in the stage's own plan |

---

## The two opt-outs, argued

### #12 — Posting detail

[detail.html:14](../../../app/src/app/web/templates/detail.html#L14) already
renders the blacklist banner and the "Remove from blacklist" button. This page
**is** the operator's route back out of a suppression. Filtering it would make
lifting unreachable from the posting that prompted it — the one page that would
explain why something vanished becomes the one page that cannot be opened.

Not a concession: spec **FR-015** makes it a requirement.

### #16 — R3 source overlap

The report measures what the **collector** returned, not what the operator should
act on. Filtering would understate a board's coverage, so the report would
silently answer a different question than its title claims — and board coverage
is the signal the report exists to protect (silent collection decay).

Not a concession: spec **FR-017** makes it a requirement.

---

## Rows that are documentation fixes, not code changes

**#14 (R1 employer activity)** behaves correctly and is not touched. Its
docstring asserts that a suppressed employer's "postings are auto-rejected (D9)",
which stops being true the moment this feature lands. Left alone it becomes
exactly the kind of drift ADR-0015 was written about — a document describing a
mechanism that no longer exists, indistinguishable from a document describing one
that does.

---

## Maintenance rule

Adding a query over `postings` obliges you to add a row here. The table is the
mechanism by which SC-005 ("100% of read paths accounted for, zero unexamined")
is checkable at all: an unexamined path shows up as a missing row, which a
reviewer can see, rather than as an absent `.where()` clause, which nobody can.
