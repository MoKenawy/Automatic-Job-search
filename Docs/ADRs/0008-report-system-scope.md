# ADR-0008: Report system — admission criteria and scope

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 27 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | Nothing |
| **Related** | [Design record](../job-discovery-pipeline-design.md) D11, D13, §4.3, §7.4; [ADR-0007](0007-scoring-evaluation-and-score-history.md) §2–§4; [SRS](../software-requirements-specification.md) §13; [Reports implementation plan](../design/reports-implementation-plan.md) |

---

## Context

The system collects and deduplicates postings but exposes only two read
surfaces: the triage list (`/postings`) and the run-health view (`/runs`). The
data held — provenance per board, re-observation timestamps, normalised titles
and employers, per-run stage counts — supports analysis that neither surface
offers.

Eleven candidate reports were assessed. The assessment was made against the
fields that are **populated today**, not against the declared schema, following
the same rule §4.3 applied to source selection: *where measurement and estimate
disagree, the measurement governs.*

Three facts constrain every answer below.

**1. Stage 3 is unbuilt.** `pipeline/runner.py` drives collect → normalise →
suppress. There is no score stage and no publish stage. `score`,
`matched_skills`, `gaps`, `rationale`, `scored_at` and `scored_by_model` are
NULL on every row, and `published` is false on every row. This is not a
data-sparsity problem that more collection would fix.

**2. Salary is absent, not sparse.** D13 recorded 0/10 populated on both
working sources and deliberately declined to promote the fields to columns.

**3. `raw_postings` is an append-only full-payload landing zone.** Any report
needing a field that was never promoted to a column costs a backfill over
`raw_postings.payload`, not a re-scrape. This materially changes the cost of
several deferred options and is the reason none of them are rejected outright.

**4. ADR-0007 has since added `posting_scores`**, an append-only history of
every scoring attempt carrying `prompt_version`, `prompt_hash`, `cv_hash` and
`model`. It is empty until stage 3 runs, but it creates a report option (D5
below) that did not exist when the eleven candidates were assessed, and it
supersedes ADR-0006's testing decision — so any report reasoning built on
ADR-0006's 16-of-20 agreement gate is stale and is not relied on here.

Without a stated rule, report selection drifts toward whatever is easy to
query, and the reports that result quietly mislead — a demand chart built from
a search-profile-shaped sample reads as a market measurement unless something
says otherwise. The rule is therefore recorded before the reports are built.

## Decision

### 1. Admission criteria

A report is built now only if it satisfies all three:

1. **Populated inputs.** Every field it reads is populated today at a known
   rate. A field at partial coverage qualifies only if the report can state
   its denominator.
2. **No new collection.** It requires no new source, no new board parameter,
   and no change to what stage 1 requests.
3. **Statable bias.** Its sampling bias can be written in one sentence and
   displayed with the output. A report whose bias cannot be stated plainly is
   not admitted, however easy the query.

Criterion 3 is the operative one. The postings table is not a sample of the job
market; it is a sample of what this operator's search profiles asked for, from
two boards, within `hours_old`. Most candidate reports are honest only with
that caveat attached.

### 2. In scope now

Six reports satisfy all three criteria. They are specified and sequenced in the
[implementation plan](../design/reports-implementation-plan.md); named here only
so the excluded set below has something to be excluded from.

| # | Report | Principal inputs |
|---|---|---|
| R1 | Employer hiring activity | `employer_id`, `normalised_title`, `first_seen_at` |
| R2 | Posting longevity and repost detection | `first_seen_at`, `last_seen_at`, `date_posted` |
| R3 | Source coverage and overlap | `sources` |
| R4 | Role demand by normalised title | `normalised_title`, `date_posted` |
| R5 | Collection health and decay | `runs.*` |
| R6 | Work arrangement mix | `is_remote`, `job_type`, `country_code` |

R2 depends on a defect fix recorded in the plan §2: `last_seen_at` carries
`onupdate=func.now()`, so it advances on any write to the row, not only on a
board re-surfacing the posting. Until that is corrected the field does not mean
what R2 needs it to mean.

### 3. Deferred, with the condition that unblocks each

None of the following are rejected. Each fails a criterion today and each has a
specific, identifiable unblocking event.

**D1 — Skills demand from descriptions.** *Fails criterion 1 in spirit:* the
descriptions are populated (Indeed natively, LinkedIn via
`linkedin_fetch_description`), but the skills are not a field — they are an
extraction product requiring a taxonomy.

This is the highest-value deferred option and the one most likely to be built
prematurely. It is deferred for a reason beyond effort: the scoring prompt
already requires a skill taxonomy — ADR-0007 §1 carries forward the requirement
that the context window hold "CV, full description and taxonomy in one call."
Building a separate extraction vocabulary for reporting now would produce two
taxonomies that disagree, and the report would then contradict the scorer's
`matched_skills` on the same posting. *Unblocked by:* the scoring taxonomy
existing. Build it against that taxonomy, not before it.

**D2 — Employer firmographics.** *Fails criterion 1:* `num_employees` and
`revenue` are populated at roughly 60–70%, and only from Indeed, so the
covered subset is itself board-biased rather than randomly missing.

Buildable, but the insight — a startup-versus-enterprise mix — is thin relative
to the care its presentation demands, since every figure needs a coverage
denominator and a note that coverage correlates with the source. *Unblocked by:*
the deferred ATS endpoints (§3.1, phase 2) raising coverage, or acceptance that
the report is explicitly "of the employers we have size data for."

**D3 — Triage funnel and operator throughput.** *Fails criterion 1 on volume:*
`status` and `status_changed_at` support new → shortlist → applied → rejected
with dwell times, but the history is operator-generated and is close to empty.

