# Quickstart: validating the Tailwind migration (006)

Run from `app/`. Nothing here needs Node.

## Prerequisites

```powershell
uv sync                         # dev group; includes pytailwindcss
uv sync --group visual          # opt-in, only for the visual gate
uv run playwright install chromium
```

## 1. Build the stylesheet

```powershell
uv run python scripts/build_css.py            # writes static/css/app.css (minified)
uv run python scripts/build_css.py --watch    # while authoring
```

Expected: a first run downloads the pinned binary; later runs are fast. SC-010: fresh clone
to rebuilt stylesheet in under 5 minutes, excluding download.

## 2. Default suite (no binary, no browser)

```powershell
uv run pytest
uv run ruff check src tests
```

Expected: all green, including `tests/test_css_build.py` (rendered classes defined, tokens
present, `@source` paths exist) and `tests/test_design_tokens.py` (contrast, reading
`input.css`).

## 3. Drift check (same as CI)

```powershell
uv run python scripts/build_css.py
git diff --exit-code -- src/app/web/static/css/app.css
```

Expected: no diff. Editing `input.css` without rebuilding makes this fail (SC-003).

## 4. Visual gate (Windows maintainer machine)

```powershell
uv run pytest --visual                      # compare against the 44 baselines
uv run pytest --visual --update-snapshots   # ONLY for a recorded decision (FR-003)
```

Expected: 44 of 44 match (11 pages x 375/1280 px x light/dark).
Baselines are captured on `006-1` before `input.css` exists.

## 5. Container

The Dockerfile runs `uv sync --no-dev` and never builds CSS; the image serves the committed
`app.css`. Confirm by `grep -n tailwind app/Dockerfile` returning nothing.

## 6. Size budget

Record the `app.css` size and first-load total (CSS, fonts, icons, scripts) at Phases 0, 1
and 3; each must be at most 150 KB (SC-004).
