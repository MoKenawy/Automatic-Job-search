"""Seniority levels: the vocabularies, the ordering, and the at-or-below band.

SC-002 governs the shape of this module: the assertions proving nothing is
wrongly rejected must be at least as numerous as those proving rejection works.
That is the suite's existing asymmetry (`CLAUDE.md` — assert non-merging at least
as hard as merging) restated for a filter, and it is why the admission cases below
outnumber the rejection cases rather than balancing them.

Fixtures marked OBSERVED are verbatim `job_level` values captured from the live
corpus on 16 November 2026 (60 raw rows): LinkedIn supplies the label on every
row, lowercased, and Indeed supplies none at all.
"""

import pytest

from app.filters.levels import (
    Level,
    admits,
    admits_any,
    is_unrecognised_label,
    level_from_title,
    merge_labels,
    parse_level,
    parse_requested,
)

# --- the scale ---------------------------------------------------------------


def test_levels_are_ordered_lowest_to_highest():
    """The whole type exists to be compared (FR-007)."""
    assert (
        Level.INTERNSHIP
        < Level.ENTRY
        < Level.ASSOCIATE
        < Level.MID_SENIOR
        < Level.DIRECTOR
        < Level.EXECUTIVE
    )


def test_no_unknown_member_exists():
    """Unknown is the absence of a Level, never a member of it (ADR-0016).

    An UNKNOWN inside an orderable enum eventually meets a `<=` and silently
    admits or rejects everything. This asserts the shape of the type, not a
    behaviour, which is why it is worth a test of its own.
    """
    absent = {"UNKNOWN", "NA", "NOT_APPLICABLE"}
    assert not any(name.upper() in absent for name in Level.__members__)


# --- board labels -----------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("mid-senior level", Level.MID_SENIOR),  # OBSERVED — LinkedIn, 22 rows
        ("entry level", Level.ENTRY),  # OBSERVED — LinkedIn, 7 rows
        ("associate", Level.ASSOCIATE),  # OBSERVED — LinkedIn, 2 rows
        ("director", Level.DIRECTOR),  # OBSERVED — LinkedIn, 1 row
        ("internship", Level.INTERNSHIP),  # documented vocabulary, not yet seen
        ("executive", Level.EXECUTIVE),  # documented vocabulary, not yet seen
        # The collector lowercases, but a board changing its mind must not break
        # the read, and punctuation differs between boards.
        ("Mid-Senior level", Level.MID_SENIOR),
        ("mid senior level", Level.MID_SENIOR),
        ("MID-SENIOR LEVEL", Level.MID_SENIOR),
    ],
)
def test_board_labels_parse(label, expected):
    assert parse_level(label) == expected


@pytest.mark.parametrize(
    "label",
    [
        None,
        "",
        "   ",
        "not applicable",  # OBSERVED — LinkedIn, 8 rows; in the board's own vocabulary
        "Not Applicable",
        "n/a",
        "unknown",
    ],
)
def test_every_spelling_of_unknown_yields_no_level(label):
    """Four spellings of one fact: no information (FR-005).

    The empty string is not hypothetical — the collector yields `""` rather than
    null for a LinkedIn row whose description was not fetched, so a sentinel here
    would silently become a level.
    """
    assert parse_level(label) is None


def test_an_unlisted_but_readable_label_is_still_evidence():
    """A board saying `senior` has told us something; refusing to read it would
    treat evidence as absence, which is the one direction this file guards."""
    assert parse_level("senior") == Level.MID_SENIOR


# --- unrecognised board labels (vocabulary drift) ---------------------------
#
# `is_unrecognised_label` is what stage 2 warns on. A false positive is noise in
# the log; a false negative is drift nobody notices. The "not unrecognised" set is
# kept the larger of the two, as everywhere in this file.


@pytest.mark.parametrize(
    "label",
    [
        "mid-senior level",  # OBSERVED
        "entry level",  # OBSERVED
        "associate",  # OBSERVED
        "director",  # OBSERVED
        "executive",  # OBSERVED — ADR-0017, 1 row
        "internship",  # OBSERVED — ADR-0017, 1 row
        "Mid-Senior level",  # as LinkedIn renders it, before the collector lowercases
        "senior",  # outside the board table but readable through the synonyms
        None,
        "",
        "   ",
        "not applicable",  # OBSERVED — the board saying nothing, not drift
        "Not Applicable",
        "n/a",
        "unknown",
    ],
)
def test_a_readable_or_uninformative_label_is_not_flagged(label):
    assert is_unrecognised_label(label) is False


