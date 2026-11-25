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

## Phase 2 step 3.1 gate (sub-branch `006-3.1`), 2026-11-22

| Check | Result |
|---|---|
| `pytest` | 737 passed, 46 skipped |
| `pytest --visual` | 44 of 44 match |
| ruff, drift (rebuild) | clean; `app.css` 28,749 bytes |

- `_macros.html`: `pill_class` / `banner_class` hold complete utility strings per status family with a neutral fallback; `status_pill` and `banner` use them. Call sites moved onto them: `base.html` (last-run pill), `index.html` (distribution pills, zero-run pill), `detail.html` (blacklisted/filtered pills, error banner), `reports/employers.html`.
- Removed the now-unused `.pill.new/.shortlist/.running/.applied/.success/.rejected/.failed` and `.banner.success/.error` rules (grep clean).
- **Forced colours moved out of `@layer components` into an unlayered block** (R5/FR-020): the new `border-transparent` utility would otherwise beat its `border: 1px solid CanvasText`. Pulled forward from T032.
- **Coverage gap:** the visual seed renders every pill status but not the success/error banners (they appear only after a flash/error), so those two are covered by the class tests and by a one-to-one token translation, not by pixels.
- New tests: status maps name only defined classes; unknown status is neutral; no pill/banner class is concatenated.

## Phase 2 steps 3.2 to 3.7 (sub-branches `006-3.2` .. `006-3.7`), 2026-11-22

Every step passed its own gate: `pytest` 737 passed / 46 skipped, ruff clean, `pytest --visual`
44 of 44, rebuild reproducible. Final `app.css` after 3.7 is in the table below.

| Step | Scope | Notes |
|---|---|---|
| 3.2 | `base.html` shell, tab strip, skip link, wordmark; the shared pill | Label text roles lost their letter-spacing (separate `tracking-label*` tokens) and `--radius` moved into the theme, so `text-label` and `rounded` are exact. Tab-strip fade stays as one commented custom rule. |
| 3.3 | `postings.html`, `_row_status.html`, `_status_control.html`; buttons, chips, icon, empty state, table wrap | `btn_class` / `chip_class` macros. C-1/C-2 fragments differ only in class strings. The old `.statusbox` rule had overridden `.row-actions` (inline-flex, 4px gap); the utilities reproduce that. |
| 3.4 | `detail.html`; cards, banners, metrics, `inline-form` | `card_class`, full-string `banner_class`. The reports caveat banner and settings read-only cards moved with the shared cards/banners. |
| 3.5 | `index.html`; metric/health grids, distribution, bars | Bar heights stay inline. The striped zero bar is the one commented custom rule (the element must not also carry a `bg-*` utility). |
| 3.6 | `runs`, `profiles`, `blacklist`, `settings` | `field_class`, `check_class`, `hint_class` macros; the switch is utilities with `aria-checked:` and `before:` variants. |
| 3.7 | `reports/*` | `.card-link` hover, focus ring and stretched link are `hover:`, `has-[a:focus-visible]:` and `after:` utilities. |
| T032 | Closing checks | Reduced motion moved into `@layer base` (still `!important`); forced-colours block is unlayered (3.1). Checked in a real browser: with `prefers-reduced-motion` the button and pill transition duration is `0s`; with forced colours the pill, chip and score badge borders resolve to `CanvasText`, over the new `border-*` utilities. The focus ring rule is unchanged. |

### Deviations and decisions

- **Rules were deleted as their classes left the markup** (not in Phase 3), because a surviving
  component rule would mask a wrong utility and the pixel gate could not tell. What remains is
  Phase 3's list: element defaults (html, body, headings, p, a, code, main, table, th/td, form
  controls, label, `:focus-visible`), `@keyframes spin`, the two one-offs (`.bars i.zero`,
  `.tab-fade::after`) and the unlayered forced-colours block.
- **Shared components were converted globally in the step that changed their macro**, so some
  templates were touched earlier than their listed step (pills in 3.2, buttons and chips in 3.3,
  cards and banners in 3.4).
