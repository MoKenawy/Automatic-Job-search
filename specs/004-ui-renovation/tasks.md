---
description: "Task list for 004 UI renovation"
---

# Tasks: UI renovation of the triage interface

**Input**: design documents in `specs/004-ui-renovation/`: `plan.md`, `spec.md`,
`research.md`, `data-model.md`, `contracts/htmx-fragments.md`, `quickstart.md`, and
`checklists/ux-a11y.md`.

**Tests**: these are included, because the spec and plan require automated checks: SC-002,
SC-005, SC-007, SC-009, FR-008 and FR-016 (plan R12). Each test task is written before the
work it guards, and must fail first where that is meaningful.

**Paths**:
- `W/` = `app/src/app/web/`
- `T/` = `app/tests/`
- Commands run from `app/`.

**Gates at the end of every phase**: `uv run pytest` and `uv run ruff check` are green. No
route, method, status code, form field or query parameter changes
(`contracts/htmx-fragments.md`). The only exception is C-6, in US8.

**Commits**: Conventional Commits with scope `web` or `ui`, one concern per commit. The
commit points are marked ⏺.

**Legacy aliases**: until a page's own phase is done, that page keeps rendering through the
old class names (`.panel`, `.card`, `.pill`, `.btn`, `.btn-xs`, `.filters`, `.formgrid`,
`.bars`, `.flash`, `.empty`, `.sub`, `.muted`, `.num`, `.split`, `dl.meta`, `.scroll-x`,
`.pager`, `.bulkbar`, `.statusbox`, `.desc`). Phase 1 restyles them with the new tokens, so
every page phase can ship on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task).
- `W/static/css/app.css` is shared, so tasks that edit it are **never** marked [P] against
  each other.

---

## Phase 1: Setup — vendored assets and static serving

**Purpose**: put the approved dependencies on disk, serve them, and add the guards (research
R2–R5, R12).

- [x] T001 [P] Vendor htmx 2.0.3 to `W/static/vendor/htmx-2.0.3.min.js`, then verify that its
      SHA-384 equals
      `0895/pl2MU10Hqc6jd4RvrthNlDiE9U1tWmX7WRESftEDRosgxNsQG/Ze9YMRzHq` (research R4).
- [x] T002 [P] Vendor `inter-latin-wght-normal.woff2` and `inter-latin-ext-wght-normal.woff2`
      from `@fontsource-variable/inter@5.3.0` to `W/static/fonts/` (research R2).
- [x] T003 [P] Build `W/static/icons.svg` as a `<symbol>` sprite from
      `@material-symbols/svg-400@0.48.3/outlined/`. Include these glyphs: `fiber_new`,
      `check_circle`, `send`, `cancel`, `block`, `undo`, `play_arrow`, `delete`, `search`,
      `expand_more`, `arrow_forward`, `open_in_new`, `settings`, `info`, `warning`, `error`,
      `schedule`, `lock`, `check`, `progress_activity`. Each symbol keeps its `viewBox`, has
      its `fill` removed, and gets an `id` equal to the glyph name. Stop and amend if any
      glyph is missing from 0.48.3 (research R3). *Amended:* `expand_more` is missing, so
      its symbol is built from `keyboard_arrow_down` under the id `expand_more`.
- [x] T004 Write `W/static/VENDORED.md`. List each vendored file with its source URL,
      version, licence and SHA-256. Include the OFL-1.1 notice for Inter and the Apache-2.0
      notice for Material Symbols. Depends on T001–T003.
- [x] T005 [P] Create `W/static/brand/.gitkeep`, a placeholder for the logo masters
      (research R14, FR-015).
- [x] T006 Mount `/static` in `W/app.py` with
      `app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")`.
      Add a comment citing ADR-0021 (research R5).
- [x] T007 In `W/deps.py`, compute `ASSET_VERSION` once at import, as a short hash of the
      `static/` files' sizes and modification times. Register it as the Jinja global
      `asset_version` (research R5).
- [x] T008 [P] Write `T/test_web_assets.py`, with these tests:
      - `/static/vendor/htmx-2.0.3.min.js` returns 200, and its bytes match the pinned
        SHA-384;
      - `/static/icons.svg` and both fonts return 200;
      - no template under `W/templates/` contains `#[0-9a-fA-F]{3,8}\b` colour literals or
        `rgb(` (SC-007);
      - no page response contains `src=` or `href=` pointing to `http(s)://` for a script,
        stylesheet or font (SC-005);
      - the first-load assets (CSS, latin font, sprite, htmx) total ≤150 KB (SC-009).

      The tests use the `client` fixture pattern from `T/test_web.py`.
