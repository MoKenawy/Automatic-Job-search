"""From stored profile fields to the criteria one posting is judged against (ADR-0018).

There are two places that must reach the same verdict for the same posting: the
stage that records it (`pipeline/filter_stage.py`) and the detail page that
re-derives it live to say whether the stored one is stale
(`services/queries.current_verdict`). Before profiles carried title rules each
rebuilt a `Criteria` by hand, which was two lines and low-risk; with per-profile
rules it would be a compile, a parse and a combination, and a second hand-written
copy is exactly how a stored verdict and a displayed one come to disagree.
Hence one builder, here, in the pure package — so it is testable without a
database, and both callers import it.

Takes plain values rather than model objects: `filters/` imports nothing from
`db/`, and `db/attribution.py` hands over primitives.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.filters.levels import parse_requested
from app.filters.titles import TitleRules
from app.filters.verdict import Contributor, Criteria

__all__ = ["ProfileInput", "build_criteria", "resolve_profile"]


@dataclass(frozen=True)
class ProfileInput:
    """The stored fields of one contributing profile, as plain values.

    Hashable, so the stage can resolve each distinct profile once per application
    rather than once per posting. A profile-less run is the all-`None` instance.
    """

    name: str | None = None
    experience: str | None = None
    title_include_pattern: str | None = None
    title_exclude_pattern: str | None = None


def resolve_profile(profile: ProfileInput) -> Contributor:
    """Compile one profile's fields into a contributor.

    Nothing here can raise or reject. An unreadable experience becomes no
    requirement (FR-002a) and is recorded on the contributor so it can be
    reported; a malformed pattern disables itself and carries its fault
    (FR-008). Silently treating either as "no requirement" is how a typo in a
    profile would go unnoticed for months, which is why both travel with the
    result instead of being discarded.
    """
    requested = parse_requested(profile.experience)
    text = (profile.experience or "").strip()
    return Contributor(
        requested=requested,
        titles=TitleRules.compile(
            profile.title_include_pattern,
            profile.title_exclude_pattern,
            source=profile.name,
        ),
        unreadable_experience=text if requested is None and text else None,
    )


def build_criteria(
    titles: TitleRules,
    profiles: Iterable[ProfileInput],
    *,
    resolved: dict[ProfileInput, Contributor] | None = None,
) -> Criteria:
    """Assemble one posting's criteria from the global rule and its contributors.

    `resolved` is an optional cache the stage passes in so that a profile
    contributing to a thousand postings is compiled once — and its malformed
    pattern is therefore reported once, not a thousand times.
    """
    cache = resolved if resolved is not None else {}
    contributors = []
    for profile in profiles:
        if profile not in cache:
            cache[profile] = resolve_profile(profile)
        contributors.append(cache[profile])
    return Criteria(titles=titles, contributors=tuple(contributors))