@pytest.mark.parametrize(
    "label",
    [
        "senior level",
        "executive level",
        "premier emploi",  # a translated LinkedIn page
        "مستوى المبتدئين",
    ],
)
def test_a_label_no_vocabulary_reads_is_flagged(label):
    """The board said something; `parse_level` returning None here is a gap in
    this module, not an absence of evidence."""
    assert parse_level(label) is None
    assert is_unrecognised_label(label) is True


# --- requested experience (FR-002) ------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("entry level", Level.ENTRY),  # OBSERVED — stored on the AI Engineer profile
        ("fresh", Level.ENTRY),  # the value the specification names
        ("fresher", Level.ENTRY),
        ("graduate", Level.ENTRY),
        ("grad", Level.ENTRY),
        ("junior", Level.ENTRY),
        ("jr", Level.ENTRY),
        ("Entry Level", Level.ENTRY),
        ("  senior  ", Level.MID_SENIOR),
        ("senior", Level.MID_SENIOR),
        ("sr", Level.MID_SENIOR),
        ("mid-senior", Level.MID_SENIOR),
        ("lead", Level.MID_SENIOR),
        ("principal", Level.MID_SENIOR),
        ("intern", Level.INTERNSHIP),
        ("internship", Level.INTERNSHIP),
        ("associate", Level.ASSOCIATE),
        ("director", Level.DIRECTOR),
        ("head", Level.DIRECTOR),
        ("executive", Level.EXECUTIVE),
        ("vp", Level.EXECUTIVE),
        # Multi-word text whose words agree resolves to the level they agree on.
        ("fresh graduate", Level.ENTRY),
        ("junior developer", Level.ENTRY),
    ],
)
def test_stored_experience_values_become_effective_without_re_entry(text, expected):
    """FR-002 — the operator must not have to retype what they already stored."""
    assert parse_requested(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "0-2 years",  # a shape this release does not read
        "3+ years of experience",
        "whatever you have",
        "junior to senior",  # words disagree: unreadable rather than averaged
        "intern or director",
    ],
)
def test_an_unreadable_request_disables_rather_than_rejects(text):
    """FR-002a — a value the system cannot interpret must disable the criterion
    and be reported, never reject everything. `None` here is what the stage
    reports and what leaves the column NULL."""
    assert parse_requested(text) is None


# --- the at-or-below band (FR-007) ------------------------------------------


@pytest.mark.parametrize(
    "actual",
    [Level.INTERNSHIP, Level.ENTRY, Level.ASSOCIATE],
)
def test_entry_request_admits_at_or_below(actual):
    """A request for a fresh/entry role admits internship, entry and associate —
    the specification's own example, stated as an asymmetry rather than a match."""
    assert admits(Level.ENTRY, actual) is True


@pytest.mark.parametrize(
    "actual",
    [Level.MID_SENIOR, Level.DIRECTOR, Level.EXECUTIVE],
)
def test_entry_request_rejects_above(actual):
    assert admits(Level.ENTRY, actual) is False


@pytest.mark.parametrize(
    ("requested", "actual"),
    [
        (Level.ENTRY, Level.ASSOCIATE),
        (Level.ASSOCIATE, Level.ENTRY),
        (Level.MID_SENIOR, Level.ASSOCIATE),
        (Level.MID_SENIOR, Level.ENTRY),
    ],
)
def test_entry_and_associate_are_one_band(requested, actual):
    """FR-007's worked example puts `associate` inside an entry request's reach,
    even though it sits above `entry level` on the boards' scale. The boards use
    the label for early-career roles that overlap entry rather than for a rung
    above it, so the comparison treats them as one band while the column keeps
    recording whichever label the board actually gave."""
    assert admits(requested, actual) is True


def test_an_associate_request_still_rejects_mid_senior():
    """The band widens the floor, not the ceiling."""
    assert admits(Level.ASSOCIATE, Level.MID_SENIOR) is False


def test_a_senior_request_admits_a_junior_posting():
    """The asymmetry is deliberate: a role below the request is worth a glance."""
    assert admits(Level.MID_SENIOR, Level.ENTRY) is True


def test_unknown_actual_level_is_admitted_at_every_request():
    """FR-005 — absence of evidence is not evidence of mismatch. One board
    supplies no label on any row, so this is the common case, not the edge."""
    for requested in Level:
        assert admits(requested, None) is True


def test_no_request_disables_the_criterion_rather_than_admitting():
    """`None`, not `True`: "not applied" and "applied and admitted" are different
    facts, and only the first keeps installation a no-op (SC-006)."""
    assert admits(None, Level.EXECUTIVE) is None
    assert admits(None, None) is None


# --- several profiles, one posting (ADR-0016) -------------------------------


