"""Collector tests.

Focused on the failure shapes measured against live boards (design §4.3): a
source refusing outright, and a source returning a DataFrame with no columns.
"""

import pandas as pd
import pytest

from app.collect.jobspy_client import _rows_from_frame, collect_one
from app.config import SearchSpec


def test_zero_by_zero_frame_yields_no_rows():
    """OBSERVED from Bayt (403) and Google: shape (0, 0), not merely no rows.

    Touching .columns on this frame would raise mid-run, converting a visible
    empty result into a crash.
    """
    assert _rows_from_frame(pd.DataFrame(), "bayt") == []


def test_none_frame_yields_no_rows():
    assert _rows_from_frame(None, "google") == []


def test_frame_with_columns_but_no_rows():
    df = pd.DataFrame(columns=["title", "company", "location"])
    assert _rows_from_frame(df, "indeed") == []


def test_nan_and_none_both_normalise_to_none():
    """JobSpy mixes None and float NaN in the same object column (OBSERVED)."""
    df = pd.DataFrame([{"title": "Data Engineer", "job_type": float("nan"), "level": None}])
    rows = _rows_from_frame(df, "indeed")
    assert rows[0]["job_type"] is None
    assert rows[0]["level"] is None


def test_site_is_stamped_when_absent():
    df = pd.DataFrame([{"title": "Data Engineer"}])
    rows = _rows_from_frame(df, "linkedin")
    assert rows[0]["site"] == "linkedin"


def test_site_from_frame_is_not_overwritten():
    df = pd.DataFrame([{"title": "Data Engineer", "site": "indeed"}])
    rows = _rows_from_frame(df, "linkedin")
    assert rows[0]["site"] == "indeed"


def test_failing_source_is_recorded_not_raised(monkeypatch):
    """Glassdoor raises outright for Egypt (OBSERVED). One bad source must not
    end the run — the other sources still have to be collected."""

    def boom(**kwargs):
        if kwargs["site_name"] == ["glassdoor"]:
            raise Exception("Glassdoor is not available for EGYPT")
        return pd.DataFrame([{"title": "Data Engineer", "company": "Acme"}])

    monkeypatch.setattr("app.collect.jobspy_client.scrape_jobs", boom)

    spec = SearchSpec(term="data engineer", sites=["glassdoor", "indeed"])
    result = collect_one(spec)

    assert "glassdoor" in result.errors
    assert result.counts_by_site["glassdoor"] == 0
    assert result.counts_by_site["indeed"] == 1
    assert result.total == 1


def test_counts_recorded_per_site(monkeypatch):
    """Per-site counts are how a single source silently dying becomes visible."""

    def responder(**kwargs):
        if kwargs["site_name"] == ["indeed"]:
            return pd.DataFrame([{"title": "a"}, {"title": "b"}])
        return pd.DataFrame()  # linkedin returns nothing

    monkeypatch.setattr("app.collect.jobspy_client.scrape_jobs", responder)

    result = collect_one(SearchSpec(term="x", sites=["indeed", "linkedin"]))
    assert result.counts_by_site == {"indeed": 2, "linkedin": 0}


@pytest.mark.parametrize(
    ("site", "expect_country_kwarg"),
    [("indeed", True), ("glassdoor", True), ("linkedin", False)],
)
def test_country_indeed_passed_only_where_it_applies(monkeypatch, site, expect_country_kwarg):
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr("app.collect.jobspy_client.scrape_jobs", capture)
    collect_one(SearchSpec(term="x", country="egypt", sites=[site]))

    assert ("country_indeed" in seen) is expect_country_kwarg


@pytest.mark.parametrize(
    ("site", "expect_fetch"),
    [("linkedin", True), ("indeed", False), ("glassdoor", False)],
)
def test_linkedin_description_fetch_passed_only_for_linkedin(monkeypatch, site, expect_fetch):
    """LinkedIn needs the extra per-posting fetch to obtain a description; other
    boards include it inline and must not carry the flag."""
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr("app.collect.jobspy_client.scrape_jobs", capture)
    collect_one(SearchSpec(term="x", country="egypt", sites=[site]))

    assert ("linkedin_fetch_description" in seen) is expect_fetch


def test_linkedin_description_fetch_can_be_disabled(monkeypatch):
    """The fetch is slower; it must be possible to turn off via configuration."""
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr("app.collect.jobspy_client.scrape_jobs", capture)
    monkeypatch.setattr(
        "app.collect.jobspy_client.settings.linkedin_fetch_description", False
    )
    collect_one(SearchSpec(term="x", sites=["linkedin"]))

    assert "linkedin_fetch_description" not in seen
