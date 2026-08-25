"""Aggregations for the report surface (ADR-0008).

Kept apart from `services/queries.py`, which is the read model for the triage
interface. Reports answer a different question on a different cadence, and
folding six aggregations into that module would obscure both.

Every function computes on demand. NFR-1 bounds the system to under a hundred
postings a day, so each of these is a single GROUP BY or one pass over a few
thousand rows; a materialised summary would cost more in staleness than it saves
in milliseconds (reports-implementation-plan.md §4.1). Revisit above roughly
100,000 postings.

Each report is admitted by ADR-0008 §1 on condition that its sampling bias is
displayed with its output — the caveat text lives in the templates and is
asserted by `tests/test_web_reports.py`, because a caveat nothing tests is a
caveat that disappears in the next layout change.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    STATUSES,
    Employer,
    Posting,
    RawPosting,
    RawPostingNormalization,
    Run,
    SearchProfile,
)
from app.services import queries


def _aware(value: datetime | None) -> datetime | None:
    """Normalise a stored timestamp so it can be compared against `now`.

    PostgreSQL returns aware datetimes for `DateTime(timezone=True)`; SQLite has
    no native datetime and returns naive ones. Subtracting one from the other
    raises, so every timestamp leaving the database is put on the same footing
    here. Values are written as UTC throughout the pipeline.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --- R1: employer hiring activity ---------------------------------------------


@dataclass
class EmployerActivity:
    """One employer's hiring footprint within what this system collected."""

    employer: Employer
    # Volume. The fingerprint collapses one real-world role to one row, so this
    # is a count of distinct roles, not of board listings.
    postings: int
    # Breadth. Twelve postings across three titles is an employer repeatedly
    # filling the same three roles — a different signal from twelve distinct
    # titles, and the reason both numbers are shown side by side.
    titles: int
    first_seen: datetime
    latest_seen: datetime
    # Days since this employer last surfaced a *new* role. Rising while volume
    # stays high is an employer that has gone quiet.
    days_quiet: int
    by_status: dict[str, int] = field(default_factory=dict)


def employer_activity(
    session: Session,
    *,
    limit: int = 50,
    include_suppressed: bool = False,
    now: datetime | None = None,
) -> list[EmployerActivity]:
    """Employers ranked by how many distinct roles they surfaced.

    Suppressed employers are excluded by default — their postings are hidden
    from every operator-facing view (ADR-0015) — but remain available behind
    `include_suppressed`, since a blacklisted employer hiring heavily is worth
    being able to see.

    `now` is injectable so `days_quiet` is testable without freezing the clock.
    """
    now = now or datetime.now(UTC)

    stmt = (
        select(
            Employer,
            func.count(Posting.id),
            func.count(func.distinct(Posting.normalised_title)),
            func.min(Posting.first_seen_at),
            func.max(Posting.first_seen_at),
        )
        .join(Posting, Posting.employer_id == Employer.id)
        .group_by(Employer.id)
        .order_by(func.count(Posting.id).desc(), Employer.name)
        .limit(limit)
    )
    if not include_suppressed:
        stmt = stmt.where(Employer.suppressed.is_(False))

    rows = session.execute(stmt).all()
    if not rows:
        return []

    # Status breakdown as a second pass rather than a crosstab: portable across
    # both dialects, and restricted to the employers this page actually shows.
    ids = [employer.id for employer, *_ in rows]
    by_employer: dict[int, dict[str, int]] = defaultdict(dict)
    for employer_id, status, count in session.execute(
        select(Posting.employer_id, Posting.status, func.count())
        .where(Posting.employer_id.in_(ids))
        .group_by(Posting.employer_id, Posting.status)
    ).all():
        by_employer[employer_id][status] = count

    activity = []
    for employer, postings, titles, first_seen, latest_seen in rows:
        latest = _aware(latest_seen)
        activity.append(
            EmployerActivity(
                employer=employer,
                postings=postings,
                titles=titles,
                first_seen=first_seen,
                latest_seen=latest_seen,
                days_quiet=(now - latest).days if latest else 0,
                by_status=by_employer.get(employer.id, {}),
            )
        )
    return activity


