# Implementation Plan: Tailwind migration of the triage interface's styling

**Branch**: `006-tailwind` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-tailwind/spec.md`

## Summary

Replace the hand-written `web/static/css/app.css` (ADR-0021) with a Tailwind v4 build driven
by the standalone CLI, installed through `pytailwindcss` in the `dev` group. No Node. The
authored source is `app/src/app/web/styles/input.css`; the minified output stays at
`web/static/css/app.css` and is **committed**, so the image, the runtime and the default test
run stay build-free. Delivery is in four phases, each on its own sub-branch and each a valid
resting point, gated by an opt-in Playwright snapshot test (`--visual`) against 44 baselines
captured on `49de3dd`. All technical decisions are in [research.md](research.md) (R1 to R11).

## Technical Context

**Language/Version**: Python 3.12 (uv), CSS (Tailwind v4), Jinja2 templates. No Node.

**Primary Dependencies**: FastAPI, Jinja2, htmx (existing). New, dev only: `pytailwindcss`
(R1). New, group `visual`, opt-in: `pytest-playwright`, `pytest-playwright-visual-snapshot` (R7).

**Storage**: N/A. No schema or data change (FR-001).

**Testing**: pytest (no Docker, no browser, no CSS binary by default). New
`tests/test_css_build.py` (R8, stdlib only); `tests/test_design_tokens.py` re-pointed at
`input.css`; `tests/test_visual.py` behind `--visual`.

**Target Platform**: Windows 11 maintainer machine (visual baselines), Linux CI runner
(drift check), Linux container (serves the committed file).

**Project Type**: Web application (server-rendered), styling toolchain change only.

**Performance Goals**: First-load payload at most 150 KB (SC-004; 004 SC-009).

**Constraints**: Zero visual difference at every gate (SC-001); local-first, no other origins
(FR-005); WCAG 2.2 AA preserved (FR-004); htmx contract frozen (FR-002).

**Scale/Scope**: about 500 lines of CSS, 14 templates (about 1,300 lines), 11 baseline pages,
44 snapshots.

**Pin**: `[tool.app.tailwind] version` in `app/pyproject.toml` is the single source. The tag
is the newest v4.x release at least two weeks old on the day task T-pin runs; it is recorded
here and in ADR-0022 when chosen. Value: *to be recorded in Phase 0.*

## Constitution Check

`.specify/memory/constitution.md` is an unfilled, gitignored template, so there are no
formal gates. The binding rules are `CLAUDE.md` and the ADRs. Checked against them:

| Rule | Status |
|---|---|
| Dependency direction (`web/` reads only; no new runtime deps) | Pass: no Python runtime code changes |
| No direct `os.environ` outside `config.py` | Pass: `build_css.py` sets `TAILWINDCSS_VERSION` for a child process in a dev script, outside `src/app` |
| Tests run without Docker, Node or browser | Pass: new tests are stdlib-only; `--visual` is opt-in |
| htmx contract and `wants_fragment` parity (004) | Pass: markup of fragments unchanged; checked at each Phase 2 step (FR-016) |
| ADR-0021 (hand-written CSS, no build) | **Deviation**, superseded by ADR-0022 (FR-023) |
| "One language at runtime, no build" (principle III / `Docs/tech-stack.md`) | **Deviation**, see Complexity Tracking |

Post-design re-check: no new violations.

## Project Structure

### Documentation (this feature)

```text
specs/006-tailwind/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 output (R1 to R11)
├── quickstart.md        # Phase 1 output: validation guide
├── contracts/
│   └── class-contract.md  # Phase 1 output: hook classes, status maps, allowlist
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output
```

`data-model.md` is intentionally not produced: no data entities are added or changed (spec
Key Entities).

### Source Code (repository root)

```text
app/
├── pyproject.toml                     # + pytailwindcss (dev), visual group, [tool.app.tailwind]
├── scripts/build_css.py               # NEW: the one build entry point (R1)
├── src/app/web/
│   ├── styles/input.css               # NEW: authored source (tokens, @theme, base, components)
│   ├── static/css/app.css             # GENERATED, minified, committed (-diff linguist-generated)
│   └── templates/                     # Phase 1 to 3 edits, group by group
└── tests/
    ├── conftest.py                    # + --visual option (mirrors --live)
    ├── test_design_tokens.py          # CSS path -> styles/input.css
    ├── test_css_build.py              # NEW: class coverage, token presence, @source paths
    ├── test_visual.py                 # NEW: opt-in, importorskip("playwright")
    └── __snapshots__/test_visual/     # NEW: 44 committed baselines
.github/workflows/ci.yml               # + binary cache, drift check after pytest (R6)
.gitattributes                         # + generated-file marker
Docs/ADRs/ADR-0022-*.md, Docs/README.md, Docs/development-guide.md, Docs/tech-stack.md
```

**Structure Decision**: single existing web app; authored CSS moves out of `static/` into
`web/styles/`, output stays at the served path so `base.html` and the Dockerfile are untouched.

### Delivery sequence (FR-027)

| Sub-branch | Phase | Content | Gate |
|---|---|---|---|
| `006-1` | 0 | Baselines first (captured with `app.css` byte-identical to `49de3dd`), then toolchain, `input.css` verbatim into `@layer components`, base-layer restores (R4), CI drift check, tests, ADR-0022 (proposed), docs | 44/44 `--visual`, full pytest, drift check |
| `006-2` | 1 | Hybrid: new layout as utilities, remove helpers (`.visually-hidden`, `.spacer`, `.muted`) after grep (FR-015); record stylesheet size | same |
| `006-3.1`..`3.7` | 2 | `_macros` → `base` → postings + fragments → `detail` → `index` → runs/profiles/blacklist/settings → reports; status maps (R9); macros for 3+ repeats | same, plus fragment parity |
| `006-4` | 3 | Delete dead rules, keep commented one-offs (R10), move a11y overrides per R5, ADR-0022 accepted, final docs | same, budget ≤ 150 KB |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Build step added; amends principle III and supersedes ADR-0021 | Stitch target is utility-based; every design iteration is otherwise a manual translation and tokens are unchecked | Staying on hand-written CSS keeps the translation cost. Node-based tooling rejected (FR-006); the committed output keeps image, runtime and tests build-free |
| New dev dependency group `visual` (Playwright) | The zero-difference gate must be automated to be trusted | Eyeballing was rejected in clarification Q2; the group is opt-in and never installed in CI |
