"""Read models for the triage interface.

Kept separate from the route handlers so the querying can be tested without a
web client, and so the templates receive plain data rather than ORM rows.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Employer, Posting, Run


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


def list_postings(
    session: Session,
    *,
    status: str | None = None,
    published_only: bool = False,
    search: str | None = None,
    limit: int = 100,
) -> list[tuple[Posting, Employer]]:
    """Postings ranked by score, then recency.

    Unscored postings sort last rather than first: `score` is NULL until stage 3
    runs, and NULLs would otherwise lead under PostgreSQL's default ordering.
    """
    stmt = (
        select(Posting, Employer)
        .join(Employer, Employer.id == Posting.employer_id)
        .order_by(Posting.score.desc().nullslast(), Posting.first_seen_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Posting.status == status)
    if published_only:
        stmt = stmt.where(Posting.published.is_(True))
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Posting.title).like(like) | func.lower(Employer.name).like(like)
        )
    return list(session.execute(stmt).all())


def get_posting(session: Session, posting_id: int) -> tuple[Posting, Employer] | None:
    return session.execute(
        select(Posting, Employer)
        .join(Employer, Employer.id == Posting.employer_id)
        .where(Posting.id == posting_id)
    ).first()


def recent_runs(session: Session, limit: int = 30) -> list[Run]:
    return list(
        session.scalars(select(Run).order_by(Run.started_at.desc()).limit(limit)).all()
    )


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
