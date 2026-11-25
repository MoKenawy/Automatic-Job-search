# Feature Specification: UI parity with the Stitch target designs (styling only)

**Feature Branch**: `007` (integration), one sub-branch per step (`007-0` … `007-9`)

**Created**: 2026-11-25

**Input**: a side-by-side comparison of the running app (light, 1536 px) with the Stitch export in
`Docs/Job Discovery UX&UI/stitch_remix_of_job_discovery_wireframe_login/…/` and its
`technical_precision/DESIGN.md`.

## Why

Spec 006 moved the styling to Tailwind without changing a pixel. The app now uses the target's
tokens, Inter and the top-nav pattern, but it still looks like the 004 wireframe. Compared with the
targets, it lacks the layout width, a footer, the page-header typography, card depth, icons and the
richer per-page components. This feature closes those gaps visually.

## Decisions (maintainer, 2026-11-25)

- **D1, page headers.** Keep today's titles and subtitles; no eyebrows and no renamed pages.
  Adopt only the target's fonts and colours.
- **D2, logo.** Keep the text wordmark until a real logo exists. No avatar and no decorative
  header icons.
- **D3, real data only.** A target element ships only when the app has a real value for it.
  Mock values in the export (latency, "Encrypted", PID or node id, tok/s, CAPTCHA, schema rev,
  "daemon synced") are dropped.
- **D4, styling only.** No new endpoints, database columns or services. A route may add context
  only from existing query functions (`queries.totals`, `source_health`, `recent_runs`,
  `list_postings`, `known_sites`, `settings_service.get`, `profile_store.list_enabled`).
- **D5, sequencing.** Starts after 006 closed (PR #50).

## Out of scope (need backend work)

CSV export; blacklist add-by-name and its reason and date-added fields; settings reset to defaults;
runs JSON export; CV upload; report time ranges; a "Filtered out" tab count; self-hosting a
monospace font (the `<code>` snapshots depend on the system font, recorded in 006).

## Gap list (from the comparison)

| Area | Target | Today |
|---|---|---|
| Width | content about 1440 px | 1280 px column |
| Footer | version and status line | none |
| Page title | headline-xl, tight tracking | headline-xl-mobile |
| Last-run pill | neutral pill with a status dot, full date | tinted pill, short date |
| Cards | hairline border, level-1 shadow, hover level 2 | flat |
| Icons | icon tiles beside headings and rows | very few |
| Overview | KPI footnotes, stacked triage bar, labelled source bars, recent postings | numbers only |
| Postings | tab counts, one-row filter bar, title + company column, board tags, icon triage, numbered pager | stacked filters, text triage buttons |
| Reports | icon cards with stat badges and "View report", summary panel | link list |
| Blacklist | stat cards with icons, initial tiles, restore link, callout | plain table |
| Schedules | toggles, coloured actions, time chips, two-column add form with action bar | pills and outline buttons |
| Settings | section icons, hints and units on fields, callout checkbox, action bar | plain form |
| Runs | value labels on trend bars, highlighted latest run, right-aligned numbers | bars only, Run # wraps |

## Functional requirements

- **FR-001**: Every page keeps its current title, subtitle and nav label (D1).
- **FR-002**: The content column, header and footer share one maximum width of 90rem.
- **FR-003**: A footer shows the app version and the configured timezone, and nothing else (D3).
- **FR-004**: Page headers come from one `page_header` macro with an optional actions slot.
- **FR-005**: New components are Jinja macros returning complete literal utility strings
  (006 FR-017/018); no component CSS classes, no concatenated class names.
- **FR-006**: New colours are tokens with light and dark values that meet the 004 contrast
  thresholds; no colour literals in templates.
- **FR-007**: The htmx contracts C-1 to C-3 keep their ids, targets, swaps and form fields. Every
  form posts the same fields as today.
- **FR-008**: Accessibility holds: one h1 per page, labelled controls, icon-only buttons named,
  status never shown by colour alone, dark mode, forced colours and reduced motion.
- **FR-009**: Each step re-baselines only the snapshots it changes, with the reason recorded in
  `verification.md`.

## Success criteria

- **SC-001**: `pytest`, ruff and the CSS drift check pass at every step; `--visual` is 44 of 44
  after each step's recorded re-baseline.
- **SC-002**: The first load stays at or under 150 KB.
- **SC-003**: Every gap row above is either closed or listed as out of scope.