def test_any_admitting_profile_admits_the_posting():
    """A disjunction, so the verdict cannot depend on run order (research R1)."""
    assert admits_any([Level.ENTRY, Level.EXECUTIVE], Level.DIRECTOR) is True


def test_the_order_profiles_are_considered_in_does_not_matter():
    """The property FR-010 and SC-007 rest on: reading one run's profile instead
    would alternate with run order rather than converge."""
    forward = admits_any([Level.ENTRY, Level.EXECUTIVE], Level.DIRECTOR)
    backward = admits_any([Level.EXECUTIVE, Level.ENTRY], Level.DIRECTOR)
    assert forward is backward is True


def test_a_contributor_with_no_requirement_admits_unconditionally():
    """A profile-less `run-all`, or a profile with no experience recorded, imposes
    nothing — so it cannot withhold (the specification's own assumption)."""
    assert admits_any([None, Level.ENTRY], Level.EXECUTIVE) is True


def test_all_contributors_without_a_requirement_leave_the_criterion_unapplied():
    assert admits_any([None, None], Level.EXECUTIVE) is None


def test_no_contributors_at_all_leaves_the_criterion_unapplied():
    assert admits_any([], Level.EXECUTIVE) is None


def test_every_profile_must_reject_before_the_posting_is_rejected():
    assert admits_any([Level.ENTRY, Level.ASSOCIATE], Level.DIRECTOR) is False


def test_repeating_a_profile_changes_nothing():
    """Idempotence, the second half of why order cannot matter."""
    once = admits_any([Level.ENTRY], Level.DIRECTOR)
    twice = admits_any([Level.ENTRY, Level.ENTRY], Level.DIRECTOR)
    assert once is twice is False


# --- merging labels across boards (FR-009) ----------------------------------


def test_the_lowest_label_wins():
    """Minimum, not first-seen: the merged value is a function of the set of
    contributing rows, and the lowest label is the admitting one."""
    assert merge_labels(["mid-senior level", "entry level"]) == "entry level"


def test_merging_is_commutative():
    assert merge_labels(["entry level", "director"]) == merge_labels(["director", "entry level"])


def test_merging_is_idempotent():
    assert merge_labels(["associate", "associate"]) == "associate"


def test_uninformative_labels_are_not_candidates():
    """`not applicable` and `""` would promote "the board said nothing useful"
    into a column whose NULL already says exactly that."""
    assert merge_labels(["not applicable", "entry level", "", None]) == "entry level"


def test_all_uninformative_labels_merge_to_nothing():
    assert merge_labels(["not applicable", "", None]) is None
    assert merge_labels([]) is None


def test_ties_break_deterministically_on_the_raw_label():
    """Two spellings of one level must not store whichever was seen first, or
    SC-007 fails on the column even while every verdict agrees."""
    assert merge_labels(["mid senior level", "mid-senior level"]) == "mid senior level"
    assert merge_labels(["mid-senior level", "mid senior level"]) == "mid senior level"


# --- the title fallback (FR-006) --------------------------------------------


@pytest.mark.parametrize(
    ("normalised_title", "expected"),
    [
        ("senior data engineer", Level.MID_SENIOR),
        ("junior backend developer", Level.ENTRY),
        ("graduate software engineer", Level.ENTRY),
        ("data engineering intern", Level.INTERNSHIP),
        ("associate data scientist", Level.ASSOCIATE),
        ("director of engineering", Level.DIRECTOR),
        ("chief technology officer", Level.EXECUTIVE),
    ],
)
def test_a_title_can_stand_in_where_no_board_declared_a_level(normalised_title, expected):
    """The second board declares nothing on any row, so this is its only signal."""
    assert level_from_title(normalised_title) == expected


@pytest.mark.parametrize(
    "normalised_title",
    [
        None,
        "",
        "data engineer",
        "backend developer",
        "machine learning engineer",
        # Word boundaries: whole tokens only. The normalised title has already
        # had punctuation stripped, which is what makes this safe.
        "internal tools engineer",  # must not read as `intern`
        "senionara engineer",  # must not read as `senior`
        "leadership programme analyst",  # must not read as `lead`
        "grader systems engineer",  # must not read as `grad`
    ],
)
def test_a_silent_or_near_miss_title_yields_no_level(normalised_title):
    assert level_from_title(normalised_title) is None


@pytest.mark.parametrize(
    "normalised_title",
    [
        "senior internship programme",
        "junior to senior data engineer",
        "associate director",
        "graduate intern",
    ],
)
def test_an_ambiguous_title_refuses_to_guess(normalised_title):
    """Conflicting markers yield nothing, so the posting is admitted. A posting
    admitted on a shrug costs a glance; one rejected on a bad guess is gone."""
    assert level_from_title(normalised_title) is None
