"""PostingStatusHistory — transactional audit trail for triage transitions.

Covers what test_models.py's in-memory Posting tests cannot: persistence
through a real session/transaction, rollback on failure, and the service
layer's use of the history table (triage.set_status / set_status_bulk).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    STATUS_APPLIED,
    STATUS_NEW,
    STATUS_REJECTED,
    STATUS_SHORTLIST,
    Base,
    Employer,
    Posting,
    PostingStatusHistory,
    RawPosting,
    Run,
)
from app.pipeline.normalise_stage import run_normalise
from app.services import blacklist as blacklist_service
from app.services import triage as triage_service

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s


def _employer(session) -> Employer:
    e = Employer(name="Acme", normalised_name="acme")
    session.add(e)
    session.flush()
    return e


def _posting(session, employer, **overrides) -> Posting:
    p = Posting(
        fingerprint=overrides.pop("fingerprint", "f" * 64),
        employer_id=employer.id,
        title="Data Engineer",
        normalised_title="data engineer",
        sources={},
        status=STATUS_NEW,
        **overrides,
    )
    session.add(p)
    session.flush()
    return p


# --- Persistence — the history row survives a commit -------------------------


def test_set_status_persists_a_history_row(session):
    employer = _employer(session)
    posting = _posting(session, employer)

    triage_service.set_status(session, posting.id, STATUS_SHORTLIST)

    rows = session.scalars(
        select(PostingStatusHistory).where(PostingStatusHistory.posting_id == posting.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].previous_status == STATUS_NEW
    assert rows[0].new_status == STATUS_SHORTLIST
    assert rows[0].actor == "operator"


def test_set_status_with_reason_is_recorded(session):
    employer = _employer(session)
    posting = _posting(session, employer)

    triage_service.set_status(session, posting.id, STATUS_REJECTED, reason="not a fit")

    row = session.scalars(
        select(PostingStatusHistory).where(PostingStatusHistory.posting_id == posting.id)
    ).one()
    assert row.reason == "not a fit"


def test_repeated_transitions_each_leave_their_own_row(session):
    employer = _employer(session)
    posting = _posting(session, employer)

    triage_service.set_status(session, posting.id, STATUS_SHORTLIST)
    triage_service.set_status(session, posting.id, STATUS_APPLIED)
    triage_service.set_status(session, posting.id, STATUS_REJECTED)

    rows = session.scalars(
        select(PostingStatusHistory)
        .where(PostingStatusHistory.posting_id == posting.id)
        .order_by(PostingStatusHistory.id)
    ).all()
    assert [r.new_status for r in rows] == [STATUS_SHORTLIST, STATUS_APPLIED, STATUS_REJECTED]
    assert [r.previous_status for r in rows] == [STATUS_NEW, STATUS_SHORTLIST, STATUS_APPLIED]


# --- Invalid transitions — rejected before anything is written ---------------


def test_set_status_with_unknown_status_raises_and_writes_nothing(session):
    employer = _employer(session)
    posting = _posting(session, employer)

    with pytest.raises(triage_service.UnknownStatusError):
        triage_service.set_status(session, posting.id, "banana")

    session.refresh(posting)
    assert posting.status == STATUS_NEW
    assert (
        session.scalars(
            select(PostingStatusHistory).where(PostingStatusHistory.posting_id == posting.id)
        ).first()
        is None
    )


def test_set_status_for_a_missing_posting_returns_none_and_writes_nothing(session):
    assert triage_service.set_status(session, 999, STATUS_SHORTLIST) is None
    assert session.scalars(select(PostingStatusHistory)).first() is None


# --- Rollback — a failure partway through leaves no partial write ------------


def test_failed_commit_leaves_no_partial_history_row(session, monkeypatch):
    employer = _employer(session)
    posting = _posting(session, employer)
    session.commit()

    def boom():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(session, "commit", boom)

    with pytest.raises(RuntimeError):
        triage_service.set_status(session, posting.id, STATUS_SHORTLIST)

    session.rollback()
    fresh = session.get(Posting, posting.id)
    assert fresh.status == STATUS_NEW
    assert session.scalars(select(PostingStatusHistory)).first() is None


def test_bulk_status_change_is_all_or_nothing(session, monkeypatch):
    """set_status_bulk updates every row and writes every history entry inside
    one transaction — a failure on commit must not leave some rows changed
    and others not, nor some history rows written and others missing."""
    employer = _employer(session)
    postings = [_posting(session, employer, fingerprint=str(i) * 64) for i in range(3)]
    session.commit()

    def boom():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(session, "commit", boom)

    with pytest.raises(RuntimeError):
        triage_service.set_status_bulk(session, [p.id for p in postings], STATUS_SHORTLIST)

    session.rollback()
    for p in postings:
        fresh = session.get(Posting, p.id)
        assert fresh.status == STATUS_NEW
    assert session.scalars(select(PostingStatusHistory)).first() is None


# --- Bulk — history recorded per posting --------------------------------------


def test_bulk_status_change_records_one_history_row_per_posting(session):
    employer = _employer(session)
    postings = [_posting(session, employer, fingerprint=str(i) * 64) for i in range(3)]

    updated = triage_service.set_status_bulk(session, [p.id for p in postings], STATUS_APPLIED)

    assert updated == 3
    rows = session.scalars(select(PostingStatusHistory)).all()
    assert len(rows) == 3
    assert all(r.new_status == STATUS_APPLIED and r.actor == "operator" for r in rows)


# --- Suppression writes no history at all (ADR-0015, SC-004) -----------------


def test_blacklist_collect_lift_cycle_writes_zero_system_actor_rows(session):
    """A full blacklist -> collect -> lift cycle leaves posting_status_history
    untouched by suppression — it is derived, never written (SC-004)."""
    employer = _employer(session)
    posting = _posting(session, employer)

    blacklist_service.blacklist(session, employer.id)

    run = Run(status="running")
    session.add(run)
    session.flush()
    session.add(
        RawPosting(
            run_id=run.id,
            site="linkedin",
            payload={
                "company": "Acme",
                "title": "Data Engineer",
                "location": "Cairo, Egypt",
                "job_url": "https://x",
            },
        )
    )
    session.commit()
    run_normalise(session, run)

    blacklist_service.lift(session, employer.id)

    assert session.get(Posting, posting.id).status == STATUS_NEW
    system_rows = session.scalars(
        select(PostingStatusHistory).where(PostingStatusHistory.actor == "system")
    ).all()
    assert system_rows == []


# --- Cascade delete — history is removed with its posting ---------------------


def test_deleting_a_posting_cascades_to_its_history(session):
    employer = _employer(session)
    posting = _posting(session, employer)
    triage_service.set_status(session, posting.id, STATUS_SHORTLIST)

    session.delete(session.get(Posting, posting.id))
    session.commit()

    assert session.scalars(select(PostingStatusHistory)).first() is None
