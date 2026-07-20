"""Employer normalisation tests.

The governing asymmetry (design §7.3): displaying one posting twice is a
nuisance; concealing a posting behind a false merge is a lost opportunity.
Tests therefore assert *non*-merging at least as hard as merging.
"""

import pytest

from app.normalise.employer import normalise_employer


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Alstom", "alstom"),              # OBSERVED — Indeed
        ("ALSTOM", "alstom"),              # OBSERVED — casing differs by board
        ("Coca-Cola HBC", "coca cola hbc"),  # OBSERVED — LinkedIn
        ("AtkinsRéalis", "atkinsrealis"),  # OBSERVED — accent stripped
        ("Valleysoft", "valleysoft"),      # OBSERVED
    ],
)
def test_observed_employers(raw, expected):
    assert normalise_employer(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acme Inc", "acme"),
        ("Acme, Inc.", "acme"),
        ("Acme LLC", "acme"),
        ("Acme Ltd.", "acme"),
        ("Acme Limited", "acme"),
        ("Acme GmbH", "acme"),
        ("Acme S.A.E.", "acme"),        # Egyptian joint-stock form
        ("Acme W.L.L.", "acme"),        # Gulf form
        ("Acme FZE", "acme"),           # UAE free zone
        ("Acme Co.", "acme"),
    ],
)
def test_legal_suffixes_removed(raw, expected):
    assert normalise_employer(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Acme Technologies",
        "Acme Solutions",
        "Acme Group",
        "Acme Systems",
    ],
)
def test_descriptor_words_retained(raw):
    """Removing these would merge genuinely distinct employers (design §7.3)."""
    assert normalise_employer(raw) != "acme"


def test_descriptors_do_not_collide_with_each_other():
    names = ["Acme Technologies", "Acme Solutions", "Acme Group", "Acme"]
    normalised = [normalise_employer(n) for n in names]
    assert len(set(normalised)) == len(names), "distinct employers merged"


def test_suffix_word_midname_is_retained():
    """'Company' here is part of the name, not a trailing legal form."""
    assert normalise_employer("Company of Egypt") == "company of egypt"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Halan - حالا", "halan"),        # OBSERVED — LinkedIn, bilingual branding
        ("sonnen Egypt", "sonnen egypt"),  # OBSERVED
    ],
)
def test_bilingual_names_prefer_latin(raw, expected):
    """One board may carry only the Latin form; keeping both defeats the match."""
    assert normalise_employer(raw) == expected


def test_arabic_only_name_is_preserved():
    """Not every employer has a Latin form; do not empty the key."""
    assert normalise_employer("شركة المقاولون") != ""


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_unusable_input(raw):
    assert normalise_employer(raw) == ""