- [x] T009a Before any template edit (contract C-8, analysis H3): grep every string asserted
      in `T/test_web*.py`, `T/test_blacklist.py`, `T/test_profiles.py` and
      `T/test_settings.py`, and compare with the list in `contracts/htmx-fragments.md` C-8.
      Amend C-8 if a string is missing. T064 repeats this check at the end.
- [x] T009 ⏺ Run `uv run pytest`. The external-URL test and the colour-literal test fail
      as expected, because of the `unpkg` tag and the inline CSS. Mark those two as
      `xfail(strict=True)`, with the reason "fixed in Phase 3 (T024/T028)". Commit:
      `feat(web): vendor htmx, Inter and icon sprite, serve /static (ADR-0021)`.

---

## Phase 2: Foundational — tokens, components, shell plumbing

**Purpose**: the blocking prerequisites for every page. This is the **tokens and base-layout
checkpoint** together with Phase 3 (US1).

### Tests first

- [x] T010 [P] Write `T/test_design_tokens.py`. It parses the light and dark custom-property
      blocks of `W/static/css/app.css` and asserts WCAG ratios for a `PAIRS` table:
      - text on every surface ≥4.5;
      - `outline` against control backgrounds ≥3.0;
      - `focus-ring` against `surface` and `surface-container-lowest` ≥3.0;
      - `on-primary-container` on `primary-container`, `on-success-container` on
        `success-container`, and `on-error-container` on `error-container`, each ≥4.5.

      Both palettes are checked (SC-002, FR-008a, research R6/R7).
- [x] T011 [P] Write `T/test_web_formatting.py`, unit tests for `relative_age`:
      "today", "1d ago", "6d ago", "3w ago", the absolute date beyond 60 days, and `None`
      giving "—" (research R13).
- [ ] ~~T012~~ Moved to Phase 3 as T024a: it needs the `base.html` shell from T024, so it
      cannot be green at the T022 gate (analysis H1).

### Implementation

- [x] T013 Create `W/static/css/app.css`, section 1, the **tokens**.
      - **Light palette.** Every DESIGN.md YAML colour role as a custom property, plus
        `--success`, `--success-container` and `--on-success-container` (R6 C10).
      - **Focus ring.** `--focus-ring`.
      - **Dark palette.** The R7 table, under
        `@media (prefers-color-scheme: dark)`.
      - **Type scale.** `--fs-*`, `--lh-*`, `--ls-*` from DESIGN.md. The font stack ends in
        system fallbacks that cover Arabic (spec edge case "Non-Latin text").
      - **Spacing and radii.** `--space-*` and `--radius-*`.
      - **Elevation.** `--shadow-1…3`, from the DESIGN.md prose.
      - **Font face.** `@font-face` for Inter (both subsets, with `unicode-range` and
        `font-display: swap`).

      Comments cite DESIGN.md, ADR-0021 and R6/R7. Run T010; it goes green.
- [x] T014 `W/static/css/app.css`, section 2, **base and layout**.
      - Reset; `body` font and colours.
      - Headings: one `h1` scale and the section `h2`.
      - Links.
      - Focus: `:focus-visible` with a 2 px outline and 2 px offset (FR-008a);
        `scroll-padding-top` for the sticky shell (2.4.11).
      - `.skip-link`.
      - `.visually-hidden`.
      - The `main` container (max-width 1280 px, gutters per DESIGN.md breakpoints).
      - `@media (prefers-reduced-motion: reduce)`, which turns off all transitions and
        animation.
      - `@media (forced-colors: active)` rules (plan §Component rules).
