"""Read models for the triage interface.

Kept separate from the route handlers so the querying can be tested without a
web client, and so the templates receive plain data rather than ORM rows.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.config import WORKING_SITES
from app.db.models import STATUS_REJECTED, Employer, Posting, Run, SearchProfile

# Selects postings whose country could not be resolved. `parse_country` returns
# None rather than guessing (normalise/country.py), so this is a real bucket the
# operator needs to reach. ISO2 codes are two characters, so no code collides
# with this sentinel.
COUNTRY_UNKNOWN = "unknown"

# Rows per page in the triage list.
PAGE_SIZE = 50


@dataclass
class Totals:
    postings: int
    published: int
    scored: int
    by_status: dict[str, int]
    employers: int
    last_run: Run | None


def totals(session: Session) -> Totals:
    by_status = dict(
        session.execute(
            select(Posting.status, func.count()).group_by(Posting.status)
        ).all()
    )
    return Totals(
        postings=session.scalar(select(func.count()).select_from(Posting)) or 0,
        published=session.scalar(
            select(func.count()).select_from(Posting).where(Posting.published)
        ) or 0,
        scored=session.scalar(
            select(func.count()).select_from(Posting).where(Posting.score.isnot(None))
        ) or 0,
        by_status=by_status,
        employers=session.scalar(select(func.count()).select_from(Employer)) or 0,
        last_run=session.scalar(select(Run).order_by(Run.started_at.desc())),
    )


def _has_source(session: Session, source: str) -> ColumnElement:
    """`sources` is keyed by board name, so membership is a key test.

    Split by dialect rather than using the JSON comparator's `[key]` indexing
    uniformly: under SQLite that compiles to `JSON_QUOTE(JSON_EXTRACT(...))`,
    and `JSON_QUOTE(NULL)` is the *string* `'null'`, not SQL NULL — an absent
    key would then satisfy `IS NOT NULL` and the filter would select
    everything. `json_extract` alone does not have this problem.
    """
    if session.get_bind().dialect.name == "sqlite":
        return func.json_extract(Posting.sources, f"$.{source}").isnot(None)
    return Posting.sources[source].isnot(None)


@dataclass
class Page:
    """One page of postings, plus what a pager needs to render itself."""

    rows: list[tuple[Posting, Employer]]
    total: int
    number: int
    per_page: int

    @property
    def pages(self) -> int:
        # Never zero: an empty result still reads as "page 1 of 1" rather than
        # "page 1 of 0".
        return max(1, -(-self.total // self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.pages

    @property
    def first(self) -> int:
        """1-based position of the first row on this page; 0 when it is empty."""
        return (self.number - 1) * self.per_page + 1 if self.rows else 0

    @property
    def last(self) -> int:
        return (self.number - 1) * self.per_page + len(self.rows)


def _ordering(status: str | None) -> tuple:
    """Row order for the list, which depends on which bucket is being worked.

    The default is a ranking: score first, and unscored postings sort last
    rather than first, since `score` is NULL until stage 3 runs and NULLs would
    otherwise lead under PostgreSQL's default ordering.

    Under the Rejected filter the bucket is a log, not a ranking — what matters
    is what was rejected most recently — so `status_changed_at` leads instead.
    For a posting whose status *is* Rejected that timestamp is its rejection
    time, which is why no separate `rejected_at` column is needed. It is NULL
    only for postings born Rejected because their employer was already
    suppressed (`Posting.create`), which have no rejection event of their own;
    those sort last.

    Every ordering ends on `id`, which is unique and stable. Without it, rows
    tying on the leading keys could be returned in a different order for each
    OFFSET, and paging would silently repeat or skip them.
    """
    if status == STATUS_REJECTED:
        return (
            Posting.status_changed_at.desc().nullslast(),
            Posting.score.desc().nullslast(),
            Posting.id.desc(),
        )
    return (
        Posting.score.desc().nullslast(),
        Posting.first_seen_at.desc(),
        Posting.id.desc(),
    )


def list_postings(
    session: Session,
    *,
    status: str | None = None,
    published_only: bool = False,
    search: str | None = None,
    country: str | None = None,
    remote: bool | None = None,
    source: str | None = None,
    page: int = 1,
    per_page: int | None = None,
) -> Page:
    """One page of postings, ordered per `_ordering`.

    Location is filtered on `country_code` and `is_remote`, never on
    `location_raw`: boards render the city segment irreconcilably and sometimes
    in Arabic (design §7.3.1), so a city match would silently drop postings.
    Country is the segment that resolves comparably, which is why it is also the
    fingerprint input. Pass `country=COUNTRY_UNKNOWN` for the unresolved bucket.

    `remote` is tri-state: None leaves the axis unfiltered, True/False select
    remote and on-site respectively.

    `page` is clamped into range rather than validated, so a link held over from
    a wider result set lands on the last page instead of an empty table.
    """
    where = []
    if status:
        where.append(Posting.status == status)
    if published_only:
        where.append(Posting.published.is_(True))
    if search:
        like = f"%{search.lower()}%"
        where.append(
            func.lower(Posting.title).like(like) | func.lower(Employer.name).like(like)
        )
    if country == COUNTRY_UNKNOWN:
        where.append(Posting.country_code.is_(None))
    elif country:
        where.append(Posting.country_code == country.upper())
    if remote is not None:
        where.append(Posting.is_remote.is_(remote))
    if source:
        where.append(_has_source(session, source))

    # The join is repeated for the count because `search` reaches into
    # `employers`. It is an inner join on a non-nullable FK, so it cannot change
    # the count on its own.
    total = session.scalar(
        select(func.count())
        .select_from(Posting)
        .join(Employer, Employer.id == Posting.employer_id)
        .where(*where)
    ) or 0

    per_page = max(1, per_page if per_page is not None else PAGE_SIZE)
    number = min(max(page, 1), max(1, -(-total // per_page)))
    stmt = (
        select(Posting, Employer)
        .join(Employer, Employer.id == Posting.employer_id)
        .where(*where)
        .order_by(*_ordering(status))
        .offset((number - 1) * per_page)
        .limit(per_page)
    )
    return Page(
        rows=list(session.execute(stmt).all()),
        total=total,
        number=number,
        per_page=per_page,
    )


@dataclass
class Facets:
    """Filter options, derived from the data actually held.

    Offering only values that exist keeps the operator from selecting a filter
    that can only return nothing.
    """

    countries: list[str]
    # Whether any posting has an unresolved country, i.e. whether offering the
    # COUNTRY_UNKNOWN option would select anything
    unknown_country: bool
    sources: list[str]


def facets(session: Session) -> Facets:
    countries = list(
        session.scalars(
            select(Posting.country_code)
            .where(Posting.country_code.isnot(None))
            .distinct()
            .order_by(Posting.country_code)
        ).all()
    )
    unknown = session.scalar(
        select(func.count()).select_from(Posting).where(Posting.country_code.is_(None))
    )
    return Facets(
        countries=countries,
        unknown_country=bool(unknown),
        sources=known_sites(session),
    )


def known_sites(session: Session) -> list[str]:
    """Boards the source filter can offer.

    Taken from the configured boards plus any a past run recorded, rather than
    from the `postings.sources` keys themselves: JSON keys cannot be enumerated
    portably across JSONB and SQLite's JSON, and a full scan to collect them
    would not stay cheap as the table grows. `runs` is one row per execution, so
    this stays small. The union means a board dropped from WORKING_SITES can
    still be used to filter the postings it left behind.
    """
    recorded = {
        site
        for counts in session.scalars(select(Run.counts_by_site))
        for site in (counts or {})
    }
    return sorted(recorded | set(WORKING_SITES))


def get_posting(session: Session, posting_id: int) -> tuple[Posting, Employer] | None:
    return session.execute(
        select(Posting, Employer)
        .join(Employer, Employer.id == Posting.employer_id)
        .where(Posting.id == posting_id)
    ).first()


def blacklisted_employers(session: Session) -> list[tuple[Employer, int]]:
    """Suppressed employers with a count of their postings (US3)."""
    stmt = (
        select(Employer, func.count(Posting.id))
        .outerjoin(Posting, Posting.employer_id == Employer.id)
        .where(Employer.suppressed.is_(True))
        .group_by(Employer.id)
        .order_by(Employer.name)
    )
    return list(session.execute(stmt).all())


def recent_runs(session: Session, limit: int = 30) -> list[Run]:
    rows = session.execute(
        select(Run, SearchProfile.name)
        .outerjoin(SearchProfile, Run.profile_id == SearchProfile.id)
        .order_by(Run.started_at.desc())
        .limit(limit)
    ).all()
    runs = []
    for run, profile_name in rows:
        run.profile_name = profile_name
        runs.append(run)
    return runs


def source_health(session: Session, limit: int = 14) -> dict[str, Any]:
    """Per-source counts across recent runs.

    This is the §7.4 surface: the dominant failure is a run that succeeds while
    returning progressively less, so the trend matters more than any single run.
    """
    runs = recent_runs(session, limit)
    sites = sorted({site for r in runs for site in (r.counts_by_site or {})})
    series = {
        site: [(r.started_at, (r.counts_by_site or {}).get(site, 0)) for r in reversed(runs)]
        for site in sites
    }
    return {"sites": sites, "series": series, "runs": list(reversed(runs))}
