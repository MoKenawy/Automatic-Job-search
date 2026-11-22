# Verification: Tailwind migration (006)

## Phase 0 gate (sub-branch `006-1`), 2026-11-22

| Check | Result |
|---|---|
| `uv run pytest` (no Node, no browser; the Tailwind binary is not used by tests) | 731 passed, 46 skipped |
| `uv run ruff check` / `ruff format --check` on `src tests scripts` | clean |
| `uv run pytest --visual` | 44 of 44 snapshots match (775 passed, 2 skipped incl. live) |
| Drift check (`build_css.py`, then diff on `app.css`) | reproducible, no diff on a second build |
| Container | `Dockerfile` unchanged and contains no CSS build step |

Pin: Tailwind `v4.3.5` (published 2026-11-06, 16 days before Phase 0), in
`app/pyproject.toml` `[tool.app.tailwind]`.

### Size (SC-004, budget 150 KB)

| Asset | Bytes |
|---|---|
| `app.css` (was 28,604 on `49de3dd`) | 28,800 |
| `inter-latin-wght-normal.woff2` | 48,256 |
| `icons.svg` | 7,796 |
| `htmx-2.0.3.min.js` | 50,387 |
| **First load (latin font; latin-ext loads only on demand)** | **135,239 (about 132 KB)** |

### Deviations from the plan, and why

- **Per-version binaries.** The installed `pytailwindcss` keeps one checksum-verified binary
  per version, so `build_css.py` calls its API with the pinned version (no
  `TAILWINDCSS_VERSION` juggling or reinstall). CI sets `TAILWINDCSS_BIN_DIR` to a cache
  directory instead of caching inside the venv (research R1 and R6 superseded on those points).
- **One class renamed.** `class="field inline"` in `profiles.html` became `field-inline`
  (and its rule). A bare `inline` collides with Tailwind's `.inline` utility, which sits in a
  later layer and overrode the component's `display: flex` (found by the visual gate).
  Classes `selrow` and `info` have no rule on `49de3dd` either and are on the hook-only
  allowlist.
- **Base-layer restores actually needed** (R4 table, confirmed by `--visual`): `svg` display,
  link underline, checkbox/radio margins. The rest of the R4 candidates needed nothing.
- **Visual seed** uses a fixed anchor date and a frozen shell clock so baselines do not drift.
- **Changed test assertions**: none beyond re-pointing `test_design_tokens.py` at `input.css`.

### Not yet done in Phase 0

- Sub-branch PR into `006-tailwind` (opened on request).
- Nothing is committed yet.

## Phase 1 gate (sub-branch `006-2`), 2026-11-22

| Check | Result |
|---|---|
| `pytest` | 731 passed, 46 skipped |
| `pytest --visual` | 44 of 44 match |
| ruff, drift (rebuild) | clean |
| `app.css` size (hybrid baseline) | 28,769 bytes (Phase 0: 28,800) |

- **Helpers removed** after grepping templates, macros, scripts, tests and docs (FR-015): `.visually-hidden` (6 uses → `sr-only`) and `.spacer` (2 uses → `flex-1`).
- **Kept on purpose:** `.muted` and `.small`. `.small` as `text-label` would also set line-height and letter-spacing (not equivalent), and `.big-score .muted` is a selector that depends on the class. Both move with their templates in Phase 2/3.
- **Regrouping:** `input.css` already follows the spec's component order (buttons, chips/pills, cards, tables, forms, shell, feedback, page-specific), so no reorder was done; moving rules inside the layer risks source-order cascade changes for no gain.
- No safelist entry was needed.