- [x] T015 `W/static/css/app.css`, section 3, **components**:
      - buttons: `.btn` outlined, `.btn-primary`, `.btn-ghost`, sizes ≥24 px and 36 px;
      - `.chip`, with an active state;
      - `.pill`, with status variants `new`, `shortlist`, `applied`, `rejected`, `running`,
        `success`, `failed`, plus the neutral default;
      - `.card` and `.panel`;
      - `.metric`;
      - `.banner`, with `info`, `success` and `error` variants;
      - `.empty-state`;
      - `.table-wrap`, which scrolls with `tabindex="0"`;
      - the table styles;
      - form controls: inputs, selects and textareas with a 36 px height and `outline`
        borders (R6 C11); checkboxes;
      - `.switch`;
      - `.bars`, with a text equivalent slot;
      - `.icon`;
      - the busy state for `.htmx-request`, including the spinner;
      - `.card-link`, a stretched `::after` overlay for whole-card links (T055).

      Elevation and radii follow DESIGN.md.
- [x] T016 `W/static/css/app.css`, section 4, **legacy aliases**. Map today's class names
      (see the header of this file) onto the new tokens and components, so that pages that
      haven't been renovated still render correctly. Each alias gets the comment
      "removed in Phase 12".
- [x] T017 [P] Create `W/formatting.py` with `relative_age(value, now) -> Markup`. It
      renders `<time datetime="…" title="DD Mon YYYY">…</time>`. Run T011; it goes green.
- [x] T018 [P] Add `latest_run(session) -> Run | None` to `app/src/app/services/queries.py`.
      It is read-only, ordered by `started_at desc`, and its docstring cites FR-013 and plan
      R8. Leave `totals()` untouched.
- [x] T019 In `W/deps.py`:
      - add `shell_context(request, db=Depends(get_db))`, which sets
        `request.state.shell = {"last_run": queries.latest_run(db), "now": datetime.now(tz)}`;
      - pass `context_processors=[_shell_processor]` to `Jinja2Templates`, where
        `_shell_processor` returns `{"shell": getattr(request.state, "shell", EMPTY_SHELL)}`;
      - register the filter `TEMPLATES.env.filters["relative_age"] = relative_age`.

      Depends on T017 and T018.
- [x] T020 In `W/app.py`, attach `dependencies=[Depends(shell_context)]` to each
      `include_router` call and to the `/` route. `/healthz` and `/static` are excluded
      (R8). Depends on T019.
- [x] T021 [P] Create `W/templates/_macros.html` with these macros:
      - `icon(name, label=None, cls="")`: `aria-hidden` when there is no label, otherwise a
        visually hidden label;
      - `status_pill(status)`: text plus icon, never colour alone (FR-007);
      - `banner(kind, message, focusable=False)`: carries `role="status"` (`role="alert"`
        for `error`) so server-rendered messages are announced (FR-018, analysis H2);
      - `empty_state(message, action_href=None, action_label=None)`;
      - `metric(label, value, href=None)`: the number is the element's sole text content
        (contracts C-8);
      - `table_wrap(label)`: a call-block with `tabindex="0"`, `role="region"` and
        `aria-label`.
- [x] T022 ⏺ Run the gates. Commit:
      `feat(ui): design tokens, components and dark palette from DESIGN.md`
      (T013–T016, T010). Commit:
      `feat(web): shell context with latest run and relative-age filter`
      (T011, T017–T021).

**Checkpoint**: the foundation is ready. Pages still render through the legacy aliases.

---

## Phase 3: User Story 1 — Consistent, legible shell (Priority: P1) 🎯 MVP

**Goal**: every page shares the new frame: a wordmark, tabs with `aria-current`, the
last-run pill, a skip link, the live region, light and dark mode, the narrow-screen tab
strip, and no external requests.

**Independent Test**: open all seven tabs at 375, 768 and 1280 px, in light and dark mode.
Check that the active tab is marked, there is no horizontal page scroll, the network log
shows the application's origin only, and the keyboard reaches the skip link first.

- [x] T023 [P] [US1] Write `T/test_web_a11y_markup.py`. For each GET page (`/`, `/postings`,
      a posting detail, `/reports`, the three reports, `/blacklist`, `/profiles`,
      `/settings`, `/runs`), and using only `html.parser`, assert:
      - exactly one `aria-current="page"`;
      - a skip link pointing at `#main`;
      - one `aria-live` region;
      - exactly one `<h1>`;
      - a non-empty, page-specific `<title>`;
      - every `<input>` (except hidden and submit), `<select>` and `<textarea>` has a
        `<label for>` or an `aria-label`;
      - every `<th>` in a `<thead>` has `scope`;
      - every `<svg>` is `aria-hidden="true"` or has an accessible name;
      - every `.table-wrap` has `tabindex="0"` and an `aria-label`.

      Pages not yet renovated are listed in `PENDING = {...}` and xfail **non-strict**, so
      checks that `base.html` already satisfies don't XPASS-fail. Each page phase removes
      its own entry.
