# Feature Specification: Collect-stage relevance and experience filtering

**Feature Branch**: `003-collect-stage-filtering` *(spec directory `003-collect-stage-filtering`)*

**Created**: 9 September 2026

**Status**: Draft

**Input**: User description: "Plumb the search profile's requested experience through to a post-collection filter; implement a filter step that evaluates each collected posting for relevance (title include/exclude patterns per D6) and for experience level (using the board-supplied seniority label where present, falling back to title-derived markers where absent); make the filter observable by populating `runs.filter_passed_count`, `runs.filter_rejected_count` and `postings.title_filter_passed`; and decide whether the board-supplied seniority, function and industry fields should be promoted out of the raw payload now that coverage justifies it."

**Implements**: design D6 (coarse pre-filter on title), the standing intent of `SearchProfile.experience` ("advisory until wired into the scorer — a post-collection filter, not a board parameter")

**Precedent**: [ADR-0015](../../Docs/ADRs/0015-employer-level-suppression.md) — exclusion is derived at read time and never destroys operator state

---

## Problem

Nothing in the pipeline rejects anything. A search profile's term is handed to
the job boards, every row they return is landed, and stage 2 promotes every
landed row to a posting the operator must personally triage. The three columns
built to record a filter's verdict — `runs.filter_passed_count`,
`runs.filter_rejected_count`, `postings.title_filter_passed` — have never been
written by any code path, and the last of them is already rendered in the
posting detail view, where it always reads as blank.

The cost is measurable. Across 32 runs and 1,092 collected rows (measured 9
September 2026):

- **Experience is ignored entirely.** The "Backend Developer" profile records a
  requested experience of `fresh`. It received 220 rows labelled *mid-senior
  level* against 85 labelled *entry level* — 61% of its haul is at the wrong
  seniority. The requested value never leaves the database: it is captured by
  the profiles form, stored, and displayed back, but dropped when the profile is
  converted into a collector instruction.
- **Off-topic postings arrive and stay.** The "Web Developer" profile's results
  contain `QA Analyst`, `Boomi Technical Consultant` and `IT Sales Systems
  Developer` alongside genuinely relevant roles. Every one of them became a
  posting.
- **Every run's funnel is flat.** In all 32 runs the number of rows landed
  equals the number collected, and deduplication is the only step at which the
  count ever falls.

The signal needed to fix the first problem is already being collected and
discarded. The boards supply a seniority label on 78% of all rows — on one board
it is present on 100% of rows, drawn from a small controlled vocabulary
(*mid-senior level*, *entry level*, *associate*, *not applicable*, *executive*,
*internship*, *director*) — and the system currently keeps it only inside the
verbatim raw payload, on the strength of a coverage measurement taken on 20 July
2026 that is now stale.

This feature adds the missing filter, feeds it the criteria the operator has
already expressed, and makes its verdict visible.

**The governing constraint is asymmetric.** A posting wrongly rejected is a
posting the operator never sees and cannot recover by looking harder — it is the
same class of failure as a false merge in deduplication, and it must be guarded
against at least as hard. A posting wrongly kept costs the operator a few
seconds of triage.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A profile's experience level is honoured (Priority: P1)

The operator records that a search profile is for fresh-graduate roles. From the
next run onward, the postings that reach their triage queue are the ones at or
near that level. Senior, director and executive postings for that profile stop
arriving. Postings the boards gave no seniority information for still arrive —
the operator would rather judge those personally than have them silently
withheld.