- **Hook classes kept** (FR-019): `pill`, `chip`, `banner`, `score-badge`, `icon`, `btn-primary`
  (forced-colours selectors), `skip-link` and `table-wrap` (a11y markup test), `last-run` (visual
  mask), `selrow` (script), `bars`/`zero` (one-off rule). Those with no rule are on the
  `HOOK_ONLY` allowlist in `tests/test_css_build.py`.
- **Changed test assertion** (styling only): `test_web_config.py` found the experience hint by its
  exact class attribute; it now finds it by `id="experience-hint"`.
- **Pixel-exactness traps found by the gate**: `font:` shorthand resets `font-variant-numeric`
  (pill inside a `tabular-nums` parent needs `normal-nums`); a later `.statusbox` rule had
  overridden `.row-actions`; `.num` carried an unrelated `margin-left:auto` rule on the legend;
  a descendant rule (`.metric .metric-label`) never applied in settings.
- **Not covered by pixels**: success/error banners and the htmx busy state are not rendered by the
  visual seed; the `max-sm` (below 640 px) rules differ from the old `max-width: 640px` only at
  exactly 640 px.

## Phase 3 final gate (sub-branch `006-4`), 2026-11-25

| Check | Result |
|---|---|
| `uv run pytest` (no browser, no Tailwind binary) | 737 passed, 46 skipped |
| `uv run ruff check` / `ruff format --check` on `src tests scripts` | clean |
| `uv run pytest --visual` | 44 of 44 match, twice in a row (after the re-baseline below) |
| Drift check (`build_css.py` twice) | reproducible |
| ADR-0022 | accepted |

### Size (SC-004, budget 150 KB)

| Asset | Bytes |
|---|---|
| `app.css` (Phase 0: 28,800; after 3.7: 30,975) | 30,918 |
| `inter-latin-wght-normal.woff2` | 48,256 |
| `icons.svg` | 7,796 |
| `htmx-2.0.3.min.js` | 50,387 |
| **First load** | **137,357 (about 134 KB)** |

`app.css` ends larger than on `49de3dd` because the utilities that replaced the component rules
are emitted once each; it stays within the budget.

### T033: rules removed (FR-015)

Every remaining rule was grepped against templates, macros, the page script and tests. Only the
radio-button selectors had no use (there is no radio input anywhere): the `input[type="radio"]`
margin restore in `@layer base` and its part of the checkbox size rule. Everything else that is
left is on FR-022's list.

### Success criteria

- **SC-005** (no unmapped classes): `tests/test_css_build.py`, green.
- **SC-006** (no colour literals, palette only): `tests/test_web_assets.py` plus `--color-*: initial`, green.
- **SC-007** (contrast, both palettes): `tests/test_design_tokens.py`, green.
- **SC-008** (no other origins): `tests/test_web_assets.py`, green.
- **SC-009** (only documented one-offs remain): what is left in `input.css` is the theme mapping,
  tokens, font faces, `@layer base` (three Preflight restores and reduced motion), element defaults
  in `@layer components` (html, body, headings, p, a, code, `:focus-visible`, main, th/td, table,
  form controls, label, `@keyframes spin`), the two commented one-offs (`.bars i.zero`,
  `.tab-fade::after`) and the unlayered forced-colours block. No bespoke component class rule
  remains. The pie named in FR-022 never needed a rule: it is inline `var(--token)` styles (3.7).

### Re-baselined snapshots (recorded decision, FR-003)

The first full `--visual` run of this gate matched 32 of 44. The same 12 failed with the 006-4
changes stashed, so none came from this phase. The maintainer approved re-baselining exactly these
12 on 2026-11-25:

- **`reports-employers` (4)**: the "days quiet" column read the real clock
  (`app.services.reports.datetime.now`), because the test froze only the shell clock. The baseline
  therefore held numbers from the day it was captured. `tests/test_visual.py` now freezes that
  clock to `ANCHOR` too; the new baseline is deterministic.
- **`settings` (4), `profiles` (4)**: only `<code>` text differs. `code` renders in the system
  monospace font (`ui-monospace, "Cascadia Mono", Consolas`), which changed on the maintainer's
  machine between 22 and 25 November. A system font is outside the stylesheet's control; the
  baselines depend on it until a mono font is self-hosted.

### Changed test code

- `tests/test_visual.py`: freezes `app.services.reports.datetime` as well as the shell clock. No
  assertion changed.