Two further limits are structural rather than temporal, and neither is fixed by
waiting.

`STATUSES` has four states and none is a post-application outcome. `rejected`
means the operator rejected the posting, not that an employer rejected the
application. The report can measure triage throughput but not application
success, and presenting it as the latter would be false.

`reject_for_suppression()` writes that same `rejected` status, so a naive
rejection count conflates "not a role I want" with "employer blacklisted" —
two quantities a throughput report has no business adding together. They are
separable via the employer's suppression flag, but only deliberately.
ADR-0007 O1 identifies this same trap for the evaluation corpus; it is one
defect with two consumers, and whichever is built first should do the
separating in a shared place rather than locally.

*Unblocked by:* accumulated triage history, plus that separation. Extending the
report to true outcomes requires new states in the `transition_to` state
machine, which is an ADR-sized change and not merely a report.

**D4 — Score distribution and skill-gap aggregate.** *Fails criterion 1
absolutely:* every input is NULL, and stage 3 is itself blocked on the CV
(SRS §13 item 1).

This is two different things wearing one name, and separating them changes
where each is scheduled.

*The calibration instrument is not a report and does not belong in this
backlog.* ADR-0007 §3 derives the publication threshold from data — the cut
sits just below the lowest score any operator-shortlisted posting received —
and requires reporting how many rejected postings sit above that cut. That
output, together with the concordance figure over the fixed twenty, is
apparatus stage 3 needs in order to be trusted at all. It should be built as
part of stage 3's validation work and scheduled against ADR-0007, not queued
behind the six reports above.

*The skill-gap aggregate is a genuine report*, and is the answer to "what am I
repeatedly missing" — the question a job seeker most wants answered and the one
nothing else here addresses. It reads `gaps` across scored postings. It remains
deferred only because its input does not exist yet.

*Unblocked by:* stage 3 landing. The instrument leads; the report follows.

**D5 — Scorer drift across prompt versions.** *Newly possible, and newly
necessary, as of ADR-0007 §2.* The `posting_scores` history table makes score,
`prompt_version`, `prompt_hash`, `cv_hash` and `model` recoverable per attempt
rather than overwritten, which is what a comparison across prompt revisions
needs to exist at all.

Two consumers make this more than a curiosity. ADR-0007 §3's iteration
discipline treats concordance rising over more than five recorded iterations
against the same twenty as fitting the set rather than improving the scorer —
and that count is only visible by reading `prompt_hash` history. ADR-0007 O2
proposes scoring the same twenty twice under one unchanged prompt to measure
sampling spread, which is the same query with the prompt held constant.

Recorded here rather than folded into D4 because it is a report about the
*scorer*, not about the job market, and because it will be wanted at the moment
of the first prompt revision rather than later. *Unblocked by:* stage 3 landing
and a second recorded prompt version. The migration alone does not unblock it —
an empty history table compares nothing.

### 4. Rejected outright — salary benchmarking

The most-requested report of this kind, and the one this data cannot support.
D13 measured salary at 0/10 populated on both working sources. There is no
degraded version: the field is absent, not sparse, so no coverage caveat
rescues it.

Two paths could in principle supply it, and both are declined for now:

- *ATS endpoints* (§3.1) are already deferred to phase 2 and would need to be
  built for their own reasons first.
- *Parsing salary from description text* is rejected on a harm argument rather
  than a cost one. Every other report here informs where the operator spends
  attention; a wrong attention decision is cheap and self-correcting. A salary
  benchmark informs a negotiation, where being wrong is neither. A figure
  derived from unvalidated text-parsing, displayed as a benchmark, would carry
  more authority than its accuracy earns.

Revisiting requires a source that supplies salary as a field, not an inference
over text.

## Consequences

*Favourable:*

- The admission criteria give "should we build this report" a checkable answer,
  and will answer the next candidate without a fresh debate.
- Criterion 3 forces the selection-bias caveat into the product rather than
  leaving it in a design document nobody reads at the moment of misreading.
- Deferring D1 until the scoring taxonomy exists prevents two divergent skill
  vocabularies, which would have been discovered only when the report and the
  scorer disagreed in front of the operator.
- Splitting D4 moves its calibration half to the work it actually gates
  (ADR-0007 §3), where it would otherwise have sat behind six lower-value
  items, while keeping its skill-gap half honestly in the report backlog.
- Rejecting salary in writing stops it being re-proposed each time the reports
  are looked at.

*Unfavourable, and accepted:*

- Six reports built against a two-board, search-profile-shaped sample will be
  over-read as market measurements despite the caveats. Caveat text is a weak
  control; it is the only one available short of not building them.
- Deferring D1 delays the single most useful output for a job seeker — what to
  learn next — behind the CV, which is the project's standing blocker. Accepted
  because a wrong skills list is worse than a late one.
- The criteria are biased toward what is measurable now, which will
  systematically favour operational reporting over market analysis for as long
  as stage 3 is unbuilt.
- No report here answers "am I competitive for this role," which is what the
  operator most wants to know. That answer lives entirely in D4.

## Control

This ADR governs report scope only. It does not alter the collection
configuration, the fingerprint, or the triage state machine, and it does not
unblock stage 3.

The deferred set is reviewed when either of two events occurs: stage 3 lands
(releasing D4's report half and, with a second prompt version, D5; and the
taxonomy releasing D1), or a new source is added (potentially releasing D2 and
reopening salary). D3 releases on accumulated triage history instead, and on
the suppression/rejection separation it shares with ADR-0007 O1.

Absent those, the six in-scope reports are the whole of the report system, and
adding a seventh means testing it against §1 and amending this record.
