"""Country resolution tests.

Fixtures marked OBSERVED are verbatim values captured from live boards on
20 July 2026 (design §4.3). They are the reason §7.3.1 was revised.
"""

import pytest

from app.normalise.country import NAME_TO_ISO2, parse_country


@pytest.mark.parametrize(
    "location_raw",
    [
        "القاهرة, C, EG",  # OBSERVED — Indeed, city localised to Arabic
        "Cairo, Egypt",  # OBSERVED — LinkedIn
        "Cairo, Cairo, Egypt",  # OBSERVED — LinkedIn, governorate repeated
    ],
)
def test_observed_egyptian_forms_all_resolve_to_eg(location_raw):
    """The decisive case: every real-world rendering must yield one value."""
    assert parse_country(location_raw) == "EG"


def test_observed_forms_are_mutually_consistent():
    """Explicitly assert cross-board agreement, not just individual correctness."""
    observed = ["القاهرة, C, EG", "Cairo, Egypt", "Cairo, Cairo, Egypt"]
    resolved = {parse_country(v) for v in observed}
    assert resolved == {"EG"}, f"boards disagree: {resolved}"


@pytest.mark.parametrize(
    ("location_raw", "expected"),
    [
        ("Dubai, United Arab Emirates", "AE"),
        ("Riyadh, Saudi Arabia", "SA"),
        ("London, United Kingdom", "GB"),
        ("London, UK", "GB"),
        ("Austin, TX, US", "US"),
        ("New York, United States", "US"),
        ("Berlin, Germany", "DE"),
        ("Amsterdam, Netherlands", "NL"),
        ("Toronto, ON, Canada", "CA"),
    ],
)
def test_country_names_and_codes(location_raw, expected):
    assert parse_country(location_raw) == expected


@pytest.mark.parametrize(
    ("location_raw", "expected"),
    [
        ("القاهرة, مصر", "EG"),
        ("دبي, الإمارات", "AE"),
    ],
)
def test_arabic_country_segment(location_raw, expected):
    assert parse_country(location_raw) == expected


@pytest.mark.parametrize("location_raw", [None, "", "   ", ",,,"])
def test_unusable_input_returns_none(location_raw):
    assert parse_country(location_raw) is None


def test_unresolvable_returns_none_rather_than_guessing():
    """A wrong code merges unrelated postings and conceals one. None is correct."""
    assert parse_country("Somewhere, Nowhere") is None


def test_trailing_noise_does_not_defeat_lookup():
    """Falls back through segments rather than trusting only the last."""
    assert parse_country("Cairo, Egypt, 11511") == "EG"


def test_map_excludes_non_countries():
    """WORLDWIDE and US_CANADA are not countries and must not pollute the map."""
    assert "worldwide" not in NAME_TO_ISO2
    assert "usa/ca" not in NAME_TO_ISO2
    assert all(len(v) == 2 for v in NAME_TO_ISO2.values())


def test_map_derived_from_jobspy_is_populated():
    """Guards against a JobSpy upgrade silently changing the Country enum shape."""
    assert len(NAME_TO_ISO2) > 50
    assert NAME_TO_ISO2["egypt"] == "eg"