**Why this priority**: This is the largest measured source of noise (61% of one
profile's haul), the criterion the operator has already taken the trouble to
record, and the one where the raw material for a fix is already being collected
and thrown away.

**Independent Test**: Set a profile's experience to a fresh/entry level, run the
pipeline against a corpus containing a known mix of seniority labels, and
confirm the operator's queue contains the entry-level and unlabelled postings
and none of the senior/director/executive ones.

**Acceptance Scenarios**:

1. **Given** a profile requesting an entry-level role, **When** a run collects a
   posting the board labelled *mid-senior level*, **Then** that posting does not
   appear in the operator's queue and is recorded as rejected on experience
   grounds.
2. **Given** a profile requesting an entry-level role, **When** a run collects a
   posting the board labelled *entry level*, **Then** that posting appears in the
   operator's queue and is recorded as passed.
3. **Given** a profile requesting an entry-level role, **When** a run collects a
   posting for which the board supplied no seniority label at all, **Then** that
   posting appears in the operator's queue rather than being withheld.
4. **Given** a profile with no experience recorded, **When** a run collects
   postings at every seniority level, **Then** none of them are rejected on
   experience grounds and the operator's queue is exactly what it is today.

---

### User Story 2 - Obviously off-topic postings stop arriving (Priority: P2)

The operator, having seen `QA Analyst` and `Boomi Technical Consultant` turn up
under a web-developer search, expresses a coarse rule about which job titles are
worth their attention. Postings whose titles fail that rule stop reaching the
queue. The rule is deliberately coarse: it exists to remove the obviously
irrelevant, not to judge fit, which remains the scorer's job.

**Why this priority**: Second-largest source of noise, and unlike experience it
needs the operator to author a rule before it does anything — so it delivers
value slightly later and depends on their judgement rather than on data already
in hand.

**Independent Test**: Author an include rule and an exclude rule, run the
pipeline against a corpus containing both matching and non-matching titles, and
confirm the queue contains exactly the titles the rules admit.

**Acceptance Scenarios**:

1. **Given** an exclude rule covering `QA Analyst`, **When** a run collects a
   posting with that title, **Then** it does not appear in the operator's queue
   and is recorded as rejected on title grounds.
2. **Given** an include rule, **When** a run collects a posting whose title does
   not satisfy it, **Then** that posting does not appear in the queue.
3. **Given** no title rules are set at all, **When** a run collects any posting,
   **Then** nothing is rejected on title grounds — the system behaves exactly as
   it does today.
4. **Given** a title rule the operator has written incorrectly and which cannot
   be applied, **When** a run executes, **Then** the run completes, the fault is
   reported to the operator, and no posting is rejected on the strength of the
   unusable rule.

---

### User Story 3 - The operator can see and tune what the filter did (Priority: P3)

The operator can tell, per run, how many postings the filter admitted and how
many it turned away, and for any individual posting whether it passed and on
what grounds. Having seen that, they can change the criteria and re-apply them
to postings already collected, without waiting for the boards to be scraped
again. A posting the filter turned away is recoverable: loosening the criteria
brings it back with its triage state intact.

**Why this priority**: Makes the first two stories safe to operate and to trust.
Without it, a filter that is rejecting too much is indistinguishable from boards
that have stopped returning results — the exact silent-decay failure the
per-stage counts were introduced to expose. It is P3 only because the filtering
itself must exist before there is anything to observe.

**Independent Test**: Run the pipeline, read the per-run passed and rejected
counts and confirm they account for every posting evaluated; open a rejected
posting and read why it was rejected; loosen the criteria, re-apply, and confirm
the posting returns with its prior triage status unchanged.

**Acceptance Scenarios**:

1. **Given** a completed run, **When** the operator inspects it, **Then** the
   passed and rejected counts are both present and together account for every
   posting the run evaluated.
2. **Given** a posting the filter rejected, **When** the operator inspects it,
   **Then** they can see that it was rejected and which criterion rejected it.
3. **Given** a posting rejected under criteria the operator then loosens, **When**
   the filter is re-applied to already-collected data, **Then** the posting is
   admitted again and carries the triage status it held before.
4. **Given** the filter is applied twice to the same collected data with
   unchanged criteria, **When** the second application completes, **Then** the
   resulting state is identical to the first — including the reported counts.

---

### Edge Cases

- **No seniority signal from the board.** One board supplies no seniority label
  on any row (0% coverage). Those postings must never be rejected on experience
  grounds by default; the fallback is a best-effort reading of the job title,
  and where even that is silent the posting is admitted.
- **A seniority label meaning "unknown".** The board's vocabulary includes *not
  applicable*, and some rows carry an empty label. These are absent information,
  not a level, and must be treated as unknown rather than as a mismatch.
- **The requested experience is unrecognised.** The stored value is free text
  and existing rows contain values like `fresh`. A value the system cannot
  interpret must disable the experience criterion for that profile and be
  reported, never silently reject everything.
- **A posting surfaced by two boards.** Deduplication folds several collected
  rows into one posting, and those rows may disagree — one board labelling it
  *entry level* and the other supplying nothing. The verdict must be defined for
  the merged posting, not left to whichever row happened to be processed last.
- **A posting already triaged.** A posting the operator has shortlisted or
  applied to must not be removed from view by a later tightening of the filter.
- **Criteria changed between runs.** Re-applying the filter must re-evaluate
  every posting under the current criteria rather than trusting a stale verdict,
  and must converge on the same state however many times it is applied.
- **Every posting rejected.** A criterion that rejects a run's entire haul is
  indistinguishable in the aggregate counts from a board that has stopped
  responding; the two must remain distinguishable to the operator.
- **A run with no search profile.** Runs triggered manually across all profiles
  record no single profile, and three such runs already exist. The filter must
  define its behaviour for postings whose originating profile is unknown.

---

## Requirements *(mandatory)*

### Functional Requirements

**Criteria plumbing**

- **FR-001**: The experience level recorded on a search profile MUST reach the
  filtering step. It is currently discarded when a profile is converted into a
  collector instruction.
- **FR-002**: The profile's experience MUST remain free text, and the system
  MUST interpret it against the boards' seniority vocabulary through a
  recognised set of synonyms — so that values already stored, such as `fresh`,
  become effective without the operator re-entering them.
- **FR-002a**: A stored experience value the system does not recognise MUST
  disable the experience criterion for that profile and MUST be reported to the
  operator. It MUST NOT cause postings to be rejected, and MUST NOT prevent the
  title criteria from applying.
- **FR-003**: The title criteria MUST be expressible by the operator and MUST be
  empty by default, so that installing this feature changes no behaviour until
  criteria are deliberately set.

**Filtering behaviour**

- **FR-004**: The system MUST evaluate every posting against the title criteria
  and the experience criterion, and record a verdict for each.
- **FR-005**: A posting for which the criterion's input is absent or means
  "unknown" MUST be admitted, never rejected. Absence of evidence is not
  evidence of mismatch.
- **FR-006**: Where a board supplies no seniority label, the system MUST make a
  best-effort determination from the job title, and MUST admit the posting where
  the title is also silent.
- **FR-007**: The seniority levels MUST form an ordered scale, and an experience
  criterion MUST admit every posting at or below the requested level while
  rejecting those above it. A request for a fresh/entry-level role therefore
  admits internship, entry-level and associate postings and rejects mid-senior,
  director and executive ones. The rule is deliberately asymmetric: a role
  below the requested level is worth the operator's glance, a role well above it
  is not.
- **FR-008**: Criteria that cannot be applied (malformed, uninterpretable) MUST
  NOT reject any posting, MUST NOT end the run, and MUST be reported to the
  operator.
- **FR-009**: Where several collected rows fold into one posting, the system
  MUST produce a single defined verdict for that posting, and MUST prefer an
  informative signal from any contributing row over the absence of a signal in
  another.
- **FR-010**: Filtering MUST be idempotent — applying it repeatedly to the same
  postings under the same criteria MUST converge on the same state and the same
  reported counts.
- **FR-011**: Filtering MUST re-evaluate postings under the current criteria
  when re-applied, so that changing the criteria changes the outcome without
  requiring re-collection from the boards.

**Preservation**

- **FR-012**: Filtering MUST NOT reduce, alter, or prevent what the collection
  step stores. Every row a board returns MUST continue to be landed verbatim,
  whatever the filter's verdict, so a criteria change can be re-applied to
  history rather than requiring a re-scrape.
- **FR-013**: A rejected posting MUST be recoverable. Rejection MUST NOT destroy
  or overwrite the operator's triage state, and loosening the criteria MUST
  restore the posting to view with that state intact.
- **FR-014**: Filtering MUST NOT change the triage status of any posting.
  Rejection and operator judgement are separate facts and must not be conflated,
  as employer suppression already establishes.

**Observability**

- **FR-015**: Each run MUST report how many postings the filter admitted and how
  many it rejected, and those figures MUST together account for every posting
  evaluated.
- **FR-016**: Each posting MUST carry its filter verdict, and the operator MUST
  be able to see which criterion rejected a rejected posting.
- **FR-017**: The operator MUST be able to review the postings the filter
  rejected, so that over-aggressive criteria are discoverable rather than silent.

**Collected fields**

- **FR-018**: The board-supplied seniority label MUST be available to the filter
  for every posting that has one.
- **FR-019**: The board-supplied seniority label MUST be promoted out of the
  verbatim payload into a first-class attribute of the posting, so the filter's
  primary input is typed and directly inspectable rather than reached through
  the landing zone.
- **FR-020**: The recorded coverage measurement that justifies leaving the
  board-supplied seniority, function and industry fields unused MUST be
  corrected for all three, since it no longer reflects the data. Function and
  industry are documented accurately and left in the payload; they do not become
  filter criteria in this feature.

### Key Entities

- **Search profile**: The operator's saved definition of a job survey. Already
  holds a requested experience level; this feature makes that value effective.
- **Collected row**: A verbatim board result. Append-only and unaffected by this
  feature; the source of the board-supplied seniority label.
- **Posting**: One real-world role. Gains a filter verdict and the grounds for
  it. Its triage status is untouched by filtering.
- **Run**: One pipeline execution. Gains populated admitted/rejected counts,
  completing the per-stage funnel it was designed to expose.
- **Filter criteria**: The title rules and the requested experience level, drawn
  from operator-editable configuration and from the search profile respectively.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a profile that records a requested experience level, at least
  90% of the postings reaching the operator's queue are at that level or carry
  no level information. Baseline on current data: 24% for the "Backend
  Developer" profile.
- **SC-002**: Zero false rejections across the regression corpus — no posting
  that satisfies the operator's stated criteria is withheld. This is verified by
  a body of tests that is at least as large as the body proving rejection works.
- **SC-003**: Every completed run reports admitted and rejected counts that sum
  to the number of postings it evaluated, replacing the flat funnel that all 32
  historical runs show.
- **SC-004**: An operator who changes the filter criteria can see the effect on
  already-collected postings without any board being contacted again, and within
  a minute for a thousand postings.
- **SC-005**: For any posting withheld from the queue, the operator can
  determine within one interaction that the filter withheld it and which
  criterion did so.
- **SC-006**: Installing the feature without setting any criteria changes no
  operator-visible outcome: the same postings arrive as before.
- **SC-007**: Re-applying the filter to unchanged data produces byte-identical
  verdicts and identical counts.

---

## Assumptions

- **Unknown never rejects.** Where a criterion's input is missing, blank, or
  explicitly "not applicable", the posting is admitted. This follows directly
  from the asymmetry between a false rejection and a false acceptance, and is
  applied throughout rather than being decided per criterion.
- **Rejection hides rather than deletes.** A rejected posting continues to exist
  with its history and triage state; it is withheld from the operator's views at
  the point they are read. This mirrors the approach already established for
  employer suppression, and is what makes a criteria change reversible.
- **The title criteria are global; the experience criterion is per profile.**
  The title include/exclude configuration already exists as operator-editable
  settings shared across the pipeline, whereas experience is recorded on each
  search profile. This feature does not move either.
- **Coarse, not clever.** The filter's job is to remove the obviously
  irrelevant cheaply, so that the expensive scoring step runs on fewer postings.
  Judging genuine fit remains the scorer's job and is out of scope here.
- **Postings from a profile-less run are admitted on experience grounds**, since
  no requested level exists to compare against. Title criteria, being global,
  still apply to them.
- **Existing postings are not retroactively filtered on installation.** The
  filter applies from its first application onward; whether to apply it to the
  1,092 rows already collected is an operator action, not an install step.
- **No board parameter can carry experience.** The collection library exposes no
  experience parameter and its board integrations emit none, so post-collection
  filtering is the only available mechanism. This is a verified property of the
  current dependency, not a design preference.

---

## Out of Scope

- Scoring postings for fit against the CV, which remains the separate scoring
  stage this filter feeds.
- Publication and the threshold that governs it.
- Adding new job boards, or changing what is collected from existing ones.
- Any change to how postings are deduplicated into real-world roles.
