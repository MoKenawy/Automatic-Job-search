"""Seniority levels: the boards' vocabulary, the operator's, and the ordering.

Three readings of "seniority" meet here and must not be confused:

1. what a board *declared* — a label from a small controlled vocabulary
   (`mid-senior level`, `entry level`, `associate`, `director`, …), delivered
   lowercased and sometimes as the empty string;
2. what the operator *asked for* — free text on a search profile, which may say
   `fresh`, `entry level` or `senior` (FR-002, and deliberately not migrated);
3. what a *title* suggests, when a board declared nothing (FR-006).

All three resolve to the same ordered scale, and all three may resolve to
nothing. Returning `None` rather than a sentinel is the rule
`normalise.country.parse_country` already sets: an unresolved value stays
unresolved and is counted, never guessed. Here it matters more than there —
under FR-005 an unknown level admits the posting, so a guess in the wrong
direction conceals it.

`Level` therefore has **no** `UNKNOWN` member. An unknown inside an orderable
enum eventually meets a `<=` and silently admits or rejects everything; keeping
it outside the type makes that unrepresentable rather than merely guarded
(ADR-0016).
"""

import re
from collections.abc import Iterable
from enum import IntEnum

from app.filters.combine import any_of

__all__ = [
    "BOARD_LABELS",
    "Level",
    "admits",
    "admits_any",
    "is_unrecognised_label",
    "level_from_title",
    "merge_labels",
    "parse_level",
    "parse_requested",
]


class Level(IntEnum):
    """Seniority, ordered (FR-007). Comparison is the whole point of the type."""

    INTERNSHIP = 1
    ENTRY = 2
    ASSOCIATE = 3
    MID_SENIOR = 4
    DIRECTOR = 5
    EXECUTIVE = 6


# The boards' controlled vocabulary, keyed on the canonical form (see _canonical).
# Measured on the live corpus 16 November 2026: mid-senior level, entry level,
# associate, director and the empty string all occur; internship and executive are
# documented members of the vocabulary not yet seen.
#
# In practice "the boards" is one board. Under JobSpy 1.4.1 only the LinkedIn
# scraper sets `job_level`, and only when `linkedin_fetch_description` is on
# (passed to JobSpy as `fetch_description`): it reads the text beside the English
# "Seniority level" heading on the job page and lowercases it, or leaves None
# when there is no such heading (ADR-0019). No other scraper sets the field
# (ADR-0020). The library's output is pinned against this table by
# tests/test_jobspy_contract.py, and a label that escapes it is logged by stage 2
# rather than silently left unpromoted.
BOARD_LABELS: dict[str, Level] = {
    "internship": Level.INTERNSHIP,
    "entry level": Level.ENTRY,
    "associate": Level.ASSOCIATE,
    "mid senior level": Level.MID_SENIOR,
    "director": Level.DIRECTOR,
    "executive": Level.EXECUTIVE,
}

# Spellings that mean "no information", not "a level". The board's own vocabulary
# includes `not applicable`, and rows also arrive with an empty label — the
# collector yields "" rather than null when LinkedIn descriptions are not fetched.
# These are absence of evidence and must never be read as a mismatch (FR-005).
_UNKNOWN_LABELS = frozenset({"", "not applicable", "na", "n a", "none", "unknown"})

# The operator's vocabulary (FR-002). Free text already stored on profiles must
# become effective without re-entry, so this is generous about phrasing while
# refusing to invent a level it cannot recognise.
_REQUESTED_SYNONYMS: dict[str, Level] = {
    "intern": Level.INTERNSHIP,
    "internship": Level.INTERNSHIP,
    "trainee": Level.INTERNSHIP,
    "placement": Level.INTERNSHIP,
    "fresh": Level.ENTRY,
    "fresher": Level.ENTRY,
    "freshers": Level.ENTRY,
    "graduate": Level.ENTRY,
    "grad": Level.ENTRY,
    "junior": Level.ENTRY,
    "jr": Level.ENTRY,
    "entry": Level.ENTRY,
    "entry level": Level.ENTRY,
    "beginner": Level.ENTRY,
    "associate": Level.ASSOCIATE,
    "mid": Level.MID_SENIOR,
    "midlevel": Level.MID_SENIOR,
    "mid level": Level.MID_SENIOR,
    "mid senior": Level.MID_SENIOR,
    "mid senior level": Level.MID_SENIOR,
    "intermediate": Level.MID_SENIOR,
    "senior": Level.MID_SENIOR,
    "sr": Level.MID_SENIOR,
    "lead": Level.MID_SENIOR,
    "staff": Level.MID_SENIOR,
    "principal": Level.MID_SENIOR,
    "manager": Level.MID_SENIOR,
    "director": Level.DIRECTOR,
    "head": Level.DIRECTOR,
    "executive": Level.EXECUTIVE,
    "chief": Level.EXECUTIVE,
    "vp": Level.EXECUTIVE,
    "c level": Level.EXECUTIVE,
}

