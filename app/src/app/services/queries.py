"""Read models for the triage interface.

Kept separate from the route handlers so the querying can be tested without a
web client, and so the templates receive plain data rather than ORM rows.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.config import WORKING_SITES, RunConfig
from app.db.attribution import requested_experience_by_posting
from app.db.models import STATUS_REJECTED, Employer, Posting, Run, SearchProfile
from app.db.visibility import filter_rejected, hidden_by_filter, not_suppressed
from app.filters import (
    Criteria,
    TitleRules,
    Verdict,
    evaluate,
    parse_level,
    parse_requested,
)

# Selects postings whose country could not be resolved. `parse_country` returns
# None rather than guessing (normalise/country.py), so this is a real bucket the
# operator needs to reach. ISO2 codes are two characters, so no code collides
# with this sentinel.
COUNTRY_UNKNOWN = "unknown"

# Rows per page in the triage list.
PAGE_SIZE = 50

# `verdict` value selecting the filter's review bucket (FR-017). A sentinel on an
# existing parameter rather than a new axis, following COUNTRY_UNKNOWN above: the
# list already threads its filter state through three places, and each new axis is
# another place to forget.
VERDICT_REJECTED = "rejected"


@dataclass
class Totals:
    postings: int
    published: int
    scored: int
    by_status: dict[str, int]
    employers: int
    last_run: Run | None


def _visible() -> tuple:
    """The two conditions every figure and listing over `postings` applies.

    Suppression (ADR-0015) and the filter verdict (ADR-0016) are independent
    reasons to withhold a posting, and both are derived at read time rather than
    stamped. Returned together so a read path adopts the pair as one idiom: two
    obligations spelled out separately at eight call sites is one of them waiting
    to be forgotten.
    """
    return (not_suppressed(), ~hidden_by_filter())


def totals(session: Session) -> Totals:
    # _visible() applies to every figure over `postings` (ADR-0015, ADR-0016).
    # The employer count below deliberately does not — those predicates are over
    # postings, not employers — and uses Employer.suppressed directly instead.
    by_status = dict(
        session.execute(
            select(Posting.status, func.count()).where(*_visible()).group_by(Posting.status)
        ).all()
    )
    return Totals(
        postings=session.scalar(select(func.count()).select_from(Posting).where(*_visible())) or 0,
        published=session.scalar(
            select(func.count()).select_from(Posting).where(Posting.published, *_visible())
        )
        or 0,
        scored=session.scalar(
            select(func.count()).select_from(Posting).where(Posting.score.isnot(None), *_visible())
        )
        or 0,
        by_status=by_status,
        employers=session.scalar(
            select(func.count()).select_from(Employer).where(Employer.suppressed.is_(False))
        )
        or 0,
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
    only for rows that predate ADR-0015 (postings born Rejected because their
    employer was already suppressed under the old materialised model, which
    have no rejection event of their own); no posting reaches this state any
    more, but existing rows still sort last.

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
    verdict: str | None = None,
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

    `verdict=VERDICT_REJECTED` inverts the filter seam, listing what the filter
    turned away (FR-017). It selects `filter_rejected()` — the verdict — and not
    the complement of the hide rule, so a posting rejected *after* the operator
    shortlisted it appears here as well as in the normal list. That overlap is
    deliberate: the strongest available evidence of a false rejection is a
    posting the operator thought worth keeping which the current criteria reject,
    and a bucket defined as "everything hidden" would conceal exactly that
    (SC-002, contracts/filter-seam.md).
    """
    where = []
    if status:
        where.append(Posting.status == status)
    if published_only:
        where.append(Posting.published.is_(True))
    if search:
        like = f"%{search.lower()}%"
        where.append(func.lower(Posting.title).like(like) | func.lower(Employer.name).like(like))
    if country == COUNTRY_UNKNOWN:
        where.append(Posting.country_code.is_(None))
    elif country:
        where.append(Posting.country_code == country.upper())
    if remote is not None:
        where.append(Posting.is_remote.is_(remote))
    if source:
        where.append(_has_source(session, source))
    # ADR-0015 and ADR-0016 — applied to both statements below. The count and the
    # page must carry the same conditions, or the pager claims rows the operator
    # cannot reach.
    where.append(not_suppressed())
    where.append(filter_rejected() if verdict == VERDICT_REJECTED else ~hidden_by_filter())

    # The join is repeated for the count because `search` reaches into
    # `employers`. It is an inner join on a non-nullable FK, so it cannot change
    # the count on its own.
    total = (
        session.scalar(
            select(func.count())
            .select_from(Posting)
            .join(Employer, Employer.id == Posting.employer_id)
            .where(*where)
        )
        or 0
    )

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
            .where(Posting.country_code.isnot(None), *_visible())
            .distinct()
            .order_by(Posting.country_code)
        ).all()
    )
    unknown = session.scalar(
        select(func.count()).select_from(Posting).where(Posting.country_code.is_(None), *_visible())
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
        site for counts in session.scalars(select(Run.counts_by_site)) for site in (counts or {})
    }
    return sorted(recorded | set(WORKING_SITES))


def get_posting(session: Session, posting_id: int) -> tuple[Posting, Employer] | None:
    # Deliberate opt-out from not_suppressed() (ADR-0015, FR-015): this page is
    # the operator's route back out of a suppression, and detail.html already
    # renders the blacklist banner and the "Remove from blacklist" control.
    # Filtering it would make lifting unreachable from the posting that
    # prompted it.
    #
    # Deliberate opt-out from hidden_by_filter() too (ADR-0016, FR-013/FR-016),
    # for the same reason and on the same terms: this is where a withheld posting
    # is reachable at all, and where detail.html names the criterion that
    # withheld it. A filtered detail page would leave the operator with a posting
    # missing from the queue and no page to read about why.
    return session.execute(
        select(Posting, Employer)
        .join(Employer, Employer.id == Posting.employer_id)
        .where(Posting.id == posting_id)
    ).first()


def stored_verdict(posting: Posting) -> Verdict:
    """The filter verdict as recorded on the posting (FR-016).

    A `Verdict` rather than two raw columns, so the detail page and the list
    derive the grounds the same way the stage does — there is one definition of
    what "rejected on title grounds" means, and it is in `app.filters`.
    """
    return Verdict(
        title_passed=posting.title_filter_passed,
        experience_passed=posting.experience_filter_passed,
        level=parse_level(posting.job_level),
    )


def current_verdict(session: Session, posting: Posting) -> Verdict:
    """What the filter would decide about this posting right now (FR-011).

    Recomputed from the criteria in force, which lets the detail page say that a
    stored verdict is out of date rather than presenting it as current. That is
    the one thing a stored reason column could never do: the operator reads the
    grounds *because* they are about to change the rule that produced them, so a
    recorded explanation is stale exactly when it is consulted (ADR-0016).

    Read-only, and cheap: one compile and one evaluation for a single posting.
    """
    config = RunConfig.resolve(session)
    requested = requested_experience_by_posting(session, [posting.id]).get(posting.id, [])
    criteria = Criteria(
        titles=TitleRules.compile(config.title_include_pattern, config.title_exclude_pattern),
        requested_levels=tuple(parse_requested(text) for text in requested),
    )
    return evaluate(
        title=posting.title,
        normalised_title=posting.normalised_title,
        job_level=posting.job_level,
        criteria=criteria,
    )


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
