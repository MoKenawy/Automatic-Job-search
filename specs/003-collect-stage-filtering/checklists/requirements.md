# Specification Quality Checklist: Collect-stage relevance and experience filtering

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 9 September 2026
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

**Iteration 1 (9 September 2026)** — one item outstanding.

Three `[NEEDS CLARIFICATION]` markers were carried at FR-002, FR-007 and FR-019.
Each was retained rather than defaulted because it changes scope or carries a
genuine trade-off with no dominant answer:

- **FR-002** (experience vocabulary) — free text versus a fixed list. Decides
  whether existing stored values need migrating and whether the profiles form
  changes.
- **FR-007** (exact level versus adjacent band) — trades false rejection against
  residual noise, which is the spec's governing asymmetry. No default is safe to
  assume on the operator's behalf.
- **FR-019** (scope of field promotion) — decides whether function and industry
  become filter criteria in this feature or are left to a later one.

Deliberately **not** marked, resolved as documented assumptions instead:

- Unknown/absent signal admits rather than rejects — follows from the stated
  asymmetry, no reasonable alternative.
- Rejection hides rather than deletes — established precedent in ADR-0015.
- Behaviour when no criteria are set — must be a no-op, or installation would
  be a breaking change.
- Postings from profile-less runs — no requested level exists to compare with.

**Iteration 2 (16 November 2026)** — all items pass; the three markers are
resolved in the specification text and removed:

- **FR-002 / FR-002a** — experience stays **free text**, interpreted through a
  recognised synonym set, so values already stored (`fresh`, `entry level`)
  become effective without the operator re-entering them. An unrecognised value
  disables the experience criterion for that profile and is reported; it never
  rejects. Nothing migrates and the profiles form is unchanged.
- **FR-007** — an **at-or-below band**, not an exact match: a request admits
  every level at or below the requested one and rejects those above it. Chosen
  deliberately asymmetric, because a role below the requested level is worth the
  operator's glance while one well above it is not.
- **FR-019 / FR-020** — **seniority only** is promoted to a first-class column.
  Function and industry stay in the verbatim payload and do not become filter
  criteria in this feature; FR-020 narrows to correcting the recorded coverage
  claim for all three.

Planning may proceed.
