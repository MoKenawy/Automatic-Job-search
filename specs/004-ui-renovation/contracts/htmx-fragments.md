# Contract: htmx fragments and in-place interactions

These are the interfaces that markup shares with the server. A presentational change MUST
leave every item below as it is (constitution VII, spec FR-001/FR-002). The only intended
change is **C-6**, which removes `hx-post`, per clarification Q3.

Notation:
- **MUST keep**: changing it breaks behaviour or a test.
- **May add**: attributes allowed as additions (R9).

---

## C-1 — Single-row status change (Postings list)

| Item | Value | Status |
|---|---|---|
| Wrapper element id | `status-{posting_id}` on the outermost element of `_row_status.html` | MUST keep |
| Form `method` / `action` | `post` / `/postings/{id}/status` | MUST keep (no-JS path) |
| `hx-post` | `/postings/{id}/status` | MUST keep |
| `hx-target` | `#status-{id}` | MUST keep |
| `hx-swap` | `outerHTML` | MUST keep |
| Fields | `status` = target status; `variant` = `row` | MUST keep |
| One form per target status | For every status ≠ the current one (FR-004) | MUST keep |
| Response, with `HX-Request: true` | `200`, body = `_row_status.html` rendered for the updated posting; the root carries the same `id` | MUST keep |
| Response, without htmx | `303` → `/postings` | MUST keep |
| Error responses | `400` unknown status, `404` posting not found; htmx swaps nothing | MUST keep, then announced by R9 |
| May add | `hx-disabled-elt`, `aria-busy` handling, icon markup inside the button, the button's visible label (FR-017) | — |

Test pins:
- `test_web_triage.py:71` counts `name="variant" value="row"`. **The attribute order and
  quoting stay exactly `name="variant" value="row"`.**
- `test_web_triage.py:81` checks `id="status-1"`.

## C-2 — Status change on the detail page

Same as C-1, with these differences:
- fragment `_status_control.html`
- `variant` = `detail`
- no-JS redirect `303` → `/postings/{id}`

The wrapper id is the same `status-{id}`.

## C-3 — Bulk status form

| Item | Value | Status |
|---|---|---|
| Form id | `bulkform` | MUST keep: row checkboxes reference it with `form="bulkform"` |
| `method` / `action` | `post` / `/postings/status` | MUST keep |
| `hx-post` / `hx-target` / `hx-swap` | `/postings/status` / `body` / `innerHTML` | MUST keep |
| Fields | `ids` (repeated, on the row checkboxes `class="selrow"`), `status`, and the echoed list state `list_status`, `q`, `country`, `source`, `published`, `verdict`, `page` | MUST keep |
| Element ids used by the inline script | `selall`, `selcount`, `bulkapply` | MUST keep (`test_web_triage.py:140-142`) |
| Row checkbox class | `selrow` | MUST keep (the inline script selects by it) |
| Response | `200`, the full postings page for the echoed state, with the flash message; htmx swaps the body | MUST keep |
| Errors | `400` when `ids` is empty or the status is unknown | MUST keep, then announced by R9 |
| Behaviour | The Apply button stays disabled until at least one row is selected; the counter reads "N selected" | MUST keep |

**Note.** Because the bulk response replaces `<body>`, the shell's live region and the inline
listeners are part of the swapped content. They MUST be written to work after a body swap:
either delegate from `document`, or re-run on load, using the same IIFE pattern as today's
`postings.html` script.

## C-4 — Filters and search (plain GET)

`<form method="get" action="/postings">` with fields `q`, `country`, `source`, plus `status`
and `verdict` as hidden fields. The status chips are plain links:
- `/postings`
- `/postings?status={s}`
- `/postings?verdict=rejected`

No htmx. MUST keep.

## C-5 — Pagination (plain links)

Links to the same list with a `page` parameter. The visible text "Page N of M" MUST stay
(`test_web_triage.py:153,169`), even when numbered page links are added.

## C-6 — Remove a blacklisted employer (**changed by this feature**)

| Item | Before | After |
|---|---|---|
| `method` / `action` | `post` / `/employers/{id}/unblacklist` | unchanged |
| Field | `return_to` = `/blacklist` | unchanged |
| `hx-post` | `/employers/{id}/unblacklist` (with no target, which caused the defect in R11) | **removed**: plain form submission (FR-016) |
| Response | `303` → `return_to` | unchanged |

Test pin, new: the `/blacklist` page contains no `hx-post`.

## C-7 — Plain form posts (no htmx; unchanged)

| Form | `action` | Fields | Response |
|---|---|---|---|
| Blacklist employer (detail page) | `/employers/{id}/blacklist` | `return_to` | `303` → `return_to`; `onsubmit` confirmation kept |
| Remove blacklist (detail page) | `/employers/{id}/unblacklist` | `return_to` | `303` → `return_to` |
| Add profile | `/profiles` | `name`, `term`, `sites` (repeated checkbox), `location`, `country`, `experience`, `title_include_pattern`, `title_exclude_pattern`, `is_remote`, `schedule_hour`, `schedule_minute` | `303` → `/profiles`, or `/profiles?error=…` |
| Enable / disable profile | `/profiles/{id}/enabled` | `enabled` = `true` or `false` | `303` → `/profiles` |
| Edit profile filters | `/profiles/{id}/filters` | `experience`, `title_include_pattern`, `title_exclude_pattern` | `303` → `/profiles`, or with `?error=` |
| Run profile now | `/profiles/{id}/run` | — | `303` → `/runs`, or `/profiles?error=…` |
| Delete profile | `/profiles/{id}/delete` | — (confirmation kept) | `303` → `/profiles`, or with `?error=` |
| Save settings | `/settings` | `results_per_search`, `hours_old`, `request_delay_seconds`, `publish_threshold`, `scoring_model`, `linkedin_fetch_description`, `title_include_pattern`, `title_exclude_pattern`, `proxies` | `303` → `/settings?saved=1`, or `400` with the form |
| Report toggles | `/reports/employers?show_suppressed=true`, `/reports/profiles?show_disabled=true` | — | GET links |

The profile enable control MAY look like a switch. It MUST stay a submit button inside this
form, exposing `role="switch"` and `aria-checked`, and showing its state as text (spec US6
AS-1).

## C-8 — Text that tests assert

The renovation MUST keep these strings in the rendered pages, because existing tests assert
them. Restyling around them is fine. Changing the words is not.

- **Overview.** "Overview".
- **Metric numbers.** Each number is the whole text content of its own element, so that
  `>3<` matches (`test_web_filter.py:129`).
- **Run counts.** Each count is the sole content of its cell, so that `>11<` matches once
  spaces are stripped (`test_web_filter.py:278`).
- **Detail page.** "Not scored yet", "Strong overlap" (the scoring rationale text), and
  "Remove from blacklist" (`test_blacklist.py:278`).
- **Profiles page.** The help copy that `test_web_config.py:245-276` asserts:
  - "in addition to"
  - "exclude always beats include"
  - "filter --all"
  - "plain keyword search"
  - "can't be recovered later"
  - "<strong>second</strong> profile"
  - "it never narrows the search"
  - "Indeed postings on title words only"
  - "none set"
  - "Save filter rules"
- **Profiles page ids.** `term-hint`, `experience-hint`, `exp-{id}-hint`.
- **Postings page.** "Page N of M".

`tasks.md` re-checks this list against a fresh grep of `tests/test_web*.py`,
`test_blacklist.py`, `test_profiles.py` and `test_settings.py` before the first template
edit.
