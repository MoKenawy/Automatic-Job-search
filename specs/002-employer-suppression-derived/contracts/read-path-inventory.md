# Contract: read-path inventory

**Features**: [002-employer-suppression-derived](../spec.md) (FR-010, SC-005) ·
[003-collect-stage-filtering](../../003-collect-stage-filtering/spec.md)
(FR-004, FR-017)

Every current query over `postings`, and its verdict — now against **two**
predicates, because there are two derived reasons to withhold a posting:
employer suppression (ADR-0015) and a filter verdict (ADR-0016). **The opt-outs
are as much a part of this contract as the adoptions** — an unexamined query is
the failure mode; an examined query that declines a predicate is a decision.

This table is the closed set. A new query over `postings` that appears without a
row here is a defect, regardless of whether it happens to behave correctly.

**One table, extended in place, rather than a second one for the filter.** A
second inventory would be a second thing to forget, and the whole value of the
artefact is that an unexamined path shows up as a missing row a reviewer can
see. For the same reason the two predicates are adopted as a pair, through
`queries._visible()`, rather than appended separately at each of eight call
sites.

The filter column's verdicts read:

- **Adopt** — applies `~hidden_by_filter()`: a rejected posting is withheld while
  it is still untriaged.
- **Invert** — applies `filter_rejected()` instead, to *show* what was turned
  away (FR-017).
- **No change** — the query does not read `postings`, or reads it for a purpose
  the verdict does not bear on.
- **Deliberate opt-out** — argued below.

---

## Verdicts