- [x] T024 [US1] Rewrite `W/templates/base.html`:
      - `<link rel="stylesheet" href="/static/css/app.css?v={{ asset_version }}">`;
      - font preload of the latin woff2;
      - `<script src="/static/vendor/htmx-2.0.3.min.js" integrity="sha384-…" crossorigin="anonymous">`,
        replacing `unpkg`;
      - a `{% block title %}` default of "<Page> — Job discovery", set by every page;
      - a skip link;
      - a sticky `<header>` with the text wordmark (FR-015: "Job" in `on-surface`,
        "discovery" in `primary`; it links to `/`);
      - `<nav aria-label="Primary">` with a `<ul>` of the seven tabs, `aria-current="page"`
        on the active one, and a blue underline;
      - the last-run pill linking to `/runs`: `shell.last_run` time and status, with an icon,
        or "No runs yet" (FR-013);
      - `<main id="main" tabindex="-1">`;
      - a `<div id="announcer" class="visually-hidden" aria-live="polite">`.

      Delete the inline `<style>`.
- [x] T024a [US1] (moved from T012) Write a test in `T/test_web.py` that renders `/` with a
      seeded `Run` and with no runs. It checks for the shell's last-run text ("No runs yet" /
      the run's status) and a link to `/runs` (FR-013). Green once T019, T020 and T024 are in.
- [x] T025 [US1] In `base.html`, add one inline script (an IIFE, about 25 lines, delegated
      from `document`, so it survives the bulk body swap, contract C-3). It does five
      things (analysis H2: FR-020/FR-008 announcements):
      - **(a)** On load, it scrolls the `aria-current` tab into view
        (`inline: "nearest"`) (FR-019, R10).
      - **(b)** On `htmx:responseError` and `htmx:sendError`, it writes "Couldn't update —
        nothing changed. Try again." into `#announcer` (R9).
      - **(c)** On `htmx:afterSwap` with target `body`, it focuses `.banner[tabindex]`
        if one exists, and otherwise `#main` (plan §Component rules).
      - **(d)** On `htmx:beforeRequest`, it sets `aria-busy="true"` on the triggering element
        and writes "Updating…" into `#announcer` (FR-020).
      - **(e)** On `htmx:afterSwap` for a target whose id starts with `status-`, it writes
        "Status updated to <status>" into `#announcer` (US2 AS-1). A live region on the
        swapped row itself would be destroyed by the `outerHTML` swap.

      A comment cites R9, R10 and the constitution III allowance.
- [x] T026 [US1] In `app.css`, add the shell styles:
      - the sticky header;
      - the tab strip: below 768 px it is single-line with `overflow-x: auto`, scroll-snap
        and edge fades; at 768 px and above it is inline (FR-019);
      - the last-run pill variants;
      - the page header (`h1` plus `.page-sub` description);
      - the `.banner` placement at the top of `<main>` (FR-018).
- [x] T027 [US1] Add `{% block title %}` to every page template:
      - `index.html`, `postings.html`, `detail.html` (keep it);
      - `blacklist.html`, `profiles.html`, `settings.html`, `runs.html`;
      - `reports/index.html`, `reports/employers.html`, `reports/sources.html`,
        `reports/profiles.html`.
- [x] T028 [US1] Remove the `xfail` marks from T009 (external URL and colour literals in
      `base.html`). Any colour literal left in a page template moves into
      `T/test_web_assets.py::PENDING_LITERALS`, which each page phase empties.
- [x] T029 [US1] ⏺ Gates, then the manual shell check: quickstart steps 1, 2 and 5 on any
      two pages. Commit:
      `feat(ui): new shell — tabs, last-run status, skip link, live region (FR-013, FR-019)`.

**🛑 Review checkpoint: tokens and base layout (Phases 1–3).** Stop for operator review.

---

## Phase 4: User Story 2 — Triage postings quickly (Priority: P1)

**Goal**: the Postings list matches the Stitch screen within the frozen contracts. That
covers the chips, the filter bar, the bulk bar with its busy state, the table, row actions
with an icon and label, and the numbered pager.

