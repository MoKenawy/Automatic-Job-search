# Tasks: UI parity with the Stitch target designs (007)

**Input**: `specs/007-ui-target-parity/` (spec.md, plan.md). Paths are relative to the repo root;
run commands from `app/`.

**Branching**: `007` is the integration branch cut from `main`. Each step is its own sub-branch
cut from `007` and merged back by its own PR after its gate (pytest, ruff, drift check,
`--visual` 44/44 after the recorded re-baseline). Commits and PRs only when the maintainer asks.

- [X] T001 `007-0`: spec scaffolding (`spec.md`, `plan.md`, `tasks.md`); point local `CLAUDE.md` here
- [X] T002 `007-1`: tokens (tertiary family, dark values, contrast tests), macros (`page_header`, `section_header`, `stat_card`, `icon_tile`, `initial_tile`, `count_badge`, `tag`, `card_hover_class`, `badge_class`)
- [X] T003 `007-1`: shell at 90rem, neutral last-run pill with dot and full date, footer (version, timezone)
- [X] T004 `007-1`: `page_header` on all 11 pages; h1 at headline-xl from 768 px
- [ ] T005 `007-2`: new sprite icons (moved from 007-1); Overview: KPI footnotes, scoring panel, stacked triage bar, labelled source bars, recent postings
- [ ] T006 `007-3`: Postings: tab counts, one-row filter bar, bulk bar, merged title column, board tags, icon triage (C-1 intact), numbered pager
- [ ] T007 `007-4`: Reports: icon cards with stat badges, pipeline summary panel, detail pages styled
- [ ] T008 `007-5`: Blacklist: stat cards, initial tiles, blocked chip, restore link, callout
- [ ] T009 `007-6`: Schedules: list card, toggles, coloured actions, time chips, two-column add form with action bar
- [ ] T010 `007-7`: Settings: section icons, field hints and units, callout checkbox, action bar, read-only panel
- [ ] T011 `007-8`: Runs: trend cards with value and run labels, history card with highlighted latest run
- [ ] T012 `007-9`: final gate and side-by-side screenshots against each target, light and dark
