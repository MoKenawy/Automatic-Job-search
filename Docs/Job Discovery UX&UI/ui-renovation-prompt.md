# Prompt — UI/UX Renovation of the Job Discovery Triage Interface

## Role

You are a senior product designer-engineer who builds server-rendered web
interfaces. You know FastAPI, Jinja2 and htmx well. You also know design-token
systems, WCAG 2.2 accessibility and spec-driven development with GitHub Spec Kit.
Treat this repository's conventions as binding. Make design decisions you can
defend in writing, and when the design package and the running system disagree,
point out the conflict instead of guessing.

## Task

Renovate the look and the user experience of the triage web interface
(`app/src/app/web/`) so it matches the approved design package in
`Docs/Job Discovery UX&UI/`. **What the application does must not change.**

**In scope: every page and partial the web app serves.**

| Page | Route | Template(s) | Design reference (Stitch export) |
|---|---|---|---|
| Overview | `/` | `index.html` | `job_discovery_overview_dashboard` |
| Postings list | `/postings` | `postings.html`, `_row_status.html` | `job_discovery_postings` |
| Posting detail | `/postings/{id}` | `detail.html`, `_status_control.html` | *none*: derive it from the postings screen and the design system |
| Reports | `/reports`, `/reports/{employers,sources,profiles}` | `reports/*.html`, `reports/_caveat.html` | `job_discovery_reports` |
| Blacklist | `/blacklist` | `blacklist.html` | `job_discovery_blacklist` |
| Schedules | `/profiles` | `profiles.html` | `job_discovery_schedules` |
| Settings | `/settings` | `settings.html` | `job_discovery_settings` |
| Runs | `/runs` | `runs.html` | `job_discovery_runs_history` |
| Shell / nav | all pages | `base.html` | shared chrome across all screens |

**Deliverables, in order:**

1. A **dependency declaration** (see Constraint 1). This is a gate: wait for my
   approval before going further.
2. Spec Kit artifacts in `specs/004-<slug>/`, produced through the workflow in
   Constraint 2.
3. The implementation, delivered page by page.
4. A short verification report. For every page, check light mode and dark mode at
   widths of 375, 768 and 1280 px, do a keyboard-only pass, and confirm the htmx
   interactions still work. Then list any mockup elements you deliberately left out,
   with the reason for each.

## Constraints

### 1. Declare dependencies before you start (hard gate)

Before you run any Spec Kit command or edit any file, output a
**Dependency declaration**. List every library, package, CDN asset, font, icon set
and build tool the renovation would add or change. For each one, give:

- the name and **exact version**
- how it is loaded: a `uv` dependency, a vendored static file, or a CDN
- why it is needed, and what the alternative without it would be
- its licence

If nothing new is needed, write **"No new dependencies"** and explain why. Then
**stop and wait for my approval.** After approval, never add anything that is not
on the approved list. If a new need comes up later, stop and amend the declaration
first.

The declaration must explicitly settle these points:

- **Tailwind.** The Stitch exports use the `cdn.tailwindcss.com` Play CDN. That is
  a development-only compiler that runs in the browser, so it must not ship. Pick
  one of these and recommend it with reasons:
  - (a) translate the design tokens into hand-written CSS custom properties. This
    adds no dependencies and matches how `base.html` works today.
  - (b) the Tailwind standalone CLI, which needs no Node, producing a built
    stylesheet.
  - (c) another option, with your justification.
- **Fonts and icons.** The mockups load Inter and Material Symbols from Google
  Fonts. `Docs/tech-stack.md` §2 says *"nothing … ships data off the machine."*
  Either self-host them (vendored `woff2`/SVG files served by FastAPI) or justify
  an exception. If you only need a few icons, prefer inline SVGs over loading a
  whole icon font.
- **htmx.** It is loaded today from `unpkg.com` at version `2.0.3`. Keep that
  version, and say whether you will vendor it along with the other assets.
- **Static file serving.** The app has no static mount today. If you add a
  `StaticFiles` mount, declare it, even though it is a code change rather than a
  package.

### 2. Follow the Spec Kit workflow (mandatory)

Run these steps in order and skip none. Each step must produce its artifact before
the next one starts.

1. **Constitution.** Read `.specify/memory/constitution.md` and follow it. Amend it
   with `/speckit.constitution` only if it has no UI or accessibility principles,
   and propose the amendment to me first.
2. **`/speckit.specify`.** This is feature **004**. The branch name must equal the
   directory name (see CONTRIBUTING.md, "Feature specifications"), for example
   `004-ui-renovation`. The spec covers **what and why only**: user stories per
   page, acceptance scenarios, and measurable success criteria. Examples of
   success criteria: number of clicks to triage a posting, WCAG AA contrast on
   every token pair, no horizontal page scroll at 375 px. Keep implementation
   detail out of the spec.
3. **`/speckit.clarify`.** Resolve every `[NEEDS CLARIFICATION]` marker by asking
   me. Ask at most 5 questions.
4. **`/speckit.plan`.**
   - Record the dependency decision from Constraint 1 in `research.md`, with the
     alternatives you rejected.
   - In `data-model.md`, state that there are no schema changes.
   - In `contracts/`, write down the **htmx fragment contracts** that must stay
     stable: element `id`s, `hx-target`, `hx-swap`, form field names, and the
     fragments that `POST /postings/{id}/status` and `POST /postings/status`
     return.
