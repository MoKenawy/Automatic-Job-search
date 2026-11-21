# Research: Tailwind migration (006)

Each entry gives the decision, its rationale, and the alternatives considered. Items marked
**verify in Phase 0** are behaviours of the pinned framework version. The first build
confirms them, and the `--visual` gate catches any surprise.

---

## R1 — Toolchain: Tailwind v4 standalone CLI through pytailwindcss

**Decision.** Add `pytailwindcss` to the `dev` dependency group. It installs a `tailwindcss`
command into the venv, and that command downloads the official standalone binary from the
Tailwind GitHub releases. The binary version is pinned with the `TAILWINDCSS_VERSION`
environment variable, using a tag such as `v4.x.y` with the `v` prefix. If it is unset, the
latest release is downloaded.

There is **one build entry point**, `app/scripts/build_css.py`. It is a short stdlib script
that does three things:

1. reads the pinned tag from `[tool.app.tailwind] version` in `app/pyproject.toml`, which is
   the single source of the pin;
2. exports `TAILWINDCSS_VERSION` and reinstalls the binary (`tailwindcss_install`) when the
   installed binary reports a different version;
3. runs `tailwindcss -i src/app/web/styles/input.css -o src/app/web/static/css/app.css --minify`,
   or the same with `--watch` when `--watch` is passed.

The pin is the latest v4.x tag that is at least two weeks old on the day Phase 0 starts.
The plan records it once the tag is chosen.

**Rationale.**
- No Node and no global install (FR-006). `uv run` works on the Windows workstation and on
  the Linux runner.
- One script means the developer command and the CI command cannot drift apart. A local and
  CI version mismatch would show up as a spurious drift failure.
- `dev` is excluded by the Dockerfile's `uv sync --no-dev`, so the image never sees it
  (FR-008).

**Alternatives.**
- **The npm `@tailwindcss/cli`.** Rejected: it needs Node.
- **Downloading the binary in a shell script.** Rejected: it means per-OS URLs, checksums
  and cache handling that pytailwindcss already does.
- **A `css` subcommand on the app CLI.** Rejected: it would put build tooling into the
  runtime package.
- **An env-var pin in CI only.** Rejected: there would be two sources for one pin.

## R2 — Entry file, scanning and safelist

**Decision.** `app/src/app/web/styles/input.css`:

```css
@import "tailwindcss" source(none);   /* no auto-detection: scan only what is declared */
@source "../templates";
@source inline("…");                  /* only if a class is built where the scanner cannot see it */
```

- Turning off automatic detection with `source(none)` stops the scanner from walking
  `.venv`, `tests` or the docs.
- 004 has no `static/js/`. Both inline scripts, in `base.html` and `postings.html`, are
  covered by `@source "../templates"`. Neither one adds or removes a class. They change
  `aria-busy`, `disabled` and text, and select on existing classes and ids.
- The safelist starts empty. It gets an entry only when the coverage test (R8) finds a
  class that is rendered but not generated.

**Rationale.** It keeps the scan explicit and makes FR-013's "every `@source` path exists"
test meaningful.

**Alternatives.** Default auto-detection. Rejected because the scan root depends on the
working directory and picks up unrelated files.

## R3 — Theme mapping: tokens stay on `:root`, utilities reference them

**Decision.**
- **Colours.** The 30 colour roles stay as hex custom properties in `:root`, with dark
  overrides under `@media (prefers-color-scheme: dark)`, moved verbatim from `app.css` §1.
  They are exposed with `@theme inline { --color-*: initial; --color-surface: var(--surface); … }`.
  With `inline`, the generated utility carries the referenced value itself
  (`.bg-surface{background-color:var(--surface)}`), so the dark override of `--surface`
  flows through without an intermediate `--color-surface` variable. `--color-*: initial`
  removes the default palette (FR-011).
- **Type.** Namespaces are cleared with `--text-*: initial`. One `--text-<role>` per
  DESIGN.md role (`headline-xl`, `headline-lg`, `headline-md`, `headline-sm`, `body-lg`,
  `body`, `body-sm`, `label`, `label-sm`), each with its `--line-height` and
  `--letter-spacing` companions, referencing the existing `--fs-*`, `--lh-*` and `--ls-*`
  tokens. `--font-sans: var(--font)`.
- **Spacing.** `--spacing: 0.25rem`. Every DESIGN.md space (0.125 to 3 rem) is a multiple
  of 0.125 rem, so the default numeric scale covers it (`p-0.5` … `p-12`). There are no
  named spacing keys.
