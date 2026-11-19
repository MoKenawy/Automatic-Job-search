# Implementation Plan: UI renovation of the triage interface

**Branch**: `004-ui-renovation` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-ui-renovation/spec.md`

## Summary

Restyle every page of the triage interface to the DESIGN.md token system, and bring the
layouts in line with the Stitch screens, without changing behaviour. The technical approach:

- **CSS.** Hand-written custom properties in a static stylesheet, with a light palette and a
  derived dark one (ADR-0021).
- **Self-hosted assets.**
  - Inter, a variable Latin subset.
  - A sprite of about 20 Material Symbols SVGs.
  - htmx 2.0.3, vendored.

  All of them are served from a new `/static` mount.
- **Two small code additions outside the templates.**
  - A shell context that gives every page the latest run (FR-013).
  - A relative-age filter (R13).
- **htmx.** Every existing htmx contract is kept. The one deliberate change is that the
  Blacklist page's Remove becomes a plain POST (FR-016).
- **Delivery.** Tokens and the shell first, then one shippable phase per page.

## Technical Context

**Language/Version**: Python 3.12 (`requires-python >=3.12,<3.13`)

**Primary Dependencies**:
- Already installed: FastAPI 0.139.2, Starlette 1.3.1, Jinja2 3.1.6.
- Vendored by this feature (research R2–R4):
  - htmx 2.0.3
  - `@fontsource-variable/inter` 5.3.0
  - `@material-symbols/svg-400` 0.48.3
- **No new `uv` dependencies.**

**Storage**: PostgreSQL 16. **No schema change** ([data-model.md](data-model.md)).

**Testing**: pytest with the in-memory SQLite and `get_db`-override fixtures in
`tests/test_web*.py`, plus `ruff check`. New pure-pytest checks for tokens, assets and
markup accessibility (R12). Manual viewport and keyboard passes are recorded in
`verification.md`.

**Target Platform**: A local Linux container or workstation, opened in a current evergreen
desktop browser. Phone and tablet widths are supported.

**Project Type**: A server-rendered web application inside a single Python project
(`app/src/app/web/`).

**Performance Goals**:
- ≤150 KB of styling, fonts, icons and scripts on the first load, and 0 KB afterwards
  (SC-009).
- One extra indexed query per page, for the shell's latest run.

**Constraints**:
- No third-party requests (constitution II).
- No build step and no JavaScript framework (constitution III).
- WCAG 2.2 AA (constitution VI).
- Routes, fields and htmx contracts stay frozen (constitution VII).

**Scale/Scope**:
- **Templates:** 15 templates (about 1,200 lines) and 9 pages.
- **Routes:** 13 routes with their contexts unchanged, plus the shell dependency.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies how | Verdict |
|---|---|---|
| **I. Preserve, never conceal** | No posting, status or count may become harder to reach. Every row transition is kept (FR-004). Every count still links where it does today. The "filtered out" chip and the banners stay. | **Pass** |
| **II. Local-first** | All assets are vendored, and the htmx CDN tag is removed. `test_web_assets.py` asserts that no external URLs appear. | **Pass.** This fixes the existing `unpkg.com` violation. |
| **III. One language, no build, server-rendered** | Hand-written CSS with no compiler. Jinja2 and htmx only. Three small inline scripts: today's bulk-select script, plus the htmx error announcer and the tab scroll-into-view (R9, R10). Every form still works without htmx. | **Pass** |
| **IV. Dependency direction** | The shell's latest-run query lives in `services/queries.py` (`latest_run`), so `web/` adds no query logic (R8). | **Pass**, with one new read-only service function; see Complexity Tracking. |
| **V. Decisions recorded** | ADR-0021 records the styling approach. Comments cite DESIGN.md, ADR-0021 and research sections. | **Pass**. ADR-0021 was accepted on 2026-11-19. |
| **VI. Accessible, token-driven** | Tokens are defined once, there are no literal colours, light and dark palettes exist, and the contrast test runs. The a11y markup test covers labels, `th[scope]`, `aria-current`, the live region, the skip link and icon labelling. | **Pass.** Two new conflicts (C10, C11) are resolved in R6. |
| **VII. UI contracts stable** | [contracts/htmx-fragments.md](contracts/htmx-fragments.md) freezes ids, targets, swaps, fields and the text tests assert. The single change, C-6, is mandated by the spec (FR-016, Q3). | **Pass** |

*Post-Phase 1 re-check*: unchanged. The design adds:
- one static mount;
- one read-only query function;
- one app-level dependency and one context processor;
- one Jinja filter module;
- three test modules.

None of these introduces an import in a prohibited direction or alters an existing route,
field or fragment beyond C-6.

## Project Structure

### Documentation (this feature)

```text
specs/004-ui-renovation/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R15, including the approved dependency declaration
├── data-model.md        # no schema change; view inputs; shell context
├── quickstart.md        # run and verify
├── contracts/
│   └── htmx-fragments.md
├── checklists/
│   └── requirements.md  # (+ ux-a11y.md from /speckit-checklist)
├── tasks.md             # /speckit-tasks
└── verification.md      # written at the end: per-page viewport, dark mode, keyboard, htmx results
```

### Source Code (repository root)

```text
app/src/app/
├── services/queries.py          # + latest_run(session)  (R8)
└── web/
    ├── app.py                   # + StaticFiles mount; shell dependency on routers  (R5, R8)
    ├── deps.py                  # + shell_context dependency, context processor, asset_version, filters
    ├── formatting.py            # NEW: relative_age filter  (R13)
    ├── static/                  # NEW
    │   ├── css/app.css          # tokens (light + dark) + components  (R1, R6, R7)
    │   ├── fonts/inter-latin-wght-normal.woff2, inter-latin-ext-wght-normal.woff2
    │   ├── icons.svg            # Material Symbols sprite  (R3)
    │   ├── vendor/htmx-2.0.3.min.js
    │   ├── brand/               # empty until the logo masters arrive  (R14)
    │   └── VENDORED.md          # source URL, version, licence, SHA-256 per file
    └── templates/
        ├── base.html            # shell: skip link, wordmark, tabs, last-run pill, live region
        ├── _macros.html         # NEW: icon(), pill(), metric_card(), empty_state(), banner()
        ├── index.html, postings.html, _row_status.html, detail.html, _status_control.html,
        ├── blacklist.html, profiles.html, settings.html, runs.html,
        └── reports/{index,employers,sources,profiles,_caveat}.html

