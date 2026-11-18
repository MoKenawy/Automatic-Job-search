"""Contract tests against JobSpy's real `job_level` output.

Every other test in the suite either stubs `scrape_jobs` or hand-types the
payload, so a JobSpy upgrade — or a LinkedIn page change — could alter the
labels the experience criterion reads and nothing here would notice. These
tests close that gap from two sides:

* **Offline (default suite).** They drive JobSpy 1.4.1's own LinkedIn code —
  `LinkedIn.scrape`, `_process_job` and the `_fetch_details` it calls — with the
  HTTP session replaced, and pin what comes out against `filters.levels`. The job
  card and job page below are **reconstructed from the CSS selectors JobSpy
  reads**, not captured from a live board, so they are deliberately not marked
  OBSERVED. They prove the library's parsing and our vocabulary agree; they
  cannot prove LinkedIn still serves that markup.
* **Live (`--live`, skipped by default).** They go through our own collector
  against the real boards, which is the only way to answer the second
  question. Run them after any JobSpy upgrade:
  `uv run pytest --live tests/test_jobspy_contract.py`.

What JobSpy 1.4.1 does, which these tests hold in place: only the LinkedIn
scraper sets `job_level`, and only with `fetch_description` on (our setting is
still called `linkedin_fetch_description`; `collect/sites.py` maps it). It reads
the text beside the English "Seniority level" heading on the job page
(`jobspy/linkedin/util.py` `criteria`) and lowercases it
(`jobspy/linkedin/__init__.py` `_fetch_details`). No other scraper sets the
field (ADR-0020). A page with no such heading, or a page that cannot be fetched,
yields `None` — the crash 1.1.82 had there was fixed upstream in 1.2.0
(speedyapply/JobSpy#354; ADR-0019).
"""

from importlib.metadata import version
from types import SimpleNamespace

import jobspy.linkedin
import pytest
from bs4 import BeautifulSoup
from jobspy import scrape_jobs
from jobspy.linkedin import LinkedIn
from jobspy.model import JobPost, ScraperInput, Site

from app.collect.client import collect_one
from app.config import RunConfig, SearchSpec
from app.filters.levels import Level, is_unrecognised_label, parse_level

# The version these tests were written against. Bumping it is a decision, not a
# chore: run the live tests first, re-read the LinkedIn scraper's job_level path,
# and only then move the pin.
PINNED_JOBSPY = "1.4.1"

# LinkedIn's "Seniority level" vocabulary as rendered on the job page, with the
# level each must resolve to. ADR-0017 counts all seven on the live corpus.
LINKEDIN_LABELS: list[tuple[str, Level | None]] = [
    ("Internship", Level.INTERNSHIP),
    ("Entry level", Level.ENTRY),
    ("Associate", Level.ASSOCIATE),
    ("Mid-Senior level", Level.MID_SENIOR),
    ("Director", Level.DIRECTOR),
    ("Executive", Level.EXECUTIVE),
    ("Not Applicable", None),  # the board saying nothing (FR-005)
]

_JOB_CARD = """
<div class="base-search-card" data-entity-urn="urn:li:jobPosting:123">
  <h3 class="base-search-card__title">Data Engineer</h3>
  <h4 class="base-search-card__subtitle"><a href="https://www.linkedin.com/company/acme">Acme</a></h4>
  <div class="base-search-card__metadata">
    <span class="job-search-card__location">Cairo, Cairo, Egypt</span>
    <time class="job-search-card__listdate" datetime="2026-11-16">1 day ago</time>
  </div>
</div>
"""

_CRITERIA_ITEM = """
<li class="description__job-criteria-item">
  <h3 class="description__job-criteria-subheader">{heading}</h3>
  <span class="description__job-criteria-text description__job-criteria-text--criteria">
    {value}
  </span>
</li>
"""


def _job_page(*criteria: tuple[str, str]) -> str:
    items = "".join(_CRITERIA_ITEM.format(heading=h, value=v) for h, v in criteria)
    return f"""
<html><body>
  <div class="show-more-less-html__markup"><p>Build pipelines.</p></div>
  <ul class="description__job-criteria-list">{items}</ul>
</body></html>
"""


class _Response:
    def __init__(self, text: str, url: str = "https://www.linkedin.com/jobs/view/123"):
        self.text = text
        self.url = url
        self.status_code = 200


def _session(page: str | None, search: str = _JOB_CARD) -> SimpleNamespace:
    """A stand-in for JobSpy's HTTP session: the search page returns `search`,
    every job page returns `page`. `page=None` makes the job-page request fail,
    as a timeout or a block would."""

    def get(url, *_args, **_kwargs):
        if "/jobs-guest/" in url:
            return _Response(search, url)
        if page is None:
            raise ConnectionError("simulated fetch failure")
        return _Response(page)

    return SimpleNamespace(get=get)


def _scrape_one(page: str | None) -> JobPost:
    """One posting through JobSpy's real LinkedIn job path, network replaced."""
    scraper = LinkedIn()
    scraper.scraper_input = ScraperInput(site_name=[Site.LINKEDIN], fetch_description=True)
    scraper.session = _session(page)
    card = BeautifulSoup(_JOB_CARD, "html.parser")
    return scraper._process_job(card, "123")


# --- the library itself -----------------------------------------------------