- **Radii and shadows.** The token names `--radius-sm`, `--radius-md`, `--radius-lg`,
  `--radius-xl`, `--radius-full` and `--shadow-1` to `--shadow-3` **collide with
  Tailwind's own theme namespaces**. Mapping them with `@theme inline { --radius-sm: var(--radius-sm) }`
  would be self-referential. These tokens therefore move from `:root` into
  `@theme static { --radius-*: initial; --radius-sm: 0.125rem; …; --shadow-*: initial; --shadow-1: …; }`.
  - `static` makes Tailwind emit them on `:root` whether or not a utility uses them.
    The hand-written components still read them through `var()`.
  - They remain defined once.
  - The dark shadow overrides stay in the dark `:root` block, which outranks the theme
    layer.
  - **Verify in Phase 0.**
- **Breakpoints.** Tailwind's defaults, `md` = 48 rem (768 px) and `lg` = 64 rem (1024 px),
  match the existing media queries. `max-width: 767px` maps to `max-md:` and
  `max-width: 640px` to `max-sm:`. No breakpoint keys change.

**Rationale.** FR-010 and FR-011. The contrast test keeps reading hex values from the
authored `:root` blocks (clarification Q1). The radius and shadow move is the smallest
change that avoids the name collision without renaming tokens that DESIGN.md and the
components use.

**Alternatives.**
- **Renaming the tokens** (`--r-sm`, `--elev-1`). Rejected: it touches every component
  rule in Phase 0, which breaks "moved verbatim".
- **Plain `@theme` with hex values.** Rejected: it would copy the palette into a second
  place and break dark mode (dev.to: the "`@theme` vs `@theme inline` gotcha").

## R4 — Preflight is kept, and today's defaults are restored in `@layer base`

**Decision.** Keep Tailwind's Preflight, as the brief says. All of today's §2 and §3 rules
move verbatim into `@layer components`. Components outrank base, so wherever today's CSS
already sets a property, it still wins over Preflight. The only restores needed are for
properties that **Preflight sets and today's CSS does not**. Known candidates, all to be
confirmed by the first `--visual` run:

| Preflight sets | Affected markup | Restore in `@layer base` |
|---|---|---|
| `svg, img { display: block; vertical-align: middle }` | Every `.icon` (inline sprite `<svg>`) | `svg { display: inline; vertical-align: baseline }` (the `.icon` rule keeps its `-0.2em`) |
| `*` margin 0 and padding 0 | `ul`/`ol` without `.chips` or `.legend`, `h4`+, `blockquote`, `figure`, `dl`, `dd` outside `dl.meta` | Browser defaults for the elements actually used, found by grepping the templates |
| `ol, ul, menu { list-style: none }` | Plain lists in detail and reports | `ul { list-style: disc } ol { list-style: decimal }` scoped to plain lists |
| `h1…h6 { font-size: inherit; font-weight: inherit }` | `h4`+ if any (h1 to h3 are set today) | Only if used |
| `button, input, select, textarea { font: inherit; color: inherit; background: transparent }` | `.switch` and any raw `<button>` | Nothing for `.btn` and `.switch` (they set everything). Check raw buttons |
| `::placeholder` colour | Inputs | Already set by today's rule |
| `table { text-indent: 0; border-color: inherit }` | Tables | Harmless; verify |
| `summary { display: list-item }`, `[hidden]` | Rules expander | Verify |

**Rationale.** Phase 2 utilities assume Preflight. For example, `border` sets only the
width and relies on Preflight's `border-style: solid`. Without Preflight, every border
utility would need an explicit style.

**Alternatives.** Importing `tailwindcss/theme` and `tailwindcss/utilities` without
Preflight. That carries less risk for Phase 0, but every later utility would sit on a
non-standard base. Rejected.

## R5 — Cascade layers and the accessibility overrides

**Decision.** Tailwind declares `@layer theme, base, components, utilities`. Every
unlayered rule outranks every layered normal declaration. Among `!important`
declarations the order reverses: earlier layers win, and layered beats unlayered.

| Rule set today | Phase 0 and 1 placement | Phase 2 and later (utilities override components) |
|---|---|---|
| `@media (prefers-reduced-motion)` with `!important` | `@layer components`, unchanged | Move to `@layer base`, keeping `!important`. An important declaration in an earlier layer beats everything, so it still cancels utility transitions |
| `@media (forced-colors: active)` without `!important` | `@layer components`, after the rules it overrides; same-layer source order, unchanged | Move out of every layer, into an **unlayered** block at the end of `input.css`, or into `forced-colors:` variants on the elements. **Not** `@layer base`: utilities would beat it (corrects the brief; spec FR-020) |
| `:focus-visible { outline… }` | `@layer components` | Base layer as the default ring, plus `focus-visible:` variants where a utility sets `outline` |

