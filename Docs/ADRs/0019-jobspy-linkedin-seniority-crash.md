# ADR-0019: JobSpy's LinkedIn seniority parse — guarding against a whole-search crash

* Status: accepted — option C (18 November 2026)
* Deciders: Mohammed
* Date: 17 November 2026; decided 18 November 2026

Technical Story: writing contract tests against JobSpy's real `job_level` output
(`app/tests/test_jobspy_contract.py`) turned up a latent defect in the library: a
LinkedIn job page that loads but carries no English "Seniority level" heading
makes JobSpy raise, and the raise discards the **whole** LinkedIn search for that
term, not one row. The record was opened as proposed; it is now accepted with
option C — the defect was fixed upstream and the pin moved to a release that
carries the fix. See [Decision](#decision).

## Context and Problem Statement

*The context below describes JobSpy 1.1.82, as it stood when this record was
opened. File and line references are to that version.*

**How JobSpy 1.1.82 produces `job_level`.** Only the LinkedIn scraper sets it, and
only with `linkedin_fetch_description` on (it is read from the job page, which is
only fetched for descriptions). `parse_job_level` finds an `<h3>` whose text
contains the English string `Seniority level` and returns the text beside it, or
`None` if there is no such heading (`jobspy/linkedin/util.py:42`). The caller then
lowercases it:

```python
job_level=job_details.get("job_level", "").lower(),   # jobspy/linkedin/__init__.py:235
```

**The defect.** The `""` default only applies when the key is *absent*, which is
the failed-fetch case (`_get_job_details` returns `{}`). When the page is fetched
the key is always present, and when the heading is missing its value is `None`.
`None.lower()` raises `AttributeError`; the scrape loop converts it into
`LinkedInException` (`jobspy/linkedin/__init__.py:162`), which propagates out of
`scrape_jobs`.

**The blast radius.** Our collector catches it per source
(`app/collect/client.py:89`), records `runs.error` / `counts_by_site`, and moves
on — so the run survives. But the rows JobSpy had already gathered for that
search live in a local list and are lost with the exception. One odd page costs
every LinkedIn posting for that search term in that run.

**When it would fire.** Any fetched page without the English heading:

* LinkedIn removes or renames the criteria block, or changes its markup;
* LinkedIn serves the page in another language despite JobSpy's
  `accept-language: en-US` header (the heading match is English-only);
* a posting type that has no seniority criterion at all.

**It has not fired yet.** ADR-0017 records `runs.error` empty on every run on file,
and LinkedIn returning 17–20 rows per search. This is a latent risk, not the
cause of the hidden LinkedIn postings — those are ADR-0017's question.

**The tripwire already exists.** `test_a_page_without_an_english_seniority_heading_yields_no_label`
is a strict `xfail(raises=AttributeError)`: it reproduces the crash against the
installed library today and turns red the day an upgrade fixes it. Alongside it,
a version-pin test fails on any JobSpy upgrade, and `--live` tests check the real
boards.

## Decision Drivers

* A lost search conceals postings the operator never learns existed — the
  governing asymmetry of deduplication and of spec 003. It is worse than a
  missing label, which merely falls back to the title (FR-006) and admits on
  unknown (FR-005).
* Patches to third-party internals fail silently on upgrade unless something
  pins them.
* The upgrade path should stay open; JobSpy is the collector's only engine
  (ADR-0003).
* The label is already optional by design: `""` and NULL are handled
  everywhere downstream, so *a page with no label* is a case the application
  copes with. Only JobSpy fails to.

## Options considered

| Option | What it does | What it costs |
|---|---|---|
| **A. Pin and accept** | Pin `python-jobspy==1.1.82` and leave the behaviour as is; rely on `runs.error` to notice | The crash stays; when it fires, a whole search is lost until someone reads the run log |
| **B. Patch the seam in `collect/`** | At import, wrap the `parse_job_level` name *imported into* `jobspy.linkedin` (not the one in `jobspy.linkedin.util`) so it returns `""` instead of `None` | A monkeypatch of a third-party module. Kept honest by the version-pin test and by the strict xfail, which would have to be inverted into a positive test of the patch |
| **C. Fix upstream, then pin to the fix** | Open a PR on JobSpy (`(job_details.get("job_level") or "").lower()`), pin to the release or commit that carries it | Depends on upstream's pace; pinning to a commit is a git dependency in `pyproject.toml` |
| **D. Retry without descriptions** | On `LinkedInException`, re-run that search with `linkedin_fetch_description` off | Recovers the rows, but without descriptions or labels for the whole search — and a description-less LinkedIn row silently disables the experience criterion's primary input (ADR-0016, ADR-0017) |

B and C are not exclusive: B can be the bridge while C is pending, and is
removed when the pinned version carries the fix (the xfail turning red is the
signal).

## Decision

**Option C — fixed upstream, pinned to the fix.** The defect was reported and
fixed in JobSpy itself: [speedyapply/JobSpy#354](https://github.com/speedyapply/JobSpy/pull/354)
("fix(linkedin): handle None job_level when LinkedIn omits 'Seniority level'"),
merged 29 September 2026 and released in **1.2.0** (2 October 2026; its release
notes: "a missing seniority level no longer crash[es]"). The upstream fix moves
the lowercasing into the parser and passes the value through, so a page without
the heading yields `None` instead of raising.

We pin **`python-jobspy>=1.4.1,<2`**, not merely 1.2.0. From 1.2.0 a failing
board logs instead of raising; only from 1.4.0 does it report the failure in the
frame (`attrs["errors"]`), which is what lets the collector keep recording it in
`runs.error`. A 1.2.x/1.3.x pin would have fixed this crash and silenced every
other one.

No monkeypatch (option B) and no description-less retry (option D) was needed.

### What the upgrade changed in this application

| Change in JobSpy 1.2.0 – 1.4.1 | What we did |
|---|---|
| Failing boards log instead of raising; `attrs["errors"]` / `["warnings"]` on the frame (1.4.0) | `collect/client.py` copies `attrs["errors"]` into `CollectionResult.errors` (so `runs.error`) and logs warnings. Rows a board returned before failing are now kept *and* the error recorded |
| `linkedin_fetch_description` deprecated for `fetch_description` (1.2.0; removed in 2.0) | `collect/sites.py` sends `fetch_description`; the setting keeps its name, so stored settings need no migration |
| `Country` enum reduced to bare names, ten countries dropped (1.4.0) | `normalise/country.py` built its name→ISO2 map from that enum; it came out **empty**, which would have changed every fingerprint. Our country table is now frozen in our code, identical to the one 1.1.82 produced (148 entries), and imports nothing from JobSpy. A separate mapper, `collect/jobspy_country.py`, translates our countries to JobSpy 1.4's `Country` values for `country_indeed` (`united kingdom` → `uk`, `turkey` → `türkiye`) and refuses, per site, the ten countries 1.4.0 dropped |
| A page that cannot be fetched keeps the job (1.3.0); its `job_level` is `None`, not `""` | Both already mean "the board said nothing" downstream (FR-005); contract test updated |
| `desired_order` removed; columns are `JobPost`'s fields (1.4.0) | Contract test checks `JobPost.model_fields` |
| Indeed renders the country name ("Egypt") where it rendered the code ("EG") | Both resolve to `EG`; covered in `test_country.py` |

## Consequences

* A LinkedIn page without an English "Seniority level" heading now costs that
  posting its label, not the search its rows. The posting falls back to the title
  (FR-006) and is admitted when the title is silent (FR-005).
* A board that fails reaches `runs.error` as `BoardError: <message>`, alongside
  whatever rows it returned first. Exceptions out of `scrape_jobs` are now mostly
  bad arguments (`ValueError` / `TypeError`), still caught per source.
* **One-off, at the upgrade:** JobSpy 1.2.0/1.3.0 stopped inferring `is_remote`
  from descriptions (LinkedIn, Indeed) and from "hybrid" (Indeed). `is_remote`
  selects the fingerprint's location token (`REMOTE` vs the country), so a
  posting first collected as remote under 1.1.82 and re-collected now may land
  as a second posting. Only postings still inside the `hours_old` window are
  exposed; the effect does not recur.
* Two country vocabularies, one seam. Ours (the fingerprint's) no longer
  follows JobSpy; JobSpy's (what `country_indeed` accepts) is reached only
  through `collect/jobspy_country.py`. A country JobSpy learns to render that is
  not in our table resolves to `UNKNOWN` and is counted per run, as before.
* A profile whose country JobSpy cannot search (unknown, or one of the ten it
  dropped) now fails its Indeed/Glassdoor search with `UnsupportedCountry` in
  `runs.error`, without a request; LinkedIn, which ignores the country, still
  runs. Before, an unknown value went to JobSpy unchecked.
* `linkedin_fetch_description` must become `fetch_description` before JobSpy 2.0;
  the `<2` bound holds that until someone decides it.

## Relationship to other records

Relates to [ADR-0016](0016-collect-stage-filter-verdicts.md), which promoted
`job_level` and recorded its dependence on `linkedin_fetch_description`, and to
[ADR-0017](0017-board-seniority-label-reliability.md), which questions how far
the label is trusted. This record concerns whether the label's *absence* can be
survived at all. [ADR-0020](0020-seniority-for-boards-without-a-label.md) covers
the boards that never supply it.

## Control

`tests/test_jobspy_contract.py`:

* `test_jobspy_is_the_version_these_contracts_were_written_against` pins 1.4.1;
  any upgrade turns it red and names what to re-read.
* `test_a_page_without_an_english_seniority_heading_yields_no_label` — formerly a
  strict xfail reproducing the crash — is now a positive test, and
  `test_such_a_page_no_longer_costs_the_whole_search` drives `scrape_jobs` end to
  end to prove the search survives.
* `uv run pytest --live tests/test_jobspy_contract.py` checks the real boards;
  run it after any upgrade. It passed against LinkedIn and Indeed on
  18 November 2026.

`tests/test_collect.py` pins that a board error reported in the frame reaches
`CollectionResult.errors`; `tests/test_country.py` pins the frozen country map;
`tests/test_jobspy_country.py` checks the mapper against the installed JobSpy —
every mapped value is a valid `Country`, every `Country` is mapped, and our
codes equal JobSpy's own — so an upgrade that moves a country fails there.
