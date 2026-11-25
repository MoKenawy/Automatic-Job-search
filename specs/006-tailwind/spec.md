# Feature Specification: Tailwind migration of the triage interface's styling

**Feature Branch**: `006-tailwind`

**Created**: 2026-11-21

**Status**: Draft

**Base**: `004-ui-renovation` at `49de3dd`. The 005 branches (`005-plain-js`,
`005-frontend-toolchain`) are not part of this feature's history and are ignored.

**Input**: User description: "Migrate the triage interface's styling from hand-written CSS
(ADR-0021) to Tailwind v4 via the standalone CLI, in four phases: Phase 0 setup with
identical output, Phase 1 hybrid, Phase 2 full utility migration, Phase 3 cleanup." The
full brief, with its decisions table, phase steps, rules and risks, was supplied in the
conversation that opened this feature. The parts that described the 005 tree are rebased
onto 004 in [Brief rebased onto 004](#brief-rebased-onto-004).

## Context

Feature 004 brought the triage interface in line with the approved design package. It did
so with one hand-written stylesheet, `web/static/css/app.css` (about 28 KB and 500 lines),
under ADR-0021: DESIGN.md tokens as custom properties on `:root`, a derived dark palette,
and semantic component classes. ADR-0021 considered and rejected the Tailwind standalone CLI
(its option B), mainly because of the build step, the binary, and utility-heavy templates.

That trade has changed. The Stitch target is written in Tailwind utilities, so each design
iteration is a manual translation into bespoke CSS. Every new layout grows the stylesheet,
and nothing checks that the tokens are applied consistently. This feature adopts Tailwind
v4 through its standalone CLI. No Node is involved. The build is only for authors: the
generated stylesheet is committed, so the container image, the runtime and the test suite
stay free of any build tool.

The work runs in four phases. Each phase is a valid place to stop:

1. **Phase 0, setup.** The toolchain produces a stylesheet that renders identically to
   today's.
2. **Phase 1, hybrid.** The semantic components stay. Utilities are used for new work and
   for light cleanup.
3. **Phase 2, full utilities.** Templates move to utilities one group at a time.
4. **Phase 3, cleanup.** Only tokens, the theme mapping, fonts, the base layer and true
   one-offs remain in authored CSS.

**What must not change.** Every 004 guarantee carries over unchanged:

- routes, methods, status codes and redirects;
- form field names and query parameters;
- the htmx ids, targets and swaps frozen in
  [`specs/004-ui-renovation/contracts/htmx-fragments.md`](../004-ui-renovation/contracts/htmx-fragments.md);
- the text that tests assert;
- WCAG 2.2 AA behaviour (004 FR-007, FR-008, FR-008a);
- local-first loading (004 FR-010, SC-005);
- the first-load budget (004 SC-009).

This feature changes how the styling is authored and delivered, never what the operator
sees or can do.

**Sources of truth.** DESIGN.md YAML tokens still win (004 conflict C1). The rendered pages
on `49de3dd` are the visual baseline. Where a utility translation and the baseline
disagree, the baseline wins.

## Brief rebased onto 004

The brief was drafted against the 005 tree. These are the points where 004 differs, and
what this spec uses instead.

| Brief says | On 004 | This spec |
|---|---|---|
| A new ADR supersedes ADR-0021 and ADR-0022 | Only ADR-0021 exists; 0022 to 0024 are 005 records | **ADR-0022** (next free number) supersedes ADR-0021 |
| `@source "../static/js"` because `app.js` toggles classes (selrow) | No `static/js/`. The only script is inline in `base.html`. It toggles **attributes** (`aria-busy`), not classes, and it selects on `.pill`, `.banner[tabindex]` and `nav a[aria-current="page"]` | Scanning the templates covers the inline script. The classes it selects on are **behaviour hooks** and must survive Phase 2 (FR-019) |
| Phase 2 groups `_results*.html`, `_status_*`, `_filter_state.html`, toasts, dialog | Flat templates: `_macros`, `_row_status`, `_status_control`, `base`, `postings`, `detail`, `index`, `runs`, `profiles`, `blacklist`, `settings`, `reports/{index,sources,employers,profiles,_caveat}`. No toasts or dialogs (004 FR-018) | Phase 2 steps are remapped (US3) |
| Page/fragment parity under ADR-0024 (`wants_fragment`) | No ADR-0024. The fragments are those in 004's htmx-fragments contract | Parity is checked against that contract (FR-016) |
| Update CLAUDE.md, whose frontend section describes Vite | CLAUDE.md is gitignored. Its Vite text comes from 005 | Updated locally only. The tracked docs are `Docs/development-guide.md` and `Docs/tech-stack.md` |
| Update `Docs/Job Discovery UX&UI/FAS.md` | FAS.md does not exist on 004; it was added in 005 | Not created. The development guide gets a "Styles" section instead (FR-024) |
| `test_design_tokens.py` needs no change | It regex-parses `\n:root {` in the **served** `app.css`. A minified build removes that layout | Covered by FR-010 and the Assumptions |

## Clarifications

### Session 2026-11-21

- Q: How do the minified stylesheet and the token contrast test fit together? → A: The
  served stylesheet is minified, and no CSS-parser dependency is added (tinycss2 was
  considered and declined). The contrast test reads the light and dark token blocks from
  the **authored** `input.css`. The hex values live there permanently, in every phase,
  because the theme mapping only references them. The rendered-class coverage test uses a
  stdlib regex over the built stylesheet, and also confirms that every authored token is
  defined there (FR-010, FR-013).
- Q: How is the zero-visual-difference gate checked? → A: Opt-in Playwright snapshots.
  pytest-playwright plus a pixelmatch-based snapshot plugin run behind a `--visual` flag,
  like the existing `--live` flag. Baselines are captured before any styling change and
  committed, and the last-run timestamp is masked. The default `pytest` run and CI stay
  free of browsers. The maintainer runs `--visual` at each gate (FR-003, FR-026).
- Q: How do the phases ship? → A: On numbered sub-branches, as in 003 and 004:
  `006-1` (Phase 0), `006-2` (Phase 1), `006-3.1` to `006-3.7` (one per Phase 2 step),
  and `006-4` (Phase 3). Each is its own PR into `006-tailwind` and passes its own
  `--visual` gate (FR-016, FR-027).

## User Scenarios & Testing *(mandatory)*

The actors are the **operator**, who uses the interface and must notice nothing, and the
**maintainer**, who authors styles, reviews changes and runs CI. Most of the value goes to
the maintainer. The operator's guarantee is that nothing changes for them.

### User Story 1 - The new toolchain renders today's interface exactly (Priority: P1)

The maintainer installs the project's normal dependencies and runs one documented command,
which writes the served stylesheet. The authored source contains:

- the existing tokens, unchanged;
- a theme mapping that exposes each token as a utility value;
- the existing rules, moved verbatim into a components layer;
- base-layer rules that restore today's element defaults where the framework's reset
  differs.

The operator sees no difference on any page, in either palette, at phone or desktop width.
CI rebuilds the stylesheet and fails if the committed copy is stale. The test suite and the
container image still need no build tool.

**Why this priority**: every later phase depends on this. On its own it removes the risk
from the decision: the toolchain is proven against a pixel baseline before any template is
touched.

**Independent Test**:

1. Capture baseline snapshots on `49de3dd` with `pytest --visual`.
2. Install the toolchain and build.
3. Run `pytest --visual` again and compare.
4. Run the full test suite on a machine with no CSS binary installed.
5. Edit the authored source without rebuilding, and confirm that CI's drift check fails.

**Acceptance Scenarios**:

1. **Given** the baseline screenshots, **When** the Phase 0 stylesheet is served, **Then**
   every baseline page matches at 375 px and 1280 px, in light and in dark.
2. **Given** a fresh clone with only the project's normal Python dependencies, **When** the
   maintainer runs the documented build command, **Then** it writes the served stylesheet
   without installing Node or any system package.
3. **Given** a change to the authored source with no rebuild, **When** CI runs, **Then** the
   drift check fails and names the stale file.
4. **Given** a machine with no CSS build binary, **When** the test suite runs, **Then** it
   passes.
5. **Given** the container image build, **When** it runs, **Then** no CSS build happens in
   it, and the image serves the committed stylesheet.
6. **Given** the theme mapping, **When** an author writes a colour utility that names a
   colour outside the project palette, **Then** no style is generated for it.
7. **Given** the reduced-motion and forced-colours rules, **When** they are placed inside or
   beside the new cascade layers, **Then** they still override the component rules exactly
   as they do today.

---

### User Story 2 - Author new work with utilities on top of the existing components (Priority: P2)

The maintainer opens the authored source and finds the components grouped as they already
are in `app.css`: buttons, chips and pills, cards, tables, forms, shell, feedback, and then
the page-specific rules. Where it reads better, a component's internals are written as
compositions of theme utilities. New layout (spacing, flex, grid) is written as utilities in
the template, not as a new bespoke rule. Rules the framework already provides, such as the
visually-hidden helper, are removed once nothing uses them.

**Why this priority**: it ships the day-to-day benefit with low risk, and it is a valid
place to stop if Phase 2 stalls.

**Independent Test**: after the change, the screenshot diff against the baseline is clean.
Grep shows that no removed class is still referenced. The first-load budget holds, and the
new stylesheet size is recorded as the hybrid baseline.

**Acceptance Scenarios**:

1. **Given** a variant selected by a class that a template builds at render time (for
   example `pill {{ status }}`, `banner {{ kind }}`, `delta down`, `bars i.zero`), **When**
   Phase 1 rewrites that component, **Then** the variant stays a selector on a semantic
   class and keeps rendering.
2. **Given** a helper class to be removed (for example `.visually-hidden`, `.spacer`,
   `.muted`), **When** it is removed, **Then** no template, macro or script still refers to
   it, and every former use now carries the equivalent utility.
3. **Given** any class that a template or script builds dynamically and the scanner cannot
   see, **When** the stylesheet is built, **Then** that class is generated, through a
   safelist entry if needed.

---

### User Story 3 - Templates move to utilities group by group (Priority: P3)

The maintainer converts one template group at a time, in dependency order, each as its own
reviewable change with its own screenshot diff. Utility clusters that repeat become Jinja
macros, not new CSS classes. Status-driven styling looks up complete class strings in a
macro-side mapping and never concatenates class names. Accessibility states (focus,
`aria-current`, `aria-busy`, `aria-checked`, reduced motion, forced colours) are expressed
through the matching variants or the base layer. Every behaviour hook the inline script and
the tests depend on is kept.

The groups, remapped to 004:

| Step | Scope | Notes |
|---|---|---|
| 3.1 | `_macros.html` | Icon, status pill and banner macros first. Status-to-class maps hold complete class strings |
| 3.2 | `base.html` | Shell, wordmark, tab strip, last-run pill, skip link, live region, `main` |
| 3.3 | `postings.html`, `_row_status.html`, `_status_control.html` | The htmx fragments. Check the full page and each fragment response |
| 3.4 | `detail.html` | Detail grid, actions, metadata list, description |
| 3.5 | `index.html` | Metric cards, distribution rows, source-health bars |
| 3.6 | `runs.html`, `profiles.html`, `blacklist.html`, `settings.html` | Forms, tables, switch, rules expander |
| 3.7 | `reports/index.html`, `reports/sources.html`, `reports/employers.html`, `reports/profiles.html`, `reports/_caveat.html` | Pie and legend keep their data-driven inline styles as small custom rules |

**Why this priority**: it is the longest phase (about 1,300 template lines), and it only
pays off once Phases 0 and 1 are in place. Every step stands on its own, so a half-finished
Phase 2 is still a valid resting state.

**Independent Test**: for each step, compare the screenshots of the pages that step touches
with the baseline. Render each htmx fragment named in the 004 contract and compare it with
the same region of the full page. Confirm that every class in the rendered output exists in
the built stylesheet.

**Acceptance Scenarios**:

1. **Given** a converted template, **When** it renders, **Then** it matches the baseline
   screenshots at 375 px and 1280 px, in light and in dark.
2. **Given** a status (new, shortlist, applied, rejected; running, success, failed; or an
   unknown value), **When** a pill renders, **Then** its full class string comes from one
   mapping in the macro, an unknown status gets the neutral style, and no class name is
   assembled from fragments.
3. **Given** the row status fragment and the detail status fragment, **When** each is
   returned to an htmx request, **Then** its markup matches the corresponding region of the
   full page, and every id, target and swap in the 004 contract is unchanged.
4. **Given** a keyboard user, **When** focus lands on any interactive element, **Then** the
   focus indicator is identical to the baseline: at least 2 px, and at least 3:1 contrast.
5. **Given** forced-colours mode or a reduced-motion preference, **When** any converted page
   renders, **Then** it behaves as it does on the baseline.
6. **Given** a utility cluster repeated in three or more places, **When** a step lands,
   **Then** that cluster lives in one macro.

---

### User Story 4 - Authored CSS shrinks to what utilities cannot express (Priority: P4)

Once every template group is converted, the maintainer removes each component rule whose
last use is gone, confirmed by grep. What remains in the authored source:

- the tokens;
- the theme mapping;
- the font faces;
- the base layer;
- a short list of true one-offs, each with a comment saying why it cannot be a utility (for
  example the striped zero bar, the pie, and the scroll fade on the tab strip).

The budget is re-measured, and the verification report and the development guide
describe the final structure. ADR-0022 is marked accepted.

**Why this priority**: tidy-up with no new capability. It is only possible after US3.

**Independent Test**: grep finds no component rule without a template use. The screenshot
diff is clean. The budget test passes. The docs describe the structure that is actually on
disk.

**Acceptance Scenarios**:

1. **Given** a component rule in the authored source, **When** cleanup finishes, **Then**
   at least one template, macro or the inline script still uses it, or it is gone.
2. **Given** the final build, **When** the first-load payload is measured, **Then** it is
   at most 150 KB, and the figure is recorded in the verification report.

---

### Edge Cases

- **Dynamically built classes.** A class assembled in Jinja or set by script is invisible to
  the scanner and is never generated. Use complete class strings in macro mappings, safelist
  entries, and a test that every class in every rendered page exists in the built stylesheet
  (FR-013).
- **Reset differences.** The framework's reset restyles headings, lists, buttons, tables and
  form controls. Today's element defaults are restored in the base layer before any later
  phase begins, and the restore is verified first on headings, `table`, `dl.meta` and form
  controls.
- **Layer precedence.** Rules inside a cascade layer lose to unlayered rules. The
  reduced-motion, forced-colours and `:focus-visible` rules must keep winning after the move
  (US1 AS-7). They must keep winning in Phase 2 too, once utilities in a later layer have
  replaced the component rules they override (FR-020).
- **Data-driven colour references.** The pie and legend take `var(--token)` strings from a
  Jinja map (`reports/profiles.html`). These are token references, not literals, and they
  stay inline (FR-021).
- **Data-driven inline styles.** Bar heights and pie segments are computed per render.
  They stay inline styles or small custom rules, and are never turned into a utility per
  value.
- **Merge conflicts on the generated file.** The resolution is always to rebuild. The drift
  check catches a bad merge.
- **Binary download fails in CI.** Only the drift check needs the binary, so tests still run
  and report. The binary is cached between runs.
- **Phase 2 stalls.** Each step is separate, and the hybrid state is a supported resting
  point. FR-019 and FR-013 hold in every intermediate state.
- **Colour literals.** An arbitrary-value utility such as a hex colour in brackets is a
  colour literal and is caught by the existing no-literal guard (004 FR-005, SC-007).
- **Unknown status.** A status outside the known sets gets the neutral pill style, as today
  (004 edge case "Status variety").
- **Non-Latin text.** The font fallback chain stays exactly as it is, so Arabic employer
  names render as on the baseline.

## Requirements *(mandatory)*

### Functional Requirements

**Invariants carried from 004**

- **FR-001**: The migration MUST NOT change routes, HTTP methods, status codes, redirect
  targets, form field names, query parameters, service behaviour or the database schema
  (004 FR-001).
- **FR-002**: The migration MUST NOT change any id, target, swap or asserted text frozen in
  the 004 htmx-fragments contract, and every form MUST still work without scripting (004
  FR-002, FR-003).
- **FR-003**: Every page MUST look the same as the `49de3dd` baseline at 375 px and 1280 px,
  in light and in dark, at every phase gate. Any intended visual difference requires a
  recorded decision.
- **FR-004**: WCAG 2.2 AA behaviour MUST be preserved, including the focus indicator, target
  sizes, `aria-current`, the busy state, reduced motion and forced colours (004 FR-007,
  FR-008, FR-008a).
- **FR-005**: Pages MUST load nothing from other origins. The fonts and the icon sprite stay
  self-hosted (004 FR-010).

**Toolchain (Phase 0)**

- **FR-006**: The CSS build MUST run through a project-pinned tool installed with the
  project's normal Python dependency manager. It MUST need no Node, no global install and no
  system package. The tool version and the framework version MUST both be pinned and
  recorded.
- **FR-007**: The authored source MUST live in one entry file outside the static directory.
  It MAY import further files from the same directory. The generated stylesheet MUST stay at
  its current served path, and it MUST stay the only stylesheet the pages load.
- **FR-008**: The generated stylesheet MUST be committed. The container image MUST NOT run
  the CSS build, and the test suite MUST NOT need the build binary.
- **FR-009**: CI MUST rebuild the stylesheet from the authored source and fail when the
  result differs from the committed copy.
- **FR-010**: The design tokens MUST stay defined once, as custom properties on `:root`,
  with the dark palette under the colour-scheme media query. They MUST be exposed to
  utilities through an inline theme mapping. The served stylesheet is minified. The WCAG
  contrast test MUST keep checking every token pair in both palettes, reading them from
  the authored source, where they are defined in every phase. No new test dependency is
  added for CSS parsing.
- **FR-011**: The theme MUST discard the framework's default colour palette, so that only
  project colour roles are available as utilities. It MUST map the DESIGN.md type scale,
  spacing, radii, shadows and font family onto theme values, one entry per DESIGN.md role.
- **FR-012**: The existing rules MUST first move into the authored source unchanged, inside
  a components layer. Today's element defaults MUST be restored in a base layer wherever the
  framework's reset differs.
- **FR-013**: A test MUST render every page and every htmx fragment and fail if any class
  in the output is not defined in the built stylesheet, or if any token in the authored
  source is not defined there. A test MUST fail if any declared
  scan source path does not exist.

**Hybrid (Phase 1)**

- **FR-014**: From Phase 1 on, new spacing, flex and grid layout MUST be written as
  utilities, not as new bespoke rules. Component internals MAY become compositions of
  theme utilities. Variants that templates select by a render-time class (status pills,
  banners, deltas, zero bars, the current chip) MUST stay selectors on semantic classes
  until US3 replaces them with mapped full class strings.
- **FR-015**: A rule MUST only be deleted after a repository-wide search shows no remaining
  reference in templates, macros, the inline script or tests.

**Full utilities (Phase 2)**

- **FR-016**: Each Phase 2 step MUST be a separate change with its own screenshot diff. For
  the htmx fragments, both the full-page and the fragment responses MUST be checked, and
  their markup MUST stay identical.
- **FR-017**: Utility clusters repeated in three or more places MUST become Jinja macros,
  not CSS classes.
- **FR-018**: Status-driven styling MUST use complete class strings from a single mapping
  per status family. Class names MUST NOT be built by concatenation or interpolation. An
  unknown status MUST map to the neutral style.
- **FR-019**: Classes that the inline script, the htmx contract or the tests select on
  (`pill`, `banner`, the `status-*` ids, `nav a[aria-current]`, `#selcount`, `#announcer`
  and the like) MUST remain in the markup as behaviour hooks, whether or not they carry
  styles.
- **FR-020**: Focus, `aria-current`, `aria-busy`, `aria-checked` and disabled styling MUST
  use the matching state variants. Reduced-motion and forced-colours handling MUST keep
  winning over every utility. Reduced motion stays `!important`, which wins from any layer.
  Forced-colours overrides use the matching variants or an unlayered block. They MUST NOT
  sit in the base layer without `!important`, because the utilities layer would override
  them (research R5). None of it may be dropped.
- **FR-021**: Data-driven geometry (bar heights, pie segments, legend dots) MAY stay as
  inline styles or small custom rules. It MUST NOT introduce colour literals into templates.

**Cleanup and records (Phase 3 and throughout)**

- **FR-022**: At the end, the authored source MUST contain only tokens, the theme mapping,
  font faces, the base layer and commented one-offs.
- **FR-023**: ADR-0022 MUST record the decision and supersede ADR-0021. It MUST amend
  constitution principle III to read in substance: "One language at runtime, server-rendered.
  A build step is permitted only for authored assets, only if it needs no Node, and only if
  its output is committed, so that the image, the runtime and the tests stay build-free."
  It is drafted in Phase 0 and accepted at the end of Phase 3.
- **FR-024**: The development guide (a new "Styles" section), `Docs/tech-stack.md` (its
  "one language" and "no build" lines) and the local CLAUDE.md MUST describe the build
  command, the watch command, the drift check and the authored-source layout in Phase 0,
  and the final structure in Phase 3.
- **FR-025**: Code and CSS comments MUST cite the decision they implement (ADR-0022, this
  spec's FR numbers, DESIGN.md), as the project's style requires.
- **FR-026**: The visual gate (FR-003) MUST be an automated, opt-in browser test behind a
  `--visual` pytest flag. It screenshots the 11 baseline pages at 375 px and 1280 px in
  both palettes, compares them pixel by pixel with committed baselines, and masks content
  that changes between renders, such as the last-run time. The baselines are captured
  before any styling change, while the served stylesheet is still byte-identical to
  `49de3dd`.
  Without the flag, the browser tooling is neither imported nor required, so the default
  `pytest` run and CI stay browser-free.
- **FR-027**: Each phase, and each Phase 2 step, MUST land on its own numbered sub-branch
  (`006-1`, `006-2`, `006-3.1` to `006-3.7`, `006-4`). Each merges into `006-tailwind`
  through its own PR, and only once its `--visual` gate, the full test suite and the drift
  check pass.

### Key Entities

No data entities are added or changed. The artefacts this feature introduces are:

- **Authored stylesheet source**: the entry file and its imports. This is the only place
  styles are hand-edited.
- **Generated stylesheet**: the committed build output at the existing served path. It is
  never hand-edited.
- **Theme mapping**: one entry per DESIGN.md role, pointing at the `:root` token.
- **Status class mapping**: per status family (posting, run, banner kind), the complete
  class string for each value, plus a neutral fallback.
- **Visual baseline**: 44 committed snapshots (11 pages, two widths, two palettes),
  captured on `49de3dd` and compared by the opt-in `--visual` test.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: **0** visual differences against the baseline on the 11 baseline pages, at
  375 px and 1280 px, in light and in dark, at each of the four phase gates. The pages are
  `/`, `/postings`, one posting detail, `/reports`, the three report pages, `/profiles`,
  `/blacklist`, `/settings` and `/runs`. The opt-in `--visual` run (FR-026) shows **44 of
  44** snapshots matching.
- **SC-002**: **100%** of the existing automated tests pass at every gate, on a machine with
  no CSS build binary and no Node. Any changed assertion is about styling only, and the
  verification report lists it with its reason.
- **SC-003**: The CI drift check fails on **100%** of commits whose authored source changed
  without a rebuild, and passes on every commit where the two agree.
- **SC-004**: The first visit downloads **≤ 150 KB** in total of styling, fonts, icons and
  scripts at every gate (004 SC-009). The stylesheet size is recorded at Phases 0, 1 and 3.
- **SC-005**: **0** classes appear in rendered pages or fragments that are missing from the
  built stylesheet.
- **SC-006**: **0** literal colours in templates, and **0** colour utilities outside the
  project palette (004 SC-007).
- **SC-007**: **100%** of token pairs meet the 004 contrast thresholds in both palettes
  (004 SC-002).
- **SC-008**: **0** requests to other origins on any page (004 SC-005).
- **SC-009**: Bespoke component rules decrease from the Phase 0 count to **only the
  documented one-offs** by the end of Phase 3. Each Phase 1 and Phase 2 change adds no new
  bespoke layout rules.
- **SC-010**: A maintainer can go from a fresh clone to a rebuilt stylesheet using only the
  documented commands, in under 5 minutes, excluding download time.

## Assumptions

- **Screenshot platform.** Baselines are captured and compared on the maintainer's Windows
  machine, because font rendering differs between platforms. CI does not run `--visual`.
- **Seeded data.** The visual test renders against a fixed, seeded in-memory database, so
  the baselines are deterministic.
- **The inline script stays inline.** Moving it to a file is out of scope. It sets
  attributes, not classes.
- **Toolchain distribution.** The pinned tool fetches a platform binary on first use. The
  maintainer's Windows machine and the Linux CI runner are the two supported platforms.
- **The constitution file.** `.specify/memory/constitution.md` in this checkout is an
  unfilled template and is gitignored. Principle III is amended through ADR-0022 (FR-023),
  and the plan's Complexity Tracking records it as a justified deviation.
- **No theme switch, no new pages, no copy changes.** Dark mode still follows the system
  preference (004 assumption). The Stitch target is not chased any further than the 004
  baseline.
- **Effort.** Roughly half a day for Phase 0, half a day to a day for Phase 1, several short
  sessions for Phase 2, and a couple of hours for Phase 3.