**Rationale.** It keeps US1 AS-7 and FR-020 true in every intermediate state.

**Alternatives.** Making everything unlayered. Rejected: unlayered component rules would
beat utilities, so Phase 1 and Phase 2 utility overrides would silently do nothing.

## R6 — Committed output and the drift check

**Decision.**
- `app/src/app/web/static/css/app.css` is generated, minified and committed. A header
  comment in `input.css` says the output is generated.
- `.gitattributes` gets the line `app/src/app/web/static/css/app.css -diff linguist-generated`,
  so reviews collapse it.
- A new step in the `test` job of `.github/workflows/ci.yml`, after `uv sync --frozen`:

```yaml
- name: Cache the Tailwind binary
  uses: actions/cache@v4
  with:
    path: app/.venv/lib/python3.12/site-packages/pytailwindcss/bin   # exact path confirmed in Phase 0
    key: tailwind-${{ runner.os }}-${{ hashFiles('app/pyproject.toml') }}
- name: Check the committed stylesheet is current
  run: |
    uv run python scripts/build_css.py
    git diff --exit-code -- src/app/web/static/css/app.css
```

- The step runs **after** `pytest`, so a binary download failure never hides test results
  (spec edge case).

**Rationale.** FR-008 and FR-009, SC-003. The Dockerfile is untouched.

**Alternatives.** Building in a Docker stage. Rejected: it adds the binary to the image
build and breaks "the image serves the committed file". A pre-commit hook only would be
easy to bypass, so CI is the gate.

## R7 — Visual gate: opt-in Playwright snapshots

**Decision.**
- **Dependencies.** A **new dependency group `visual`**: `pytest-playwright` and
  `pytest-playwright-visual-snapshot`, which is active (0.5.1, Feb 2026) and supports
  global mask selectors and `--update-snapshots`. It is installed only with
  `uv sync --group visual`, followed once by `uv run playwright install chromium`. The
  default `uv sync` (dev only) and CI never install it.
- **Test module.** `app/tests/test_visual.py`:
  - it starts with `pytest.importorskip("playwright")`;
  - it is marked `visual`, and a new `--visual` option in `tests/conftest.py` mirrors
    `--live`: the tests are skipped unless the flag is given.
- **Server fixture.** It runs uvicorn in a background thread on `127.0.0.1:<free port>`,
  with `get_db` overridden to a **seeded** in-memory SQLite (`StaticPool`). The seed is a
  fixed set: postings in every status, Arabic and very long employer names, a filtered-out
  posting, three runs (running, success, failed), two profiles, one blacklisted employer
  and source health. Posting dates are relative to seed time, so "2d ago" is stable.
- **Matrix.** 11 pages × {375×812, 1280×800} × {light, dark}, using
  `page.emulate_media(color_scheme=…)`. Every page is a full-page screenshot with
  `animations="disabled"`, taken after `document.fonts.ready`.
- **Masks.** `.last-run` (the time) and any other render-time value found in the first run.
- **Baselines.** Stored under `app/tests/__snapshots__/test_visual/` and committed. They are
  captured on `006-1` **before** `input.css` exists, while `app.css` is byte-identical to
  `49de3dd`. They are only regenerated by a recorded decision (FR-003).
- **Platform.** Windows only (spec Assumptions). Snapshot paths include the platform, so a
  stray Linux run will not compare against Windows baselines.

**Rationale.** Clarification Q2. Research summary: `toHaveScreenshot()` exists only in
the JS runner, so pytest needs a plugin. Of the two maintained plugins,
`pytest-playwright-visual-snapshot` has config-level masks, which this page set needs.

**Alternatives.**
- **`pytest-playwright-visual` 2.1.2.** Also maintained, also uses pixelmatch, but masks
  are per call only. Kept as the fallback if the chosen plugin stalls.
- **Hand-rolled Pillow and pixelmatch.** Rejected: it would reimplement what the plugin
  already does.
- **Comparing by eye.** Rejected in Q2.

## R8 — Class coverage, token presence and source-path tests (stdlib only)

**Decision.** A new file, `app/tests/test_css_build.py`. It needs no binary and no new
dependency (clarification Q1, revisited).

