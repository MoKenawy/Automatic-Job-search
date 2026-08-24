# Specification Quality Checklist: Employer-level suppression, derived at read time

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 13 August 2026
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

## Validation notes

Two items needed a second pass before they read as clean:

**"No implementation details" — initially failed.** The first draft named the
shared filter definition as a module and described it as a query predicate,
which is a `/speckit-plan` decision, not a spec one. Reworded to state the
*obligation* (FR-010: every read path applies the rule or records an exemption)
and to carry the structural commitment as an Assumption rather than a
requirement. The distinction matters here: ADR-0015 identifies the shared seam
as the place this decision can go wrong, so the spec must say a single shared
definition is required without dictating its shape.

**"Success criteria are measurable" — SC-005 and SC-006 reworked.** Both began
as process statements ("read paths are reviewed"), which cannot fail a test.
SC-005 now counts paths and requires zero unexamined; SC-006 requires one
per-view invisibility test, which is what makes a silently dropped filter fail
the suite instead of passing. This mirrors the project's governing testing
asymmetry — the concealment risk runs toward *resurfacing* a blacklisted
employer, so the negative assertions carry the weight, one per view rather than
one in total.

**No [NEEDS CLARIFICATION] markers were raised.** One candidate was considered
and resolved from source: whether surfacing the old/new blacklist asymmetry on
the blacklist view is in scope. The implementation plan §6 calls it "worth
surfacing" but schedules no work for it. Resolved in favour of including it at
its minimum useful form (FR-013, recorded in Assumptions), because an
unexplained asymmetry between two blacklists that look identical is exactly the
kind of surprise the ADR was written to stop going unrecorded.

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
- All items pass. Spec is ready for `/speckit-plan`.