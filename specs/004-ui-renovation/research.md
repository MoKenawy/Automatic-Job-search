# Research: UI renovation (004)

Each entry gives the decision, the rationale, and the alternatives that were rejected. R1–R5
record the **dependency declaration** that the operator approved on 2026-11-19 (gate 1 of
the brief). Nothing outside it may be added without amending this file first.

---

## R1 — Styling approach: hand-written CSS custom properties

**Decision.** Define the design tokens once as CSS custom properties in a static
stylesheet, `web/static/css/app.css`, and write the components by hand with semantic class
names. Move the CSS that is inline in `base.html` today into that file. There is no build
step and no runtime compilation. Recorded in
[ADR-0021](../../Docs/ADRs/0021-ui-styling-hand-written-tokens.md).

**Rationale.**

- It adds no dependencies and no build stage in Docker or CI (constitution III).
- It continues how `base.html` already works: tokens plus about 150 lines of components.
- Semantic classes keep the markup readable, along with the htmx contracts and the text
  that tests assert ([contracts/](contracts/)).
- The token set (about 45 roles plus a dark palette) and roughly 30 components fit
  comfortably in about 25 KB.

**Alternatives rejected.**

- **(b) Tailwind standalone CLI.** It's a platform-specific binary of about 40 MB. It needs a
  build step, and the generated CSS would either be committed to the repo or built in a
  Docker stage. It also pushes the templates toward utility-class markup copied from Stitch.
- **(c) Pico CSS or Open Props.** Either one is a new dependency whose defaults fight the
  DESIGN.md tokens.
- **Keep the CSS inline in `base.html`.** It would be re-sent with every page and could not
  be cached. A static mount is needed anyway (R5).
- **Tailwind Play CDN, as in the Stitch exports.** It is a development-only compiler that
  runs in the browser, and it makes a third-party request (constitution II).

## R2 — Typeface: self-hosted Inter, variable, Latin subset

**Decision.** Use `@fontsource-variable/inter@5.3.0` (OFL-1.1), taking two files:
`inter-latin-wght-normal.woff2` (48.3 KB) and `inter-latin-ext-wght-normal.woff2`
(85.1 KB). Both are served from `web/static/fonts/`, with `font-display: swap` and a
`unicode-range` on each, so the latin-ext file downloads only when a page contains those
glyphs. Arabic and other scripts fall back to the system font stack. SHA-256 checksums are
recorded at vendoring time in `web/static/VENDORED.md`.

**Rationale.** DESIGN.md sets the whole interface in Inter, and the brand guide agrees for
UI text. One variable file covers weights 400–700, where four static files would otherwise
be needed. Self-hosting satisfies constitution II.

**Alternatives rejected.**

- **Google Fonts, as in the Stitch exports.** A third-party request.
- **Four static weights.** About 90 KB for the Latin subset alone.
- **The system font stack.** Off-design.
- **Montserrat for headings, as the brand guide asks.** DESIGN.md wins (spec C2).

## R3 — Icons: a Material Symbols Outlined SVG sprite

**Decision.** Vendor individual SVGs from `@material-symbols/svg-400@0.48.3` (Apache-2.0,
published 2026-11-04) into a single sprite, `web/static/icons.svg`, made of `<symbol>`
elements. A Jinja macro, `icon(name, label=None)`, renders
`<svg aria-hidden="true"><use href="/static/icons.svg?v=…#name"></svg>`. When a label is
given, it renders a visually hidden label instead of `aria-hidden`.

The SVGs are drawn with `fill="currentColor"`, so they follow the text colour and the dark
theme.

**Glyph set.** About 20 glyphs, at about 0.5 KB each:

| Group | Glyphs |
|---|---|
| Status actions | `fiber_new`, `check_circle`, `send`, `cancel` |
| Navigation and actions | `block`, `undo`, `play_arrow`, `delete`, `search`, `expand_more`, `arrow_forward`, `open_in_new`, `settings` |
| Status indicators | `info`, `warning`, `error`, `schedule`, `lock`, `check` |

`progress_activity` is for the busy state. Any glyph from this package and version is within
the approved declaration. Each glyph's presence in 0.48.3 is checked at vendoring time.

**Alternatives rejected.**

- **The Material Symbols web font, as in the Stitch exports.** Over 300 KB, and it is a
  third-party request.
- **Text-only actions.** Slower to scan, and FR-017 asks for an icon plus a label.
- **Another icon set (Lucide, Heroicons).** It would diverge from the mock-ups for no gain.
- **0.49.0.** Only 7 days old at the time of the declaration. Supply-chain hygiene prefers a
  release at least two weeks old.

