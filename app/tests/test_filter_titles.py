"""The coarse title filter (design D6, SRS FR-16).

The first test in this module is the one that matters most. Both patterns ship
empty, and `re.search("", title)` matches every string — so a filter that
compiles its defaults and asks "did the exclude pattern match?" rejects the whole
corpus on the first run after installation. SC-006 says installing the feature
without setting criteria changes nothing observable, and that single test is what
holds it up.

Fixtures marked OBSERVED are titles the specification recorded arriving under a
web-developer search on 9 September 2026 — the postings that motivated this
criterion.
"""

import pytest

from app.filters.titles import TitleRules

# OBSERVED — arrived under the "Web Developer" profile and became postings
OFF_TOPIC = ["QA Analyst", "Boomi Technical Consultant", "IT Sales Systems Developer"]
ON_TOPIC = ["Web Developer", "Frontend Developer", "Full Stack Engineer"]


# --- SC-006: no criteria, no change -----------------------------------------


@pytest.mark.parametrize("title", OFF_TOPIC + ON_TOPIC)
def test_sc006_the_shipped_empty_patterns_reject_nothing(title):
    """SC-006 — the keystone of this module.

    `TitleRules.compile("", "")` is what every installation starts with. If
    emptiness were decided after compiling rather than before, `re.search("")`
    would match here and every posting in the database would be rejected at once.
    """
    rules = TitleRules.compile("", "")
    assert rules.enabled is False
    assert rules.verdict(title) is None


@pytest.mark.parametrize("pattern", ["", "   ", "\t", "\n  "])
def test_whitespace_only_patterns_are_also_disabled(pattern):
    """An operator clearing a field leaves whitespace as often as nothing."""
    assert TitleRules.compile(pattern, pattern).enabled is False


def test_a_disabled_criterion_reports_no_verdict_rather_than_a_pass():
    """`None`, not `True`: "not applied" and "applied and admitted" are different
    facts, and only the first keeps the verdict column's NULL honest (ADR-0016)."""
    assert TitleRules.compile().verdict("Anything At All") is None


# --- exclude ----------------------------------------------------------------


@pytest.mark.parametrize("title", OFF_TOPIC)
def test_an_exclude_rule_rejects_what_it_names(title):
    rules = TitleRules.compile("", "qa analyst|boomi|sales")
    assert rules.verdict(title) is False


@pytest.mark.parametrize("title", ON_TOPIC)
def test_an_exclude_rule_admits_everything_it_does_not_name(title):
    rules = TitleRules.compile("", "qa analyst|boomi|sales")
    assert rules.verdict(title) is True


# --- include ----------------------------------------------------------------


@pytest.mark.parametrize("title", ON_TOPIC)
def test_an_include_rule_admits_what_satisfies_it(title):
    rules = TitleRules.compile("developer|engineer", "")
    assert rules.verdict(title) is True


def test_an_include_rule_rejects_a_title_that_does_not_satisfy_it():
    rules = TitleRules.compile("developer|engineer", "")
    assert rules.verdict("QA Analyst") is False


# --- both together ----------------------------------------------------------


def test_exclude_wins_over_a_permissive_include():
    """An explicit "never show me this" beats a broad include rule."""
    rules = TitleRules.compile("developer", "sales")
    assert rules.verdict("IT Sales Systems Developer") is False


def test_both_rules_can_admit_the_same_title():
    rules = TitleRules.compile("developer", "sales")
    assert rules.verdict("Web Developer") is True


# --- case, and the absent title ---------------------------------------------


@pytest.mark.parametrize("title", ["WEB DEVELOPER", "web developer", "Web Developer"])
def test_matching_ignores_case_so_the_operator_need_not_think_about_it(title):
    assert TitleRules.compile("web developer", "").verdict(title) is True


@pytest.mark.parametrize("title", [None, ""])
def test_a_missing_title_is_admitted(title):
    """FR-005. `postings.title` is NOT NULL, so this is defence rather than a
    live case — but the direction it fails in is the one that matters."""
    assert TitleRules.compile("developer", "sales").verdict(title) is True


# --- malformed patterns (FR-008, US2 scenario 4) ----------------------------


def test_a_malformed_pattern_disables_its_criterion_and_reports():
    """The run completes, the fault is reported, and nothing is rejected on the
    strength of an unusable rule."""
    rules = TitleRules.compile("", "developer(")
    assert rules.exclude is None
    assert rules.errors
    assert "title_exclude_pattern" in rules.errors[0]


def test_a_malformed_pattern_does_not_raise():
    """Compilation happens once per run; an exception here would end the run,
    which FR-008 forbids."""
    TitleRules.compile("[unclosed", "also(bad")


def test_a_malformed_pattern_rejects_nothing():
    rules = TitleRules.compile("", "developer(")
    assert rules.enabled is False
    for title in OFF_TOPIC + ON_TOPIC:
        assert rules.verdict(title) is not False


def test_one_bad_pattern_does_not_disable_the_other():
    """An unusable exclude rule must not take a working include rule down with
    it — each criterion stands or falls on its own."""
    rules = TitleRules.compile("developer", "bad(")
    assert rules.include is not None
    assert rules.exclude is None
    assert len(rules.errors) == 1
    assert rules.verdict("Web Developer") is True
    assert rules.verdict("QA Analyst") is False


def test_a_valid_pattern_reports_no_errors():
    assert TitleRules.compile("developer", "sales").errors == ()
