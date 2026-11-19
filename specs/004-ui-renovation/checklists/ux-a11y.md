# UX & Accessibility Requirements Checklist: UI renovation (004)

**Purpose**: test whether the *requirements* for UX and WCAG 2.2 AA accessibility are
complete, clear, consistent and measurable before tasks are generated ("unit tests for the
English"). This does not verify the implementation; that is `verification.md`.
**Created**: 2026-11-19
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [contracts](../contracts/htmx-fragments.md)
**Depth**: Standard · **Audience**: the author before `/speckit-tasks`, and the reviewer at
PR time.

How to read the marks:
- `[x]` the spec or plan already answers the question.
- `[ ]` it is still open.
- *Amended* means the gap was found by this checklist and the spec was fixed in this pass.

## Requirement Completeness

- [x] CHK001 Are WCAG 2.2 AA requirements listed explicitly, rather than "accessible" in
      general? [Completeness, Spec §FR-008]
- [x] CHK002 Is a target-size requirement (2.5.8, 24 × 24 CSS px) specified for small
      controls such as row status actions and pager links? [Gap, Spec §FR-008] *Amended*
- [x] CHK003 Is "focus not obscured" (2.4.11) required, given the shell is sticky?
      [Gap, Spec §FR-008] *Amended*
- [x] CHK004 Are page-title and heading-structure requirements defined for every page?
      [Gap, Spec §FR-008] *Amended*
- [x] CHK005 Are keyboard requirements defined for horizontally scrollable table regions, not
      only for controls? [Gap, Spec §FR-008] *Amended*
- [x] CHK006 Are text alternatives required for the bar charts (source health, per-source
      trend)? [Gap, Spec §FR-008, US5 AS-3] *Amended*
- [x] CHK007 Are empty-state requirements defined for every page and section?
      [Completeness, Spec §Edge Cases, US4 AS-4, US8 AS-2]
- [x] CHK008 Are loading and in-flight states specified for every asynchronous interaction?
      [Completeness, Spec §FR-020]
- [x] CHK009 Is the failure state for in-place actions specified (announced, control
      restored, status unchanged)? [Exception Flow, Spec §Edge Cases]
- [x] CHK010 Are success and confirmation messages specified, including whether they persist
      or time out? [Completeness, Spec §FR-018]
- [x] CHK011 Is the no-script behaviour required for every form? [Completeness, Spec §FR-003,
      US2 AS-7]
- [x] CHK012 Are requirements defined for Windows High Contrast / `forced-colors` mode, so
      that pills, focus rings and bars stay visible? [Gap] *Resolved in plan §Component rules. It is in the plan as
      a CSS obligation, not a spec FR, because it is not a WCAG AA success criterion.*
- [x] CHK013 Is the behaviour of the logo / wordmark specified before and after the master
      files arrive? [Completeness, Spec §FR-015]

## Requirement Clarity

- [x] CHK014 Is "visible focus" quantified (thickness, contrast)? [Clarity, Spec §FR-008a]
      *Amended*
- [x] CHK015 Are the contrast thresholds quantified per element class (text, large text,
      UI components, focus)? [Clarity, Spec §SC-002]
- [x] CHK016 Is "work at 375 px" defined measurably, including reflow at 320 px and 200%
      zoom? [Clarity, Spec §FR-009, SC-003] *Amended*
- [x] CHK017 Is "current tab visible" on narrow screens defined unambiguously?
      [Clarity, Spec §FR-019]
- [x] CHK018 Is "one primary action per area" defined so a reviewer can check it?
      [Clarity, Spec §SC-010]
- [x] CHK019 Is "area" in SC-010 defined (page, card, form)? [Ambiguity, Spec §SC-010]
      *Resolved in plan §Component rules.*
- [x] CHK020 Are the status-pill semantics specified (text plus icon, never colour alone)?
      [Clarity, Spec §FR-007]
- [x] CHK021 Is the relative-age format specified, and is the exact date kept available?
      [Clarity, Plan R13]

## Requirement Consistency

- [x] CHK022 Do the status-action presentation rules agree between list rows and the
      detail page? [Consistency, Spec §FR-017] *Amended: FR-017 now covers both.*
- [x] CHK023 Is the chip-count behaviour consistent with FR-011 and the data each page
      receives? [Consistency, Spec §US2 AS-8, data-model.md] *Amended: no counts; follow-up
      11.*
- [x] CHK024 Does FR-013 agree with the plan about service changes?
      [Consistency, Spec §FR-013, Plan R8] *Amended*
- [x] CHK025 Are the blacklist interactions consistent: plain POST everywhere, after FR-016?
      [Consistency, Spec §FR-016, C8]
- [x] CHK026 Do the design-source precedence rules agree between the spec, the constitution
      and ADR-0021? [Consistency, Spec §Context, C1–C9]
- [x] CHK027 Are the success-colour usage rules consistent with the measured contrast?
      [Consistency, Plan R6 C10]

## Acceptance Criteria Quality

- [x] CHK028 Is every success criterion measurable without reading the implementation?
      [Measurability, Spec §SC-001–SC-010]
- [x] CHK029 Is SC-004 (keyboard flows) tied to named flows that can be repeated?
      [Measurability, Spec §SC-004]
- [x] CHK030 Can SC-008 ("no fabricated figures") be checked against a concrete inventory?
      [Measurability, Spec §Mock-up element classification]
- [x] CHK031 Are the automated and manual checks of each criterion identified?
      [Traceability, Plan R12, quickstart.md]

## Scenario Coverage

- [x] CHK032 Are the four UX-doc flows (setup, daily triage, blocking, weekly review) each
      covered by a user story? [Coverage, US2, US3, US5, US6, US8]
- [x] CHK033 Are dark-mode scenarios specified for every page, not just the shell?
      [Coverage, Spec §FR-006, US1 AS-2]
- [x] CHK034 Are offline scenarios specified? [Coverage, Spec §US1 AS-4, FR-010]
- [x] CHK035 Are reduced-motion scenarios specified? [Coverage, Spec §FR-008, Edge Cases]
- [x] CHK036 Are screen-reader expectations specified for the bulk action's full-body swap
      (where focus goes, and what is announced, after the swap)? [Gap, Spec §US2 AS-4,
      contracts C-3] *Resolved in plan §Component rules: focus moves to the status banner after the bulk
      swap.*

## Edge Case Coverage

- [x] CHK037 Are long titles, employer names, regexes and proxy lists addressed?
      [Edge Case, Spec §Edge Cases]
- [x] CHK038 Is non-Latin text (Arabic) addressed? [Edge Case, Spec §Edge Cases]
- [x] CHK039 Are unknown status values addressed? [Edge Case, Spec §Edge Cases]
- [x] CHK040 Are "no runs yet" and "no scores yet" states addressed in the shell and the
      tables? [Edge Case, Spec §FR-013, Edge Cases]

## Non-Functional (privacy, performance)

- [x] CHK041 Is it required that secrets are never displayed, even masked?
      [Security, Spec §FR-012]
- [x] CHK042 Is the asset payload budget quantified? [Performance, Spec §SC-009]
- [x] CHK043 Is the no-third-party-request rule stated as a measurable criterion?
      [Privacy, Spec §SC-005]

## Dependencies & Assumptions

- [x] CHK044 Is the assumption "follow the system colour scheme, no in-app switch" stated?
      [Assumption, Spec §Assumptions]
- [x] CHK045 Is the dependency on brand-supplied logo masters documented, with a fallback?
      [Dependency, Spec §FR-015, C6]

## Notes

- 45 items. All 45 pass after this pass: 42 through the spec, and 3 (CHK012, CHK019,
  CHK036) through the new Component rules section of the plan.
- Spec amendments made in this pass:
  - FR-008: target size, focus not obscured, titles and headings, scroll regions, chart text.
  - New FR-008a: focus indicator metrics.
  - FR-009: reflow at 320 px, 200% zoom, text spacing.
  - FR-013: consistent with plan R8.
  - FR-017: now also covers the detail page.
  - US2 AS-8: chip counts.
  - Follow-up 11 added.
