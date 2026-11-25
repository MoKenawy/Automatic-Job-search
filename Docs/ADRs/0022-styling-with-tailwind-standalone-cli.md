# ADR-0022: Styling with Tailwind v4 through the standalone CLI

* Status: proposed (22 November 2026); to be accepted when Phase 3 of feature 006 lands
* Deciders: Mohammed
* Date: 22 November 2026
* Supersedes: [ADR-0021](0021-ui-styling-hand-written-tokens.md)

Technical Story: feature 006 (`specs/006-tailwind/`). Decisions and alternatives are in
`specs/006-tailwind/research.md` (R1 to R11).

## Context and Problem Statement

ADR-0021 chose one hand-written stylesheet and rejected the Tailwind standalone CLI (its
option B), mainly because of the build step, the binary and utility-heavy templates. That
trade has changed. The Stitch design target is written in Tailwind utilities, so every
design iteration is a manual translation into bespoke CSS, every new layout grows the
stylesheet, and nothing checks that tokens are applied consistently.

## Decision

Adopt Tailwind v4 through its standalone CLI, with no Node:

- `pytailwindcss` in the `dev` dependency group fetches a checksum-verified binary. The
  version is pinned in `app/pyproject.toml` (`[tool.app.tailwind] version`, currently
  `v4.3.5`), the only place the pin is recorded.
- The authored source is `app/src/app/web/styles/input.css`. The generated, minified
  `static/css/app.css` is **committed**; `uv run python scripts/build_css.py` rebuilds it.
- CI rebuilds it and fails when the committed copy differs. The container image runs
  `uv sync --no-dev` and never builds CSS. The test suite needs no binary.
- DESIGN.md tokens stay defined once on `:root` and are exposed to utilities through an
  inline theme mapping. The default Tailwind palette is discarded.
- Migration is phased (0 setup, 1 hybrid, 2 utilities, 3 cleanup). Each phase is gated by an
  opt-in pixel comparison (`pytest --visual`) against baselines captured on `49de3dd`.

### Amendment to constitution principle III

> One language at runtime, server-rendered. A build step is permitted only for authored
> assets, only if it needs no Node, and only if its output is committed, so that the image,
> the runtime and the tests stay build-free.

(`.specify/memory/constitution.md` is an unfilled, gitignored template in this checkout; this
record is where the amendment lives.)

## Consequences

* Positive: design iterations translate directly; token use is checkable; the cost stays
  local and recurring-cost free.
* Negative: a maintainer-side build step and binary; generated file in the diff (marked
  `linguist-generated`); class names that are also Tailwind utilities (for example `inline`)
  collide with components and must not be used as bespoke class names.
* Neutral: runtime, image and default tests are unchanged.
