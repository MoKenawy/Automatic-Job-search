# ADR-0018: Per-profile title rules — two levels, one combination rule

* Status: accepted
* Deciders: Mohammed
* Date: 17 November 2026

Technical Story: the title include/exclude patterns were global — one pair at
`/settings`, applied identically to every posting whatever search found it
([ADR-0016](0016-collect-stage-filter-verdicts.md)). An operator running a
`backend developer` search and a `data engineer` search wants different rules for
each. This record decides where a profile's own rules live, how they combine with
the global ones, and what happens when one posting was found by several profiles.
It also answers, in one place, a question the code had answered only in a
docstring: which wins, include or exclude.

## Context and Problem Statement

A `Posting` carries no profile. It is the deduplicated record of a real-world
role, and the fingerprint that folds rows into it is employer + title +
location/remote — it knows nothing about which search or which profile found the
role (design §8). So a posting found by `data engineer` and by `ai engineer`
becomes **one** row with two contributing profiles, and the filter stores **one**
verdict per posting.

That is not hypothetical. On 17 November 2026, **15 of 135 postings (11%)** had
more than one contributing profile. Any rule that lets a profile influence a
verdict has to say what happens to those, and the answer has to be one the
read-time predicate can enforce without knowing which profile is looking
([ADR-0016](0016-collect-stage-filter-verdicts.md) rejected per-profile verdicts
on exactly that ground).

## Decision Drivers

* A posting wrongly rejected is one the operator never sees and cannot recover by
  looking harder; a posting wrongly kept costs seconds of triage. This is the
  governing asymmetry of spec 003.
* Installing the feature must change no verdict (SC-006).
* The same verdict must come out whichever run is filtered, in whatever order
  (FR-010, SC-007).
* The stage that records a verdict and the page that explains it must not be able
  to disagree about how it was reached.

## Decision

### 1. Rules live on the search profile, and add to the global ones

Two nullable columns on `search_profiles`: `title_include_pattern` and
`title_exclude_pattern`. NULL means **"this profile adds nothing"** — not "this
profile admits everything" — so every existing profile behaves exactly as it did.

A profile's rules apply **in addition to** the global rules, never instead of
them. A house rule at `/settings` is therefore one a profile cannot lose or
loosen, and a profile's rule is a refinement for its own searches.

*Per run* was considered and rejected. A run is an execution record — one is
created each time a profile fires, four so far — not something an operator
authors, and a rule attached to it would be gone the next morning. The profile is
the persistent, authored thing.

### 2. The title verdict is `all_of(global, any_of(profiles))`

```
title_passed = all_of( global_rule(title),
                       any_of( profile_rule(title) for each contributing profile ) )
```

Both combinators are three-valued (`True` / `False` / `None` = not applied) and
live once, in `filters/combine.py`.

* **`all_of`** ignores what was not applied: `False` if any applied rule
  rejected, `True` if at least one applied and none rejected, `None` if nothing
  applied. That last case is what keeps installation a no-op.
* **`any_of`** is `levels.admits_any`'s rule, lifted so the title criterion cannot
  grow a subtly different one: admitted if any contributor admits; a contributor
  with nothing to say cannot withhold, so it counts as admitting; `None` when no
  contributor said anything.

**Rejected: per-contributor conjunction, then disjunction.** The first design
computed `any_of( all_of(global, profile_rule) for each contributor )`. It reads
naturally and it is wrong. With **no** contributing run — a posting no run
accounts for — the inner loop never executes, and the global rule vanishes: the
same title under the same exclude pattern would be rejected or kept according to
whether a `Run` row happened to exist, a cliff rather than a rule. It also
contradicts spec 003 ("title criteria, being global, still apply") and breaks
`test_filter_all_judges_a_posting_no_run_accounts_for`. Keeping the global rule
outside the per-profile combination makes it a hard gate that no amount of
attribution can lift, which is what "global" has to mean.

### 3. Exclude beats include, at every level

An explicit "never show me this" wins over a permissive include. Within one
pattern pair this was already so (`TitleRules.verdict` tests exclude first); it
now holds across levels, because the global rule and a profile's rule are both
binding and `False` from either rejects. A profile that asks for `senior` does not
get it past a global exclude of `senior`.

### 4. One profile's silence defeats another's exclude — deliberately

Across profiles the rule is disjunction, the same as the experience criterion. If
profile A excludes `analyst` and profile B sets no rule, a posting both found is
**kept**: B imposes nothing, so it cannot withhold, so it admits.

This is the leak, stated plainly rather than discovered. It is accepted because
the alternative — rejecting when any profile's exclude matches — lets a profile
the operator is not thinking about conceal a posting another profile asked for,
and there is no per-profile view in the triage queue in which the operator could
ever notice. Under the governing asymmetry, disjunction is the only admissible
combinator across profiles.

It was measured, not assumed. Excluding `developer` on `Backend developer` in a
rolled-back transaction against the live corpus: 18 postings matched. Five were
found only by that profile and were rejected. One was found by that profile and by
another, and was **defeated**. Twelve were found only by other profiles, which the
rule correctly never touched. The rule reaches the postings the profile alone
surfaced, and cannot reach the shared ones.

