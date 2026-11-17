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

from app.filters.levels import Level, admits_any, level_from_title, parse_level
from app.filters.titles import TitleRules

__all__ = ["Criteria", "Verdict", "evaluate"]

# Where the seniority used for the verdict came from. Diagnosis, not storage:
# `postings.job_level` holds the board's own label and never an inference
# (ADR-0012's lesson, restated in data-model.md).
SOURCE_BOARD = "board"
SOURCE_TITLE = "title"


@dataclass(frozen=True)
class Criteria:
    """What one posting is judged against.

    `titles` is global — operator-editable settings shared across the pipeline.
    `requested_levels` is per posting: the requested level of every search profile
    that has surfaced it, with `None` for a contributor that imposes no
    requirement (a profile-less run, or a profile whose experience is absent or
    unreadable). An empty tuple means nothing has surfaced it at all, and the
    experience criterion does not apply.
    """

    titles: TitleRules = field(default_factory=TitleRules)
    requested_levels: tuple[Level | None, ...] = ()

    @property
    def errors(self) -> tuple[str, ...]:
        """Faults the operator must be told about (FR-002a, FR-008)."""
        return self.titles.errors


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

    return Verdict(
        title_passed=criteria.titles.verdict(title),
        experience_passed=admits_any(criteria.requested_levels, level),
        level=level,
        level_source=source,
    )
