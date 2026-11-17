"""How a verdict is assembled from parts (ADR-0016, ADR-0018) — pure, no database.

The title verdict is `all_of(global, any_of(profiles))`. Every property below is
one the shape has to have, and several are failures of the shape that was
considered and discarded: nesting the global rule inside the per-profile loop
makes it vanish for a posting no run accounts for, so the same title under the
same exclude pattern would be kept or rejected according to whether a `Run` row
happened to exist.

SC-002 sets the balance: cases proving nothing is wrongly withheld outnumber
those proving rejection works.
"""

import pytest

from app.filters import (
    Contributor,
    Criteria,
    ProfileInput,
    TitleRules,
    all_of,
    any_of,
    build_criteria,
    evaluate,
    resolve_profile,
)

NONE = None


# --- the two combinators ------------------------------------------------------


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], None),
        ([None], None),
        ([None, None], None),
        ([True], True),
        ([True, None], True),  # what was not applied is skipped, not counted as a pass
        ([None, True], True),
        ([True, True], True),
        ([False], False),
        ([False, None], False),
        ([False, True], False),
        ([True, False], False),
    ],
)
def test_all_of_ignores_what_was_not_applied(verdicts, expected):
    assert all_of(verdicts) is expected


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], None),
        ([None], None),
        ([None, None], None),
        ([True], True),
        ([True, None], True),
        ([True, False], True),
        ([None, False], True),  # a contributor with nothing to say cannot withhold
        ([False, None], True),
        ([False, False], False),
        ([False], False),
    ],
)
def test_any_of_admits_if_any_contributor_does(verdicts, expected):
    assert any_of(verdicts) is expected


def test_any_of_does_not_depend_on_order():
    for verdicts in ([True, False, None], [None, False, True], [False, True, None]):
        assert any_of(verdicts) is True
        assert any_of(list(reversed(verdicts))) is True


# --- evaluate: the title verdict ----------------------------------------------


def _titles(*, include: str = "", exclude: str = "") -> TitleRules:
    return TitleRules.compile(include, exclude)


def _verdict(title: str, *, global_rules: TitleRules, contributors=()):
    return evaluate(
        title=title,
        criteria=Criteria(titles=global_rules, contributors=tuple(contributors)),
    ).title_passed


def test_sc006_no_rule_anywhere_applies_no_criterion():
    """The no-op property: with nothing configured at any level the verdict is
    NULL, not "admitted" — installing this changes nothing."""
    plain = Contributor()
    assert _verdict("Data Engineer", global_rules=_titles(), contributors=[plain]) is None
    assert _verdict("Data Engineer", global_rules=_titles(), contributors=[plain, plain]) is None
    assert _verdict("Data Engineer", global_rules=_titles()) is None


def test_the_global_rule_binds_a_posting_no_run_accounts_for():
    """THE CLIFF. With no contributor at all the global exclude must still apply.
    Nesting it inside the per-profile loop would return None here — and the same
    title would be kept or rejected according to whether a Run row existed."""
    assert _verdict("QA Analyst", global_rules=_titles(exclude="qa analyst")) is False
    # Applied and admitted, not "not applied": the rule ran and let this one through.
    assert _verdict("Data Engineer", global_rules=_titles(exclude="qa analyst")) is True


def test_the_global_rule_binds_whatever_the_profiles_say():
    silent = Contributor()
    permissive = Contributor(titles=_titles(include="analyst"))
    rules = _titles(exclude="analyst")
    assert _verdict("QA Analyst", global_rules=rules, contributors=[silent]) is False
    assert _verdict("QA Analyst", global_rules=rules, contributors=[permissive]) is False
    assert _verdict("QA Analyst", global_rules=rules, contributors=[silent, permissive]) is False


def test_a_profile_rule_applies_when_there_is_no_global_rule():
    contributor = Contributor(titles=_titles(exclude="intern"))
    assert _verdict("Data Intern", global_rules=_titles(), contributors=[contributor]) is False
    assert _verdict("Data Engineer", global_rules=_titles(), contributors=[contributor]) is True


def test_a_global_rule_with_a_silent_profile_matches_the_global_rule_alone():
    """Global set, profile blank behaves exactly as global alone (pinned against
    the behaviour before profiles carried rules)."""
    rules = _titles(exclude="qa analyst")
    silent = Contributor()
    for title in ("QA Analyst", "Data Engineer", "Backend Developer"):
        alone = _verdict(title, global_rules=rules)
        with_silent = _verdict(title, global_rules=rules, contributors=[silent])
        assert alone == with_silent


def test_exclude_beats_include_across_levels():
    """Profile include 'engineer', global exclude 'data': the exclude wins."""
    contributor = Contributor(titles=_titles(include="engineer"))
    assert (
        _verdict("Data Engineer", global_rules=_titles(exclude="data"), contributors=[contributor])
        is False
    )


def test_exclude_beats_include_within_one_profile():
    contributor = Contributor(titles=_titles(include="engineer", exclude="data"))
    assert _verdict("Data Engineer", global_rules=_titles(), contributors=[contributor]) is False
    assert _verdict("Backend Engineer", global_rules=_titles(), contributors=[contributor]) is True


