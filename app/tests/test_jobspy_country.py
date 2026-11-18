"""The seam between our country vocabulary and JobSpy's (`collect/jobspy_country`).

Our table (`normalise/country.py`) is frozen and JobSpy-free; the mapper is a
literal table too. These tests are what ties the mapper to the installed JobSpy:
on an upgrade that adds, drops or renames a country, or changes its code, they
fail and say which — rather than a profile's search quietly going to the wrong
Indeed site.
"""

import pandas as pd
import pytest
from jobspy.indeed.constant import country_codes
from jobspy.model import Country

from app.collect.client import collect_one
from app.collect.jobspy_country import (
    JOBSPY_COUNTRY,
    UNSUPPORTED_BY_JOBSPY,
    UnsupportedCountry,
    from_jobspy,
    to_iso2,
    to_jobspy,
)
from app.config import RunConfig, SearchSpec
from app.normalise.country import NAME_TO_ISO2

# --- the mapper against the installed JobSpy --------------------------------


def test_every_mapped_value_is_a_jobspy_country():
    """JobSpy 1.4 raises ValueError on any `country_indeed` it does not know."""
    invalid = [v for v in JOBSPY_COUNTRY.values() if Country(v).value != v]
    assert not invalid, invalid


def test_every_jobspy_country_is_mapped():
    """A country JobSpy adds must be added here (and to our table) deliberately."""
    unmapped = {c.value for c in Country} - set(JOBSPY_COUNTRY.values())
    assert not unmapped, f"JobSpy countries with no mapping: {sorted(unmapped)}"


def test_our_codes_are_jobspys_codes():
    """The mapper's keys must be the codes JobSpy itself uses for each country
    (its Indeed code table) — the codes boards' location strings carry."""
    disagree = {
        iso2: country_codes[Country(value)].lower()
        for iso2, value in JOBSPY_COUNTRY.items()
        if country_codes[Country(value)].lower() != iso2
    }
    assert not disagree, disagree


def test_every_country_in_our_table_is_mapped_or_known_unsupported():
    ours = set(NAME_TO_ISO2.values())
    assert set(JOBSPY_COUNTRY) | UNSUPPORTED_BY_JOBSPY == ours
    assert not set(JOBSPY_COUNTRY) & UNSUPPORTED_BY_JOBSPY


def test_the_unsupported_countries_are_really_gone_from_jobspy():
    values = {c.value for c in Country}
    names = {
        name for iso2 in UNSUPPORTED_BY_JOBSPY for name, i in NAME_TO_ISO2.items() if i == iso2
    }
    assert not names & values


# --- translation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("ours", "jobspy"),
    [
        ("egypt", "egypt"),  # the default profile country
        ("Egypt ", "egypt"),
        ("EG", "egypt"),
        ("saudi arabia", "saudi arabia"),
        ("united arab emirates", "united arab emirates"),
        ("united kingdom", "uk"),
        ("gb", "uk"),
        ("uk", "uk"),
        ("united states", "usa"),
        ("us", "usa"),
        ("turkey", "türkiye"),
        ("czechia", "czech republic"),
    ],
)
def test_to_jobspy(ours, jobspy):
    assert to_jobspy(ours) == jobspy


@pytest.mark.parametrize("country", ["croatia", "Slovenia", "bd", "malta"])
def test_a_country_jobspy_dropped_is_refused_by_name(country):
    with pytest.raises(UnsupportedCountry, match="no Indeed/Glassdoor site"):
        to_jobspy(country)


@pytest.mark.parametrize("country", ["atlantis", "", None, "usa/ca"])
def test_an_unknown_country_is_refused_not_defaulted(country):
    """Passing nothing would make JobSpy search the USA instead."""
    with pytest.raises(UnsupportedCountry, match="unknown country"):
        to_jobspy(country)


def test_round_trip():
    for iso2, value in JOBSPY_COUNTRY.items():
        assert from_jobspy(value) == iso2
        assert to_iso2(value) == iso2
    assert from_jobspy("atlantis") is None


# --- the collector ----------------------------------------------------------


def test_the_collector_sends_jobspys_value(monkeypatch):
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr("app.collect.client.scrape_jobs", capture)
    collect_one(SearchSpec(term="x", country="united kingdom", sites=["indeed"]), RunConfig())

    assert seen["country_indeed"] == "uk"


def test_an_unsupported_country_fails_that_site_only(monkeypatch):
    """Recorded for Indeed without a request; LinkedIn, which ignores the
    country, is still collected."""
    called = []

    def responder(**kwargs):
        called.append(kwargs["site_name"])
        return pd.DataFrame([{"title": "a"}])

    monkeypatch.setattr("app.collect.client.scrape_jobs", responder)
    spec = SearchSpec(term="x", country="croatia", sites=["indeed", "linkedin"])

    result = collect_one(spec, RunConfig(request_delay_seconds=0))

    assert called == [["linkedin"]]
    assert result.errors["indeed"].startswith("UnsupportedCountry:")
    assert result.counts_by_site == {"indeed": 0, "linkedin": 1}