# --- R3: source coverage and overlap ------------------------------------------


@dataclass
class SourceOverlap:
    """What each board contributes, and which one gets there first."""

    sites: list[str]
    # Postings carrying each board in `sources`
    per_site: dict[str, int]
    # Which board combinations occur, most common first, e.g. ("indeed",) and
    # ("indeed", "linkedin")
    combinations: list[tuple[tuple[str, ...], int]]
    # Strictly-first counts, over contested postings only
    first_by: dict[str, int]
    # Contested postings where the boards recorded the same instant
    ties: int
    # Postings carrying more than one board — the denominator for first_by/ties,
    # kept separate because a single-board posting has no race to win
    contested: int
    total: int


def _first_seen(entry: object) -> datetime | None:
    """Read a board's `first_seen` out of its provenance entry.

    Stored as an ISO string by `normalise_stage`. Parsed rather than compared
    lexically: the two agree for a consistent format, but nothing guarantees the
    format stays consistent, and a silent mis-ordering here would be invisible.
    """
    if not isinstance(entry, dict):
        return None
    raw = entry.get("first_seen")
    if not raw:
        return None
    try:
        return _aware(datetime.fromisoformat(str(raw)))
    except ValueError:
        return None


def source_overlap(session: Session) -> SourceOverlap:
    """Per-board coverage, cross-board overlap, and first-surfacer counts.

    Aggregated in Python rather than in SQL. `sources` is JSONB in production and
    JSON under SQLite, and reading a *nested* value portably across the two is
    worse than the key-membership problem `queries._has_source` already exists to
    work around. At this scale one pass over the column is both cheaper and
    correct (reports-implementation-plan.md §4.2).

    The site vocabulary comes from `queries.known_sites`, which is also why board
    names are not enumerated from the JSON keys — though any key actually present
    is still counted, so a board missing from that list cannot go unreported.

    Parameters:
        session: Open SQLAlchemy session. It is the only input: every `postings`
            row is read, with no status, date, or suppressed-employer filter, so
            the figures cover the whole table rather than a triage subset.

    Returns:
        A `SourceOverlap` filled as follows.

        `sites` is `queries.known_sites` plus any key observed in `sources`,
        sorted. Keys are counted as written — nothing here normalises spelling or
        checks them against a vocabulary. `per_site` and `first_by` are keyed by
        that same list, carrying 0 for a site never seen. `combinations` pairs
        each distinct sorted tuple of a posting's keys with its count, in
        `Counter.most_common()` order, so equal counts fall back to the order the
        combination was first encountered.

        `total` counts every row scanned, including rows whose `sources` is NULL
        or empty; those contribute to nothing else. `contested` counts only
        postings carrying two or more boards *and* two or more parseable
        `first_seen` stamps, and is the denominator for `first_by` and `ties` —
        it can therefore sit below the number of multi-board postings.
        `first_by` moves only when exactly one board holds the earliest stamp;
        an equal earliest stamp increments `ties` instead.

    Error behaviour:
        Nothing is raised here, and malformed provenance is skipped rather than
        reported. A `sources` entry that is not a dict, carries no `first_seen`,
        or carries one `datetime.fromisoformat` rejects yields no stamp (see
        `_first_seen`), so the posting drops out of `contested`, `first_by` and
        `ties` while still counting toward `per_site`, `combinations` and
        `total` — an under-count that leaves no trace in the output. Naive
        stamps are read as UTC (`_aware`). An empty table returns zeroed counts
        over whatever `known_sites` reports. Database errors propagate from the
        session untouched.
    """
    sites = list(queries.known_sites(session))
    per_site: Counter[str] = Counter()
    first_by: Counter[str] = Counter()
    combinations: Counter[tuple[str, ...]] = Counter()
    ties = 0
    contested = 0
    total = 0

    # Deliberate opt-out from not_suppressed() (ADR-0015, FR-017): this report
    # measures what the collector returned, not what the operator should act
    # on. Filtering would understate a board's coverage.
    for sources in session.scalars(select(Posting.sources)):
        total += 1
        sources = sources or {}
        if not sources:
            continue

        present = tuple(sorted(sources))
        combinations[present] += 1
        per_site.update(present)

        if len(sources) < 2:
            continue

        # Which board got there first. Every site processed in one run shares a
        # single `now` (normalise_stage computes it once), so two boards
        # surfacing a role in the same run record an identical timestamp. That
        # is a real tie — "both had it at that collection" — and is reported as
        # its own category rather than broken arbitrarily, which would turn dict
        # ordering into a finding.
        stamps = {
            site: seen
            for site, entry in sources.items()
            if (seen := _first_seen(entry)) is not None
        }
        if len(stamps) < 2:
            continue

        contested += 1
        earliest = min(stamps.values())
        winners = [site for site, seen in stamps.items() if seen == earliest]
        if len(winners) == 1:
            first_by[winners[0]] += 1
        else:
            ties += 1

    for site in per_site:
        if site not in sites:
            sites.append(site)

    return SourceOverlap(
        sites=sorted(sites),
        per_site={site: per_site.get(site, 0) for site in sorted(sites)},
        combinations=combinations.most_common(),
        first_by={site: first_by.get(site, 0) for site in sorted(sites)},
        ties=ties,
        contested=contested,
        total=total,
    )