## R4 — htmx: kept at 2.0.3, vendored

**Decision.** Vendor `htmx.org@2.0.3/dist/htmx.min.js` (0BSD; 50,387 bytes, 16.2 KB gzipped)
as `web/static/vendor/htmx-2.0.3.min.js`. It is loaded with a `defer`-free `<script>` in
`<head>`, as today, so htmx is ready before the inline scripts run. Its SRI hash is
`sha384-0895/pl2MU10Hqc6jd4RvrthNlDiE9U1tWmX7WRESftEDRosgxNsQG/Ze9YMRzHq` and is set as
`integrity=`.

**Rationale.** Today's `unpkg.com` request sends the operator's IP and referrer off the
machine, and fails when offline (constitution II). Keeping the same version avoids any
behaviour change.

**Alternatives rejected.**

- **Keep the CDN.** Violates constitution II.
- **Upgrade to 2.0.11.** That's a behaviour change, out of scope for a presentation feature.

## R5 — Static file serving and cache-busting

**Decision.** Add one line to `web/app.py`:

```python
app.mount("/static", StaticFiles(directory=…/static), name="static")
```

`StaticFiles` comes from Starlette 1.3.1, which is already installed through FastAPI 0.139.2.
It needs no `aiofiles`. Asset URLs carry `?v={{ asset_version }}`. `asset_version` is a Jinja
global, computed once at import as a short hash of the static files' modification times, so
a deploy invalidates the browser cache. Starlette's `StaticFiles` already sends `ETag` and
`Last-Modified`.

**Packaging.** Hatchling already includes every non-ignored file under `src/app` (that is how
templates ship today), and the Dockerfile runs `COPY . .`. Neither needs changing.

**Alternatives rejected.**

- **Inline everything (data URIs, inline CSS).** Can't be cached, and pages grow by about
  130 KB each.
- **A reverse proxy for static files.** That's a deployment change, and the app has none.

---

## R6 — Token source and conflict resolution

**Decision.** The DESIGN.md YAML front-matter is the token source. Each role becomes a CSS
custom property with the same name (`--surface`, `--on-surface`, `--primary-container`, …),
plus a type scale (`--fs-headline-lg`, …), spacing (`--space-*`), radii (`--radius-*`) and
elevation (`--shadow-1…3`, taken from the DESIGN.md prose). Templates use semantic
component classes only. FR-005 is enforced by a test that greps templates for `#[0-9a-f]{3,8}`
and for `rgb(` (R12).

The spec records the resolutions (C1–C9), and the measurements below add two more.

- **C10 (new) — the success green fails as text.** The brand's `#1E8E3E` gives 4.21:1 on
  white and 3.99:1 on `surface`, which is below 4.5:1. **Resolution:** green is used only for
  non-text indicators (dots and icons, where ≥3:1 passes). Success text uses
  `--on-success-container: #0d5323` on `--success-container: #e6f4ea`, which gives 8.12:1.
- **C11 (new) — `outline-variant` is too faint for control borders.** `#c3c6d7` is about
  1.7:1 against white, but the boundaries of inputs, checkboxes and selects need ≥3:1
  (WCAG 1.4.11). **Resolution:** control boundaries use `--outline` (4.50:1 on white).
  `--outline-variant` is used only for decorative hairlines between rows and cards, which
  1.4.11 does not cover.