# Title markers for the FR-006 fallback, matched as whole tokens. Deliberately
# smaller than the operator vocabulary above: a title is weaker evidence than a
# declaration, and this list is the feature's chief false-rejection risk, so a
# marker earns its place only if it is unambiguous in a job title.
#
# Where a marker could plausibly sit at two levels it is mapped to the *lower*
# one. `principal` and `staff` are the cases: reading them as mid-senior admits
# them for a mid-senior request, and admission is the direction a false reading
# must fail in (FR-005, ADR-0016).
_TITLE_MARKERS: dict[str, Level] = {
    "intern": Level.INTERNSHIP,
    "internship": Level.INTERNSHIP,
    "trainee": Level.INTERNSHIP,
    "apprentice": Level.INTERNSHIP,
    "junior": Level.ENTRY,
    "jr": Level.ENTRY,
    "graduate": Level.ENTRY,
    "grad": Level.ENTRY,
    "fresher": Level.ENTRY,
    "entry": Level.ENTRY,
    "associate": Level.ASSOCIATE,
    "senior": Level.MID_SENIOR,
    "sr": Level.MID_SENIOR,
    "lead": Level.MID_SENIOR,
    "principal": Level.MID_SENIOR,
    "staff": Level.MID_SENIOR,
    "director": Level.DIRECTOR,
    "head": Level.DIRECTOR,
    "chief": Level.EXECUTIVE,
    "cto": Level.EXECUTIVE,
    "ceo": Level.EXECUTIVE,
    "cio": Level.EXECUTIVE,
    "vp": Level.EXECUTIVE,
    "president": Level.EXECUTIVE,
}

# How high a request reaches. FR-007's worked example is explicit: a request for
# a fresh/entry-level role "admits internship, entry-level and associate postings
# and rejects mid-senior, director and executive ones" — so `associate` is inside
# an entry request's reach even though it sits above `entry level` on the boards'
# own scale.
#
# That is not an exception to the at-or-below rule; it is what the boards mean.
# `associate` labels early-career roles that overlap entry level rather than a
# rung above it, which is why the specification groups them. Encoding it as a
# ceiling keeps the two levels distinct for storage and diagnosis — the board said
# `associate`, and the column records that — while the comparison treats them as
# one band. Any level absent from this mapping reaches exactly itself.
_ADMISSION_CEILING: dict[Level, Level] = {Level.ENTRY: Level.ASSOCIATE}

_NON_WORD = re.compile(r"[^\w\s]", flags=re.UNICODE)