# --- R?: triage status per search profile --------------------------------------


@dataclass
class ProfileStatusBreakdown:
    """One profile's postings, split by triage status."""

    profile: SearchProfile
    by_status: dict[str, int]
    total: int


def postings_by_profile_status(
    session: Session, *, include_disabled: bool = False
) -> list[ProfileStatusBreakdown]:
    """Triage status split for each search profile's postings.

    A `Posting` carries no direct link to `SearchProfile` — it is reached only
    via `Posting -> RawPostingNormalization -> RawPosting -> Run -> SearchProfile`
    (design §8, RawPostingNormalization docstring), and a posting can be
    surfaced by more than one profile's runs (or by none, via a profile-less
    manual run-all). Rather than pick one profile to credit, every matching
    profile counts the posting — so a posting seen by two profiles appears in
    both pie charts, and totals summed across profiles can exceed the number
    of distinct postings collected. That trade-off is the caveat the route
    surfaces (ADR-0008 §1); `func.count(distinct(...))` below only prevents a
    posting being double-counted *within* one profile's own multiple runs.
    """
    profiles_stmt = select(SearchProfile).order_by(SearchProfile.name)
    if not include_disabled:
        profiles_stmt = profiles_stmt.where(SearchProfile.enabled.is_(True))
    profiles = session.scalars(profiles_stmt).all()
    if not profiles:
        return []

    ids = [p.id for p in profiles]
    counts_stmt = (
        select(Run.profile_id, Posting.status, func.count(func.distinct(Posting.id)))
        .select_from(Run)
        .join(RawPosting, RawPosting.run_id == Run.id)
        .join(
            RawPostingNormalization,
            RawPostingNormalization.raw_posting_id == RawPosting.id,
        )
        .join(Posting, Posting.id == RawPostingNormalization.posting_id)
        .where(Run.profile_id.in_(ids))
        .group_by(Run.profile_id, Posting.status)
    )
    by_profile: dict[int, dict[str, int]] = defaultdict(dict)
    for profile_id, status, count in session.execute(counts_stmt).all():
        by_profile[profile_id][status] = count

    return [
        ProfileStatusBreakdown(
            profile=profile,
            by_status={s: by_profile.get(profile.id, {}).get(s, 0) for s in STATUSES},
            total=sum(by_profile.get(profile.id, {}).values()),
        )
        for profile in profiles
    ]