| # | Read path | Location | Suppression (ADR-0015) | Filter (ADR-0016) | Verification |
|---|---|---|---|---|---|
| 1 | Triage list — page statement | [queries.py:193-200](../../../app/src/app/services/queries.py#L193-L200) | **Adopt** | **Adopt** | A rejected, untriaged posting is absent from the list; an admitted one is present |
| 2 | Triage list — count statement | [queries.py:184-189](../../../app/src/app/services/queries.py#L184-L189) | **Adopt** | **Adopt** (same `where` list as #1) | Absent from `Page.total`. Must match #1 or the pager lies |
| 3 | `published_only` filter | [queries.py:165-166](../../../app/src/app/services/queries.py#L165-L166) | **Adopt** (same statement as #1/#2) | **Adopt** (same statement) | A `published=True` posting that the filter rejected is absent while untriaged |
| 4 | Dashboard — total postings | [queries.py:44](../../../app/src/app/services/queries.py#L44) | **Adopt** | **Adopt** | Excluded from the count |
| 5 | Dashboard — published count | [queries.py:45-47](../../../app/src/app/services/queries.py#L45-L47) | **Adopt** | **Adopt** | Excluded from the count |
| 6 | Dashboard — scored count | [queries.py:48-50](../../../app/src/app/services/queries.py#L48-L50) | **Adopt** | **Adopt** | Excluded from the count |
| 7 | Dashboard — `by_status` grouping | [queries.py:37-41](../../../app/src/app/services/queries.py#L37-L41) | **Adopt** | **Adopt** | Withheld postings absent from every bucket |
| 8 | Dashboard — employer count | [queries.py:52](../../../app/src/app/services/queries.py#L52) | **Adopt, differently** — `Employer.suppressed.is_(False)`, **not** `not_suppressed()` | **No change** — a count of employers, which no posting-level verdict bears on | Blacklisted employer excluded from the figure |
| 9 | Facets — countries | [queries.py:225-232](../../../app/src/app/services/queries.py#L225-L232) | **Adopt** | **Adopt** | A country whose only posting is withheld is not offered |
| 10 | Facets — unknown-country flag | [queries.py:233-235](../../../app/src/app/services/queries.py#L233-L235) | **Adopt** | **Adopt** | Flag false when only withheld postings lack a country |
| 11 | Facets — sources | [queries.py:243-258](../../../app/src/app/services/queries.py#L243-L258) | **No change** — reads `runs.counts_by_site` and `WORKING_SITES`, never `postings` | **No change** — same reason | n/a |
| 12 | Posting detail | [queries.py:261-266](../../../app/src/app/services/queries.py#L261-L266) | **Deliberate opt-out** | **Deliberate opt-out** | Detail page of a withheld posting still loads, and names the criterion |
| 13 | Blacklisted employers list | [queries.py:269-274](../../../app/src/app/services/queries.py#L269-L274) | **No change** — selects suppressed employers by definition | **No change** — about employers, not verdicts | Page lists the blacklisted employer |
| 14 | R1 employer activity | [reports.py:83-112](../../../app/src/app/services/reports.py#L83-L112) | **Already opts out knowingly** via `include_suppressed` | **No change** — measures employer activity as collected | Existing report tests unchanged |
| 15 | R1 status breakdown — second pass | [reports.py:105-110](../../../app/src/app/services/reports.py#L105-L110) | **No change** — inherits #14's decision | **No change** — inherits #14 | Covered by #14 |
| 16 | R3 source overlap | [reports.py:193](../../../app/src/app/services/reports.py#L193) | **Deliberate opt-out** | **Deliberate opt-out** — measures what the collector returned | Withheld postings still counted |
| 17 | Stage 3 — scoring | not yet built | **Must adopt.** Scoring a blacklisted employer's postings is wasted model time | **Must adopt** — this is the reduction in model invocations D6 exists for, and the reason the filter is a prior step rather than part of the scorer | Deferred; recorded in the stage's own plan |
| 18 | Stage 4 — publication | not yet built | **Must adopt**, both when selecting candidates and when writing `run.published_count` | **Must adopt** — publishing a posting the filter withheld would contradict the queue | Deferred; recorded in the stage's own plan |
| 19 | Filter review bucket | [queries.py `list_postings`, `verdict=VERDICT_REJECTED`](../../../app/src/app/services/queries.py) | **Adopt** — a blacklisted employer's postings stay out of it | **Invert** — selects `filter_rejected()`, deliberately *not* the complement of the hide rule | The bucket contains a withheld posting **and** one rejected after being shortlisted |

---

## The opt-outs, argued

### #12 — Posting detail

[detail.html:14](../../../app/src/app/web/templates/detail.html#L14) already
renders the blacklist banner and the "Remove from blacklist" button. This page
**is** the operator's route back out of a suppression. Filtering it would make
lifting unreachable from the posting that prompted it — the one page that would
explain why something vanished becomes the one page that cannot be opened.

Not a concession: spec **FR-015** makes it a requirement.

The filter opts out here on exactly the same terms, and the same condition
applies: the page carries a banner naming the criterion that withheld the
posting, shipped in the same commit as the predicate. 002's opt-out is only
defensible because the banner and the lift control were already there, so
003 reproduced that structure rather than assuming it (spec 003 FR-013,
FR-016, SC-005).

### #19 — The review bucket, which inverts rather than opts out

The bucket is not the complement of the hide rule. It selects `filter_rejected()`
— every posting a criterion turned away — so a posting rejected *after* the
operator shortlisted it appears both there and in the normal list.

That overlap is the point. FR-017 and SC-002 exist to make **false** rejections
discoverable, and the strongest available evidence of one is a posting the
operator thought worth keeping which the current criteria reject. A bucket
defined as "everything currently hidden" would conceal precisely that evidence.

Because the two sets are deliberately different, they can drift apart in
silence, so a partition test over every (verdict x status) pair asserts
`hidden + visible == all` and names the overlap
(`app/tests/test_visibility.py`).

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

Adding a query over `postings` obliges you to add a row here, **with a verdict in
both predicate columns**. The table is the mechanism by which 002's SC-005 ("100%
of read paths accounted for, zero unexamined") is checkable at all: an unexamined
path shows up as a missing row, which a reviewer can see, rather than as an
absent `.where()` clause, which nobody can.

A row with one column filled and the other blank is the same defect as a missing
row. Two predicates is twice the opportunity to forget one, which is why
`queries._visible()` exists: a read path adopts the pair, or argues its way out
of both in a comment.
