# Tasks: Tailwind migration of the triage interface's styling (006)

**Input**: `specs/006-tailwind/` (spec.md, plan.md, research.md, quickstart.md, contracts/class-contract.md)

**Tests**: Required by the spec (FR-013, FR-026), so test tasks are included.

**Paths**: relative to the repo root. `app/` is the Python project; run commands from `app/`.

**Branching (FR-027)**: each phase below is its own sub-branch cut from `006-tailwind` and
merged by its own PR, only after its gate (full `pytest`, `pytest --visual` 44/44, drift
check). Branch creation and commits happen only when the user asks.

**Format**: `- [ ] T### [P?] [Story?] Description with path`. `[P]` = different files, no
dependency on an unfinished task.

---

## Phase 1: Setup (branch `006-1`)

- [X] T001 Create sub-branch `006-1` from `006-tailwind` (on user confirmation)
- [X] T002 Pick the pin: newest Tailwind v4.x release at least 2 weeks old; add `pytailwindcss` to `[dependency-groups] dev` and a `[tool.app.tailwind] version = "v4.x.y"` table in `app/pyproject.toml`; add a `visual` dependency group with `pytest-playwright` and `pytest-playwright-visual-snapshot`; run `uv lock`. Record the pin in `specs/006-tailwind/plan.md` (Pin line)
- [X] T003 [P] Add `app/src/app/web/static/css/app.css -diff linguist-generated` to `.gitattributes`

## Phase 2: Foundational — the visual gate and baselines (blocks every story)

**Why first**: baselines must be captured while `app.css` is byte-identical to `49de3dd` (FR-026).

- [X] T004 Add the `--visual` option and skip logic (mirror `--live`) plus a `visual` marker in `app/tests/conftest.py`; register the marker in `app/pyproject.toml`
- [X] T005 Write the seeded-data fixture (postings in every status, Arabic and very long employer names, a filtered-out posting, runs running/success/failed, two profiles, one blacklisted employer, source health; dates relative to seed time) in `app/tests/visual_seed.py`
- [X] T006 Write `app/tests/test_visual.py`: `pytest.importorskip("playwright")`, uvicorn thread on a free port with `get_db` overridden to the seeded in-memory SQLite (`StaticPool`), matrix 11 pages × {375×812, 1280×800} × {light, dark} via `emulate_media`, `animations="disabled"`, wait on `document.fonts.ready`, mask `.last-run`
- [X] T007 Run `uv sync --group visual` and `uv run playwright install chromium`; run `uv run pytest --visual --update-snapshots` with `app.css` untouched; check there is no flakiness by running `--visual` twice; add further masks for any render-time value found; commit baselines in `app/tests/__snapshots__/test_visual/` (44 files)

**Checkpoint**: 44/44 baselines pass on the untouched stylesheet.

## Phase 3: User Story 1 — toolchain renders today's interface exactly (P1) 🎯 MVP

**Goal**: Tailwind build produces a stylesheet visually identical to today's.
**Independent test**: `--visual` 44/44; `pytest` green with no binary; editing `input.css` without rebuilding fails the drift check.

### Tests for US1

- [X] T008 [P] [US1] Write `app/tests/test_css_build.py` (stdlib only): rendered page and fragment classes (11 pages, C-1 and C-2 with `HX-Request: true`) ⊆ classes defined in built `app.css` (regex extraction and unescape, R8; allowlist from `contracts/class-contract.md` §3); every `--token` in `input.css` `:root` blocks is declared in `app.css`; every `@source` path in `input.css` exists
- [X] T009 [P] [US1] Re-point `CSS` in `app/tests/test_design_tokens.py` to `src/app/web/styles/input.css`; confirm its regexes still match the moved-verbatim token blocks

### Implementation for US1