**Independent Test**: quickstart steps 1–4 on `/postings`. Use each chip, search, both
facets, a row change by mouse and by keyboard, a bulk change on page 2, a forced error, and
the no-htmx run.

- [x] T030 [P] [US2] Extend `T/test_web_triage.py` with two tests.
      - Each row status form has `hx-disabled-elt`, and still has
        `name="variant" value="row"` in that exact order.
      - The bulk form keeps `id="bulkform"`, `hx-target="body"` and `hx-swap="innerHTML"`
        (contracts C-1 and C-3).
- [x] T031 [US2] Rewrite `W/templates/_row_status.html`. Keep:
      - the root `id="status-{{ p.id }}"`;
      - the forms, actions, `hx-post`, `hx-target`, `hx-swap` and the hidden fields.

      Add `hx-disabled-elt="find button"`. Use `status_pill(p.status)`. Each button shows
      an icon plus a visible label (FR-017), using `fiber_new` for new, `check_circle` for
      shortlist, `send` for applied and `cancel` for rejected. Each target is ≥24 px. If
      `find button` isn't supported in 2.0.3, fall back to `this` on each button, and
      record the fallback in research R9.
- [x] T032 [US2] Rewrite `W/templates/postings.html`, keeping every contract in C-3, C-4,
      C-5 and C-8. Build these parts:
      - **Page header.** The title and the "Showing … ranked by score" line, unchanged.
      - **Status chips.** `.chip` links with no counts (US2 AS-8), with `aria-current` on
        the active chip.
      - **Filter bar.** The search input with a visible label (it may be visually hidden,
        but it must exist), the location and source selects with labels, and an outlined
        Search button.
      - **Verdict note and flash.** The flash becomes `banner('success', flash,
        focusable=True)` (FR-018).
      - **Bulk bar.** `#selcount`, the status select, and the `#bulkapply` primary button
        with `hx-disabled-elt="#bulkapply"`.
      - **Table.** `table_wrap("Postings")`, with `th[scope=col]`.
        - Score badge.
        - Title link, with the employer underneath.
        - Location with an icon.
        - Source pills.
        - `relative_age`.
        - The conditional Rejected and Turned-away columns.
        - The status cell (`_row_status.html`).
      - **Empty state.** Via the macro.
      - **Pager.** Numbered links that keep the text "Page N of M", `rel` attributes and
        `aria-label`s.

      Keep the inline select-all script and its ids (`selall`, `selcount`, `bulkapply`,
      `.selrow`).
- [x] T033 [US2] In `app.css`, add the Postings components: `.filter-bar`, `.bulk-bar`,
      `.score-badge`, `.row-actions`, and the pager.

      Below 768 px, the filter bar stacks and the table scrolls inside `.table-wrap`
      (FR-009).
- [x] T034 [US2] Remove `/postings` from the `PENDING` list in `T/test_web_a11y_markup.py`,
      and from the pending colour literals.
- [x] T035 [US2] ⏺ Gates, then the manual quickstart steps 1–5 on `/postings`. Commit:
      `feat(ui): renovate the postings triage list (US2)`.

**🛑 Review checkpoint: first full page.** Stop for operator review.

---

## Phase 5: User Story 3 — Read and act on one posting (Priority: P2)

**Goal**: the detail page is derived from the postings design. It has a header and status
control, then the banners, then a two-column body.

**Independent Test**: on a detail page, change the status, blacklist (after confirming),
then un-blacklist. The redirects should match today's, and the layout should hold at 375 px.

- [x] T036 [US3] Rewrite `W/templates/_status_control.html`, the same way as T031 but with
      `variant=detail` (contract C-2, FR-017).
- [x] T037 [US3] Rewrite `W/templates/detail.html`. Build:
      - a back link;
      - the `h1` title, with the employer, location and remote status beneath it;
      - the status control;
      - the employer blacklist area: an outlined button with the `block` icon, keeping
        `onsubmit` confirmation and `return_to` (C-7); and a `banner('error')` when the
        employer is blacklisted, with an `undo` button whose text stays "Remove from
        blacklist" (C-8, `test_blacklist.py:278`);
      - the filter-verdict banner, with its copy unchanged;
      - a two-column body that becomes one column below 768 px:
        - the description card;
        - the assessment card, keeping the "Not scored yet" and "Strong overlap" copy
          (C-8);
        - the sources card, with `open_in_new` links;
        - the record card.

      Remove the inline `style=` attributes.
