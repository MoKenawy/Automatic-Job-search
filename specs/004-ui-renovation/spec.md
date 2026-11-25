# Feature Specification: UI renovation of the triage interface

**Feature Branch**: `004-ui-renovation`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "Renovate the look and the user experience of the triage web
interface so it matches the approved design package in `Docs/Job Discovery UX&UI/`. What the
application does must not change." (Full brief:
[`Docs/Job Discovery UX&UI/ui-renovation-prompt.md`](../../Docs/Job%20Discovery%20UX&UI/ui-renovation-prompt.md).)

## Context

The triage interface (ADR-0004) is where the single operator reviews postings and configures
the pipeline (ADR-0005). It works, but it was built to a §11 time-box. The visual hierarchy
is flat, every action looks the same, and nothing on screen tells the operator what is
clickable, what is healthy and what needs attention. A design package now exists: a UX
specification, brand guidelines, a design-token file and Stitch mock-ups of seven screens.
This feature brings every page into line with that package. It changes only how the existing
information and actions are presented, never what they are.

**Sources, and which one wins.** In order of precedence:

1. `technical_precision/DESIGN.md`. Its YAML tokens take precedence over its prose.
2. `Job_Discovery_Brand_Guidelines.pdf`, wherever DESIGN.md says nothing.
3. `Job_Discovery_UX_Documentation.pdf`, for flows and behaviour.
4. The Stitch screens, as an illustrative visual target only.

