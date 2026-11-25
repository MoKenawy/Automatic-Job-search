# Verification report: 004 UI renovation

Status: **automated checks complete; manual passes still to be recorded by the operator.**
Nothing in the manual sections below has been run by the implementer, so none of them is
marked as passed.

## 1. Automated (run from `app/`)

| Check | Result |
|---|---|
| `uv run pytest` | 728 passed, 2 skipped, 0 failed |
| `uv run ruff check src tests` | clean |
| `uv run ruff check` (whole project) | fails only on the old Alembic migration files, which this feature does not touch |
| Token contrast, light and dark (SC-002, `test_design_tokens.py`) | every pair meets its threshold |
| Local-first (SC-005, `test_web_assets.py`) | no page references a script, stylesheet or font on another origin; htmx matches its pinned SHA-384 |
| No colour literals in templates (SC-007) | passes, with no allow-list |
| First-load payload (SC-009) | 132,675 B of 153,600 B: `app.css` 26,645 + Inter latin 48,256 + `icons.svg` 7,387 + htmx 50,387 |
| Markup audit on all 11 GET pages (`test_web_a11y_markup.py`) | one `aria-current`, skip link, one live region, one `h1`, specific `<title>`, labelled controls, `th[scope]`, named SVGs and table regions |
| Contract pins | C-1, C-3 (`test_web_triage.py`), C-6 (`test_blacklist.py`), C-8 strings (existing suites, unchanged) |
| FR-012 | `/settings` never contains the database URL (`test_web_config.py`) |
| FR-013 | the shell shows the last run, or "No runs yet", and links to `/runs` (`test_web.py`) |

**Assertions changed (SC-006): none.** Every existing test assertion is unchanged; this
feature only added tests (516 lines added, 0 removed under `app/tests/`).

## 2. Manual passes (to be completed and recorded)

For each page, light and dark mode, at 375, 768 and 1280 px, plus 320 px reflow and 200 % zoom:

| Page | Light 375 / 768 / 1280 | Dark 375 / 768 / 1280 | 320 px | 200 % zoom |
|---|---|---|---|---|
| Overview | | | | |
| Postings | | | | |
| Posting detail | | | | |
| Reports index and 3 reports | | | | |
| Blacklist | | | | |
| Schedules | | | | |
| Settings | | | | |
| Runs | | | | |

Also to record:

- **Keyboard only (SC-004):** daily triage, bulk change, blacklist and un-blacklist, run a profile now. Focus visible at every step, and never hidden under the sticky shell.
- **htmx, with and without the script:** row status, detail status, bulk apply. Then a forced error (stop the server), checking the control re-enables and the error is announced.
- **Network log:** only the application's origin.
- **Reduced motion, forced colours.**
- **SC-003 / SC-010:** no page-level horizontal scroll; at most one filled primary button per form or card.

## 3. Mock-up elements deliberately left out

As listed in the spec's "Mock-up element classification" table. In particular:

- Employers and Scored cards are not interactive (no destination).
- No counts in the Postings status chips (flagged follow-up 11).
- No Upload CV, export, hand-add blacklist or telemetry elements (flagged follow-ups 1–10).
- The Postings location column has no icon, because the sprite has no pin glyph.
- The yield delta is shown only when a source has two or more runs.

## 4. Deviations from the tasks

- `expand_more` is built from `keyboard_arrow_down`, because 0.48.3 has no `expand_more` (see `VENDORED.md`).
- T012 moved to T024a, and T025 grew from three behaviours to five (busy and success announcements), per the analysis findings H1 and H2.
- Checkboxes in the Postings table are labelled through `aria-labelledby` pointing at the title link, because existing tests count and parse the title text.
- The a11y test accepts implicit labels (a control wrapped in its `<label>`).
- The Reports "Triage status per search profile" page referenced CSS variables that no longer exist after the shell change; its inline `<style>` was moved into `app.css` on the new tokens.
