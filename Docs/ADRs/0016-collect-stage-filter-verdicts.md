# ADR-0016: Filter verdicts — derived criteria, derived visibility

* Status: accepted
* Deciders: Mohammed
* Date: 16 November 2026

Technical Story: nothing in the pipeline rejected anything. A search profile's
term went to the boards, every row was landed, and stage 2 promoted every landed
row to a posting the operator triaged personally. The three columns built to
record a filter's verdict — `runs.filter_passed_count`,
`runs.filter_rejected_count`, `postings.title_filter_passed` — had never been
written by any code path, and the last was already rendered on the posting
detail page, where it always read blank. This record decides how the verdict is
computed, where it is stored, and how it is enforced. Specified in
[spec 003](../../specs/003-collect-stage-filtering/spec.md); extends
[ADR-0015](0015-employer-level-suppression.md)'s read-time mechanism to a second
kind of exclusion.

## Context and Problem Statement

Two criteria the operator had already expressed were doing nothing.

**Experience.** `SearchProfile.experience` was captured by the profiles form,
stored, and displayed back — then dropped in `services/profiles.to_spec()` when
the profile became a collector instruction. Its model comment said "advisory
until wired into the scorer — a post-collection filter, not a board parameter",
and nothing had ever wired it. The collection library exposes no experience
parameter and its board integrations emit none, so post-collection filtering is
the only available mechanism; this is a verified property of the dependency, not
a preference.

**Title relevance.** `title_include_pattern` and `title_exclude_pattern` have
existed in `config.py` since D6, ride in `RunConfig`, and are editable at
`/settings`. They sat in `services/settings.PENDING_KEYS` marked "stage 3 —
title filter" for four months, consumed by nothing, because the stage that was
to read them does not exist.

Meanwhile the signal needed to make the first criterion work was being collected
and thrown away. The boards supply a seniority label from a small controlled
vocabulary — measured 16 November 2026: **100% of LinkedIn rows, 0% of Indeed
rows** — and the system kept it only inside the verbatim payload, on the
strength of a 20 July 2026 measurement recording it as "LinkedIn-declared, never
populated".

**The governing asymmetry.** A posting wrongly rejected is one the operator never
sees and cannot recover by looking harder — the same class of failure as a false
merge in deduplication, and it must be guarded against at least as hard. A
posting wrongly kept costs a few seconds of triage. Every decision below is
resolved in that direction.

## Decision Drivers

* Unknown must never reject. Absence of evidence is not evidence of mismatch.
* Installing the filter with no criteria set must change nothing observable.
* A rejection must be reversible, with the operator's triage state intact.
* Re-applying unchanged criteria must converge, and be observably identical.
* The verdict must be defined for a posting several boards or profiles surfaced,
  not left to whichever row or run was processed last.

## Decision

### 1. The experience verdict is a disjunction over contributing profiles

A posting is admitted on experience grounds if **any** search profile that has
ever surfaced it admits it. A contribution from a profile-less run — a manual
`run-all` — admits unconditionally, as does a profile with no experience
recorded.

The obvious alternative, reading `run.profile_id` for the run being filtered, is
wrong rather than merely inferior. A posting can be surfaced by several profiles'
runs, as `services/reports.py` already records when it refuses to pick one
profile to credit. Its verdict would then be whichever the most recent run
computed: it would alternate with run order rather than converge, and a
whole-corpus re-apply would have no defined meaning at all.

Disjunction is commutative, associative and idempotent, so the verdict is a total
function of `(job_level, normalised_title, {profile.experience})` and nothing
else — which is what reduces "re-applying is identical" to "the function is pure
and nothing is timestamped".

**Rejected: a per-profile verdict table.** It is the only *fully* correct model
of a per-profile criterion — profile A should hide a posting that profile B
should show. It is rejected because the triage list has no profile context at
read time, so such a verdict could not be enforced by a read-time predicate at
all. It would be recorded and unenforceable.

**Accepted consequence.** Once a profile-less `run-all` has touched a posting, no
profile's experience criterion can withhold it, permanently. That follows from
the spec's own assumption and is the price of it. If the exemption becomes a
nuisance, the change to make is to ignore profile-less contributions where a
profile-attributed one exists — recorded here so that it is a decision rather
than a rediscovery.