def test_a_silent_contributor_defeats_anothers_exclude_deliberately():
    """DELIBERATE (ADR-0018). Under the governing asymmetry a false rejection
    conceals a posting unrecoverably, so a contributor that imposes nothing wins."""
    excluding = Contributor(titles=_titles(exclude="analyst"))
    silent = Contributor()
    assert (
        _verdict("Data Analyst", global_rules=_titles(), contributors=[excluding, silent]) is True
    )
    assert (
        _verdict("Data Analyst", global_rules=_titles(), contributors=[silent, excluding]) is True
    )


def test_every_contributor_excluding_rejects():
    a = Contributor(titles=_titles(exclude="analyst"))
    b = Contributor(titles=_titles(exclude="data"))
    assert _verdict("Data Analyst", global_rules=_titles(), contributors=[a, b]) is False


def test_a_profile_include_that_matches_admits():
    contributor = Contributor(titles=_titles(include="engineer"))
    assert _verdict("Data Engineer", global_rules=_titles(), contributors=[contributor]) is True


def test_the_requested_levels_stay_aligned_with_the_contributors():
    """One record per profile, so level and rules cannot come from different sets."""
    from app.filters import Level

    a = Contributor(requested=Level.ENTRY, titles=_titles(exclude="x"))
    b = Contributor(requested=None)
    criteria = Criteria(titles=_titles(), contributors=(a, b))
    assert criteria.requested_levels == (Level.ENTRY, None)


# --- fault attribution ----------------------------------------------------------


def test_a_fault_names_its_profile():
    rules = TitleRules.compile("", "developer(", source="Backend developer")
    assert rules.errors
    assert "Backend developer" in rules.errors[0]
    assert "title_exclude_pattern" in rules.errors[0]


def test_a_global_fault_is_unchanged_by_the_source_label_existing():
    """No source, no prefix — the messages the operator already knows keep reading
    exactly as they did."""
    rules = TitleRules.compile("", "developer(")
    assert rules.errors[0].startswith("title_exclude_pattern")
    assert "profile" not in rules.errors[0]


def test_a_malformed_profile_pattern_disables_only_itself():
    rules = TitleRules.compile("engineer", "developer(", source="P")
    assert rules.exclude is None
    assert rules.include is not None
    assert len(rules.errors) == 1


def test_none_is_an_unset_pattern_like_empty():
    """A profile with no rule stores NULL, which must read as 'disabled'."""
    rules = TitleRules.compile(None, None, source="P")
    assert not rules.enabled
    assert rules.errors == ()


def test_criteria_errors_are_global_then_profile_and_deduplicated():
    bad = resolve_profile(ProfileInput(name="P", title_exclude_pattern="a("))
    criteria = Criteria(
        titles=TitleRules.compile("", "z("),
        contributors=(bad, bad),  # the same profile contributing twice
    )
    assert len(criteria.errors) == 2
    assert criteria.errors[0].startswith("title_exclude_pattern")
    assert "profile 'P'" in criteria.errors[1]


# --- resolving a stored profile -------------------------------------------------


def test_a_profile_with_nothing_set_resolves_to_a_silent_contributor():
    contributor = resolve_profile(ProfileInput(name="plain"))
    assert contributor.requested is None
    assert not contributor.titles.enabled
    assert contributor.unreadable_experience is None


def test_a_profile_less_run_resolves_to_a_silent_contributor():
    contributor = resolve_profile(ProfileInput())
    assert contributor == Contributor()


def test_a_readable_experience_resolves():
    from app.filters import Level

    assert resolve_profile(ProfileInput(experience="entry level")).requested == Level.ENTRY
    assert resolve_profile(ProfileInput(experience="junior")).requested == Level.ENTRY


def test_an_unreadable_experience_is_no_requirement_and_is_carried_for_reporting():
    contributor = resolve_profile(ProfileInput(name="P", experience="entery lvl"))
    assert contributor.requested is None
    assert contributor.unreadable_experience == "entery lvl"


def test_a_blank_experience_is_not_reported_as_unreadable():
    for blank in (None, "", "   "):
        assert resolve_profile(ProfileInput(experience=blank)).unreadable_experience is None


# --- build_criteria ---------------------------------------------------------------


def test_build_criteria_compiles_each_distinct_profile_once():
    """The hoisting that keeps a malformed pattern from being reported once per
    posting: a shared cache means one compile per profile, however many postings."""
    profile = ProfileInput(name="P", title_exclude_pattern="analyst")
    cache: dict = {}
    first = build_criteria(_titles(), [profile], resolved=cache)
    second = build_criteria(_titles(), [profile], resolved=cache)
    assert first.contributors[0] is second.contributors[0]
    assert len(cache) == 1


def test_build_criteria_without_a_cache_still_works():
    criteria = build_criteria(_titles(), [ProfileInput(name="P", title_exclude_pattern="x")])
    assert len(criteria.contributors) == 1


def test_build_criteria_with_no_profiles_has_no_contributors():
    assert build_criteria(_titles(exclude="x"), []).contributors == ()
