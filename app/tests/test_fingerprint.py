"""Fingerprint tests — the cross-board collision cases design §12 item 4 requires.

Coverage: seniority, discipline, locality and cross-board variants.
"""

import pytest

from app.normalise.fingerprint import (
    REMOTE_TOKEN,
    UNKNOWN_TOKEN,
    build_fingerprint,
)


def fp(employer, title, location, is_remote=False):
    return build_fingerprint(
        employer=employer, title=title, location_raw=location, is_remote=is_remote
    ).digest


# --- cross-board: the case that motivated §7.3.1 ----------------------------


def test_same_role_from_indeed_and_linkedin_collides():
    """The decisive test. These are OBSERVED renderings of one real-world city."""
    indeed = fp("ALSTOM", "Data Engineer", "القاهرة, C, EG")
    linkedin = fp("Alstom", "Data Engineer", "Cairo, Egypt")
    assert indeed == linkedin


def test_linkedin_internal_inconsistency_collides():
    """LinkedIn alone returns both forms; they must not produce two records."""
    a = fp("Alstom", "Data Engineer", "Cairo, Egypt")
    b = fp("Alstom", "Data Engineer", "Cairo, Cairo, Egypt")
    assert a == b


def test_cosmetic_employer_variation_collides():
    a = fp("Acme Technologies Inc", "Data Engineer", "Cairo, Egypt")
    b = fp("Acme Technologies, Inc.", "Data Engineer", "Cairo, Egypt")
    assert a == b


# --- seniority and discipline must NOT collide ------------------------------


@pytest.mark.parametrize(
    ("title_a", "title_b"),
    [
        ("Data Engineer", "Senior Data Engineer"),
        ("Data Engineer", "Junior Data Engineer"),
        ("Data Engineer", "Lead Data Engineer"),
        ("Data Engineer", "Staff Data Engineer"),
    ],
)
def test_seniority_variants_do_not_collide(title_a, title_b):
    """Merging these conceals a posting — the intolerable failure (§7.3)."""
    assert fp("Acme", title_a, "Cairo, Egypt") != fp("Acme", title_b, "Cairo, Egypt")


@pytest.mark.parametrize(
    ("title_a", "title_b"),
    [
        ("Data Engineer", "Data Analyst"),
        ("Data Engineer", "Data Scientist"),
        ("Data Engineer", "Software Engineer"),
        ("Data Engineer", "Machine Learning Engineer"),
    ],
)
def test_discipline_variants_do_not_collide(title_a, title_b):
    assert fp("Acme", title_a, "Cairo, Egypt") != fp("Acme", title_b, "Cairo, Egypt")


def test_distinct_employers_do_not_collide():
    assert fp("Acme", "Data Engineer", "Cairo, Egypt") != fp(
        "Acme Technologies", "Data Engineer", "Cairo, Egypt"
    )


# --- locality ---------------------------------------------------------------


def test_different_countries_do_not_collide():
    assert fp("Acme", "Data Engineer", "Cairo, Egypt") != fp(
        "Acme", "Data Engineer", "Dubai, United Arab Emirates"
    )


def test_same_country_different_city_collides_by_design():
    """Accepted cost of D12. Both source URLs are retained under provenance."""
    assert fp("Acme", "Data Engineer", "Cairo, Egypt") == fp(
        "Acme", "Data Engineer", "Alexandria, Egypt"
    )


# --- remote and unresolved --------------------------------------------------


def test_remote_collapses_regardless_of_stated_location():
    """Boards disagree on the nominal location of a remote role (§7.3)."""
    a = fp("Acme", "Data Engineer", "Cairo, Egypt", is_remote=True)
    b = fp("Acme", "Data Engineer", "Anywhere, United States", is_remote=True)
    assert a == b


def test_remote_and_onsite_do_not_collide():
    onsite = fp("Acme", "Data Engineer", "Cairo, Egypt")
    remote = fp("Acme", "Data Engineer", "Cairo, Egypt", is_remote=True)
    assert onsite != remote


def test_unresolved_country_is_distinct_from_remote():
    """UNKNOWN must be countable separately, not merged into the remote bucket."""
    parts_unknown = build_fingerprint(
        employer="Acme", title="Data Engineer", location_raw="Somewhere, Nowhere"
    )
    parts_remote = build_fingerprint(
        employer="Acme", title="Data Engineer", location_raw=None, is_remote=True
    )
    assert parts_unknown.location == UNKNOWN_TOKEN
    assert parts_remote.location == REMOTE_TOKEN
    assert parts_unknown.digest != parts_remote.digest
    assert not parts_unknown.country_resolved


# --- properties -------------------------------------------------------------


def test_deterministic():
    args = dict(employer="Acme Inc", title="Data Engineer", location_raw="Cairo, Egypt")
    assert build_fingerprint(**args).digest == build_fingerprint(**args).digest


def test_digest_fits_declared_column_width():
    """Posting.fingerprint is String(64); sha256 hex is exactly 64 chars."""
    assert len(fp("Acme", "Data Engineer", "Cairo, Egypt")) == 64


def test_parts_are_exposed_for_diagnosis():
    parts = build_fingerprint(
        employer="Acme Inc", title="Senior Data Engineer", location_raw="Cairo, Egypt"
    )
    assert parts.employer == "acme"
    assert parts.title == "senior data engineer"
    assert parts.location == "EG"
    assert parts.country_resolved
