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

## Step 007-3 gate: Postings, 2026-11-25

| Check | Result |
|---|---|
| `uv run pytest` | 817 passed, 46 skipped (74 new in `tests/test_status_counts.py`) |
| ruff check / format | clean |
| `uv run pytest --visual` | 44 of 44 after re-baselining the 4 `postings` snapshots |
| First load: `app.css` 34,256 + font 48,256 + icons 13,596 + htmx 50,387 | 146,495 bytes (budget 150 KB) |

### Decisions (maintainer, recorded in spec D6, D7)
- **D6**: row triage actions are icon-only (amends 004 FR-017 for list rows).
- **D7**: tab counts follow the active filters, which needs one backend read path.

### Backend
- `queries._query_filters` holds the search, location, source and published conditions, used by
  both `list_postings` (unchanged behaviour) and the new `queries.status_counts`.
- `status_counts` runs two queries: a `GROUP BY status` over the visible queue and one count over
  the filter's review bucket. The status axis is not applied, so each tab counts what it opens.
- `tests/test_status_counts.py` checks, for all 72 combinations of the query axes, that every tab
  count equals `list_postings(...).total` for that tab, plus two hand-counted cases (blacklisted
  and filtered-out postings excluded from the queue).

### What changed on the page
- Tabs carry a `count_badge` that inverts on the selected tab.
- Filter bar: search with a leading icon, selects and a primary Search button on one line;
  labels are visually hidden (still associated).
- Bulk bar: tinted strip; options read "Set to …"; Apply is a secondary button.
- Table: one "Title & company" column with an initial tile; neutral score badge ("—" when
  unscored); location chip (globe icon when remote); board tags (LinkedIn primary tint, Indeed
  tertiary tint); "Status & triage" column.
- Row control (`_row_status.html`): icon-only ghost buttons, `aria-label` and `title`
  "Set status to …"; the status pill stays as text; kept on one line. Contract C-1 unchanged
  (id, hx-post/target/swap/disabled-elt, field names and order); `tests/test_web_triage.py`
  passes untouched.
- Pager moved into the table footer: "Showing a–b of N · Page x of y" and ghost page buttons
  with first/last, ellipses and Prev/Next.
- `btn_class` gains an `icon` size (32 px square).

### Re-baselined snapshots
`postings` × 4. Reviewed `postings-1280-light`, `postings-1280-dark`, `postings-375-light`. The
visual seed has one page only, so the multi-page pager is covered by `test_web_triage.py`
("Page 1 of 2", "Page 2 of 2"), not by pixels.

## Step 007-4: Reports index

- `reports/index.html`: `card_hover` rows with `icon_tile`, real stat badge (postings/employers, boards, active profiles), decorative CSS thumbnail (`aria-hidden`), "View report" link; pipeline summary panel (distinct rate, average run time, scoring model) from `recent_runs(30)` and settings. Route adds context from `queries.totals`, `known_sites`, `profile_store.list_enabled`, `recent_runs`. New sprite icon: `monitoring`.
- Dropped: time-range control, latency/telemetry mock values (D3).
- Re-baselined: `reports` x 4 (index page redesign). Detail report pages unchanged in pixels.
- Gate: pytest, ruff, CSS build, `--visual` all green after re-baseline.
- Environment note: Playwright chromium had to be reinstalled locally (`uv run playwright install chromium`).

## Step 007-5: Blacklist

- Count badge in the header action slot; two `stat_card`s (`domain`, `visibility_off`); `initial_tile` employer rows; "N postings hidden" badge with icon; primary-colour Restore button (same POST form, `return_to` unchanged); footer "Showing N blacklisted employers"; FR-013 note as a callout panel (wording unchanged); empty state gets an icon.
- Not built (D4): add form, reason/date columns, export.
- Re-baselined: `blacklist` x 4. Gate: pytest, ruff, CSS build, `--visual` all green.

## Step 007-6: Schedules

- "Run settings" moved to a header action button (`tune`); "Profiles" section header with "N active" badge; location icon chip (`public` when remote); site `tag`s; runs-at monospace chip with the timezone; pill toggle (still a submit button with `role="switch"`/`aria-checked`, text Active/Paused); Run now (primary) and Delete (error) ghost buttons via new `btn_class` variants `ghost-primary`/`ghost-error`.
- Add form: section header with `add_circle`, tinted sites group, monospace regex inputs, tinted action bar with Save (`save` icon) and compact hour/minute inputs. Field names, ids and hint text unchanged.
- Not built: sync/throttle/storage strip, keyboard-shortcut hints, Glassdoor (D3).
- Re-baselined: `profiles` x 4. Gate: pytest, ruff, CSS build, `--visual` green.

## Step 007-7: Settings

- Section headers with `tune` / `filter_alt`; right-aligned rule hints from `services/settings.py` (int > 0, ≥ 0, 0–100, regex, one per line); unit suffixes inside inputs (items, hours, sec, score; decorative, `aria-hidden`); tinted taller inputs; monospace regex and proxies fields; LinkedIn checkbox in a tinted callout with one explanatory line (restates the seniority dependency already stated on the page); Save with `save` icon; read-only panel with uppercase keys and semibold values (`database_url` still "hidden — environment only").
- Number input `step` left at the browser default, so validation behaviour is unchanged.
- Not built: Reset to defaults, Export JSON, Audit log, slider, sync strip, inference ping (D3/D4).
- Re-baselined: `settings` x 4. Gate: pytest, ruff, CSS build, `--visual` green.

## Step 007-8: Runs

- Per-source trend: one card with a trend heading and "Last N runs" badge; per-board panels with initial tile, "Run #N: X postings" badge, bars with value above and run id below, newest bar highlighted and outlined ("now"), older bars in a lighter primary tint, striped zero bar kept, "vs previous run" delta kept, sr-only list unchanged. Run ids come from `health.runs`, which is aligned with `health.series`.
- History: section header and subtitle; `whitespace-nowrap` on # and Started; rejected count in error colour when above 0; newest row tinted with a primary left accent; monospace by-source text separated with "·"; error row gets an `error` icon; footer "Showing N recent runs".
- Not built: JSON export, filter button, trigger button, throttle status (D3/D4).
- Re-baselined: `runs` x 4. Gate: pytest, ruff, CSS build, `--visual` green.