def _canonical(text: str | None) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    So that `Mid-Senior level`, `mid senior level` and `MID-SENIOR LEVEL` are one
    key. Punctuation goes rather than being mapped, because the boards disagree
    about hyphens and the operator should not have to guess which form is stored.
    """
    if not text:
        return ""
    return " ".join(_NON_WORD.sub(" ", str(text)).split()).lower()


def parse_level(label: str | None) -> Level | None:
    """A board's declared seniority label as a `Level`, or `None` if it says nothing.

    `None`, the empty string, whitespace and `not applicable` are four spellings
    of one fact — no information — and all four return `None` (FR-005).

    A label outside the controlled vocabulary falls through to the operator's
    synonym table rather than being discarded: a board that says `senior` has told
    us something, and refusing to read it would be treating evidence as absence.
    """
    canonical = _canonical(label)
    if canonical in _UNKNOWN_LABELS:
        return None
    return BOARD_LABELS.get(canonical) or _REQUESTED_SYNONYMS.get(canonical)


def is_unrecognised_label(label: str | None) -> bool:
    """Whether a board said something about seniority that `parse_level` cannot read.

    Distinguishes two reasons `parse_level` returns `None`. A label that carries
    no information — absent, empty, `not applicable` — is the board saying
    nothing. A label that carries words outside every vocabulary here is the
    board saying something *we* did not understand: vocabulary drift, a layout
    change, a translated page.

    Both leave `postings.job_level` NULL, but only the second is a gap in this
    module. The label itself is not lost — `raw_postings.payload` keeps it
    verbatim (FR-012), so adding it to `BOARD_LABELS` and backfilling costs no
    re-scrape. What would be lost without this is *noticing*: stage 2 counts and
    logs these so drift shows up in the run log rather than in a payload query.
    """
    canonical = _canonical(label)
    if not canonical or canonical in _UNKNOWN_LABELS:
        return False
    return parse_level(label) is None


def parse_requested(text: str | None) -> Level | None:
    """A profile's requested experience as a `Level`, or `None` if unrecognised.

    `None` disables the experience criterion for that profile and is reported to
    the operator; it never rejects anything (FR-002a). That is why an unreadable
    value is distinguished from a readable one rather than defaulted.

    A whole-string match is tried first, then the individual words. Words that
    disagree — `junior to senior` — yield `None`: a request the system cannot read
    unambiguously is one it must not act on.
    """
    canonical = _canonical(text)
    if not canonical or canonical in _UNKNOWN_LABELS:
        return None

    exact = _REQUESTED_SYNONYMS.get(canonical)
    if exact is not None:
        return exact

    found = {_REQUESTED_SYNONYMS[word] for word in canonical.split() if word in _REQUESTED_SYNONYMS}
    if len(found) == 1:
        return found.pop()
    return None


def level_from_title(normalised_title: str | None) -> Level | None:
    """Best-effort seniority from a job title, where no board declared one (FR-006).

    Takes the *normalised* title: `normalise.title.normalise_title` has already
    lowercased it, folded accents and stripped punctuation while deliberately
    retaining seniority words, so matching whole tokens here gives word-boundary
    semantics for free — `internal` cannot match `intern`.

    Returns `None` wherever the title is silent **or** ambiguous. `Senior
    Internship Programme` resolves to nothing rather than to either reading,
    because a posting admitted on a shrug costs a glance while one rejected on a
    bad guess is gone.
    """
    tokens = _canonical(normalised_title).split()
    found = {_TITLE_MARKERS[token] for token in tokens if token in _TITLE_MARKERS}
    if len(found) == 1:
        return found.pop()
    return None


def merge_labels(labels: Iterable[str | None]) -> str | None:
    """The one label to store for a posting several boards surfaced (FR-009).

    The **minimum** seniority among the informative labels, ties broken
    lexicographically on the raw label. Minimum, not first-seen: the merged value
    must be a function of the *set* of contributing rows, not of which row
    happened to be processed first, which is what FR-009 asks for beyond mere
    convergence. The tie-break is what keeps the stored string itself
    deterministic, and so keeps SC-007 true of the column and not just of the
    verdict.

    Minimum is also the admitting direction: rejection happens only *above* the
    requested level (FR-007), so when boards disagree the lowest label is the one
    that shows the operator the posting.

    Labels that carry no level — absent, empty, `not applicable` — are not
    candidates. They would promote "the board said nothing useful" into a column
    whose NULL already says exactly that.
    """
    candidates = [
        (level, str(label)) for label in labels if (level := parse_level(label)) is not None
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda pair: (pair[0], pair[1]))[1]


def admits(requested: Level | None, actual: Level | None) -> bool | None:
    """Whether one profile's requested level admits a posting at `actual` (FR-007).

    `None` requested means the criterion is disabled for that profile — absent or
    unreadable experience — and returns `None`, not `True`: "not applied" and
    "applied and admitted" are different facts, and only the first makes
    installation a no-op (SC-006).

    `None` actual means the posting's level is unknown, which **admits** (FR-005).

    The comparison is deliberately asymmetric: every level at or below the request
    is admitted, everything above it rejected. A role below the requested level is
    worth the operator's glance; one well above it is not.

    "At or below" is measured against the request's reach, not its own ordinal —
    see `_ADMISSION_CEILING`, which puts `associate` inside an entry request's
    band because FR-007 says so and because that is how the boards use the label.
    """
    if requested is None:
        return None
    if actual is None:
        return True
    return actual <= _ADMISSION_CEILING.get(requested, requested)


def admits_any(requested: Iterable[Level | None], actual: Level | None) -> bool | None:
    """Combine the requests of every profile that surfaced a posting (ADR-0016).

    A disjunction: admitted if **any** contributing profile admits it. A posting
    can be surfaced by several profiles' runs, or by none at all through a manual
    `run-all`, and `services/reports.py` already records the same fan-out when it
    refuses to pick one profile to credit.

    Reading one run's profile instead would make the verdict depend on which run
    happened to be filtered last — it would alternate rather than converge, which
    breaks FR-010 and SC-007 and leaves a whole-corpus re-apply with no defined
    meaning (research R1). Disjunction is commutative, associative and idempotent,
    so the verdict is order-independent by construction.

    An entry of `None` is a contributor that imposes no requirement — a
    profile-less run, or a profile with absent or unreadable experience — and it
    admits unconditionally. When *every* contributor is like that, the criterion
    was never applied, and the answer is `None`.
    """
    return any_of(admits(request, actual) for request in requested)
