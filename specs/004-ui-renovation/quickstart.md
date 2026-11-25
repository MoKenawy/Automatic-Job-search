# Quickstart: run and verify the renovated UI (004)

All commands run from `app/`.

## Run it

```bash
uv sync
uv run alembic upgrade head        # no new migrations; ensures the DB is current
uv run python -m app web           # or: docker compose up web
```

Then open <http://localhost:8000>.

## Automated checks (must pass before every commit)

```bash
uv run ruff check
uv run pytest
```

The pytest run includes the new checks:

| Module | What it checks |
|---|---|
| `tests/test_design_tokens.py` | WCAG contrast for every token pair, in light and dark mode (SC-002) |
| `tests/test_web_assets.py` | No colour literals in templates, no external URLs, the htmx hash, the payload budget (SC-005, SC-007, SC-009) |
| `tests/test_web_a11y_markup.py` | `aria-current`, labels, `th[scope]`, icon labelling, the live region, the skip link (FR-008) |

## Manual verification (recorded in `verification.md`)

For each page (Overview, Postings, Posting detail, Reports and its three reports, Blacklist,
Schedules, Settings, Runs):

1. **Viewports.** Check light mode and dark mode at 375, 768 and 1280 px. Use DevTools
   device mode, and "Emulate CSS prefers-color-scheme" for the scheme. Confirm there is
   no page-level horizontal scroll, and that wide tables scroll inside their own panel.
2. **Keyboard only.** Starting from the address bar, use Tab, Shift+Tab, Enter and Space.
   - The skip link comes first, then the tabs, then the page.
   - Focus is visible on every stop.
   - Run the four flows in SC-004.
3. **htmx interactions.** Each must behave as it does today:
   - a row status change (no page reload; the busy state shows);
   - a detail-page status change;
   - a bulk apply on a filtered second page (the page and filters are kept);
   - a forced error: block the request in DevTools, and the failure is announced and the
     control re-enabled.
4. **No htmx.** Block `/static/vendor/htmx-2.0.3.min.js`, then repeat step 3. Each action
   completes through a page submission.
5. **Network.** With "Disable cache" on, reload each page. Every request goes to
   `localhost:8000`, and the transfer total is ≤150 KB.
6. **Reduced motion.** With `prefers-reduced-motion: reduce` emulated, nothing animates.