- [X] T010 [US1] Write `app/scripts/build_css.py` (R1): read the pin from `[tool.app.tailwind]`, export `TAILWINDCSS_VERSION`, reinstall the binary on version mismatch, run `tailwindcss -i src/app/web/styles/input.css -o src/app/web/static/css/app.css --minify` (or `--watch`)
- [X] T011 [US1] Create `app/src/app/web/styles/input.css`: header comment (generated output, ADR-0022, FR numbers); `@import "tailwindcss" source(none)`; `@source "../templates"`; `:root` light tokens and dark `prefers-color-scheme` block moved verbatim from `app.css` §1, except radius and shadow tokens moved into `@theme static` (R3)
- [X] T012 [US1] In `input.css` add `@theme inline` with `--color-*: initial` and one entry per colour role, the `--text-*` roles with line-height and letter-spacing companions, `--font-sans`, `--spacing: 0.25rem` (R3, FR-011)
- [X] T013 [US1] Move the remaining `app.css` rules (§2 and §3) verbatim into `@layer components`, keeping the reduced-motion (`!important`) and forced-colours blocks after the rules they override (R5, US1 AS-7); move font faces unchanged
- [X] T014 [US1] Run the build; save the old `app.css` as reference outside the repo; run `pytest --visual`; add `@layer base` restores for each Preflight difference found (R4 table: svg display, list styles, margins, raw buttons, summary), checking headings, `table`, `dl.meta`, form controls first, until 44/44 pass
- [X] T015 [US1] Confirm the Tailwind verify-in-Phase-0 items (R3 radius/shadow `@theme static` output on `:root`; dark shadows still win) and the CI cache path for the binary; update `research.md` if any assumption was wrong
- [X] T016 [US1] Add to `.github/workflows/ci.yml` (`test` job): binary cache step and, after `pytest`, `uv run python scripts/build_css.py` then `git diff --exit-code -- src/app/web/static/css/app.css` (R6). Leave `app/Dockerfile` untouched
- [X] T017 [P] [US1] Draft `Docs/ADRs/ADR-0022-styling-with-tailwind-standalone-cli.md` (Status: proposed; supersedes ADR-0021; amended principle III wording from FR-023); mark ADR-0021 `superseded by ADR-0022`; update the `Docs/README.md` index
- [X] T018 [P] [US1] Docs: add a "Styles" section (build, watch, drift check, layout) to `Docs/development-guide.md`; update the "one language"/"no build" lines in `Docs/tech-stack.md`; update local `CLAUDE.md` (gitignored)
- [X] T019 [US1] Phase 0 gate: `uv run pytest`, `uv run ruff check src tests`, `uv run pytest --visual` (44/44), drift check clean; run the suite with the Tailwind binary absent; record `app.css` size and first-load total (≤ 150 KB) in `specs/006-tailwind/verification.md`. Open PR `006-1` → `006-tailwind` on user request (not yet opened)

**Checkpoint**: MVP. Stop here for user review before Phase 1.

## Phase 4: User Story 2 — utilities on top of components (P2) (branch `006-2`)

**Goal**: new layout via utilities; low-risk cleanup. **Test**: `--visual` clean, no removed class still referenced.

- [X] T020 [US2] Create sub-branch `006-2` from updated `006-tailwind` (on user confirmation)
- [X] T021 [US2] Regroup `input.css` components by existing order (buttons, chips/pills, cards, tables, forms, shell, feedback, page-specific); rewrite component internals as `@apply` compositions of theme utilities only where it reads better; keep render-time variants (`pill {{ status }}`, `banner {{ kind }}`, `delta down`, `bars i.zero`) as selectors on semantic classes (FR-014)
- [X] T022 [P] [US2] For each helper (`.visually-hidden`, `.spacer`, `.muted`, others found): grep templates, macros, scripts and tests, replace uses with `sr-only` / equivalent utilities in `app/src/app/web/templates/**`, then delete the rule (FR-015)
- [X] T023 [US2] Add a `@source inline(...)` safelist entry only for classes `test_css_build.py` reports as rendered-but-missing (US2 AS-3)
- [X] T024 [US2] Phase 1 gate: pytest, ruff, `--visual` 44/44, drift check; record the stylesheet size as the hybrid baseline in `verification.md`