- [x] T038 [US3] In `app.css`, add `.detail-grid`, `.desc` (wrapping, readable line length)
      and `dl.meta` in the new tokens.
- [x] T039 [US3] ⏺ Clear the detail page from PENDING, run the gates and do the manual checks.
      Commit: `feat(ui): renovate the posting detail page (US3)`.

---

## Phase 6: User Story 4 — See where the pipeline stands (Priority: P2)

**Goal**: Overview shows the metric cards, the scoring callout, the triage distribution and
source health.

**Independent Test**: compare every number with today's and follow every link. Seed one
source at zero, and check it can be told apart without relying on colour.

- [x] T040 [US4] Rewrite `W/templates/index.html`. Build:
      - **Four metric cards, using `metric()`.**
        - Postings links to `/postings`.
        - Published links to `/postings?published=true`.
        - Employers and Scored are not interactive (classification table).
        - Each number is the sole text of its element, so `test_web_filter.py:129`'s `>3<`
          holds.
      - **Scoring callout.** `banner('info')` with the existing copy and no Upload button
        (FR-011).
      - **Triage card.** For each `by_status` entry: a status pill link, the count, and a
        proportional bar with a text percentage.
      - **Source-health card.** For each site: the name, the latest count, and the bar
        series. Each bar carries `aria-hidden`, plus a visually hidden list giving every
        value (FR-008). Zero bars show a hatched style as well as a colour (US4 AS-3).
      - **Empty states.**
- [x] T041 [US4] In `app.css`, add `.metric-grid`, `.distribution`, and `.bars` for zero and
      hatched bars.
- [x] T042 [US4] ⏺ Clear the page from PENDING, run the gates and do the manual checks.
      Commit: `feat(ui): renovate the overview dashboard (US4)`.

---

## Phase 7: User Story 5 — Catch silent degradation on Runs (Priority: P3)

**Goal**: Runs shows a per-source trend with text values, a yield delta, and a history
funnel with status pills.

**Independent Test**: seed runs that are running, succeeded and failed, plus one run the
filter never touched. Check that statuses read as text and icon, that the untouched run
shows "—", that the error text shows, and that the trend values are available as text.

- [x] T043 [P] [US5] Add a test to `T/test_web_filter.py` or `T/test_web.py`. It asserts:
      - a failed run renders with the text "failed" and its error text;
      - a run with no filter counts still renders "—" in Passed and Rejected;
      - the existing `>11<` and `>14<` assertions still hold.
- [x] T044 [US5] Rewrite `W/templates/runs.html`. Build:
      - **Per-source trend cards.** One card per site, with bars for each run, a text list of
        values, the latest count, and a yield delta against the previous run. The delta is
        shown only when two or more runs exist, and it is computed in the template from
        `health.series`.
      - **History table.** In `table_wrap("Run history")`, with `th[scope]`:
        - funnel column grouping;
        - `status_pill(r.status)`;
        - "—" kept per the R5 comment;
        - counts that are each the sole text of their cell (C-8);
        - the error row restyled as `.run-error`.
- [x] T045 [US5] ⏺ Clear the page from PENDING, run the gates and do the manual checks.
      Commit: `feat(ui): renovate the runs history (US5)`.

---

## Phase 8: User Story 6 — Manage search schedules (Priority: P3)

**Goal**: Schedules shows the profile list (switch-styled enable, run now, delete, the
filter-rules disclosure) and a grouped add form.

**Independent Test**: add a profile, trigger a validation error, toggle a profile, run it,
edit its rules and delete it. Each outcome should match today's.

- [x] T046 [US6] Rewrite `W/templates/profiles.html`, keeping every field, id and copy in
      C-7 and C-8.
      - **Profile list.**
        - The name, with the role underneath.
        - The location, with an icon.
        - Site pills.
        - The experience level.
        - The run time.
        - The enable control: a submit `<button role="switch" aria-checked=…>` that keeps
          its text label "Enabled" or "Disabled", inside the unchanged form.
        - `play_arrow` Run now.
        - `delete` Delete, with its confirmation kept.
        - The `<details>` filter rules, with the summary copy kept.
      - **Error banner.** `?error=` becomes `banner('error', …, focusable=True)`.
      - **Add form.** Two column groups:
        - left: name, term with `term-hint`, location, country;
        - right: the sites checkboxes, experience with `experience-hint`, and the title
          regexes.

        A footer holds the remote-only checkbox, the run time, an outlined
        `<button type="reset">Cancel</button>`, and "Save schedule" as the one primary
        button.
      - **"Run settings" link** to `/settings`.