### 5. The verdict is a function of the set of contributing profiles

Consequence of 4, and a change in what the stored column promises. Before this
record `title_filter_passed` was a function of the posting and the criteria. It is
now a function of the posting, the criteria **and which profiles currently
contribute to it**. A posting a single profile's exclude rejected is admitted once
a second, silent profile also surfaces it — with no criteria change at all — and
the next application of the filter writes that.

This is documented behaviour with a test named for it, not a defect. The
converged re-application property (SC-007) holds for a fixed set of contributors,
and the difference-guarded write still emits nothing when nothing has changed. The
detail page's "stale verdict" notice now says *"the criteria, or the profiles that
found this posting, have changed"* rather than blaming the criteria alone, since
either can be the cause.

### 6. One builder, so the stage and the detail page cannot drift

The stage that stores a verdict and the page that re-derives it live (to say
whether the stored one is stale) both build their criteria through
`filters.build_criteria`, in the pure package. Previously each rebuilt a
`Criteria` by hand, which was two lines and safe; with per-profile rules it would
be a compile, a parse and a combination, and a second hand-written copy is how a
stored verdict and a displayed one come to disagree. A parametrised test pins that
they agree across the combinations that matter.

`Criteria` carries **one record per contributing profile** holding that profile's
requested level and its title rules together, so the two criteria cannot be
assembled from different sets of contributors.

### 7. Editing goes through a narrow route, not the generic update

`/profiles` had an add form and no edit form; `POST /profiles/{id}/update`
existed and nothing posted to it. Wiring a form to it is the obvious move and it
is a trap: `update()` writes every column `_clean` returns, and `_clean` defaults
every field it is not sent — so a form carrying only the filter fields would reset
the profile's country and schedule, blank its location, and **re-enable a disabled
profile**. Nothing had stepped on it because nothing posted there.

Editing therefore goes through `set_filter_rules` and
`POST /profiles/{id}/filters`, which can write exactly three columns —
`experience`, `title_include_pattern`, `title_exclude_pattern` — and nothing else,
so an operator can correct a profile without deleting it and losing the
`profile_id` every run is attributed to. The two new keys are also deliberately
left out of `_clean`'s defaults when the caller did not send them, so the generic
route cannot erase them by omission either. Fixing `_clean`'s existing defaults is
out of scope and noted below.

Malformed patterns are refused at the form, reusing `TitleRules.compile` as the
single definition of "valid" — narrowing FR-008 the same way `/settings` already
does — and the stage keeps its own guard, because a pattern can reach the database
another way and a run must never end on one. A fault now **names the profile**:
an operator with four profiles cannot act on "a pattern is invalid".

## Consequences

* **A profile with nothing set behaves as before**, and with no rule anywhere the
  verdict stays NULL. Verified against the live corpus: re-applying with the new
  columns installed changed 0 of 135 verdicts.
* **A profile's exclude rule is only as strong as its profile's exclusivity.** It
  fully governs postings no other profile found (89% of them today) and can be
  defeated on the rest. Operators who want a rule to be absolute should put it in
  the global settings.
* **A blank experience box has the same property** and is unchanged by this
  record: it admits everything the profile touches, overriding profiles that did
  state a requirement. Documented in the operations guide; see also
  [ADR-0017](0017-board-seniority-label-reliability.md).
* **The detail page cannot name which profile's pattern rejected a posting.**
  Under disjunction a rejection means *every* contributor rejected it, which is
  worth printing, but the banner does not yet. Noted, not done.
* **`/profiles` cannot trigger a re-apply.** A rule change reaches
  already-collected postings only after `filter --all`; the page says so.

## Not decided here

* How far to trust a board's seniority label — [ADR-0017](0017-board-seniority-label-reliability.md),
  proposed.
* `_clean`'s default-every-field behaviour, which makes the generic update route
  unsafe for partial forms. Left as found; flagged so the next change to that route
  does not walk into it.
* Per-(posting, profile) verdicts, rejected in ADR-0016 for want of profile context
  at read time, and not revisited.

## Relationship to other records

Extends [ADR-0016](0016-collect-stage-filter-verdicts.md), which decided how
verdicts are computed, stored and enforced and which fixed disjunction over
contributing profiles for the experience criterion; this record extends the same
rule to the title criterion and adds the global/profile layering. Nothing in
ADR-0016 is superseded — its statement that the title patterns are global
describes the state this record changes, and is read here as the baseline it
extends. Builds on [ADR-0015](0015-employer-level-suppression.md)'s read-time
mechanism, which is unchanged: the read-time predicates still read the same two
verdict columns and do not know profiles exist.

## Control

`test_the_detail_page_and_the_stage_reach_the_same_verdict` fails if the two
resolution paths diverge. `test_the_global_rule_binds_a_posting_no_run_accounts_for`
and `test_a_global_rule_with_a_silent_profile_matches_the_global_rule_alone` fail
if the global rule is ever nested inside the per-profile combination again — they
were checked against that mutation and each fails independently. The deliberate
leak is pinned by tests whose names say it is deliberate, so it reads as a
decision when a future change breaks it.
