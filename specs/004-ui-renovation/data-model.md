# Data model: UI renovation (004)

## Schema

**There are no schema changes.** This feature adds no table, column, index, constraint,
Alembic migration or seed data. Every page presents data that the system already stores and
already computes.

## What each page receives (view inputs)

This is the template context each route passes today. It sets the limit of what a page may
display (FR-011). Anything not listed here is out of scope or needs backend work; see the
spec's classification table.

| Page | Context keys | Used for |
|---|---|---|
| Overview `/` | `totals` (`postings`, `employers`, `scored`, `published`, `by_status`, `last_run`), `health` (`sites`, `series`, `runs`) | Metric cards, scoring callout, triage distribution, source health |
| Postings `/postings` | `pager` (`rows`, `number`, `pages`, `total`, `first`, `last`, `has_prev`, `has_next`), `statuses`, `status`, `verdict`, `q`, `country`, `source`, `published`, `facets` (`countries`, `sources`, `unknown_country`), `flash`, `page_url()` | List, chips, facets, bulk bar, pager |
| Posting detail | `p` (Posting), `employer`, `statuses`, `verdict`, `current` | Header, status control, banners, description, assessment, sources, record |
| Reports index | `reports` (href, title, blurb) | Cards. No figures |
| Reports pages | Per-report rows and toggles (unchanged) | Tables, caveats |
| Blacklist | `employers` (employer, hidden-postings count) | Table. Header figures are derived from these rows only |
| Schedules `/profiles` | `profiles`, `error`, site options | Profile list, add form |
| Settings | `values`, `readonly`, `saved`, `error` | Form, read-only block |
| Runs | `health`, `runs` | Trend, history |

## Shell context, added on every page (FR-013, research R8)

| Key | Type | Source | Notes |
|---|---|---|---|
| `shell.last_run` | `Run \| None` | `queries.latest_run(db)`, new and read-only | `status` ∈ {`running`, `success`, `failed`}, plus `started_at` |
| `shell.now` | `datetime` | The request time | Lets `relative_age` render deterministically (R13) |
| `asset_version` | `str` | A hash computed at import (R5) | Cache-busting for `/static` URLs |

## Display states, derived only

| Concept | Values | Presentation |
|---|---|---|
| Posting status | `new`, `shortlist`, `applied`, `rejected` | Pill with text and icon. Status colour roles only, never colour alone (FR-007) |
| Run status | `running`, `success`, `failed`, and any unknown value | Pill with text and icon. Unknown values get the neutral style |
| Filter verdict | passed / turned away on title, experience or both | Banner on detail; "Turned away on" column |
| Employer blacklisted | `suppressed` true/false | Banner and action on detail |