app/tests/
├── test_design_tokens.py        # NEW  (R12)
├── test_web_assets.py           # NEW  (R12)
├── test_web_a11y_markup.py      # NEW  (R12)
└── test_web_formatting.py       # NEW  (R13)

Docs/ADRs/0021-ui-styling-hand-written-tokens.md   # NEW (accepted)
Docs/README.md                                      # ADR index row
```

**Structure Decision**: this is the existing single-project layout. All UI work stays under
`app/src/app/web/`. The only change outside it is one read-only function in
`services/queries.py`.

## Component rules (resolve checklist CHK012, CHK019, CHK036)

- **Primary action per area (SC-010).** An *area* is one `<form>`, or one card or panel that
  holds actions. Each area has at most one `.btn-primary`. Every other action is `.btn`
  (outlined) or a text link.
- **Forced colours.** Under `@media (forced-colors: active)`:
  - pills, chips, the active tab and bar segments get a real `border` or `outline`, so they
    don't depend on a background colour;
  - focus rings use `outline` (not `box-shadow`) with `Highlight`;
  - icons stay `currentColor`.
- **Focus after the bulk swap.** The bulk response replaces `<body>`. On `htmx:afterSwap`
  with target `body`, the shell's inline listener moves focus to the status banner
  (`tabindex="-1"`) when one is present, and otherwise to `<main>`. Nothing new is needed
  for the announcement, because the banner sits in the live region.
- **Focus indicator (FR-008a).** `outline: 2px solid var(--focus-ring); outline-offset: 2px`.
  `--focus-ring` is `primary` in light mode and `primary` (#b4c5ff) in dark mode. The
  contrast test checks it at ≥3:1 against `surface` and `surface-container-lowest`.
  `scroll-padding-top` equals the height of the sticky shell, so focused elements are never
  hidden behind it (2.4.11).
- **Targets (2.5.8).** Buttons, chips, pager links and tab links are at least 24 px tall,
  with at least 4 px between neighbours. Primary and outlined buttons are 36 px tall
  (DESIGN.md).

## Delivery phases (input to `/speckit-tasks`)

Every phase ends with `uv run pytest` and `uv run ruff check` green, plus the manual checks
for that page. Each phase can ship on its own: pages that haven't been renovated yet still
render correctly inside the new shell, because the existing class names (`.panel`, `.card`,
`.pill`, `.btn`, `.filters`, …) are kept as aliases in `app.css` until their page is done.

| Phase | Content | Review checkpoint |
|---|---|---|
| **0. Assets & plumbing** | Vendor the assets with checksums (`VENDORED.md`); add the `/static` mount; add `asset_version`; add the token and asset tests (red first, then green). | — |
| **1. Tokens & shell** (US1) | <ul><li>`app.css` tokens, light and dark</li><li>Base components</li><li>`_macros.html`</li><li>`base.html` shell: skip link, wordmark, tabs with `aria-current` and scroll-into-view, last-run pill (R8), live region, htmx error announcer (R9)</li><li>Legacy class aliases</li><li>a11y markup test</li></ul> | **Checkpoint: tokens and base layout** |
| **2. Postings** (US2) | <ul><li>Chips</li><li>Filter bar</li><li>Bulk bar with busy state</li><li>Table: score badge, title and employer, relative age</li><li>`_row_status.html` actions with icon and label (FR-017), using `hx-disabled-elt`</li><li>Numbered pager that keeps "Page N of M"</li></ul> | **Checkpoint: first full page** |
| 3. Posting detail (US3) | Header and status control, then banners, then a two-column body (description; assessment, sources, record). `_status_control.html`. | — |
| 4. Overview (US4) | Metric cards (interactive only where a destination exists), scoring callout, triage distribution, source-health bars. | — |
| 5. Runs (US5) | Per-source trend, with values exposed as text, a yield delta, and a history funnel with status pills. | — |
| 6. Schedules (US6) | Profile list, switch-styled enable button (C-7), run and delete, filter-rules disclosure, grouped add form. | — |
| 7. Settings (US7) | Two-column groups, inline hints, read-only block. `database_url` is never shown. | — |
| 8. Blacklist (US8) | Header figures derived from rows, table, plain-POST Remove (FR-016, plus a new test), FR-013 callout, empty state. | — |
| 9. Reports (US9) | Index cards, then the three report pages, with caveats kept. | — |
| 10. Clean-up & verification | Remove the legacy class aliases and the inline `style=` attributes. Write `verification.md` (viewports × schemes × pages, keyboard flows, htmx with and without the script, network log, reduced motion). | Final report |

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| New read-only `queries.latest_run()` plus an app-level dependency (R8) | FR-013, as confirmed by Q1: the last-run status appears on every page | Reusing `queries.totals()` costs five aggregate queries per page. A query in `web/` breaks constitution IV. A context processor opening its own session bypasses the test overrides. |
| One shell inline script beyond today's one (R9, R10) | Failed, busy and successful in-place actions must be announced (FR-020, FR-008), which htmx's defaults keep silent. FR-019 requires the active tab to be scrolled into view. | htmx has no declarative announcement, and CSS can't set an initial scroll position. The script is about 25 lines, delegated from `document`, and progressive. |
| Behaviour change C-6 (Remove becomes a plain POST) | Fixes the defect found in R11, as decided in Q3 | Keeping `hx-post` would need an `hx-target="body"` swap, which would make it the only htmx blacklist action (spec C8). |
