# ADR-0021: Styling the triage interface — hand-written design tokens, self-hosted assets

* Status: accepted (19 November 2026)
* Deciders: Mohammed
* Date: 19 November 2026

Technical Story: feature 004 (`specs/004-ui-renovation/`) brings the triage interface in
line with an approved design package. The Stitch mock-ups in that package are written in
Tailwind utility classes, compiled in the browser by the Tailwind Play CDN. They load Inter
and Material Symbols from Google Fonts. None of that can ship as it is. This record chooses
how the interface is styled instead, and where its assets come from.

## Context and Problem Statement

The interface is server-rendered Jinja2 with htmx (ADR-0004). Today all of its CSS is about
150 lines inline in `base.html`. It uses the system font stack, has no icons, and loads htmx
2.0.3 from `unpkg.com`.

The design package brings three things:

- a token file, `technical_precision/DESIGN.md`, with about 45 colour roles, an Inter type
  scale, spacing, radii and elevation;
- a typeface;
- an icon set.

Three constraints bind the choice:

- **Nothing ships data off the machine** (`tech-stack.md` §2). A CDN request from the browser
  sends the operator's IP and referrer out, and fails offline. Today's `unpkg.com` htmx tag
  already breaks this rule.
- **One language, no build step** (`tech-stack.md`). There is no Node toolchain in the image
  or in CI.
- **The markup is a contract.** htmx ids, targets and form field names, and the text that
  tests assert, live in the templates. A styling approach that rewrites the templates into
  utility-class soup makes those contracts harder to see and keep.

## Decision Drivers

- No new runtime or build dependency unless it pays for itself.
- No runtime CSS compilation. No third-party requests.
- The tokens are defined once and used everywhere: no literal colours in templates, with light
  and dark palettes.
- Templates stay readable enough that the htmx and form contracts stay visible.

## Options considered

**A. Hand-written CSS custom properties.** Translate the DESIGN.md tokens into custom
properties in one static stylesheet. Write components with semantic class names.
- Zero dependencies and no build. It is how `base.html` already works.
- Costs: hand-writing about 25 KB of CSS, and keeping it consistent with DESIGN.md by
  review rather than by generation.

**B. Tailwind standalone CLI.** A Node-free binary compiles a stylesheet from the templates.
- Close to the Stitch markup.
- Costs:
  - a roughly 40 MB platform-specific binary;
  - a build step in Docker and CI, with the generated CSS either committed or built in a
    stage;
  - templates rewritten in utility classes;
  - one more tool to pin and update.

**C. A CSS library (Pico CSS, Open Props).**
- Less CSS to write.
- Costs: a dependency whose defaults fight the DESIGN.md tokens. The overrides would be about
  as large as option A.

## Decision

**Option A.** The specifics:

- **Stylesheet.** `web/static/css/app.css` holds the tokens (light, plus a derived dark
  palette under `prefers-color-scheme`) and the components. The DESIGN.md YAML is the source
  of truth (spec 004, conflict C1). A contrast test over the token pairs guards WCAG AA.
- **Self-hosted assets**, served through one `StaticFiles` mount at `/static`:

  | Asset | Version | Licence |
  |---|---|---|
  | Inter, variable, Latin and Latin-ext subsets | `@fontsource-variable/inter@5.3.0` | OFL-1.1 |
  | Material Symbols Outlined, as an SVG sprite of about 20 glyphs | `@material-symbols/svg-400@0.48.3` | Apache-2.0 |
  | htmx, vendored at the same version and pinned by SRI | `2.0.3` | 0BSD |

- **Cache-busting** uses an asset-version query string.

## Consequences

- **Gained.**
  - The interface works offline and makes no third-party requests.
  - No build step and no new Python dependency.
  - About 134 KB is transferred on the first visit and is cached after that.
- **Given up.**
  - The Stitch markup can't be pasted in; each screen is rebuilt in semantic markup.
  - DESIGN.md changes are applied to `app.css` by hand.
- **Obligations.**
  - Vendored files are upgraded deliberately, with their checksums recorded in
    `web/static/VENDORED.md`.
  - The constitution's principle II (no third-party requests) is enforced by
    `test_web_assets.py`.

## Relationship to other records

- [ADR-0004](0004-web-app-replaces-notion.md) established the server-rendered interface. This
  record styles it and does not change its architecture.
- Spec 004's research (`specs/004-ui-renovation/research.md`, R1–R5) holds the measured sizes
  and the full dependency declaration.

## Control

`app/tests/test_design_tokens.py` fails if any token pair falls below its WCAG threshold.
`app/tests/test_web_assets.py` fails if any of these happens:

- a template contains a literal colour;
- a page references an external origin;
- the vendored htmx no longer matches its pinned hash;
- the first-load assets exceed 150 KB.