### 2. Levels are an ordered scale with no `UNKNOWN` member

`internship < entry < associate < mid-senior < director < executive`, and a
request admits every level at or below its reach while rejecting those above.

Unknown is the **absence** of a level, returned as `None`, following
`normalise.country.parse_country`'s established rule that an unresolved value
stays unresolved and is counted rather than guessed. An `UNKNOWN` member inside
an orderable enum eventually meets a `<=` and silently admits or rejects
everything; keeping it outside the type makes that unrepresentable.

`not applicable` (in the boards' own vocabulary), the empty string (which the
collector emits for a LinkedIn row whose description was not fetched), whitespace
and a missing value are four spellings of one fact and all return `None`.

**On `associate`.** FR-007's worked example admits `associate` for an
entry-level request although it sits above `entry level` on the boards' scale.
That is encoded as an admission ceiling rather than a reordering: the boards use
`associate` for early-career roles overlapping entry, so the comparison treats
the two as one band while the column still records whichever label the board
gave.

### 3. One board label per posting, merged by minimum seniority

Where several collected rows fold into one posting, `postings.job_level` holds
the **lowest** label among them, ties broken lexicographically on the raw string.

Minimum, not first-seen: FR-009 asks for a value *defined* for the merged
posting, and minimum makes it a function of the set of contributing rows rather
than of processing order. The tie-break keeps the stored string itself
deterministic, so a re-apply cannot swap one spelling for another.

Minimum is also the admitting direction — rejection happens only above the
requested level, so when boards disagree the lowest label is the one that shows
the operator the posting.

**The title-derived fallback is never persisted.** `postings.job_level` is named
after a payload field and must answer "what did the board say?". Writing an
inference into it would repeat exactly the conflation
[ADR-0012](0012-retrieval-date-column-split.md) split `last_retrieved_at` from
`updated_at` to undo.

### 4. The verdict is two nullable booleans; the grounds are derived

`postings.title_filter_passed` (existing) and
`postings.experience_filter_passed` (new), one per criterion, each tri-state:

| Value | Meaning |
|---|---|
| NULL | the criterion was **not applied** — never filtered, or disabled (empty pattern, absent or unreadable experience, malformed pattern) |
| TRUE | applied, and **admitted** — including admitted because the input was unknown |
| FALSE | applied, and **rejected** |

Whether a posting is rejected, and on which grounds, is computed from the pair.

**Rejected: a stored reason column.** FR-011 makes criteria changes routine, and
the operator reads the grounds *because* they are about to loosen the rule that
produced them — so a recorded explanation is stale exactly when it is consulted.
A derived one cannot be. It also buys something a column could not: the detail
page re-evaluates under current criteria and says when the stored verdict
predates them.

**Rejected: a `filtered_at` timestamp.** It is the only field in the design
capable of making "re-applying produces identical verdicts" unfalsifiable, and
the run counters already carry the when.

**Rejected: NOT NULL with a default.** It would destroy the distinction between
"not applied" and "applied and admitted", which is the distinction that makes
installing the feature observably a no-op, and would make every existing posting
claim a verdict it never received.

### 5. Hiding is separate from the verdict, and enforced at read time

Two predicates in `db/visibility.py`:

* `filter_rejected()` — the verdict alone, with no reference to triage state.
* `hidden_by_filter()` — `filter_rejected() AND status = 'new'`, which is what
  every read path over `postings` negates.

A posting the operator has shortlisted or applied to is **never** withdrawn by a
later tightening. Triage is their judgement, and a criteria change must not reach
back into it. When the filter first ran on the live corpus, 10 of its 14
rejections were already triaged, so the status term is load-bearing rather than
defensive.

The review bucket is built on `filter_rejected()` and is deliberately **not** the
complement of the hide rule: a posting rejected *after* being shortlisted appears
in both the queue and the bucket, because that is the clearest available evidence
that a criterion is too aggressive — which is what the bucket exists to surface.

Enforcement is derived at read time and never stamped, exactly as ADR-0015
established for employer suppression, which is what makes a rejection reversible
for free rather than by engineering.

