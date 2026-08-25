# Feature Specification: Employer-level suppression, derived at read time

**Feature Branch**: `job-post-transitions` *(spec directory `002-employer-suppression-derived`; this work continues an existing branch rather than opening a new one, per the implementation plan)*

**Created**: 13 August 2026

**Status**: Draft

**Input**: User description: "Employer-level suppression derived at read time (ADR-0015): stop stamping `rejected` on postings when their employer is blacklisted; instead answer 'is this posting out of play because of its employer?' at read time from `employers.suppressed`, through one shared filter seam that every read path applies. Implements Docs/design/IMPLEMENTATION_PLAN_ADR-0015-Employer-level.md and Docs/ADRs/0015-employer-level-suppression.md. Supersedes FR-007, FR-009, FR-011 of specs/001-ui-self-service."

**Implements**: [ADR-0015](../../Docs/ADRs/0015-employer-level-suppression.md) · [Implementation plan](../../Docs/design/IMPLEMENTATION_PLAN_ADR-0015-Employer-level.md)

**Supersedes**: [001-ui-self-service](../001-ui-self-service/spec.md) FR-007, FR-009, FR-011

---

## Problem

Today a posting's triage status carries two unrelated facts at once: what the
operator thinks of the posting, and whether the posting's employer is
blacklisted. The second is a copy — the employer record already holds it — and
the copy is pushed down onto every posting of that employer as *Rejected*.

Two copies of one fact can disagree, and the machinery that keeps them agreeing
is where the operator loses work:

- The system overwrites the operator's own judgement. A posting the operator
  shortlisted becomes Rejected, and afterwards nothing on disk distinguishes
  "the operator rejected this" from "the system rejected this".
- Because the overwrite destroyed the operator's decision, un-blacklisting
  cannot restore it. A blacklist applied by mistake is not reversible.
- New postings from a blacklisted employer are only suppressed once a catch-up
  pass runs, so between collection and that pass they are visible.

This feature removes the copy. Blacklist state lives on the employer alone, and
whether a posting is out of play because of its employer is worked out at the
moment it is read.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A blacklisted employer disappears completely (Priority: P1)

The operator blacklists an employer they never want to hear from again. From
that moment, that employer's postings are absent from every view the operator
works in: the posting list, the result count above it, the dashboard figures,
the filter options, and anything eligible for publication. Nothing is left
half-hidden — there is no view in which the employer still shows up.

**Why this priority**: This is the whole point of a blacklist, and it is the
property that must never regress. Everything else in this feature is in service
of it.

**Independent Test**: Blacklist an employer that has postings across several
triage statuses and countries, then check every operator-facing view. The
employer and its postings are absent from all of them, and the list's total
count matches the rows actually shown.

**Acceptance Scenarios**:

1. **Given** an employer with postings in New, Shortlist, and Applied,
   **When** the operator blacklists that employer,
   **Then** none of those postings appear in the posting list, and the list's
   reported total excludes them.
2. **Given** the same employer,
   **When** the operator views the dashboard,
   **Then** the posting, published, scored, and per-status figures all exclude
   that employer's postings, and the employer count excludes the employer.
3. **Given** a blacklisted employer whose postings are the only ones from a
   particular country,
   **When** the operator opens the country filter,
   **Then** that country is not offered, because selecting it could only return
   an empty list.
4. **Given** a posting that was already marked as published,
   **When** its employer is blacklisted,
   **Then** the posting is excluded from the published view.

---

### User Story 2 - Suppression covers postings not yet collected (Priority: P2)

Having blacklisted an employer, the operator does not have to think about it
again. A posting collected from that employer tomorrow, or next month, is
suppressed the moment it arrives. No catch-up job runs, and there is no window
in which the new posting is visible.

**Why this priority**: This is the requirement that the previous design could
only satisfy with a reconciliation pass, and the reason that pass existed. It
is separable from Story 1 — Story 1 concerns postings that already exist — and
it is where the previous design leaked.