- **Rendered classes ⊆ built classes.**
  - Render the 11 pages and the two htmx fragments (C-1 and C-2, posted with
    `HX-Request: true`) through the existing in-memory `TestClient` fixture. The bulk
    response (C-3) is the postings page and is covered by it.
  - Collect `class` attribute tokens with `html.parser`.
  - Extract defined class selectors from the minified `app.css` with
    `re.finditer(r"\.((?:\\.|[A-Za-z0-9_-])+)", css)` and unescape `\:` `\/` `\[` `\]`
    `\.` `\%` `\#`.
  - Assert that the difference is empty, apart from the documented hook-only allowlist
    ([contracts/class-contract.md](contracts/class-contract.md) §3).
- **Tokens present.** Every `--name:` declared in `input.css` `:root` blocks appears as a
  declaration in `app.css`.
- **Sources exist.** Every `@source "…"` path in `input.css` resolves, relative to
  `input.css`, to an existing directory.

The existing `test_design_tokens.py` changes one line: `CSS = …/web/styles/input.css`. Its
regexes match the authored layout, which is the moved-verbatim §1.

**Rationale.** FR-010, FR-013, SC-005. A regex over a single minified file is enough for
selectors. The hand-written format of `input.css` is under the project's control.

## R9 — Status class mapping (Phase 2)

**Decision.** Each status family gets one Jinja dict in `_macros.html` that maps the status
to a complete utility string. Families are posting status, run status and banner kind.
There is a `_neutral` fallback. The `pill` and `banner` hook classes stay first in the
class list, as FR-019 requires. The exact strings are in
[contracts/class-contract.md](contracts/class-contract.md) §2. `base.html`'s last-run pill
and `index.html`'s distribution pills already go through `status_pill()` or are switched to
it in step 3.1, so no template keeps `pill {{ status }}`.

**Rationale.** FR-018. The scanner sees literal strings in `_macros.html`.

## R10 — Data-driven styles that stay inline

**Decision.** Bar heights (`style="height: N%"` in `index.html`, `runs.html` and
`reports/sources.html`), the pie `conic-gradient` and legend dots
(`reports/profiles.html`, `var(--token)` strings) stay inline. The striped zero bar, the
pie geometry and the tab-strip fade are the documented one-offs that remain as small
custom rules after Phase 3 (FR-021, FR-022).

## R11 — Constitution III amendment and ADR-0022

**Decision.**
- ADR-0022, "Styling with Tailwind v4 via the standalone CLI", supersedes ADR-0021. ADR-0021
  gets `Status: superseded by ADR-0022`. The `Docs/README.md` index gets a new row, and
  0021's row is updated.
- The ADR states the amended principle III: *"One language at runtime, server-rendered. A
  build step is permitted only for authored assets, only if it needs no Node, and only if
  its output is committed, so that the image, the runtime and the tests stay build-free."*
- It is drafted in `006-1` with **Status: proposed**, and **accepted** in `006-4` (FR-023).
- `.specify/memory/constitution.md` is an unfilled template and gitignored, so it is not
  edited.
- `Docs/tech-stack.md`'s "one language end to end" line gets a pointer to ADR-0022.

## Sources

- [pytailwindcss on PyPI](https://pypi.org/project/pytailwindcss): `TAILWINDCSS_VERSION`
  and `tailwindcss_install`.
- [Tailwind v4 alpha post](https://tailwindcss.com/blog/tailwindcss-v4-alpha):
  `--color-*: initial` and split imports.
- [tailwindcss discussion #17826](https://github.com/tailwindlabs/tailwindcss/discussions/17826):
  `@theme` vs `@theme inline` output.
- [tailwindcss discussion #19367](https://github.com/tailwindlabs/tailwindcss/discussions/19367):
  source detection and omitting Preflight.
- [camoa v4 configuration guide](https://camoa.github.io/dev-guides/design-systems/tailwind/v4-configuration):
  `@source inline` safelisting.
- [dev.to: `@theme` vs `@theme inline` gotcha](https://dev.to/forrestmiller/tailwind-v4-dark-mode-the-theme-vs-theme-inline-gotcha-that-broke-my-contrast-tests-3p3o).
- [pytest-playwright-visual-snapshot](https://pypi.org/project/pytest-playwright-visual-snapshot)
  and [its release feed](https://pypi.org/rss/project/pytest-playwright-visual-snapshot/releases.xml).
- [pytest-playwright-visual 2.1.2](https://pypi.org/project/pytest-playwright-visual/2.1.2/).
- [Martin Fowler, Test-Driving HTML Templates](https://www.martinfowler.com/articles/tdd-html-templates.html).