def test_jobspy_is_the_version_these_contracts_were_written_against():
    """The alarm for 'did the library change'. pyproject allows >=1.4.1,<2, so
    an upgrade arrives with `uv lock --upgrade` and nothing else would flag it."""
    installed = version("python-jobspy")
    assert installed == PINNED_JOBSPY, (
        f"python-jobspy is {installed}, these contracts pin {PINNED_JOBSPY}. "
        "Run `uv run pytest --live tests/test_jobspy_contract.py`, re-read "
        "jobspy/linkedin (criteria() and _fetch_details), fix whatever "
        "tests/test_jobspy_country.py reports in collect/jobspy_country.py "
        "(and its JOBSPY_VERSION), check ADR-0019 and ADR-0020 still describe "
        "it, then move PINNED_JOBSPY."
    )


def test_job_level_survives_into_the_scraped_frame():
    """Since 1.4.0 the frame's columns are `JobPost`'s fields, in order; a field
    dropped from the model would reach the collector as absent on every row."""
    assert "job_level" in JobPost.model_fields


def test_job_level_defaults_to_none_for_scrapers_that_never_set_it():
    """The Indeed shape: no scraper but LinkedIn assigns the field, so every
    other board's rows carry the model default (ADR-0020)."""
    assert JobPost.model_fields["job_level"].default is None


# --- LinkedIn's labels, end to end ------------------------------------------


@pytest.mark.parametrize(("rendered", "expected"), LINKEDIN_LABELS)
def test_every_linkedin_label_reaches_the_filter_readable(rendered, expected):
    """Pins the library's output and our vocabulary together: JobSpy must still
    deliver the label lowercased, and `parse_level` must still read it."""
    page = _job_page(("Seniority level", rendered), ("Employment type", "Full-time"))

    post = _scrape_one(page)

    assert post.job_level == rendered.lower()
    assert parse_level(post.job_level) == expected
    assert not is_unrecognised_label(post.job_level)


def test_a_failed_job_page_fetch_yields_no_label():
    """`_fetch_details` returns `{}` on a failed page, so the model default
    applies. Under 1.1.82 this was `""`; since 1.2.0 it is `None`. Both read
    as "the board said nothing" downstream (FR-005)."""
    post = _scrape_one(page=None)

    assert post.job_level is None
    assert parse_level(post.job_level) is None
    assert not is_unrecognised_label(post.job_level)


_NO_HEADING_PAGES = pytest.mark.parametrize(
    "page",
    [
        _job_page(("Employment type", "Full-time")),  # no seniority block at all
        _job_page(("Niveau hiérarchique", "Premier emploi")),  # a translated page
    ],
    ids=["no-seniority-block", "translated-heading"],
)


@_NO_HEADING_PAGES
def test_a_page_without_an_english_seniority_heading_yields_no_label(page):
    """The ADR-0019 crash, now a positive test. Under 1.1.82 this raised
    AttributeError (`None.lower()`); fixed upstream in 1.2.0 (#354)."""
    post = _scrape_one(page)

    assert post.job_level is None
    assert post.description  # the rest of the page was still read


@_NO_HEADING_PAGES
def test_such_a_page_no_longer_costs_the_whole_search(monkeypatch, page):
    """ADR-0019's blast radius, through `scrape_jobs` itself: the posting comes
    back and the board reports no error."""
    monkeypatch.setattr(jobspy.linkedin, "create_session", lambda *_a, **_k: _session(page))

    jobs = scrape_jobs(
        site_name="linkedin", search_term="data engineer", fetch_description=True, verbose=0
    )

    assert jobs.attrs["errors"] == {}
    assert list(jobs["title"]) == ["Data Engineer"]
    assert jobs["job_level"].isna().all()


# --- live (run with --live) -------------------------------------------------


def _live_config() -> RunConfig:
    return RunConfig(
        results_per_search=5,
        hours_old=168,
        request_delay_seconds=0,
        linkedin_fetch_description=True,
        proxies=[],
    )


@pytest.mark.live
def test_live_linkedin_labels_are_all_readable():
    spec = SearchSpec(term="software engineer", location="Cairo, Egypt", sites=["linkedin"])

    result = collect_one(spec, _live_config())

    assert "linkedin" not in result.errors, (
        f"LinkedIn collection failed: {result.errors.get('linkedin')}"
    )
    assert result.records, "LinkedIn returned no rows; nothing was checked"
    labels = [r.get("job_level") for r in result.records]
    assert all(label is None or isinstance(label, str) for label in labels), labels
    assert any(labels), "no LinkedIn row carried a label; is fetch_description reaching JobSpy?"
    unrecognised = sorted({label for label in labels if is_unrecognised_label(label)})
    assert not unrecognised, (
        f"LinkedIn delivered labels filters.levels cannot read: {unrecognised}. "
        "Add them to BOARD_LABELS (or _UNKNOWN_LABELS) and backfill."
    )


@pytest.mark.live
def test_live_indeed_declares_no_level():
    """Fact 1 of ADR-0020, re-measured: if Indeed starts supplying a level, that
    record's premise has changed and the title fallback is no longer its only
    seniority signal."""
    spec = SearchSpec(term="software engineer", location="Cairo", sites=["indeed"])

    result = collect_one(spec, _live_config())

    assert "indeed" not in result.errors, result.errors.get("indeed")
    assert result.records, "Indeed returned no rows; nothing was checked"
    assert all(r.get("job_level") is None for r in result.records)