**Independent Test**: Blacklist an employer, then run collection so a new
posting from that employer is stored. Without running anything else, confirm the
new posting is invisible in every view from Story 1, and that its triage status
was never touched by the system.

**Acceptance Scenarios**:

1. **Given** an employer that is already blacklisted,
   **When** a new posting from that employer is collected and stored,
   **Then** the posting is recorded with the ordinary starting triage status,
   **And** it does not appear in the posting list or its total.
2. **Given** that newly collected posting,
   **When** the operator inspects the record of triage decisions,
   **Then** there is no system-authored entry claiming to have rejected it.

---

### User Story 3 - Un-blacklisting restores what it hid (Priority: P2)

The operator blacklists an employer, then changes their mind — a mis-click, or a
company that turned out to be worth watching. Removing the blacklist brings that
employer's postings back exactly as they were: a posting the operator had
shortlisted returns as shortlisted, one the operator had genuinely rejected
stays rejected, and one never triaged returns as new.

**Why this priority**: A blacklist that cannot be undone is a trap, and it is
the failure that motivated this change. It ranks alongside Story 2 rather than
above it because the safety property (nothing leaks) must hold first.

**Independent Test**: Record the triage status of every posting of an employer,
blacklist the employer, un-blacklist it, and confirm each posting is visible
again carrying the status it started with.

**Acceptance Scenarios**:

1. **Given** an employer with one shortlisted, one applied, one new, and one
   operator-rejected posting,
   **When** the operator blacklists and then un-blacklists that employer,
   **Then** all four postings are visible again, each with its original triage
   status.
2. **Given** the same sequence,
   **When** the operator inspects the record of triage decisions for those
   postings,
   **Then** it shows no entries added by the blacklist or the un-blacklist.
3. **Given** an employer blacklisted *before* this change took effect, whose
   postings were stamped Rejected at the time,
   **When** the operator un-blacklists that employer,
   **Then** those postings remain Rejected, **And** the blacklist view explains
   that blacklists applied before this change do not restore on removal.

---

### User Story 4 - The way back out stays reachable (Priority: P3)

A suppressed posting is hidden from the lists, but the operator who arrives at
its detail page — from a bookmark, a browser-history entry, or a link kept from
before the blacklist — still sees the page, sees clearly that the employer is
blacklisted, and can remove the blacklist from there.

**Why this priority**: Without it, filtering is a one-way door: the posting that
would tell the operator *why* something vanished becomes the one page they
cannot open. Low priority because it is a deliberate carve-out from Story 1
rather than new capability.

**Independent Test**: Note a posting's address, blacklist its employer, then open
that address directly. The page loads, shows the blacklist state, and offers the
removal action.

**Acceptance Scenarios**:

1. **Given** a posting whose employer is blacklisted,
   **When** the operator opens that posting's detail page directly,
   **Then** the page loads rather than reporting the posting as missing,
   **And** it shows that the employer is blacklisted,
   **And** it offers the action to remove the blacklist.

---

### Edge Cases

- **A posting is collected from an employer that is blacklisted moments later.**
  The posting is stored normally; the next read of any view already excludes it.
  Nothing needs to re-examine it.
- **An employer is blacklisted while the operator is looking at a list page that
  includes its postings.** The stale page is not rewritten; the next request the
  operator makes reflects the blacklist. The operator's next triage action on a
  now-suppressed posting is a decision on their own status field and does not
  conflict with the blacklist.
- **An employer is blacklisted, un-blacklisted, and blacklisted again.** Triage
  statuses are untouched throughout; visibility follows the current flag each
  time.
- **A posting the operator genuinely rejected, whose employer is then
  blacklisted and later un-blacklisted.** It returns as Rejected — the
  operator's own decision, preserved rather than re-derived.
- **Postings stamped Rejected by the old mechanism.** They stay Rejected and are
  left alone. Which of them were rejected by the operator and which by the old
  sweep is not recoverable, so nothing tries to guess.