5. **`/speckit.checklist`.** Produce a UX and accessibility checklist.
6. **`/speckit.tasks`.**
   - Order the work as design tokens and the base layout first, then one phase per
     page.
   - Mark tasks that can run in parallel with `[P]`.
   - Make each page phase shippable on its own.
7. **`/speckit.analyze`.** Fix every CRITICAL or HIGH finding before you implement.
8. **`/speckit.implement`.** Work through the phases in order.

**Review checkpoints.** Stop for my review at each of these points:

- after `specify`
- after `plan`
- after `tasks`
- after the tokens and base-layout phase
- after the first full page is finished

### 3. Preserve behaviour

- **Change presentation only.** Do not change any of these: routes, HTTP methods,
  status codes, form field names, query parameters, services, the database schema
  or migrations. If a UX improvement needs one of these changes, record it in the
  spec as a separate, flagged follow-up and do not implement it.
- **Keep every htmx interaction working:**
  - the single-row status change
  - the bulk status bar
  - filters and search
  - pagination
  - blacklist and unblacklist
  - profile enable, run and delete
- **Keep server rendering.** It stays Jinja2 plus htmx. Add no JS framework and no
  SPA. Use small inline scripts only where htmx cannot do the job.
- **Keep tests and lint green.** `uv run pytest` and `uv run ruff check` must both
  pass. Change a test assertion only if it checked markup or styling alone, and
  list every test you change with the reason.
- **Mockups are illustrative, not a spec of features.** For every element in a
  mockup that the backend has no data for (for example a login screen, since the
  app has no authentication, or a metric nothing computes), mark it as one of:
  - **implement with existing data**
  - **out of scope**
  - **needs backend work**, to be done as a separate feature

  Never copy placeholder data or fake numbers.

### 4. Design system and quality bar

- **Tokens.** `technical_precision/DESIGN.md` is the single source of truth for
  colours, type and spacing. Define the tokens once as CSS custom properties, and
  use **no raw hex values in templates**.
- **Conflicts.** Where `Job_Discovery_Brand_Guidelines.pdf` and the Stitch output
  disagree, the brand guidelines win. Record each conflict you find.
- **Dark mode.** The current UI supports `prefers-color-scheme: dark`, and the
  renovation must keep it. DESIGN.md defines only a light palette, so derive a
  dark palette and check its contrast.
- **Accessibility (WCAG 2.2 AA):**
  - colour contrast
  - visible focus states
  - full keyboard operation
  - labelled form controls
  - `aria-live` on regions that htmx swaps
  - correct table headers
  - icons that are either labelled or marked decorative
  - respect for `prefers-reduced-motion`
- **Responsive layout.** The UI is desktop-first and must work at 375, 768 and
  1280 px or wider. Wide tables scroll inside their own container, not the page.
- **Performance.** Do no CSS compilation at runtime. State the total CSS, font and
  icon payload in `plan.md`.

### 5. Repository conventions

- Use Conventional Commits with the scope `ui` or `web`, one concern per commit.
- The styling-approach decision chooses between approaches whose trade-off a future
  reader would otherwise have to reconstruct, so it needs an **ADR**. Write it as
  `Docs/ADRs/0021-…`, following CONTRIBUTING.md.
- Comments explain *why* and name their source, for example `DESIGN.md` or
  `ADR-0021`.
- Do not commit `.specify/` or `.claude/`; both are gitignored on purpose.
- Do not push or open a pull request without asking me.

## Context

- **The product.** A self-hosted job-discovery pipeline with a single operator: it
  collects postings, then normalises, filters and scores them. The web app is
  where the operator triages postings and configures the system (ADR-0004,
  ADR-0005).
- **The stack.** Python 3.12, `uv`, FastAPI, Jinja2, htmx 2.0.3, PostgreSQL 16.
  The guiding principles are zero recurring cost and no data leaving the machine
  (`Docs/tech-stack.md`).
- **The current UI.** All CSS lives inline in `base.html`: about 150 lines of
  tokens and components, the system font stack, and light and dark palettes. The
  navigation is Overview, Postings, Reports, Blacklist, Schedules, Settings, Runs.
  The page "Schedules" is served at `/profiles`.
- **The design package** in `Docs/Job Discovery UX&UI/`. Read it before you
  write the spec.
  - `Job_Discovery_UX_Documentation.pdf`: user flows, information architecture,
    and the rationale behind them. **Read this first.**
  - `Job_Discovery_Brand_Guidelines.pdf`: the brand rules.
  - `stitch_remix_of_job_discovery_wireframe_login/.../<screen>/screen.png` and
    `code.html`: the visual target for each screen. Treat `code.html` as
    reference markup, not production code.
  - `technical_precision/DESIGN.md`: the design tokens (colour roles, the Inter
    type scale, spacing, radii).
  - `16371c6c-….png`: an additional reference image.
  - `ui .txt`: a link to the Stitch project. The exported files above are the
    source of truth.
- **Prior art to read:**
  - `CONTRIBUTING.md`
  - `specs/001-ui-self-service/`, the last UI feature and a model for spec style
  - `app/tests/test_web*.py`, which shows what the existing tests assert about the
    markup
- **Spec Kit.** `.specify/` is local to this machine and gitignored. Features
  001–003 exist, so this one is 004.