- [x] T047 [US6] In `app.css`, add `.profile-list`, `.switch`, `.form-grid-2`
      (one column below 768 px) and `.form-footer`.
- [x] T048 [US6] ⏺ Clear the page from PENDING, run the gates (`T/test_web_config.py` must
      pass unchanged) and do the manual checks. Commit:
      `feat(ui): renovate the schedules page (US6)`.

---

## Phase 9: User Story 7 — Edit settings safely (Priority: P3)

**Goal**: the settings form is split into execution/scoring and filters/network groups,
with inline hints, and a read-only block.

**Independent Test**: save valid and invalid values. The messages and stored values should
match today's, and `database_url` must never appear.

- [x] T049 [P] [US7] Add a test to `T/test_settings.py` or `T/test_web_config.py`. It
      asserts that the `/settings` response contains no `postgresql://` string and no
      substring of the configured database URL (FR-012).
- [x] T050 [US7] Rewrite `W/templates/settings.html`.
      - Keep the field macro, the field names and the order of submission.
      - **Group 1, "Execution & scoring".** Results per search, hours old, request delay,
        publish threshold (with its "0–100" hint), scoring model (still a text field), and
        the LinkedIn checkbox with its label next to the box.
      - **Group 2, "Filters & network".** The title include and exclude patterns, the
        D6/ADR-0016 note with its copy unchanged, and proxies.
      - **Primary button.** "Save settings".
      - **Banners.** `saved` becomes a success banner reading "Settings saved — applies on
        the next run." (US7 AS-1). The error becomes an error banner.
      - **Read-only block.** A `lock` icon, the "Read-only (restart required)" heading, a
        grid of key/value tiles, and `database_url` shown as "hidden — environment only".
- [x] T051 [US7] ⏺ Clear the page from PENDING, run the gates and do the manual checks.
      Commit: `feat(ui): renovate the settings page (US7)`.

---

## Phase 10: User Story 8 — Review the blacklist (Priority: P3)

**Goal**: the Blacklist page shows summary figures derived from its rows, the table, a
plain-POST Remove (FR-016), the FR-013 callout and an empty state.

**Independent Test**: remove one employer. Their postings should reappear with the prior
status, and you should land on an intact Blacklist page.

- [x] T052 [P] [US8] Add tests to `T/test_blacklist.py`.
      - The `/blacklist` markup contains no `hx-post` (contract C-6).
      - The Remove form still posts to `/employers/{id}/unblacklist` with
        `return_to=/blacklist`.
- [x] T053 [US8] Rewrite `W/templates/blacklist.html`.
      - **Header and rule copy.** Keep both, including the legacy-blacklist note.
      - **Two figures**, derived in the template from `employers`: "Employers blacklisted"
        (the row count) and "Postings hidden" (the sum of counts).
      - **Table.** In `table_wrap`: the employer, a "N postings hidden" pill, and the Remove
        action. Remove becomes a **plain form**: drop `hx-post` and keep the action and
        `return_to` (FR-016, C-6). It is a text-link-style button with the `undo` icon.
      - **FR-013 callout.** Built with `banner('info')`.
      - **Empty state.** "No employers blacklisted. Blacklist one from a posting's detail
        page." (US8 AS-2).
- [x] T054 [US8] ⏺ Clear the page from PENDING, run the gates and do the manual checks.
      Commit (behaviour fix): `fix(web): make blacklist Remove a plain form post (FR-016)`.
      Commit (styling): `feat(ui): renovate the blacklist page (US8)`.

---

## Phase 11: User Story 9 — Find and read reports (Priority: P3)

**Goal**: the Reports index uses full-width link cards, and the three report pages use the
shared design language with their caveats kept.

**Independent Test**: open each report from the index. Every figure and caveat should match
today's.

- [x] T055 [P] [US9] Rewrite `W/templates/reports/index.html`. Each report is a `.card` whose
      title is the single link, stretched over the whole card with the `::after` overlay
      technique. Each card has the blurb and an `arrow_forward` icon. There are no badges and
      no previews (classification table: backend work).
