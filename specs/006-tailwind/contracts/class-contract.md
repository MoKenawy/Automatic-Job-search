# Contract: classes the markup, script and tests depend on

Applies at every phase gate (FR-019, FR-013, SC-005). Source of truth for what a template
may emit and what the built stylesheet must define.

## 1. Behaviour hooks (must stay in the markup, styled or not — FR-019)

Selected by the inline scripts in `base.html` and `postings.html`, by the 004 htmx contract
([C-1 to C-8](../../004-ui-renovation/contracts/htmx-fragments.md)) or by tests:

- Classes: `pill`, `banner` (with `tabindex`), `.last-run`.
- Selectors: `nav a[aria-current="page"]`.
- Ids: `status-*` row/detail targets, `#selcount`, `#announcer`.
- Attributes toggled by script: `aria-busy`, `disabled`. The scripts set no classes.

The full list is re-derived by grepping templates and tests when Phase 0 starts, and is
recorded here.

## 2. Status class mappings (Phase 2, step 3.1 — FR-018, R9)

One Jinja dict per family in `_macros.html`; each value is a **complete literal class
string** (so the scanner sees it); `_neutral` is the fallback for unknown values; the hook
class comes first.

| Family | Keys | Fallback |
|---|---|---|
| Posting status | new, shortlist, applied, rejected | `_neutral` |
| Run status | running, success, failed | `_neutral` |
| Banner kind | the kinds used by `base.html`/`_macros.html` today | `_neutral` |

Implemented in `_macros.html` as `pill_class(status)` and `banner_class(kind)` (step 3.1). The
base `.pill` / `.banner` component rules still supply the neutral look; the mapped utilities
override colours only:

| Value | Classes |
|---|---|
| posting `new` | `bg-secondary-container text-on-secondary-container border-transparent` |
| posting `shortlist`, run `running` | `bg-surface-container-lowest text-primary border-primary` |
| posting `applied`, run `success` | `bg-success-container text-on-success-container border-transparent` |
| posting `rejected`, run `failed` | `bg-error-container text-on-error-container border-transparent` |
| banner `success` | `bg-success-container text-on-success-container border-success` |
| banner `error` | `bg-error-container text-on-error-container border-error` |
| unknown / banner `info` | empty (neutral) |

Every call site goes through these two macros; `test_css_build.py` fails if a template builds a
pill/banner class name by interpolation or if a mapped class is missing from the built CSS.
Forced-colours rules are unlayered (FR-020, R5) so they still beat these utilities.

## 3. Hook-only allowlist (classes allowed in markup but absent from the stylesheet)

Phase 0 allowlist (unstyled on `49de3dd` too): `selrow` (bulk-select script hook) and `info` (default banner kind). Later: `pill` and `banner` only if, after Phase 3, they carry no styles. Every other
rendered class MUST exist in the built stylesheet (`test_css_build.py`, R8). An addition to
this list needs a reason recorded here.

## 4. Colours

No colour literals in templates and no colour utility outside the project palette
(`--color-*: initial`, FR-011; 004 FR-005, SC-007). Data-driven `var(--token)` inline styles
in `reports/profiles.html` and bar heights stay inline (FR-021, R10).