- **Every posting in the system belongs to blacklisted employers.** The list is
  legitimately empty and reports a total of zero; the dashboard reads zero
  rather than showing a count no view can account for.
- **A report that deliberately measures collector behaviour.** It counts what the
  boards returned, including suppressed employers, and says so — otherwise it
  would understate a board's coverage.

---

## Requirements *(mandatory)*

### Functional Requirements

**Where suppression lives**

- **FR-001**: Employer blacklist state MUST be held in exactly one place — on the
  employer record. The system MUST NOT record it on individual postings.
- **FR-002**: A posting's triage status MUST represent operator judgement only.
  The system MUST NOT set a posting's triage status as a consequence of its
  employer being blacklisted, at any time, including when the posting is first
  stored.
- **FR-003**: Blacklisting an employer MUST take effect for every posting of that
  employer — those already collected and those collected afterwards — without any
  subsequent reconciliation or catch-up pass.
- **FR-004**: Blacklisting and un-blacklisting MUST each take effect as a single
  indivisible change, such that no reader can observe a partially applied
  blacklist.
- **FR-005**: The record of triage decisions MUST contain no entries attributable
  to blacklisting or un-blacklisting.

**What suppression hides** *(supersedes 001 FR-007 and FR-009)*

- **FR-006**: Postings of a blacklisted employer MUST NOT appear in the posting
  list, and MUST NOT be included in the total that list reports. The total and
  the rows shown MUST be derived consistently, so the pager cannot claim results
  the operator cannot reach.
- **FR-007**: Postings of a blacklisted employer MUST be excluded from the
  dashboard's total, published, scored, and per-status figures. The dashboard's
  employer figure MUST exclude blacklisted employers.
- **FR-008**: Filter options offered to the operator MUST be derived only from
  postings the operator can see, so that no offered option can return an empty
  result purely because of suppression.
- **FR-009**: Postings of a blacklisted employer MUST never be published, and
  this MUST hold whether or not the posting was marked published before its
  employer was blacklisted.
- **FR-010**: Every path that reads postings MUST either apply the suppression
  rule or carry a recorded, justified exemption. An exemption MUST state its
  reason at the point of exemption; a path that neither applies the rule nor
  records an exemption is a defect.
- **FR-011**: Future stages that read postings — scoring and publication — MUST
  apply the suppression rule when selecting postings to work on and when
  reporting counts of work done.

**Reversal** *(supersedes 001 FR-011, which this inverts)*

- **FR-012**: Removing an employer's blacklist MUST restore that employer's
  postings to visibility, each carrying the triage status it held before the
  blacklist was applied.
- **FR-013**: The blacklist view MUST state that postings suppressed before this
  change took effect remain Rejected when their employer's blacklist is removed,
  so the operator is not surprised by the difference between old and new
  blacklists.

**Preserved from 001**

- **FR-014**: Postings of a blacklisted employer MUST be retained, never deleted
  (design D9; 001 FR-008 unchanged).
- **FR-015**: The operator MUST be able to reach a suppressed posting's detail
  page, see that its employer is blacklisted, and remove the blacklist from
  there.
- **FR-016**: Existing postings stamped Rejected by the previous mechanism MUST
  be left unmodified. The system MUST NOT attempt to determine which historical
  rejections were operator decisions and which were system decisions.

**Reporting**

- **FR-017**: A report whose subject is what the collector retrieved, rather than
  what the operator should act on, MUST be permitted to include suppressed
  employers, and MUST state that it does so.

### Superseded requirements from 001-ui-self-service

| 001 requirement | Status | Replaced by |
|---|---|---|
| FR-007 — blacklist sets every posting to Rejected | **Reversed.** No posting's status is changed by a blacklist | FR-002, FR-003, FR-006 |
| FR-008 — auto-rejected postings retained, never deleted | **Stands**, reworded — postings are hidden, not auto-rejected | FR-014 |
| FR-009 — a blacklisted employer's postings are never published | **Stands**, enforcement moves from write time to read time | FR-009 |
| FR-011 — removing a blacklist does not reinstate previously rejected postings | **Inverted.** Removing a blacklist restores postings with their prior status | FR-012, FR-013 |

