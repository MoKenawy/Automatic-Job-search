# Plan — spec 007: UI parity with the Stitch target designs (styling only)

## Context
I compared screenshots of the running app (http://localhost:8000, light, 1536px) against the Stitch targets in `Docs/Job Discovery UX&UI/stitch_remix_of_job_discovery_wireframe_login/…/` (plus `technical_precision/DESIGN.md`). The app already uses the right tokens, Inter and the top-nav pattern. It falls short of the targets on layout width, footer, page-header typography, card depth and iconography, and on the richer per-page components: KPI footnotes, stacked triage bar, styled filter bar, icon triage buttons, report cards, toggles and the trend charts.

**Decisions from the user**
- **Page headers:** keep the current titles and subtitles (no eyebrows or new names). Adopt only the target's fonts and colours.
- **Header logo:** keep the current text logo until a real logo exists. Drop the avatar and the decorative terminal/code icons.
- **Real data only:** a target element ships only when the app has a real value for it. Drop mock data such as latency, "Encrypted", PID/node, tok/s, CAPTCHA and schema rev.
- **Styling only:** no new endpoints, DB columns or services. Route handlers may pass extra context **only from existing query functions** (`queries.totals`, `queries.source_health`, `queries.recent_runs`, `queries.list_postings`, `queries.known_sites`, `settings_service.get`, `profile_store.list_enabled`).
  - Out of scope: CSV export, blacklist add-by-name and its reason/date fields, settings reset, runs JSON export, CV upload, report time ranges, the "Filtered out" count.
- **Sequencing:** new spec `007-ui-target-parity`, started after 006 closes (T033–T035), so 006's "pixels unchanged" gate stays valid.

## Execution kickoff (006 is merged to main via PR #50)
1. `git checkout main && git pull --ff-only origin main` (fetch and fast-forward; the untracked `Docs/Job-matching-intelligence-research/` stays untouched).
2. `git checkout -b 007`, the integration branch for this spec (same model as `006-tailwind`).
   - Each step below is cut as its own sub-branch from `007` (`007-0`, `007-1`, …) and merged back by its own PR after its gate.
   - Commits and PRs happen only when the user asks.
3. Start with 007-0 (spec scaffolding), then 007-1 (foundations).
   - 007-2 to 007-8 depend on 007-1's macros and tokens, and all edit `_macros.html`, `input.css` and the snapshots, so they run sequentially in this session, not in parallel sessions.
4. **Extra item from the 006 gate:** the `<code>` snapshots depend on the system monospace font. 007-1 sets `code` to the same `ui-monospace` stack as today and records the dependency. Self-hosting a mono font is not in scope; it would be a separate decision.

## Ground rules (apply to every step)
- **Macros, not classes.** Components stay Jinja macros in `app/src/app/web/templates/_macros.html` that return complete literal utility strings (spec 006 FR-017/018). No `.btn`/`.card` CSS classes and no concatenated class names.
- **No colour literals in templates** (`tests/test_web_assets.py`). New colours become tokens in `app/src/app/web/styles/input.css`:
  - light values on `:root`
  - dark values in the `prefers-color-scheme: dark` block
  - the `@theme inline` mapping
- **Keep dark mode working.** Every step checks both schemes.
- **Keep the htmx contracts and accessibility intact:**
  - C-1 `_row_status.html` and C-2 `_status_control.html`
  - C-8 metric value as sole text
  - exactly one h1 per page
  - icon-only buttons get an `aria-label` or `icon(label=…)`
  - labelled controls (visually hidden labels are fine)
- **New icons** go into the vendored sprite `app/src/app/web/static/icons.svg`, as Material Symbols `<symbol>`s with the same viewBox and the same source as the existing 21.
  - Expected: `domain`, `hub`, `filter_alt`, `tune`, `visibility_off`, `bar_chart`, `monitoring`, `memory`, `terminal`, `calendar_clock`, `add_circle`, `download`, `save`, `restart_alt`, `public`, `link`, `trending_up`.
- **After each step:**
  - rebuild CSS with `uv run python scripts/build_css.py` and commit `static/css/app.css`
  - re-baseline the affected visual snapshots, recording the reason in `specs/007-ui-target-parity/verification.md`
- **One PR per step:** `007-1`, `007-2`, … (same convention as 006-3.x).

## Step 007-0: spec scaffolding
- Create `specs/007-ui-target-parity/` with `spec.md`, `plan.md` and `tasks.md`, holding this plan, the user decisions above and the gap list from the comparison.
- Point `CLAUDE.md` at the new plan.

## Step 007-1: shell and foundations (all pages)
**Files:** `templates/base.html`, `styles/input.css`, `_macros.html`

- **Width:**
  - Raise the header wrapper `max-w-320` and the `main { max-width: 80rem }` rule (`input.css:263`) to 90rem (1440px; DESIGN.md allows 1280 or 1440).
  - Keep the existing 1.5rem/2rem inline padding.
- **Header:**
  - Nav links at body-md size, `on-surface-variant` with an `on-surface` hover; the active tab keeps the primary underline.
  - Last-run pill restyled as neutral: `surface-container-low` background, hairline border, a small coloured status dot instead of the tinted pill, and the full date format "Last run: 19 Nov 2026, 04:00 — Success".
  - Keep the `.last-run` hook; it is masked in the visual tests.
- **Footer (new):**
  - Hairline top border, `body-sm` text in `on-surface-variant`, same width as the content.
  - Left: "Job discovery v{version} • Local pipeline".
    - Version comes from `importlib.metadata` and is exposed through `shell_context` (`web/deps.py:61`).
  - Right: the timezone setting.
  - Nothing fabricated.
- **New `page_header(title, subtitle=None)` macro with a `{% call %}` slot for right-aligned actions.** It replaces the 11 hand-written header blocks (`index.html:7`, `postings.html:9`, `reports/index.html:7`, `blacklist.html:7`, `runs.html:7`, `profiles.html:9`, `settings.html:10`, `detail.html:9`, the three report detail pages).
  - **Title:** headline-xl on desktop and headline-xl-mobile below 768px, weight 600, tracking −0.025em, `on-surface`. Change the h1 rule at `input.css:248`.
  - **Subtitle:** body-lg in `on-surface-variant`.
  - **Text:** unchanged per page.
- **Cards:** `card_class()` and `table_wrap` keep shadow-1. Add a `card_hover` variant (border-outline plus shadow-2) for clickable cards.
- **New macros used by later steps:**

| Macro | Renders |
|---|---|
| `icon_tile(name)` | 36px rounded-md `surface-container-low` square with a primary icon |
| `initial_tile(text)` | Company initial in a 36px rounded-md tile |
| `count_badge(n)` | Small rounded count for tabs |
| `tag(text, kind)` | Uppercase label-sm tag: `NEW` / `SHORTLIST` / board names |
| `section_header(title, subtitle=None, icon=None)` with a `{% call %}` slot for badges | Section heading row |
| `stat_card(label, value, icon=None, footnote=None, footnote_icon=None, badge=None, href=None)` | Extends `metric`; keeps the C-8 rule that the value is the sole text content |

- **Tokens:**
  - Add `tertiary` / `tertiary-container` / `on-tertiary-container` (the orange used for the Indeed board chip), with dark-mode values from the target palette (`DESIGN.md`).
  - Add contrast cases to `tests/test_design_tokens.py`.

## Step 007-2: Overview (`index.html`, route `web/app.py:37`)
- **KPI row** with `stat_card`, using real footnotes:
  - **Postings:** "N% deduplicated", computed in the template from `health.runs`' `deduplicated_count / collected_count`.
  - **Employers:** "Across N job sources", from `known_sites`.
  - **Scored:** "Awaiting CV at data/cv.txt" when the value is 0.
  - **Published:** "Threshold ≥ N", from `settings_service.get(db, "publish_threshold")`.
  - Value size grows to headline-xl.
- **Scoring banner:** replace the plain info strip with a tinted panel that has an `icon_tile` (memory), a semibold heading, a body line, the `data/cv.txt` path in a code chip and the scoring model name. No upload button.
- **Triage card:**
  - A segmented stacked bar on top: one segment per status, widths from `totals.by_status`, colours from the status tokens.
  - A legend below with colour dot, label, count and percentage. Keep the status links to `/postings?status=…`.
  - "N in total" badge in the top-right.
- **Source health card:**
  - Per board: `icon_tile`, board name, large latest count on the right, and bars with axis labels (`#run.id`, the last one "Now"). The latest bar uses the primary colour and earlier bars a lighter tint.
  - "N/N online" badge: boards with a count above 0 in the latest run.
- **New "Recent postings" section:**
  - Data: `queries.list_postings(db, per_page=5).rows`.
  - Each row: `initial_tile`, title, company, location, source, `relative_age(date_posted)`, `status_pill` and a "Details" secondary button to `/postings/{id}`.
  - Header badge: "Showing top 5 of N".

## Step 007-3: Postings (`postings.html`, `_row_status.html`)
- **Status tabs:**
  - Styled as the target: the selected tab is a dark `inverse-surface` pill (already `chip_class` `aria-current`).
  - Each tab gets a `count_badge`: All = `totals.postings`, the others from `totals.by_status`. "Filtered out" gets no count (out of scope).
- **Filter bar:** one row inside a card.
  - Search input with a leading magnifier icon.
  - Location and source selects at 36px height.
  - Primary Search button.
  - Visible labels become `sr-only`.
- **Bulk-action bar:** tinted `surface-container-low` strip with the select-all checkbox, "N selected", a status select and an Apply button styled like the target.
- **Table:**
  - Merge title and company into one column: `initial_tile`, title in semibold `on-surface` (no underline until hover), company in muted text.
  - Score: neutral badge showing "—" when the posting has no score.
  - Location: neutral chip with an icon.
  - Source: `tag` per board (LinkedIn uses primary-container tint, Indeed uses tertiary-container tint).
  - Posted: muted text.
  - Status: `tag`.
  - Row hover uses the `surface-container-low` tint.
- **Triage control in `_row_status.html`:**
  - Replace the text buttons with compact icon buttons: shortlist (check_circle), reject (cancel), applied (send), new (fiber_new). Each has an `aria-label`, `aria-pressed` for the current state, and a primary fill when active.
  - The htmx attributes (`hx-post`, `hx-target="#status-{id}"`, `hx-swap="outerHTML"`) and form fields stay byte-identical.
  - Update `tests/test_web_triage.py` only if its assertions depend on the button text.
- **Pager:** footer with "Showing a–b of N" on the left and numbered page links on the right (current page highlighted, ellipsis, Next arrow), using the existing `pager` and `page_url(n)`.

## Step 007-4: Reports (`reports/index.html`, route `web/routes/reports.py:43`)
- **Each report becomes a `card_hover` row:**
  - `icon_tile` (domain / hub / filter_alt), title as headline-md (stretched link), a stat badge from real data, the description, a small decorative CSS mini-chart thumbnail (token colours, `aria-hidden`), and a "View report →" link in primary.
  - The route adds `totals`, `known_sites` and `len(profile_store.list_enabled(db))` to the context.
- **Stat badges:**
  - Employers: "N postings across M employers".
  - Sources: "N boards".
  - Profiles: "N active profiles".
- **Pipeline summary panel** (real data only), from `recent_runs(limit=30)`, computed in the template or route from existing fields:
  - **Distinct rate:** the sum of `deduplicated_count` over the sum of `collected_count`.
  - **Average run duration:** `finished_at − started_at`.
  - **Scoring model:** from settings.
- **Report detail pages:** apply `page_header`, and section/card styling on the tables and charts.
- **Dropped:** the time-range control.

## Step 007-5: Blacklist (`blacklist.html`)
- `page_header`, plus a count badge next to the title ("N blacklisted").
- **Stat cards:** two `stat_card`s with icons (`domain`, `visibility_off`), using the existing values only.
- **Table:**
  - `initial_tile` and employer name.
  - Hidden-postings count as a `visibility_off` chip: "N postings blocked".
  - Restore: text button in primary with the `undo` icon. It still POSTs to the existing `/employers/{id}/unblacklist` form.
  - Footer line: "Showing N blacklisted employers".
- The ADR-0015 note becomes a callout panel: `icon_tile`(info), a semibold heading and body text. The wording is unchanged.
- **Empty state:** an icon above the existing message.
- **Not built:** the add form and the reason/date columns.

## Step 007-6: Schedules (`profiles.html`)
- `page_header` (text unchanged). The "Run settings" link moves from the subtitle into the header action slot as a secondary button with the `tune` icon.
- **List card:**
  - The table moves into a card with `section_header` and an "N active" badge (enabled count).
  - Name and role: name in semibold, term in muted text.
  - Location: icon chip, or `public` when the profile is remote.
  - Sites: `tag`s.
  - Experience: plain text.
  - Runs at: a monospace chip showing `HH:MM` and the timezone.
  - Enabled: the existing switch restyled as a pill toggle (primary track, white knob) beside "Active"/"Paused" text. It keeps `aria-checked` and the existing POST.
  - Actions: Run now as a ghost button in primary with `play_arrow`; Delete as a ghost button in error colour with `delete`.
  - The filter-rules expander keeps its behaviour, styled as a muted disclosure row.
- **Add-profile form** (`profiles.html:106-189`):
  - Becomes a card with `section_header`, using `add_circle`.
  - Two-column grid: left holds name, role, location, country; right holds sites checkboxes in a tinted group, experience, the include/exclude regex fields in monospace with "regex" hints.
  - Bottom action bar in a tinted strip: remote-only checkbox with its hint, the runs-at hour:minute inputs, and a primary Save button with the `save` icon.
  - Field names stay exactly as they are; the posted form fields don't change.

## Step 007-7: Settings (`settings.html`)
- `page_header` with the existing text. The saved and error banners stay.
- **Section headings:** "Execution & scoring" (`tune`) and "Filters & network" (`filter_alt`), using the existing text.
- **Fields:**
  - Each label row gets a right-aligned muted hint from the existing validation rules in `services/settings.py:22-78`: "int > 0", "≥ 0", "0–100", "regex", "one per line".
  - Inline unit suffixes inside the inputs: items, hours, sec, score.
  - Taller tinted inputs.
  - The include and exclude regex inputs use the monospace font.
- **LinkedIn checkbox:** a tinted callout box with a heading and a description line.
- **Action bar** at the bottom of the card: a primary Save button with the `save` icon.
- **Read-only section:**
  - A tinted panel with a `section_header` (`lock`, "Read-only (restart required)") and cards with uppercase label-sm keys and semibold values.
  - `database_url` stays "hidden — environment only".
- **Not built:** Reset to defaults, Export JSON, Audit log, the slider, and the sync-status strip.

## Step 007-8: Runs (`runs.html`)
- `page_header` with the existing text.
- **Per-source trend:**
  - A card with `section_header` (`trending_up`) and a legend (board name with colour swatch).
  - Each board panel: `icon_tile`, name, a "Run #N: X postings" badge, bars with value labels above and `#run.id` labels below, the latest bar highlighted ("now") and outlined, and a footer with the existing "vs previous run" delta.
  - The existing striped zero bar stays.
- **History:**
  - A card with `section_header` ("History", with a subtitle line).
  - `whitespace-nowrap` on the Run # and Started columns, which fixes the "1/1" wrap.
  - Numeric columns right-aligned and `tabular-nums`. Rejected count in error colour when above 0.
  - Latest row tinted, with a primary left accent.
  - By-source cell as monospace text, `indeed=26 · linkedin=30`.
  - The error detail row becomes a full-width error-container strip with an `error` icon.
  - Footer: "Showing N recent runs".
- **Not built:** JSON export, the filter button, the trigger button and throttle status.

## Step 007-9: closing gate
Full pytest, ruff, the CSS drift check, the 150 KB budget, and `pytest --visual` with all re-baselined snapshots signed off in `verification.md`. Then a final side-by-side screenshot pass against each target image in light and dark.

## Critical files
- `app/src/app/web/templates/base.html`, `_macros.html`, `_row_status.html`, and every page template
- `app/src/app/web/styles/input.css` → `app/src/app/web/static/css/app.css` (generated, committed)
- `app/src/app/web/static/icons.svg`
- `app/src/app/web/deps.py` (footer version), `web/app.py`, `web/routes/reports.py` (context only)
- Tests:
  - `app/tests/test_css_build.py` (the class-definition check catches unbuilt classes)
  - `test_web_a11y_markup.py`, `test_web_assets.py`, `test_design_tokens.py`, `test_web_triage.py`
  - visual snapshots under `tests/__snapshots__/test_visual/`

## Verification (per step and at the end)
Run from `app\`:
1. `uv run python scripts/build_css.py`, then `git diff --exit-code src/app/web/static/css/app.css` after commit (the CI drift check).
2. `uv run pytest -q`: unit, markup, a11y, CSS-build and token-contrast tests.
3. `uv run ruff check src tests scripts` and `uv run ruff format --check src tests scripts`.
4. `uv run pytest --visual --update-snapshots`, limited to pages changed in the step. Review the diffs and record the reasons; then run `uv run pytest --visual` to confirm 44/44.
5. **Manual comparison in the built-in browser** at http://localhost:8000:
   - 1536×1000 light and dark, plus 375px mobile.
   - Screenshot each page and compare it with its target `screen.png`.
   - Exercise the htmx triage buttons, bulk apply, the profile toggle, Run now, the add-profile form, settings save and blacklist restore to confirm behaviour is unchanged.
