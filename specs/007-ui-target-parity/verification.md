# Verification: UI parity with the Stitch targets (007)

## Step 007-1 gate: shell and foundations, 2026-11-25

| Check | Result |
|---|---|
| `uv run pytest` | 743 passed, 46 skipped (6 new contrast cases for the tertiary tokens) |
| ruff check / format | clean |
| `uv run pytest --visual` | 44 of 44 after the re-baseline below |
| Drift check (`build_css.py` twice) | reproducible |
| First load: `app.css` 32,770 + font 48,256 + icons 7,796 + htmx 50,387 | 139,209 bytes (budget 150 KB) |

### What changed
- **Width**: header, `main` and the new footer share a 90rem maximum (was 80rem).
- **Page title**: h1 is headline-xl from 768 px (was headline-xl-mobile) and headline-xl-mobile
  below (was headline-lg), with −0.025em tracking. Subtitles are body-lg. Titles and subtitles are
  unchanged (D1).
- **`page_header` macro** replaces the 11 hand-written header blocks; a `{% call %}` body becomes
  right-aligned actions (used from 007-6).
- **Last-run link**: a neutral pill with a status dot and "Last run: DD Mon YYYY, HH:MM — Status".
  The status stays in the text. The `pill` hook was removed from it: it is no longer a status pill,
  and `test_pill_and_banner_class_names_are_never_concatenated` forbids `pill` next to a template
  expression.
- **Footer** (FR-003): app version from the package metadata and the configured timezone.
- **Tokens**: `tertiary`, `tertiary-container`, `on-tertiary-container` from DESIGN.md (light) and
  derived dark values; contrast pairs added to `tests/test_design_tokens.py`.
- **Macros added** for the next steps: `card_hover_class`, `badge_class`, `section_header`,
  `icon_tile`, `initial_tile`, `count_badge`, `tag`, `stat_card`.

### Re-baselined snapshots (FR-009)
All 44: every page gains the footer and the wider column, and every h1 grows. Reviewed
`profiles-1280-light` and `index-375-dark` by eye.

### Deferred
- **New sprite icons** move to 007-2, the first step that uses them. They come from the same
  package as the existing 21 (`@material-symbols/svg-400`), which needs a download.