### Key Entities

- **Employer**: The party a posting is attached to. Carries the single
  authoritative record of whether it is blacklisted. Nothing else in the system
  needs to be updated when that changes.
- **Posting**: A job advertisement attached to exactly one employer. Carries a
  triage status that means only "what the operator thinks of this", and which
  only the operator's actions change.
- **Triage decision record**: The history of who moved a posting to which status
  and why. After this change it contains operator decisions only.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Blacklisting an employer removes its postings from every
  operator-facing view within that single operator action — no scheduled run, no
  waiting period, no second step.
- **SC-002**: A posting collected from an already-blacklisted employer is
  invisible from the moment it is stored, with zero reconciliation passes having
  run.
- **SC-003**: Across a blacklist-then-remove cycle applied after this change,
  100% of the employer's postings return carrying the exact triage status they
  held beforehand.
- **SC-004**: The triage decision record accumulates zero system-authored
  entries as a result of blacklisting activity, measured over a full
  blacklist/collect/remove cycle.
- **SC-005**: 100% of the paths that read postings are accounted for — each
  either applies suppression or carries a recorded justification for not doing
  so — with zero paths unexamined.
- **SC-006**: Every one of the views named in FR-006 through FR-009 has a test
  proving a blacklisted employer's posting is absent from it, so that removing
  the rule from any single view fails the suite rather than passing silently.
- **SC-007**: The operator can undo a blacklist applied by mistake in one
  action, with no data loss.

---

## Assumptions

- **The operator is a single person on a low-traffic local tool.** Solutions are
  sized accordingly: no retry loops, no version columns, no coordination
  protocols.
- **No schema change is needed.** The employer blacklist flag and its supporting
  index already exist and are already written by the blacklist action; what
  changes is that they become the only record, and that reads consult them.
- **The suppression rule is applied through one shared definition** rather than
  restated per query, because FR-010's obligation is only sustainable if there
  is a single thing to apply and a single place to read about the obligation.
  This is the one structural commitment the spec makes, and ADR-0015 names it as
  the place the decision can go wrong.
- **Historical Rejected rows are ambiguous and stay that way.** The triage
  decision record post-dates the old mechanism, so it cannot attribute
  pre-existing rejections. FR-016 accepts the resulting asymmetry between old
  and new blacklists rather than guessing; FR-013 makes the asymmetry visible
  instead of silent.
- **FR-013's wording is adopted from the implementation plan's recommendation.**
  The plan calls surfacing the asymmetry "worth surfacing on the blacklist page"
  without scheduling it; this spec treats it as in scope at its minimum useful
  form — a standing note on the blacklist view, not a per-posting distinction,
  which is not recoverable in any case.
- **Scoring and publication do not exist yet.** FR-011 states an obligation they
  inherit; building them is not part of this feature.
- **Publication is currently latent.** Nothing marks postings as published today,
  so FR-009's read-time enforcement is proven against the published filter rather
  than against a live publication flow.

## Out of Scope

- **Hiding a restored back catalogue.** FR-012 means removing a blacklist can
  return a batch of older postings to the queue. If that is unwanted, the remedy
  is a UI affordance — default-hide with an explicit restore, or a date filter —
  chosen deliberately with full information. It is a separate feature, and this
  spec deliberately does not smuggle it in as an irreversible mutation.
- **Rewriting historical Rejected postings** (see FR-016).
- **Building the scoring or publication stages** (see FR-011).
- **Recording when an employer was blacklisted, or reporting on suppression over
  time.** If that is ever needed it belongs on the employer record or an employer
  history — never as a per-posting copy, which is the invariant this feature
  establishes.