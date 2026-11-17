"""One posting, two criteria, one verdict (FR-004).

Pure: no database, no session, no configuration. The stage supplies the criteria
and the posting's stored fields; this decides, and decides the same way every
time it is asked. That is the whole of FR-010 and SC-007 — `evaluate` is total
and order-free, and nothing here records when it ran.

The verdict is two tri-state booleans, one per criterion, and the grounds for a
rejection are *derived* from them rather than stored (ADR-0016). FR-011 makes
criteria changes routine, so a stored reason would be stale exactly when it
matters: the operator reads the grounds because they are about to loosen the rule
that produced them.
"""

from dataclasses import dataclass, field

from app.filters.combine import all_of, any_of
from app.filters.levels import Level, admits_any, level_from_title, parse_level
from app.filters.titles import TitleRules

__all__ = ["Contributor", "Criteria", "Verdict", "evaluate"]

# Where the seniority used for the verdict came from. Diagnosis, not storage:
# `postings.job_level` holds the board's own label and never an inference
# (ADR-0012's lesson, restated in data-model.md).
SOURCE_BOARD = "board"
SOURCE_TITLE = "title"


@dataclass(frozen=True)
class Contributor:
    """What one search profile that surfaced a posting asks for.

    A profile-less run (a manual `run-all`) is a contributor with nothing set, as
    is a profile whose fields are blank: both impose no requirement, so both are
    the same thing to the criteria.

    Requested level and title rules travel **together**, in one record per
    profile, so that the two criteria cannot be assembled from different
    profile sets and quietly disagree about who contributed.

    `unreadable_experience` carries the profile's experience text when it could
    not be read, so the stage can report it (FR-002a). It plays no part in the
    verdict, where an unreadable value is simply no requirement.
    """

    requested: Level | None = None
    titles: TitleRules = field(default_factory=TitleRules)
    unreadable_experience: str | None = None


@dataclass(frozen=True)
class Criteria:
    """What one posting is judged against (ADR-0016, ADR-0018).

    `titles` is the **global** rule, from `/settings`: it binds every posting, and
    nothing about attribution can lift it. `contributors` is per posting — one
    record for each search profile that has surfaced it. An empty tuple means no
    run accounts for the posting at all.

    The two are not interchangeable and are not nested: the title verdict is
    `all_of(global, any_of(profiles))`. Nesting the global rule *inside* the
    per-profile loop would make it vanish for a posting with no contributor, so
    the same title, under the same exclude pattern, would be rejected or kept
    according to whether a `Run` row happened to exist — a cliff, not a rule.
    """

    titles: TitleRules = field(default_factory=TitleRules)
    contributors: tuple[Contributor, ...] = ()

    @property
    def requested_levels(self) -> tuple[Level | None, ...]:
        """The requested level of every contributing profile, in contributor order."""
        return tuple(contributor.requested for contributor in self.contributors)

    @property
    def errors(self) -> tuple[str, ...]:
        """Pattern faults the operator must be told about (FR-008).

        Global first, then each profile's — which already names the profile.
        Deduplicated in order: the same malformed pattern on a profile that
        contributed twice is one fault.
        """
        seen: dict[str, None] = dict.fromkeys(self.titles.errors)
        for contributor in self.contributors:
            seen.update(dict.fromkeys(contributor.titles.errors))
        return tuple(seen)


@dataclass(frozen=True)
class Verdict:
    """The outcome, with the inputs that produced it.

    Shaped on `normalise.fingerprint.FingerprintParts`: a frozen value object
    carrying its inputs alongside its result, so a surprising verdict can be
    explained without re-deriving it.

    Each criterion is tri-state, and the three states are different facts:
    `None` the criterion was not applied, `True` applied and admitted (including
    admitted *because* the input was unknown), `False` applied and rejected.
    """

    title_passed: bool | None = None
    experience_passed: bool | None = None
    level: Level | None = None
    level_source: str | None = None

    @property
    def rejected(self) -> bool:
        """Whether the filter withholds this posting on either ground."""
        return self.title_passed is False or self.experience_passed is False

    @property
    def grounds(self) -> str | None:
        """Which criterion rejected it (FR-016), or `None` if none did."""
        failed = [
            name
            for name, passed in (
                ("title", self.title_passed),
                ("experience", self.experience_passed),
            )
            if passed is False
        ]
        if not failed:
            return None
        return "both" if len(failed) == 2 else failed[0]


def evaluate(
    *,
    title: str | None,
    normalised_title: str | None = None,
    job_level: str | None = None,
    criteria: Criteria,
) -> Verdict:
    """Judge one posting against the criteria. Never raises.

    The board's declared label is preferred, and the title is consulted only
    where the board said nothing (FR-006) — one board supplies the label on every
    row and the other on none, so this fallback is the whole of the second
    board's seniority signal. Where both are silent the level is unknown, and
    unknown admits (FR-005).
    """
    level = parse_level(job_level)
    source = SOURCE_BOARD if level is not None else None

    if level is None:
        level = level_from_title(normalised_title)
        source = SOURCE_TITLE if level is not None else None

    # The global rule binds unconditionally; the profiles' rules are a
    # disjunction, exactly as the experience criterion's are, so that a profile
    # the operator is not thinking about cannot conceal what another asked for.
    title_passed = all_of(
        [
            criteria.titles.verdict(title),
            any_of(contributor.titles.verdict(title) for contributor in criteria.contributors),
        ]
    )

    return Verdict(
        title_passed=title_passed,
        experience_passed=admits_any(criteria.requested_levels, level),
        level=level,
        level_source=source,
    )