## Phase 5: User Story 3 — templates to utilities, group by group (P3)

**Goal**: each step is its own sub-branch and PR with its own gate (FR-016, FR-027). Every step:
convert the listed templates; compare screenshots; for fragments compare markup with the full-page region against the 004 contract; keep hook classes (FR-019); repeated clusters (3+) become macros (FR-017).

- [X] T025 [US3] `006-3.1` — `app/src/app/web/templates/_macros.html`: add one dict per status family (posting, run, banner kind) of complete literal class strings with `_neutral` fallback (R9); fill in `contracts/class-contract.md` §2 with the real strings; route `base.html` last-run pill and `index.html` distribution pills through `status_pill()`; extend `test_css_build.py` for unknown-status fallback
- [ ] T026 [US3] `006-3.2` — `base.html`: shell, wordmark, tab strip, last-run pill, skip link, live region, `main`; state variants for `aria-current`/`aria-busy`/focus (FR-020)
- [ ] T027 [US3] `006-3.3` — `postings.html`, `_row_status.html`, `_status_control.html`; assert C-1, C-2, C-3 ids/targets/swaps unchanged and fragment markup equals the full-page region
- [ ] T028 [US3] `006-3.4` — `detail.html`: detail grid, actions, metadata list, description
- [ ] T029 [US3] `006-3.5` — `index.html`: metric cards, distribution rows, source-health bars (bar heights stay inline, FR-021)
- [ ] T030 [US3] `006-3.6` — `runs.html`, `profiles.html`, `blacklist.html`, `settings.html`: forms, tables, switch (`aria-checked`), rules expander
- [ ] T031 [US3] `006-3.7` — `reports/index.html`, `sources.html`, `employers.html`, `profiles.html`, `_caveat.html`: pie and legend stay as small custom rules with `var(--token)` inline styles
- [ ] T032 [US3] Phase 2 closing check: move reduced-motion (`!important`) into `@layer base` and forced-colours into an unlayered block at the end of `input.css` (R5/FR-020); verify keyboard focus indicator (≥2 px, ≥3:1) and forced-colours/reduced-motion behaviour against baseline

## Phase 6: User Story 4 — authored CSS shrinks (P4) (branch `006-4`)

- [ ] T033 [US4] Create `006-4`; for every component rule, grep templates/macros/script/tests; delete rules with no use (FR-015); leave only tokens, theme mapping, font faces, base layer and commented one-offs (striped zero bar, pie, tab-strip fade) (FR-022)
- [ ] T034 [P] [US4] Mark ADR-0022 accepted; update `Docs/README.md`, `Docs/development-guide.md` "Styles" section and `Docs/tech-stack.md` to the final structure; update local `CLAUDE.md`
- [ ] T035 [US4] Final gate: pytest, ruff, `--visual` 44/44, drift check, budget ≤ 150 KB; write final figures and the list of any changed assertions with reasons to `specs/006-tailwind/verification.md`; confirm SC-005–SC-009 (no unmapped classes, no literal colours, contrast, no other origins, rule count)

---

## Dependencies & Order

- Phase 1 → Phase 2 (baselines) → US1 (blocks everything) → US2 → US3 (T025 before T026–T031; T026–T031 largely sequential because each rebases on the last) → T032 → US4.
- Within US1: T008, T009 can be written first (they fail until T011/T013); T010 → T011 → T012 → T013 → T014 → T015 → T016; T017, T018 parallel with T014+.
- Parallel: T003; T008 ∥ T009; T017 ∥ T018; T022 across templates; T034.

## Implementation Strategy

- **MVP = through T019** (Phase 0 gate). Stop there and review before US2.
- Each later phase or step is an independent resting point; never merge a step whose gate fails.
- Baselines are regenerated only by a recorded decision (FR-003).

## Validation

Total: 35 tasks. Phase 1: 3 · Phase 2: 4 · US1: 12 · US2: 5 · US3: 8 · US4: 3.
