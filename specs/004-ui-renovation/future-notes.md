# Future notes: icons and a React frontend

Captured 2026-11-20 after closing the Stitch design drift (commit `49de3dd`). Neither item is
planned or specified. Each would be its own feature, with its own spec and ADR.

## 1. Go back to icon-based controls

**What it is.** The Stitch mock-ups use icon-only controls where the build uses icon plus text.
Examples: the "Triage" column of icon-only status buttons on Postings, and the terminal/code
icon buttons in the header. The build has a 21-glyph SVG sprite (`static/icons.svg`) but
mostly pairs each glyph with a visible label.

**Constraints to resolve first.**

- **FR-017** says every status action shows an icon *and* a visible label, at every width,
  and that icon-only status buttons are not used. Going back to icons means amending
  FR-017 in the spec and recording why in an ADR.
- Icon-only controls need an accessible name (`aria-label` or a visually hidden label) and a
  visible tooltip or `title`. `test_web_a11y_markup.py` would need updating to match.
- Touch targets must stay at least 24 px (WCAG 2.5.8). `.btn-sm` is 28 px high.
- Icon-only is fine on wide screens only if narrow screens keep a label, or the meaning is
  unambiguous. Shortlist, Reject, Applied and Blacklist are not obviously distinguishable by
  glyph alone, and the colour must never carry the meaning alone (FR-007).

**Options, cheapest first.**

1. Keep the sprite. Make the row actions icon-only from 1024 px up and icon plus label below
   (the label becomes `.visually-hidden` on wide screens).
2. Add glyphs to the sprite as needed from the pinned `@material-symbols/svg-400@0.48.3`,
   and record each in `VENDORED.md`. The sprite hash changes each time.
3. Return to a Material Symbols icon font. **Not recommended**: the font is over 300 KB, and
   the first-load budget (SC-005/SC-009, 150 KB) and the no-third-party rule (constitution II)
   both argue against it.

## 2. Consider React for the frontend

**Why look at it.** Overview and Postings now carry a lot of composition (cards, toolbars,
segmented chips, bulk selection). Client-side state such as bulk selection, live status
changes and toasts is hand-rolled JS today. Several flagged follow-ups (spec "Flagged
follow-ups": undo and toasts, live report cards, status counts, CV upload) are easier with
client state.

**What it would cost.** These are the decisions that would need an ADR.

- **Constitution III (no build step).** React brings a bundler (Vite or similar), a Node
  toolchain and a `package.json`. That is a constitution amendment, not a local choice.
- **Architecture.** `web/` today is server-rendered Jinja plus htmx and reads the database
  directly. React needs a JSON API layer (`web/routes/` returning data, not HTML). Keep it
  read-only for pipeline data, as `web/` is now, and keep the per-posting filter criteria
  going through `filters.build_criteria` so the API and the detail page cannot disagree.
- **Budget.** React plus ReactDOM is roughly 45 KB gzipped before any app code, against a
  150 KB first-load cap that is already at 132.7 KB. Preact (about 4 KB) would fit.
- **Tests.** The suite runs with no Docker and no Node. A React frontend adds a JS test
  runner, and the markup tests (`test_web_a11y_markup.py`, `test_web_assets.py`) would move
  from rendered HTML to built output or component tests.
- **Throwing away work.** 004 deliberately chose progressive enhancement, so forms work
  without JS. A single-page app gives that up unless it is server-rendered.

**Lower-cost alternatives to compare first.**

- More htmx: out-of-band swaps for toasts and counts, `hx-boost` for navigation. This needs
  no build step and covers most of the flagged follow-ups.
- Alpine.js or a small vendored web-component layer for selection and toggles.
- Preact with `htm` (no JSX, so no build step), vendored like htmx.

**Suggested next step.** Pick one flagged follow-up that genuinely needs client state (for
example undo after blacklisting), prototype it in htmx, and note where it strains. Decide on
React only if that prototype fails. Then write the ADR.
