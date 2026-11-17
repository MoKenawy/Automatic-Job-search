# ADR-0019: JobSpy's LinkedIn seniority parse — guarding against a whole-search crash

* Status: proposed
* Deciders: Mohammed
* Date: 17 November 2026

Technical Story: writing contract tests against JobSpy's real `job_level` output
(`app/tests/test_jobspy_contract.py`) turned up a latent defect in the library: a
LinkedIn job page that loads but carries no English "Seniority level" heading
makes JobSpy raise, and the raise discards the **whole** LinkedIn search for that
term, not one row. This record states the evidence and the options and
**decides nothing**. It is proposed, not accepted — see [Decision](#decision).

## Context and Problem Statement

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

**Deferred.** No behaviour changes with this record. It stays *proposed* until
the operator chooses, and becomes accepted (with the chosen option stated here)
or superseded.

## Consequences

Until this is settled:

* A LinkedIn page without an English "Seniority level" heading loses that
  search's LinkedIn rows for the run. `runs.error` and `counts_by_site` show it;
  nothing else does.
* The next scheduled run re-searches, so a transient cause (one odd posting)
  usually heals itself; a structural one (LinkedIn markup change) would not.
* A JobSpy upgrade is caught by the version-pin test before it can change this
  behaviour unobserved.

## Relationship to other records

Relates to [ADR-0016](0016-collect-stage-filter-verdicts.md), which promoted
`job_level` and recorded its dependence on `linkedin_fetch_description`, and to
[ADR-0017](0017-board-seniority-label-reliability.md), which questions how far
the label is trusted. This record concerns whether the label's *absence* can be
survived at all. [ADR-0020](0020-seniority-for-boards-without-a-label.md) covers
the boards that never supply it.

## Control

Watch `runs.error` for `NoneType` / `lower` on LinkedIn. Re-run
`uv run pytest --live tests/test_jobspy_contract.py` after any JobSpy upgrade and
periodically; if `test_live_linkedin_labels_are_all_readable` fails with the
crash, the risk has become an incident and this should be settled.
