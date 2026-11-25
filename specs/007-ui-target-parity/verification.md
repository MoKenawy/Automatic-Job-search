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

## Step 007-2 gate: Overview, 2026-11-25

| Check | Result |
|---|---|
| `uv run pytest` | 743 passed, 46 skipped |
| ruff check / format | clean |
| `uv run pytest --visual` | 44 of 44 after re-baselining the 4 `index` snapshots |
| First load: `app.css` 33,960 + font 48,256 + icons 13,596 + htmx 50,387 | 146,199 bytes (budget 150 KB) |

### Icons
Fetched with the maintainer's approval from
`https://cdn.jsdelivr.net/npm/@material-symbols/svg-400@0.48.3/outlined/<name>.svg` (the
package and version ADR-0021 names), into a scratch folder. Each file was checked to be a single
`<path>` with path data only before its `d` was merged into `static/icons.svg` (existing symbols
untouched, alphabetical order kept). Kept, 12: `add_circle`, `description`, `domain`,
`filter_alt`, `hub`, `memory`, `public`, `save`, `trending_up`, `tune`, `visibility_off`, `work`.
Dropped after download to protect the 150 KB budget, because only out-of-scope features would use
them: `bar_chart`, `calendar_clock`, `download`, `link`, `monitoring`, `restart_alt`, `terminal`.

### What changed
- **KPI cards** (`stat_card`): real footnotes only. Postings shows the distinct share across the
  runs in `source_health` (sum of `deduplicated_count` over `collected_count`). Employers shows the
  `known_sites` count. Scored says it is waiting for a CV when nothing is scored. Published shows
  the configured `publish_threshold`.
- **Scoring panel** replaces the info banner: icon tile, the same heading, the CV path from config
  and the scoring model from settings. No upload control (D4).
- **Triage**: one stacked bar, then a legend of dot, status, mini bar, count and percentage. The
  status is the link text, so colour never carries it alone.
- **Source health**: per board an icon tile, name, run count and a large latest value; bars are
  tinted, with the latest at full strength and labelled "#first run … Now". The header badge
  counts boards that returned postings in the latest run.
- **Top of the queue** (new): the first 5 rows of `list_postings`, in the Postings page's own
  order, with an initial tile, metadata, status pill and a Details link that names the posting
  for screen readers. Named for what it shows (the queue order is by score), not "recent".
- `tag` no longer title-cases its text.
- Route context (`web/app.py`): adds `known_sites`, the first page of `list_postings`,
  `publish_threshold`, `scoring_model` and `cv_path`. No new query (D4).

### Re-baselined snapshots
`index` × 4 (light, dark; 375, 1280). Reviewed `index-1280-light`, `index-1280-dark` and
`index-375-light` by eye; the mobile queue rows were reworked after the first review so the text
takes the full width and the pill and button wrap below.