- **C12 (new) — `on-secondary-container` retargeted.** The YAML value `#5c647a` is replaced
  by `#3f465c` (the YAML's own `on-secondary-fixed-variant`) so text on `secondary-container`
  (new-status pill, score badge, info banner) keeps comfortable AA headroom.
- **C13 (new) — `code` is monospace.** DESIGN.md `code-sm` is Inter 12/16, but regexes and
  paths are ambiguous in a proportional face, so `code` uses a system monospace stack at the
  same size. This is a deliberate, local divergence from the token file.
- **C14 (new) — the page title grows with the viewport.** `h1` is `--fs-lg` (24 px) on
  mobile and `--fs-xl-mobile` (28 px) from 768 px, and KPI figures are 24 px on mobile and
  `--fs-xl` (36 px) from 768 px, so the figure outranks the title.

### Measured contrast, light palette (DESIGN.md YAML)

| Foreground \ background | `surface` #faf8ff | `container-lowest` #fff | `container` #ededf9 | `container-high` #e7e7f3 |
|---|---|---|---|---|
| `on-surface` #191b23 | 16.31 | 17.18 | 14.79 | 14.01 |
| `on-surface-variant` #434655 (muted text) | 8.88 | 9.35 | 8.05 | 7.62 |
| `outline` #737686 (borders only) | 4.27 | 4.50 | 3.88 | 3.67 |
| `primary` #004ac6 (links, active tab) | 7.13 | 7.51 | 6.47 | 6.13 |
| `error` #ba1a1a | 6.13 | 6.46 | 5.56 | 5.27 |

Filled primary button: `on-primary-container` (#fff) on `primary-container` #2563eb gives
**5.17**. The DESIGN.md prose sets the fill at #2563EB, and the YAML's `primary` (#004ac6)
gives a **7.51** link colour.

## R7 — Dark palette (derived)

**Decision.** DESIGN.md defines a light scheme only. The dark scheme is derived the way
Material 3 derives one from the same key colour, anchored on the roles DESIGN.md already
gives: `inverse-surface`, `inverse-on-surface`, `inverse-primary`, `primary-fixed-dim`,
`tertiary-fixed-dim`. It is applied under `@media (prefers-color-scheme: dark)`, as today.

| Role | Dark value | Derived from |
|---|---|---|
| `surface` | #121318 | M3 neutral tone 6 |
| `surface-container-lowest` / `low` / ∅ / `high` / `highest` | #0c0e13 / #1a1b21 / #1e1f25 / #282a2f / #33353a | M3 neutral tones 4 / 10 / 12 / 17 / 22 |
| `on-surface` | #e2e2e9 | Close to `inverse-on-surface` |
| `on-surface-variant` | #c3c6d7 | Light `outline-variant` (tone 80) |
| `outline` / `outline-variant` | #8d90a0 / #434655 | Tone 60 / light `on-surface-variant` |
| `primary` | #b4c5ff | `inverse-primary` / `primary-fixed-dim` |
| `primary-container` / `on-primary-container` | #2563eb / #ffffff | Unchanged; 5.17 |
| `error` / `error-container` / `on-error-container` | #ffb4ab / #93000a / #ffdad6 | M3 error tones |
| `success` / `success-container` / `on-success-container` | #7dd99a / #0d3b1e / #b7f0c8 | Brand green, lightened and darkened |

The lowest contrasts measured in dark mode are `outline` on `container-high` (4.53) and
`on-surface` on `container-high` (11.14). Every text pair is ≥8.4:1.

## R8 — Last-run status on every page (spec FR-013, clarification Q1)

**Decision.**

1. Add a read-only helper, `queries.latest_run(session) -> Run | None`, to
   `services/queries.py`.
2. Add an app-level FastAPI dependency, `web.deps.shell_context`. It depends on `get_db`
   (so the test override still applies) and stores the latest run on `request.state`.
3. Register a Jinja2 context processor (`Jinja2Templates(context_processors=[…])`, supported
   by Starlette 1.3.1) that exposes it to every template as `shell.last_run`.
4. `queries.totals()` is left untouched.

**Rationale.** FastAPI caches a dependency per request, so the shell shares the request's
session. `get_db` stays the single place a session is created, which keeps the
dependency-override fixtures in `test_web*.py` working. A context processor that opened its
own `SessionFactory()` would bypass those overrides and hit the real database during tests.

**Deviation to note.** At clarification time the change was described as "no service
change". `latest_run` is a new read-only function. It changes no existing service's
behaviour, and it keeps query logic out of `web/` (constitution IV).

**Alternatives rejected.**

- **Call `queries.totals(db)` on every page.** That's five aggregate queries per request to
  read one row.
- **Query from `web/deps.py` directly.** Puts query logic in the web layer (constitution IV).
- **Add the run to each route's context.** That's 13 route edits instead of one dependency.

**Excluded paths.** `/healthz` and `/static` don't render templates. The dependency is
attached to the routers and the index route, not to the whole app, so `/healthz` makes no
extra query.

## R9 — Busy state, double-submit and error feedback for htmx actions (FR-020)

**Decision.** Use only htmx's built-in features:

- `hx-disabled-elt="find button"` on each status form and the bulk form, so the triggering
  button is disabled while the request is in flight.
- The `htmx-request` class drives a CSS spinner, which is static under
  `prefers-reduced-motion`.
- `aria-busy="true"` is toggled by htmx's `htmx-request` hook in a small inline listener.
- One inline listener in `base.html` handles `htmx:responseError` and `htmx:sendError`. It
  writes "Couldn't update — nothing changed. Try again." into the shell's polite live region.

**Rationale.** htmx 2.0.3 supports `hx-disabled-elt`. Today a 4xx response swaps nothing, so
the failure is silent, and the spec's edge case requires it to be announced. Constitution III
allows small inline scripts where htmx cannot do the job.

**Contract impact.** These are attribute *additions*. Ids, targets and swaps are unchanged
([contracts/htmx-fragments.md](contracts/htmx-fragments.md)).

## R10 — Tab strip below 768 px (FR-019)

**Decision.** The navigation is a `<nav aria-label="Primary">` holding a list.

- Below 768 px the list gets `overflow-x: auto; flex-wrap: nowrap;
  scroll-snap-type: x proximity`, and edge fades show there is more to scroll.
- A three-line inline script calls `scrollIntoView({inline: "nearest", block: "nearest"})` on
  the link with `aria-current="page"` once the page has loaded. CSS alone cannot set an
  initial scroll position.
- Without scripting, the row still scrolls, starting at Overview.

## R11 — Blacklist page "Remove" (FR-016, clarification Q3)

**Finding, confirmed by reading the code.** The Remove form in `blacklist.html` carries
`hx-post` with no `hx-target`. htmx 2 defaults to `innerHTML` on the form itself. It follows
the 303 redirect to `/blacklist` and swaps the body of that page into the form, so a second
header, nav and table appear inside the table cell. No test covers it, because
`test_blacklist.py:146` posts without `HX-Request`.

**Decision.** Remove `hx-post`. The form becomes a plain POST with the same `action` and
`return_to` field, like the detail page's blacklist forms. Add a test that checks the
Blacklist page markup contains no `hx-post`, pinning the contract.

## R12 — Automated checks for the quality bar

**Decision.** Use three pure-pytest modules. No new packages.

1. **`tests/test_design_tokens.py`** parses `app.css`. It extracts the light and dark `:root`
   blocks, then asserts every pair listed in a `PAIRS` table, against the WCAG 2.x relative
   luminance formula:
   - text pairs ≥4.5
   - large text and UI pairs ≥3.0
   - focus ring ≥3.0 against both `surface` and `surface-container-lowest`

   This covers SC-002.
2. **`tests/test_web_assets.py`** checks that:
   - every template is free of hex colours and `rgb(`;
   - every page response is free of `http://` or `https://` URLs in `src=` or `href=` for
     scripts, styles and fonts;
   - `/static/vendor/htmx-2.0.3.min.js` returns 200 and matches the recorded SHA-384;
   - the total size of the first-load assets is ≤150 KB.

   This covers SC-005, SC-007 and SC-009.
3. **`tests/test_web_a11y_markup.py`** checks markup-level rules on every page:
   - exactly one `aria-current="page"`;
   - every `<input>`, `<select>` and `<textarea>` has a `<label for>` or an `aria-label`;
   - every `<table>` has `<th>` cells with `scope`;
   - every icon `<svg>` is either `aria-hidden` or labelled;
   - an `aria-live` region exists;
   - a skip link exists.

   It uses `html.parser` from the standard library. This covers part of SC-004 and FR-008.

**Not automatable here, so checked manually and recorded in `verification.md`:**

- the viewport checks at 375, 768 and 1280 px (SC-003);
- the keyboard-only flows (SC-004);
- an inspection of the network log (SC-005, confirmed in a browser).

## R13 — Relative posting age ("2d ago")

**Decision.** Add a Jinja filter, `relative_age(date, now)`, registered on `TEMPLATES.env`,
in a new pure module `web/formatting.py`.

- It renders "today", "1d ago", "6d ago", "3w ago", or, beyond 60 days, the absolute date.
- It is wrapped in `<time datetime="…" title="18 Nov 2026">`, so the exact date stays
  available.
- `now` is passed in from the template (`shell.now`, set by the context processor) so that
  tests are deterministic.
- It has a unit test of its own.

## R14 — Brand logo

**Decision.** Until the master SVGs arrive, the header shows the wordmark as text: "Job" in
semibold `on-surface` and "discovery" in `primary`, both in Inter, with no signal mark (spec
C6, FR-015). When the files arrive, they go in `web/static/brand/` (primary and reversed),
and a `<picture>` element switches to the reversed file through
`media="(prefers-color-scheme: dark)"`. That needs no amendment, because the files are
brand-owned, not third-party.

## R15 — Payload budget (SC-009)

| Asset | Bytes | First load | Cached after |
|---|---|---|---|
| `app.css` (measured) | 26,645 | yes | yes |
| Inter latin variable woff2 | 48,256 | yes | yes |
| Inter latin-ext woff2 | 85,068 | only if needed | yes |
| `icons.svg` (20 glyphs, measured) | 7,387 | yes | yes |
| htmx 2.0.3 | 50,387 | yes | yes |
| **Total, first load** | **132,675** | | |

The ≤150 KB budget in SC-009 covers the "yes" rows. `test_web_assets.py` enforces it against
the real file sizes.
