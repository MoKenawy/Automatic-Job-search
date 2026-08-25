"""The visibility seam in isolation (ADR-0015, contracts/visibility-seam.md).

Three cases: a normal employer's posting is selected; a suppressed employer's
posting is rejected; and — the keystone — a suppressed employer's posting
whose `status` is still `new` is rejected too. That last case is the
assertion this whole feature exists to make true: under the old materialised
model, "suppressed but still new" was a state the system could not represent.
"""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import STATUS_NEW, Base, Employer, Posting
from app.db.visibility import not_suppressed


def _factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _posting(session, employer, name, status=STATUS_NEW):
    posting = Posting(
        fingerprint=name.ljust(64, "0"),
        employer_id=employer.id,
        title=name,
        normalised_title=name.lower(),
        sources={"linkedin": {"url": "https://x"}},
        status=status,
    )
    session.add(posting)
    session.commit()
    return posting


def test_normal_employers_posting_is_selected():
    factory = _factory()
    with factory() as s:
        emp = Employer(name="Good", normalised_name="good", suppressed=False)
        s.add(emp)
        s.flush()
        posting = _posting(s, emp, "Role")

        rows = s.scalars(select(Posting).where(not_suppressed())).all()
        assert posting in rows


def test_suppressed_employers_posting_is_rejected():
    factory = _factory()
    with factory() as s:
        emp = Employer(name="Spammer", normalised_name="spammer", suppressed=True)
        s.add(emp)
        s.flush()
        _posting(s, emp, "Role")

        rows = s.scalars(select(Posting).where(not_suppressed())).all()
        assert rows == []


def test_suppressed_employers_new_posting_is_rejected():
    """The keystone case: suppressed but status is still `new`."""
    factory = _factory()
    with factory() as s:
        emp = Employer(name="Spammer", normalised_name="spammer", suppressed=True)
        s.add(emp)
        s.flush()
        _posting(s, emp, "Role", status=STATUS_NEW)

        rows = s.scalars(select(Posting).where(not_suppressed())).all()
        assert rows == []