- [x] T056 [P] [US9] Rewrite `W/templates/reports/employers.html`. Its toggles become
      `.chip` links with `aria-current` (C-7), and its table goes in `table_wrap`.
- [x] T057 [P] [US9] Rewrite `W/templates/reports/sources.html`, with tables in
      `table_wrap`. Any bars get a text equivalent.
- [x] T058 [P] [US9] Rewrite `W/templates/reports/profiles.html`: toggles as chips, and
      tables in `table_wrap`.
- [x] T059 [P] [US9] Restyle `W/templates/reports/_caveat.html` as `banner('info')`, with
      its copy unchanged.
- [x] T060 [US9] ⏺ Clear the pages from PENDING, run the gates (`T/test_web_reports.py`
      and `T/test_reports.py` must pass unchanged) and do the manual checks. Commit:
      `feat(ui): renovate the reports pages (US9)`.

---

## Phase 12: Polish & cross-cutting

- [x] T061 Delete the legacy alias section from `W/static/css/app.css` (T016). Grep the
      templates to confirm that no alias class is still used.
- [x] T062 Grep `W/templates/` for `style="`. The only inline styles left should be dynamic
      values (bar heights, as percentages). Move everything else into classes.
- [x] T063 Confirm that `PENDING` in `T/test_web_a11y_markup.py` and `PENDING_LITERALS` in
      `T/test_web_assets.py` are empty, then delete both constants.
- [x] T064 Re-run the C-8 grep: list every string asserted in `tests/test_web*.py`,
      `test_blacklist.py`, `test_profiles.py` and `test_settings.py`, and confirm each one is
      still rendered.
- [x] T065 Measure the real `app.css` size, update research R15 and plan §Performance, and
      confirm that the SC-009 test margin holds.
- [ ] T066 Write `specs/004-ui-renovation/verification.md`. It covers:
      - for every page: light and dark mode × 375, 768 and 1280 px (plus the 320 px reflow
        and 200% zoom spot checks);
      - the keyboard-only pass for each SC-004 flow;
      - each htmx interaction, with and without the script, plus a forced error;
      - the network-origin log;
      - reduced motion;
      - forced colours;
      - a list of every test assertion that was changed, with the reason (SC-006);
      - the mock-up elements deliberately left out, with reasons (from the classification
        table).
- [x] T067 Update the `README.md` and `Docs/development-guide.md` references to the web UI,
      if any of them describe the inline CSS or the htmx CDN.
- [x] T068 ⏺ Run the final gates. Commit:
      `chore(ui): remove legacy style aliases and inline styles`. Commit:
      `docs(ui): verification report for 004`.

---

## Dependencies & execution order

- **Phase 1** → **Phase 2** → **Phase 3 (US1)**. These are strictly sequential, because each
  builds on the last, and they end at the **tokens and base-layout checkpoint**.
- **Phase 4 (US2)** comes next, and ends at the **first full page checkpoint**.
- **Phases 5–11 (US3–US9)** each depend only on Phase 3. Their template tasks are
  independent, but every phase also edits `app.css`. Run them in priority order (US3, US4,
  then the P3 stories), or in parallel branches that resolve `app.css` section by section.
- **Phase 12** comes after every story phase.
- **Within a phase**: tests come before templates, and templates before that phase's CSS.
  The ⏺ task comes last.

### Parallel opportunities

- **Phase 1.** T001, T002, T003 and T005, then T008 alongside T006 and T007.
- **Phase 2.** T010, T011 and T012 together. T017, T018 and T021 together, after T013 starts.
- **Phase 11.** T055–T059. These are five separate templates, and none of them needs new CSS
  beyond the Phase 2 components.
- **The test-first tasks** in each story phase: T030, T043, T049, T052.

## Implementation strategy

- **MVP.** Phases 1–3 (the shell) plus Phase 4 (Postings) give the operator the daily
  workspace in the new design. Every other page still works through the legacy aliases.
- **Incremental delivery.** Each later phase is one page, ships on its own, and ends green
  with its own commit.
- **Scope guard.** Any need found during implementation that touches routes, fields,
  services (beyond R8) or dependencies stops work. The spec's Flagged follow-ups, or the
  dependency declaration, is amended first.