**Both predicates use `.is_(False)`, never `== False`.** Every verdict is NULL
until the stage has run, and stays NULL while no criteria are set. Under
three-valued logic `NOT (NULL = FALSE)` is NULL and the row is not selected, so
the obvious spelling would hide the **entire corpus** while a test suite that
only asserts absences stayed green. This is recorded as a decision because it
looks like a style choice and is not.

### 6. Its own re-runnable stage, without renumbering the design

The filter runs between deduplication and the planned scorer, as `filter`, with
`--run-id`, `--all` and `--dry-run`.

Stage 3 does not exist, so folding D6's filter into it would leave the counters
unwritten indefinitely. FR-011 needs a standalone entry point regardless —
re-evaluating under changed criteria without re-collecting is the whole of the
operator's ability to tune it — and once that exists, "inside stage 3" is merely
a call site. The design's stage numbering is left intact: this extracts D6's
filter out of stage 3 into a prior step whose verdict stage 3 will consume.

`--all` writes no run counters. FR-015's counts belong to a run that evaluated
postings during an execution; attaching a re-application's totals to some past
run would decouple them from its `collected_count` and break the invariant that
passed + rejected equals that run's distinct postings.

Writes are difference-guarded, so a converged re-application emits no UPDATE at
all. `postings.updated_at` carries `onupdate`, and a blind write would move every
row's timestamp without changing a verdict.

## Consequences

*Favourable:*

- The operator's two stated criteria take effect, and the per-run funnel the
  counts were designed to expose stops being flat by construction.
- A rejection is reversible: loosen the criteria, re-run `filter --all`, and the
  posting returns with its triage status intact, because nothing writes it.
- `job_level` is typed and inspectable, so the filter never reaches into JSONB —
  which also avoids the dialect split `queries._has_source` needed.
- Stage 3, when built, inherits a smaller candidate set through a seam it must
  adopt rather than logic it must duplicate. D6's stated purpose, finally served.

*Unfavourable, and accepted:*

- **A second read-path obligation.** There were one; there are now two, and
  forgetting either is silent. Contained the same way ADR-0015 contained the
  first: one definition, a closed inventory
  ([read-path-inventory.md](../../specs/002-employer-suppression-derived/contracts/read-path-inventory.md),
  extended in place rather than cloned), per-path two-sided tests, and
  `queries._visible()` so a read path adopts the pair as one idiom.
- **A profile-less run permanently exempts what it touches** (decision 1).
- **`linkedin_fetch_description` is a hidden switch on the experience
  criterion.** The collector populates `job_level` only when descriptions are
  fetched, so turning that editable setting off takes the criterion's primary
  input from 100% coverage to 0% on the only board that supplies it. It fails
  *open*, which is the right direction, but silently, which is not. Recorded
  here and noted on the settings field; forcing the setting on would override a
  deliberate operator choice from an unrelated screen.
- **Installing is not behaviour-neutral on an installation that already records
  an experience value.** "No criteria set" is a statement about criteria, not
  about this machine, where a profile already stores `entry level`.
  `--dry-run` exists so that effect is measured before it is enforced.

## Relationship to ADR-0007

[ADR-0007](0007-scoring-evaluation-and-score-history.md) §O3 leaves the title
pre-filter unresolved — "replace, demote, or drop" — and leans toward replacing
the regex with an embedding gate, the regex demoted to an availability fallback.

This record **does not settle O3**. It implements the regex gate D6 specifies,
because that is what spec 003 asks for and what the operator's existing settings
express. What it does is make O3 answerable: ADR-0007 names three measurements
that would settle the question, the first being "the filter's current drop rate,
from the `title_filter_passed` column already in the schema" — a column that was
unwritten precisely because this filter had never been built. It is written now.

A later record may replace the regex. It should treat this one's §4 and §5 —
the verdict's shape and its enforcement — as orthogonal to how the title
decision is reached, because they are.

## Control

The invariant this ADR establishes, alongside ADR-0015's:

> **A filter verdict is a statement about criteria, and a triage status is a
> statement about the operator's judgement. Neither is ever written into the
> other, and a posting is filtered by its verdict, never stamped as rejected
> because of it.**

If a future requirement needs to know *when* a verdict was computed, or to report
on filtering over time, put it on the run — do not add a timestamp to the posting
and do not let a criterion write `status`.
