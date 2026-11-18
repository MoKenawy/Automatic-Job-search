# ADR-0020: Seniority for boards that declare none — title fallback, or seniority in the search term?

* Status: accepted — option A, with operator guidance (18 November 2026)
* Deciders: Mohammed
* Date: 17 November 2026; decided 18 November 2026

Technical Story: the experience criterion's primary input, `postings.job_level`,
comes from one board. Every other board the collector queries supplies nothing,
and the criterion falls back to reading the title (FR-006). The operator asked
whether it would be better to put the seniority into the search itself. The
record was opened as proposed; it is now accepted with option A plus guidance
for the operator on wording profiles — see [Decision](#decision).

## Context and Problem Statement

**Only LinkedIn sets `job_level`.** Under JobSpy 1.4.1 (1.1.82 when this was
opened) the LinkedIn scraper is the only one that assigns the field, and only
with description fetching on: it reads the text beside the English "Seniority
level" heading on the job page and lowercases it (`jobspy/linkedin/util.py`
`criteria`, `jobspy/linkedin/__init__.py` `_fetch_details`). Indeed, Glassdoor, Google, ZipRecruiter,
Bayt, BDJobs and Naukri never set it, so their rows carry the model default
`None`. Measured on the live corpus: LinkedIn 100%, Indeed 0% (`db/models.py`
module docstring, 16 November 2026). Pinned in code by
`app/tests/test_jobspy_contract.py`, offline and `--live`.

**What happens to those rows today.** With no board label, `filters.verdict.evaluate`
reads the normalised title through `level_from_title`. That fires only on an
explicit, unambiguous seniority word (`senior`, `junior`, `intern`, `lead`, …)
and otherwise returns nothing; nothing admits (FR-005). So for Indeed the
criterion hides only titles that *say* they are above the request, and passes
every plainly titled role.

**The search parameters JobSpy exposes contain no seniority.** LinkedIn's guest
search accepts an experience-level filter (`f_E`) on the website, but JobSpy's
request carries only keywords, location, distance, remote, job type, Easy Apply,
company ids and age (`jobspy/linkedin/__init__.py:94-114`). Indeed's GraphQL
filters cover job type, remote, date and Indeed Apply only
(`jobspy/indeed/__init__.py:137`). Without patching JobSpy, the **query text** is
the only lever. Re-checked against JobSpy 1.4.1 (18 November 2026): still
true. `scrape_jobs` takes `search_term`, `location`, `distance`, `job_type`,
`hours_old`, `easy_apply`, `is_remote`, `linkedin_company_ids` and
`google_search_term`, and nothing about experience. Seniority appears only in
what comes *back*: LinkedIn's `job_level`, and Naukri's `experience_range` — a
board this application does not collect (`WORKING_SITES` is Indeed and
LinkedIn).

**The constraint any option must meet.** FR-012: filtering must not reduce what
collection stores. Every row a board returns is landed verbatim so that a
criteria change is re-appliable to history (FR-011, FR-013) rather than a reason
to re-scrape. A posting that was never collected cannot be recovered by loosening
a rule.

## Decision Drivers

* A posting wrongly withheld is never seen; one wrongly shown costs seconds.
  Collection-time narrowing is the strongest form of withholding: it leaves no
  row to re-filter and nothing in `/postings?verdict=rejected`.
* The operator wants the filter to reduce triage work, and Indeed postings
  currently get only the weaker, title-only judgement.
* `results_per_search` caps rows per search, so the query text decides *which*
  rows fill the cap, not only how many exist.
* Every extra search is another request to boards that rate-limit (design §9.3).

## Options considered

| Option | What it does | What it costs |
|---|---|---|
| **A. Title fallback only (as built)** | No change. Indeed rows are judged on title words; silence admits | Plainly titled senior roles on Indeed are never hidden; the criterion is much weaker there than on LinkedIn |
| **B. Replace the term with a seniority-qualified one** (`junior data engineer`) | The board's search engine does the narrowing | Loses plainly titled entry roles ("Data Engineer") at collection, unrecoverable under FR-012/FR-013; keyword matching on "junior" is not a seniority filter (it also matches descriptions that mention juniors); makes the profile's experience a collection parameter, which spec 003 deliberately avoided |
| **C. Add a seniority-qualified search alongside the plain one** | Keep every existing search; add e.g. `junior data engineer` / `graduate data engineer` for profiles with an entry request | Additive only — nothing is lost, and roles that would fall outside the plain search's `results_per_search` cap can surface. Costs more requests and more rate-limit exposure; the extra rows still need the filter, since the board's keyword match is no guarantee |
| **D. Read the experience stated in the description** ("0–2 years", "3+ years of experience") | A new pure parser in `filters/`, used where the board declared nothing, ahead of or alongside the title | A new heuristic with its own false-rejection risk, and it needs its own OBSERVED fixtures; overlaps with what the stage-3 scorer will read |

B is listed because it was asked, and is the only option that conflicts with an
existing requirement rather than merely costing something. C is the form of the
same idea that does not.

## Decision

**Option A — the title fallback, as built.** No behaviour changes. Indeed
postings keep being judged on title words, and a plainly titled one is admitted.

B is rejected: it narrows collection on a keyword match, which loses postings
unrecoverably (FR-012, FR-013). C and D stay open for later; neither is needed to
make the criterion usable today, and both cost something (more requests; a new
heuristic with its own false rejections).

Because the term is the only collection lever and seniority in it is the costly
mistake, the decision comes with **guidance where profiles are made**:

* **On the profile form** (`/profiles`): a hint under *Role / search term*
  saying the term goes to the boards as plain keywords, to name the role only,
  and why seniority in it loses postings; and a hint under *Experience* (on the
  add form and on each profile's filter rules) saying it is applied after
  collection and never narrows the search, listing the words it understands,
  and saying how LinkedIn and Indeed are judged differently. A test keeps the
  listed words in step with `filters.levels`.
* **In the operations guide** (§6a, "Setting up a new profile"): the same,
  with the full word-to-level table, and the one safe way to use a
  seniority-qualified term — as a **second** profile *alongside* the plain one,
  never in place of it. That is option C done by hand, at the operator's
  discretion and cost, rather than automatically for every profile.

## Consequences

* The experience criterion is asymmetric across boards: LinkedIn postings are
  judged on a declared label (with ADR-0017's caveats), Indeed postings on title
  words alone.
* A posting surfaced by both boards takes LinkedIn's label (min-wins merge,
  FR-009), so the asymmetry applies only to Indeed-only postings.
* The quality of what is collected depends on how profiles are worded, which
  is now explained where they are made rather than left to be discovered.
* An operator who follows the second-profile advice spends more requests on the
  boards (design §9.3); the guide says to add such profiles sparingly.

## Relationship to other records

Extends [ADR-0016](0016-collect-stage-filter-verdicts.md) (FR-006, the title
fallback). Related to [ADR-0017](0017-board-seniority-label-reliability.md): if
that record settles on judging from the title alone (its option B), the board
asymmetry here disappears and this question narrows to C or D.
[ADR-0019](0019-jobspy-linkedin-seniority-crash.md) covers the one board that
does supply a label failing to; the JobSpy upgrade it chose is the version this
record was re-checked against. ADR-0017 kept the label-led rule as built, so the
asymmetry stands.

## Control

`test_live_indeed_declares_no_level` re-measures the premise. If it fails —
Indeed, or an upgraded JobSpy, starts supplying a level — this record's context
has changed and the decision should be revisited. The profile-form hints are
held to `filters.levels` by `test_every_experience_word_the_hint_lists_is_understood`.
