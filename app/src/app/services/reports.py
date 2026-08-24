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

from app.db.models import Employer, Posting
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