Constitution VI records this order. Every conflict found is logged in
[Design-source conflicts](#design-source-conflicts).

## Clarifications

### Session 2026-11-19 (post-specify)

- **Q1.** Show last-run status on every page? → **Yes.** Every page receives the latest run
  so the shell can show it (FR-013). This is a small code change outside the templates. It
  adds no route and changes no service.
- **Q2.** Add Blacklist to each postings row? → **No.** Blacklisting stays on the posting
  detail page only (FR-014).
- **Q3.** Fix the Blacklist page's Remove control? → **Option A.** Make it a plain form
  submission, consistent with the other blacklist actions (FR-016).

### Session 2026-11-19 (clarify)

- Q: How are the row status quick actions presented? → A: An icon plus a short text label,
  at every width (FR-017).
- Q: How is action feedback presented? → A: A persistent inline status banner at the top of
  the content, announced, and kept until the next page load. No toasts, because nothing
  pushes events from the server yet (FR-018).
- Q: How do the seven tabs behave below 768 px? → A: A single row that scrolls horizontally
  on its own, with the current tab brought into view (FR-019).
- Q: What loading states are shown? → A: No skeleton screens. During an in-place action, the
  triggering control is disabled and shows an announced busy state, which also prevents
  double submission (FR-020).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A consistent, legible shell on every page (Priority: P1)

Whichever page the operator opens, they see the same frame:

- the product name, which returns to Overview;
- one row of tabs (Overview, Postings, Reports, Blacklist, Schedules, Settings, Runs), with
  the current tab marked visually and for assistive technology;
- a page title with a one-line description of what the page is for.

The frame follows the operator's light or dark preference. It works on a phone, a tablet
and a desktop, and the browser never contacts anything except the application itself.

**Why this priority**: every other story renders inside this frame. On its own it already
improves every page, and nothing else can ship without it.

**Independent Test**: open each of the seven tabs at 375, 768 and 1280 px in light and in
dark mode, then check four things: the active tab is marked, the page title and description
are present, there is no horizontal page scroll, and the network log shows requests to the
application's own origin only.

**Acceptance Scenarios**:

1. **Given** any page, **When** it loads, **Then** the tab for that page is marked as current
   and announced as current to assistive technology.
2. **Given** the operator's system prefers a dark colour scheme, **When** any page loads,
   **Then** it renders in the dark palette, and every text/background pair meets the
   contrast thresholds in SC-002.
3. **Given** a 375 px viewport, **When** any page loads, **Then** the tabs sit in a single
   row that scrolls sideways on its own, with the current tab visible. The page itself does
   not scroll horizontally (FR-019).
4. **Given** a machine with no internet access, **When** any page loads, **Then** it renders
   completely, with the same fonts, icons and interactions as when connected.
5. **Given** a keyboard user, **When** they press Tab from the top of any page, **Then**
   focus moves through the tabs in order with a clearly visible focus indicator. A
   "skip to content" control is offered first.

---

### User Story 2 - Triage postings quickly (Priority: P1)

The operator opens Postings and scans a ranked list. Each row reads, at a glance, in this
order:

1. the score,
2. the title, with the employer below it,
3. the location,
4. the source boards,
5. the age,
6. the status.

Status chips (All, each status, Filtered out) change the list with one click. A search box
and the location and source facets narrow it further. One click on a row's quick action
changes that posting's status without leaving the list. Selecting several rows and
choosing a status changes them all at once. The operator can page through long lists.

**Why this priority**: triage is the product's main workspace (UX doc §3). It is used daily,
and how fast it reads is where the renovation pays back most.

**Independent Test**: with a seeded database, do each of the following and check that the
outcome matches today's behaviour:

- filter by each status chip;
- search for a title;
- pick a location and a source;
- change one row's status by mouse and then by keyboard;
- bulk-change three rows;
- go to page 2.

**Acceptance Scenarios**:

1. **Given** the list, **When** the operator activates a status quick action on a row,
   **Then** that row's status updates in place, without reloading the page, and the change
   is announced to assistive technology.
2. **Given** a row whose status is any of new, shortlist, applied or rejected, **When** the
   operator looks at its quick actions, **Then** every other status that is reachable today
   is still reachable from that row.
3. **Given** no rows selected, **When** the operator looks at the bulk bar, **Then** the
   Apply control is disabled, and the counter reads "0 selected".
4. **Given** three rows selected and a status chosen, **When** the operator applies it,
   **Then** all three change. The list re-renders on the same filter, search and page, and
   the confirmation message is announced.
5. **Given** a keyboard-only operator, **When** they tab into a row, **Then** its quick
   actions are visible and operable. They do not appear only on mouse hover.
6. **Given** a list wider than the viewport, **When** viewed at 375 px, **Then** the table
   scrolls horizontally inside its own container, and the page does not.
7. **Given** htmx has not loaded, **When** the operator submits a quick action or the bulk
   form, **Then** the change still happens through a normal page submission.
8. **Given** the status chips, **When** they render, **Then** they show no counts. The
   postings page receives no per-status counts today, so none are invented (FR-011). Counts
   in chips are flagged follow-up work. *Superseded by spec 007 (D7, 2026-11-25): the chips
   now show counts from `queries.status_counts`, under the same search, location, source and
   published filters as the list, so each count equals what its chip opens.*

---

### User Story 3 - Read and act on one posting (Priority: P2)

From a list row, the operator opens a posting and reads, without hunting:

- its title, employer, location and status;
- its filter verdict, if any;
- its sources and description.

From this page they can change its status, and blacklist or un-blacklist its employer.

**Why this priority**: this page has no mock-up. It is reached from US2, and it is where
decisions are made that the list cannot support.

**Independent Test**: open a posting, change its status, blacklist the employer (after
confirming), then remove the blacklist. Check that the outcomes and redirects are the same
as today.

**Acceptance Scenarios**:

1. **Given** a posting, **When** the page loads, **Then** the title, employer, status
   control, any filter-verdict banner and any blacklist banner come before the description.
2. **Given** the operator blacklists the employer, **When** they confirm, **Then** the same
   request as today is made and they return to this posting.
3. **Given** a long description, **When** viewed at 375 px, **Then** it wraps within the
   viewport and stays readable.

---

### User Story 4 - See where the pipeline stands (Priority: P2)

Overview answers "where does my pipeline stand, and what should I do next?" (UX doc §2). It
shows:

- four metric cards: postings, employers, scored, published;
- a callout when scoring has not run;
- the triage distribution by status, with each status linking to its filtered list;
- source health, a short bar series per board.

**Why this priority**: this is the landing page. It is read every day, but nothing is
decided here.

**Independent Test**: with a seeded database, compare every number on the page with the
current Overview. Then follow every link and check where it lands.

**Acceptance Scenarios**:

1. **Given** postings exist and none are scored, **When** Overview loads, **Then** a callout
   says scoring has not run and names the requirement (a CV at `data/cv.txt`). It offers no
   action that the system cannot perform (FR-011).
2. **Given** a metric card whose number has an existing filtered destination, **When** the
   operator activates it, **Then** they land on that list. A card with no such destination
   is not presented as interactive.
3. **Given** a source whose latest count fell to zero, **When** source health renders,
   **Then** the drop is distinguishable without relying on colour alone.
4. **Given** no runs yet, **When** Overview loads, **Then** every section shows an empty
   state that tells the operator what to do next.

---

### User Story 5 - Catch silent degradation on Runs (Priority: P3)

The operator reviews Runs weekly to spot runs that succeed while returning steadily fewer
postings (§7.4). There is a per-source trend, then a history table that reads left to right
as a funnel: collected → distinct → passed / rejected → scored → published → by source.

**Why this priority**: the review is weekly, not daily.

**Independent Test**: seed runs with running, success and failed statuses, plus one run the
filter never touched. Check four things: statuses can be told apart by text and icon as well
as colour, the untouched run shows "—" rather than 0, error text is shown, and the trend
values match the data.

**Acceptance Scenarios**:

1. **Given** a run that failed, **When** history renders, **Then** its status reads "failed"
   with an icon. The error text is shown with that run.
2. **Given** a run the filter never processed, **When** history renders, **Then** Passed and
   Rejected show "—", not 0 (the current behaviour, `reports-implementation-plan.md` §R5).
3. **Given** a trend bar, **When** it is hovered or focused, **Then** its value is available
   as text.

---

### User Story 6 - Manage search schedules (Priority: P3)

On Schedules the operator sees each profile with its role, location, sites, experience,
run time and enabled state. From there they can:

- enable or disable it;
- run it now;
- delete it, after confirming;
- view and edit its filter rules.

They can also add a new profile with a clearly grouped form.

**Why this priority**: profiles are configured rarely and then left to run.

**Independent Test**: for each action, run it and compare the resulting redirect, error
display and stored state with today's:

- add a profile;
- trigger a validation error;
- toggle a profile;
- run a profile;
- edit its filter rules;
- delete it.

**Acceptance Scenarios**:

1. **Given** a profile, **When** the operator toggles enabled, **Then** the state changes
   exactly as today. The control shows its current state as text, not only as a switch
   position.
2. **Given** the add form, **When** a field is invalid, **Then** the error appears as it
   does today, and every field keeps its visible label.
3. **Given** a delete, **When** activated, **Then** a confirmation is asked first (as today).

---

### User Story 7 - Edit settings safely (Priority: P3)

On Settings the operator edits operational configuration in a form grouped into
execution/scoring and filters/network. It is clear that changes apply on the next run, and
the restart-only values are shown read-only.

**Why this priority**: settings change rarely.

**Independent Test**: submit valid and invalid values, and check that the success and error
messages, and the stored values, match today's.

**Acceptance Scenarios**:

1. **Given** a save, **When** it succeeds, **Then** a success message says the change applies
   on the next run, and it is announced.
2. **Given** the read-only block, **When** it renders, **Then** `database_url` is never shown,
   not even partly masked. It reads "hidden — environment only", as today.
3. **Given** the LinkedIn description checkbox, **When** it renders, **Then** its label is
   adjacent to the box and is clickable.

---

### User Story 8 - Review the blacklist (Priority: P3)

On Blacklist the operator sees every blacklisted employer, with the number of postings
hidden for each. They can remove any of them. The page restates the rule: postings are
hidden, not deleted, and removing a blacklist restores the prior status (FR-013), with the
legacy-blacklist caveat. When the list is empty, the page says how employers get added.

**Why this priority**: blacklisting is done from postings. This page is for occasional
review.

**Independent Test**: remove one employer, then check that the employer's postings reappear
in the list with their prior status, and that the operator lands back on Blacklist with the
page intact.

**Acceptance Scenarios**:

1. **Given** a blacklisted employer, **When** the operator removes it, **Then** the request
   is the same as today, and they land on an intact Blacklist page, not on a page nested
   inside the table (FR-016).
2. **Given** no employers are blacklisted, **When** the page loads, **Then** an empty state
   explains that employers are blacklisted from a posting's detail page.

---

### User Story 9 - Find and read reports (Priority: P3)

Reports lists three analyses as full-width cards. Each card has a title, the question it
answers, and an affordance showing it opens a detailed page. Each report page presents its
tables and caveats in the shared design language.

**Why this priority**: reports are analysis, separate from daily triage (ADR-0008).

**Independent Test**: open each report from the index, and check that every figure and
caveat matches the current pages.

**Acceptance Scenarios**:

1. **Given** the Reports index, **When** a card is activated anywhere on its surface,
   **Then** the matching report opens. There is exactly one link per card for assistive
   technology.
2. **Given** a report page, **When** it renders, **Then** every caveat
   (`reports/_caveat.html`) is still shown.

---

### Edge Cases

- **Empty data.** No postings, runs, profiles or blacklist entries: every section shows an
  empty state with the next action. Nothing renders blank.
- **Long values.** Very long titles, employer names, regexes and proxy lists wrap or
  truncate with the full value available. They never widen the page.
- **Non-Latin text.** Arabic employer names and titles render in a fallback font, with no
  missing-glyph boxes.
- **Status variety.** A run is `running`, `success` or `failed` (the UX doc's "partial" does
  not exist in the system). Any status outside the known sets still renders readably, with a
  neutral style.
- **Scoring off.** Scores are absent for every posting: the score column shows "—", and the
  sort note still says unscored postings sort last.
- **Reduced motion.** The operator prefers reduced motion: there are no animated
  transitions.
- **htmx missing.** htmx fails to load: every form still submits and works.
- **In-place action fails.** An in-place action gets an error response or loses the
  network. The control is re-enabled, the posting's status is shown unchanged, and an error
  is announced (FR-020).

## Requirements *(mandatory)*

### Functional Requirements

**Scope and behaviour**

- **FR-001**: The renovation MUST NOT change any of the following:
  - routes or HTTP methods;
  - status codes or redirect targets;
  - form field names or query parameters;
  - service behaviour or the database schema.

  A UX improvement that would need any of these is recorded under
  [Flagged follow-ups](#flagged-follow-ups) and is not built (constitution VII).
- **FR-002**: The interactions that use htmx today MUST keep working, with the same element
  ids, targets and swap behaviour. These are:
  - the single-row status change on the list;
  - the status change on the posting detail page;
  - the bulk status form.

  All other interactions are plain form submissions today, and they MUST keep working as
  plain submissions:
  - filters and search;
  - pagination;
  - blacklist and unblacklist;
  - profile enable, run, delete and filter edit;
  - add profile;
  - save settings.
- **FR-003**: Every form MUST still complete its action with scripting unavailable.
- **FR-004**: Every status transition that a row offers today MUST still be offered from that
  row.

**Design system**

- **FR-005**: Colours, type sizes, weights, spacing, radii and elevation MUST come from one
  shared set of design tokens derived from DESIGN.md. Templates MUST NOT contain literal
  colour values.
- **FR-006**: The interface MUST provide a light palette and a derived dark palette. It
  selects one from the operator's system preference.
- **FR-007**: Status MUST NOT be conveyed by colour alone. Every status pill and indicator
  also carries text, an icon, or both.

**Accessibility (WCAG 2.2 AA)**

- **FR-008**: The interface MUST meet each of the following:
  - visible focus on every interactive element;
  - full keyboard operation;
  - a visible label on every form control;
  - header cells on every data table;
  - every icon either labelled or hidden from assistive technology;
  - `aria-current` on the active tab;
  - a skip-to-content link;
  - live announcement of in-place updates and confirmation messages;
  - no motion when reduced motion is preferred;
  - **pointer targets at least 24 × 24 CSS px**, or spaced so that a 24 px circle around
    each target overlaps no other target (2.5.8);
  - **a focused element is never fully hidden by the sticky shell** (2.4.11);
  - **a unique, descriptive page `<title>` on every page**, and one `h1` per page with
    headings in order (2.4.2, 1.3.1);
  - **each scrollable table region reachable and scrollable by keyboard**, and named for
    assistive technology (2.1.1);
  - **a text equivalent for every bar series** (source health, per-source trend), giving
    each value as text (1.1.1).
- **FR-008a**: The focus indicator MUST be at least 2 CSS px thick, contrast at least 3:1
  with the colours next to it, and be visible in both palettes.

**Layout**

- **FR-009**: Every page MUST work at 375, 768 and 1280 px or wider, with no horizontal scroll
  at page level. Wide tables MUST scroll inside their own container. Content MUST also:
  - reflow without loss at a 320 CSS px viewport (1.4.10);
  - stay usable at 200% browser zoom (1.4.4);
  - lose nothing when the user overrides text spacing (1.4.12).

**Local-first**

- **FR-010**: Every font, icon, script and stylesheet MUST be served by the application.
  Pages MUST make no requests to other origins (constitution II).

**Truthful content**

- **FR-011**: Every number, status and label MUST come from data that the system already
  provides to that page. Mock-up elements without such data are handled as listed in
  [Mock-up element classification](#mock-up-element-classification). Placeholder figures
  from the mock-ups MUST NOT appear.
- **FR-012**: Secrets MUST NOT be displayed, either fully or partly masked. This covers the
  database URL and any proxy credentials beyond what the settings form already shows.

**Shell**

- **FR-013**: The shell MUST show a last-run status indicator on every page, linking to Runs.
  It shows the time and status of the most recent run, and is distinguishable by text and
  icon for running, success and failed. When there are no runs, it reads "No runs yet".
  Every page supplies the latest run to the shell (Q1). No route changes. No existing service
  changes; one new read-only lookup is added (plan R8).
- **FR-019**: Below 768 px, the tab row MUST stay a single line that scrolls horizontally
  within itself. It MUST NOT wrap or collapse into a menu. When a page loads, the current
  tab MUST be visible inside the row. Every tab stays reachable by touch and by keyboard.

**Postings rows**

- **FR-014**: Postings rows MUST NOT gain a Blacklist action. Blacklisting an employer stays
  on the posting detail page only, with its confirmation (Q2).

- **FR-017**: Each status action, both in list rows and on the posting detail page, MUST show
  an icon together with a visible text label naming the target status, for example
  "Shortlist" or "Reject", at every viewport width. Icon-only status buttons are not used.
  *Amended by spec 007 (D6, 2026-11-25) for list rows only: row actions are icon-only, each
  named by `aria-label` and a matching tooltip ("Set status to Shortlist"), with the current
  status still shown as text. The detail page keeps icon plus label.*

**Blacklist page**

- **FR-016**: The Remove control on the Blacklist page MUST be a plain form submission, like
  every other blacklist action. After removal the operator lands on an intact Blacklist
  page. This corrects existing markup that could insert the redirected page inside the
  table (Q3). It is the one deliberate interaction change in this feature, and the htmx
  contract records it.

**Feedback**

- **FR-018**: Confirmation and error messages that pages already produce MUST be shown as an
  inline status banner at the top of the page content. Examples are "Settings saved", the
  bulk-apply message, and the profile and settings errors. The banner MUST be announced to
  assistive technology and MUST NOT disappear on a timer. Toasts are out of scope until the
  server can push events (see Flagged follow-ups, item 6).
- **FR-020**: While an in-place status change or bulk apply is in flight, the control that
  started it MUST be disabled and show a busy state that is announced to assistive
  technology. A second submission is not possible until the response arrives. Skeleton
  screens are not used, because every page is rendered complete.

**Logo**

- **FR-015**: The product name MUST appear as a plain-text wordmark until the brand's master
  logo files are supplied. After that, the supplied files are used unaltered, with the
  reversed version in dark mode.

### Key Entities

No data entities are added or changed. The pages present the existing entities:

- posting (with its status and filter verdict);
- employer (with its blacklisted state);
- search profile;
- run (with per-source counts);
- application settings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Changing a posting's status from the list still takes exactly **one**
  activation, and still causes no full page load.
- **SC-002**: **100%** of foreground/background colour pairs meet **4.5:1** (normal text) or
  **3:1** (large text, UI components, focus indicators), in both light and dark palettes.
- **SC-003**: **0** pages scroll horizontally at 375, 768 or 1280 px.
- **SC-004**: The four key flows can be completed with the keyboard alone, with focus visible
  at every step (UX doc flows B, C, A3, D). The flows are:
  - daily triage;
  - bulk status change;
  - blacklisting and un-blacklisting an employer;
  - running a profile now.
- **SC-005**: **0** network requests go to any origin other than the application, across all
  pages.
- **SC-006**: **100%** of the existing automated tests pass. Every assertion that is changed
  checked markup or styling only, and is listed in the verification report with its reason.
- **SC-007**: **0** literal colour values in any page template.
- **SC-008**: **0** figures, labels or states are displayed that the system does not compute.
  This is checked against the classification table.
- **SC-009**: A first visit downloads **≤ 150 KB** in total of styling, fonts, icons and
  scripts. Later page views download **0 KB** of those, because they are cached.
- **SC-010**: Every page has exactly one primary (filled) action per area, matching the UX
  doc's button rule. Every other action is outlined or a text link.

## Mock-up element classification

Each element in the Stitch screens that goes beyond what the page shows today is placed in
one of three groups:

- **Implement**: implement with existing data.
- **Out of scope**: not part of this product.
- **Backend**: needs backend work, as a separate feature.

| Screen | Element | Decision | Reason |
|---|---|---|---|
| All | Avatar, account menu, Login screen | Out of scope | The app has no authentication (single operator, ADR-0004) |
| All | Footer "v1.0 · Local pipeline · Secure session · Encrypted · Latency 24ms" | Out of scope | Nothing computes these values |
| All | Terminal / code icon buttons in the header | Out of scope | No corresponding function |
| All | Breadcrumb eyebrow ("PIPELINE ENGINE / TRIAGE VIEW") | Out of scope | Decorative copy that names no real section |
| All | Last-run pill in the header | Implement | Q1 = yes (FR-013) |
| Overview | Four metric cards | Implement | `totals` provides all four numbers |
| Overview | Postings card → list; Published card → `/postings?published=true` | Implement | Both destinations exist |
| Overview | Employers card and Scored card destinations | Backend | No employer view, and no "scored" filter parameter; the cards render as non-interactive |
| Overview | "+12 today", "95 target", "Pending", "Ready: 0", "100% deduplicated", "Across 2 job sources" | Out of scope | Not computed. "Threshold ≥60" may be shown only if the threshold reaches the page. It doesn't today, so it is left out |
| Overview | "Sync Pipeline", "Run Scrapers" buttons | Backend | No pipeline-wide trigger exists; per-profile Run now exists on Schedules |
| Overview | "Scoring not yet run" callout | Implement | Text only |
| Overview | "Upload CV" button in the callout | Backend | No upload endpoint |
| Overview | Triage distribution with links per status | Implement | `totals.by_status` |
| Overview | Source health bars, latest count | Implement | `source_health` |
| Overview | Scraper versions, latency, "2/2 online", R-6…Now labels | Out of scope | Not computed |
| Overview | "Recent intake stream" (salaries, tags, "Awaiting match") | Out of scope | Not on this page today. Salary and tags are not stored |
| Postings | Status chips | Implement | The chips are built. Their counts are not (US2 AS-8): the page receives no per-status counts. Counts need backend work |
| Postings | "⌘K" shortcut badge | Out of scope | No command palette |
| Postings | "Export CSV", "Fetch Fresh" | Backend | No endpoints |
| Postings | Score badge, title + employer, location, sources, posted, status | Implement | Existing fields |
| Postings | Employer initial tile | Implement | Derived from the employer name, decorative, hidden from assistive technology |
| Postings | Skill / tag line under the employer ("Infrastructure · Enterprise Hybrid") | Out of scope | Not stored |
| Postings | Relative age ("2d ago") | Implement | Derived from the posted date already on the page; the absolute date stays available |
| Postings | Row quick actions | Implement | All current transitions kept (FR-004) |
| Postings | Row Blacklist action | Out of scope | Q2 = no; it stays on the detail page (FR-014) |
| Postings | Numbered pagination (1 2 3 … 27) | Implement | Page count and number exist |
| Postings | "New since latest run" badge | Backend | No per-run marker on postings |
| Blacklist | Hand-add input "Enter employer name to blacklist" + "Apply to historical postings" | Backend | No blacklist-by-name endpoint |
| Blacklist | KPI cards (total employers, hidden postings) | Implement | Count of rows, sum of counts |
| Blacklist | "Rule integrity: FR-013 Active", "Sync status", "Engine: Inverted Bloom Filter" | Out of scope | Not computed |
| Blacklist | Date added, reason / notes, employer domain | Backend | Not stored |
| Blacklist | "Export Audit Log" | Backend | No endpoint |
| Blacklist | FR-013 rule callout | Implement | Existing text, restyled |
| Schedules | Profile list with enable toggle, Run now, Delete, filter-rules expander | Implement | Existing actions |
| Schedules | "Next cluster tick", "cron daemon v2.4", average runtime, storage, worker pool, "UTC" suffix | Out of scope | Not computed. The run time is shown in the configured timezone, not labelled UTC |
| Schedules | "Run Settings" link | Implement | Link to `/settings` |
| Schedules | Glassdoor (beta) site option | Out of scope | Only sites the form offers today |
| Schedules | Keyboard shortcut hints (⌘S, Esc) | Out of scope | No such shortcuts |
| Schedules | "Cancel" on the add form | Implement | Resets the form; no request |
| Settings | Two-column grouping, inline hints | Implement | Existing fields |
| Settings | Publish-threshold slider | Out of scope | Kept as a number field. A paired slider needs scripting for no new capability |
| Settings | Scoring model as a dropdown of models | Backend | No list of available models |
| Settings | "Export JSON", "Audit Log", "Reset to Defaults" | Backend | No endpoints |
| Settings | Sync status bar, schema rev, inference ping, node ID, PID, uptime, pool | Out of scope | Not computed |
| Settings | Partially masked `database_url` | Out of scope | Never shown (FR-012) |
| Runs | Per-source trend, history funnel, status pills | Implement | `source_health`, run rows |
| Runs | Yield delta vs previous run | Implement | Computable in the page from the series already provided; shown only when two or more runs exist |
| Runs | Proxy pool, CAPTCHA, latency, retry frequency, retention policy, throttle status | Out of scope | Not computed |
| Runs | Audit links filtered to a run and source | Backend | No run filter on Postings |
| Runs | "Trigger Execution", "Filter Pipeline", "Download JSON log", "View Scraper Specs", "Configure Alert Webhook" | Backend / Out of scope | No endpoints |
| Reports | Three report cards with "View report" | Implement | Existing reports |
| Reports | Card badges with live counts, mini chart previews from real data | Backend | The index receives no data today (UX doc §4 asks for real data, not static art) |
| Reports | Date-range switch (Last 30 days / QTD / All time) | Backend | No range parameter |
| Reports | "Ingest & classification telemetry" panel | Out of scope | Not computed |

## Flagged follow-ups

None of these is built in this feature. Each one needs backend work, and would be specified
as its own feature:

1. CV upload from the Overview callout.
2. A pipeline-wide "run all profiles now".
3. Postings filters for "scored" and for a given run (for the Runs audit links).
4. An employer view, as the destination of the Employers card.
5. Blacklist by typed name, with date added and a reason.
6. Undo after blacklisting, and success toasts that need server-sent state.
7. Live data in the Reports index cards, and a date-range parameter.
8. A list of installed models for the scoring-model field.
9. CSV / JSON export of postings, runs, settings or the blacklist.
10. A "new since latest run" marker on postings.
11. Per-status counts in the Postings status chips.

## Design-source conflicts

| ID | Conflict | Resolution |
|---|---|---|
| C1 | DESIGN.md's YAML tokens are Material-3 generated (primary `#004ac6`, surface `#faf8ff`). Its prose uses Tailwind slate (`#2563EB`, `#F8FAFC`, `#E2E8F0`, `#0F172A`). | **The YAML wins.** The Stitch screens use only the YAML roles. The prose fills gaps: elevation shadows, placeholder colour, focus-ring alpha. |
| C2 | Typeface: DESIGN.md uses Inter only. The brand guide uses Montserrat for headings and Inter for UI. | **DESIGN.md wins.** Inter only. |
| C3 | Colours differ between DESIGN.md, the brand guide (navy `#1E2530`, blue `#1A73E8`, ice `#E8F0FE`) and the UX doc (`#243040`, `#146FF4`, `#EAF2FE`, green `#1F9D55`, red `#D64545`). | **DESIGN.md YAML wins.** DESIGN.md defines no success colour, so the brand guide's `#1E8E3E` fills that gap. |
| C4 | DESIGN.md's `outline` (`#737686`), used as text in the mock-ups, reaches about 4.25:1 on the `surface` canvas. That fails AA. | Muted text uses `on-surface-variant`. `outline` is used for borders and decoration only. |
| C5 | Type scale: the brand H1 is 28/36 Montserrat Bold. DESIGN.md `headline-lg` is 24/32 Inter 600. | **DESIGN.md wins.** |
| C6 | The brand guide requires the master logo files and forbids redrawing. Only a raster image on white is supplied, with no reversed version. | Plain-text wordmark until the masters arrive (FR-015). |
| C7 | The mock-ups contain screens and figures with no backing data: Login, telemetry, salaries. | Classified above. Nothing invented (FR-011). |
| C8 | The brief lists blacklist/unblacklist and profile enable/run/delete as htmx interactions. In the code they are plain form submissions. | Spec follows the code (FR-002). |
| C9 | The UX doc's row quick actions show only Shortlist, Reject and Blacklist. Today's rows offer every other status, including new and applied. | Every current transition is kept (FR-004). |

## Assumptions

- The operator uses a current evergreen desktop browser. Phone and tablet use is secondary,
  but must work (FR-009).
- "Dark mode" means following the system preference. No in-app theme switch is added.
- The current page copy (sub-titles, caveats, ADR / FR references) stays, because it carries
  traceability (UX doc B, "Traceability"). It may be shortened only where meaning is kept.
- The absence of authentication stays as it is. The deployment model (local, single
  operator) is unchanged.
- The approved dependency declaration (vendored htmx 2.0.3, Inter, and a Material Symbols
  icon subset; no new Python packages; no build step) bounds how this is delivered. It is
  recorded in the plan, not here.
