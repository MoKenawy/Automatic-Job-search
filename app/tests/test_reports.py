"""Report aggregations (ADR-0008).

Service-level, no web client — same split as `services/queries.py`, which is
kept separate from the routes so the querying is testable on its own.

Run against in-memory SQLite like the rest of the suite. That is not only for
speed here: SQLite returns *naive* datetimes for `DateTime(timezone=True)` while
PostgreSQL returns aware ones, so these tests are what exercise
`reports._aware`. A regression there would raise on the production dialect only.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import STATUS_NEW, STATUS_SHORTLIST, Base, Employer, Posting
from app.services import reports

# Two boards collected in the same run share one timestamp; a later run differs.
SAME_RUN = "2026-07-20T06:00:00+00:00"
NEXT_RUN = "2026-07-21T06:00:00+00:00"

NOW = datetime(2026, 7, 27, tzinfo=UTC)


@pytest.fixture
def session():
    """Four postings across two employers, shaped for the assertions below.

    Acme holds three roles spanning only two normalised titles, so volume and
    breadth differ — the distinction the report exists to draw. Blacklisted is
    suppressed, so it must not appear unless asked for.
    """
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        acme = Employer(name="Acme", normalised_name="acme")
        blacklisted = Employer(name="Blacklisted", normalised_name="blacklisted", suppressed=True)
        s.add_all([acme, blacklisted])
        s.flush()

        s.add_all(
            [
                # Both boards, same run — a tie, not a winner
                Posting(
                    fingerprint="a" * 64,
                    employer_id=acme.id,
                    title="Data Engineer",
                    normalised_title="data engineer",
                    first_seen_at=datetime(2026, 7, 1),
                    status=STATUS_NEW,
                    sources={
                        "indeed": {"url": "https://i/1", "first_seen": SAME_RUN},
                        "linkedin": {"url": "https://l/1", "first_seen": SAME_RUN},
                    },
                ),
                # Same normalised title as above: volume 2, breadth 1 so far
                Posting(
                    fingerprint="b" * 64,
                    employer_id=acme.id,
                    title="Data Engineer II",
                    normalised_title="data engineer",
                    first_seen_at=datetime(2026, 7, 10),
                    status=STATUS_SHORTLIST,
                    sources={"indeed": {"url": "https://i/2", "first_seen": SAME_RUN}},
                ),
                # Both boards, LinkedIn a run earlier — a strict winner
                Posting(
                    fingerprint="c" * 64,
                    employer_id=acme.id,
                    title="Analytics Engineer",
                    normalised_title="analytics engineer",
                    first_seen_at=datetime(2026, 7, 20),
                    status=STATUS_NEW,
                    sources={
                        "indeed": {"url": "https://i/3", "first_seen": NEXT_RUN},
                        "linkedin": {"url": "https://l/3", "first_seen": SAME_RUN},
                    },
                ),
                Posting(
                    fingerprint="d" * 64,
                    employer_id=blacklisted.id,
                    title="Junior Dev",
                    normalised_title="junior dev",
                    first_seen_at=datetime(2026, 7, 5),
                    status=STATUS_NEW,
                    sources={"linkedin": {"url": "https://l/4", "first_seen": SAME_RUN}},
                ),
            ]
        )
        s.commit()
        yield s


# --- R1: employer hiring activity ---------------------------------------------


def test_volume_and_breadth_are_different_numbers(session):
    """Three roles across two titles. Reporting only the first would hide that
    the employer is refilling the same seat."""
    (acme,) = reports.employer_activity(session, now=NOW)
    assert acme.employer.name == "Acme"
    assert acme.postings == 3
    assert acme.titles == 2


def test_suppressed_employers_are_excluded_by_default(session):
    assert [r.employer.name for r in reports.employer_activity(session, now=NOW)] == ["Acme"]


def test_suppressed_employers_are_available_on_request(session):
    rows = reports.employer_activity(session, now=NOW, include_suppressed=True)
    assert {r.employer.name for r in rows} == {"Acme", "Blacklisted"}


def test_days_quiet_is_measured_from_the_most_recent_new_role(session):
    """Acme's newest role landed 20 July; NOW is the 27th.

    Also the cross-dialect guard: `first_seen_at` comes back naive from SQLite
    and `now` is aware, so this raises unless `_aware` normalises them.
    """
    (acme,) = reports.employer_activity(session, now=NOW)
    assert acme.days_quiet == 7


def test_status_breakdown_is_attributed_to_the_right_employer(session):
    (acme,) = reports.employer_activity(session, now=NOW)
    assert acme.by_status == {STATUS_NEW: 2, STATUS_SHORTLIST: 1}


def test_employers_with_no_postings_are_absent(session):
    session.add(Employer(name="Nobody", normalised_name="nobody"))
    session.commit()
    assert "Nobody" not in {r.employer.name for r in reports.employer_activity(session, now=NOW)}


# --- R3: source coverage and overlap ------------------------------------------


def test_same_run_boards_are_a_tie_not_a_winner(session):
    """The assertion most likely to be got wrong.

    `normalise_stage` computes one `now` per run, so both boards stamp an
    identical `first_seen`. Picking a winner there would report dict ordering as
    a finding.
    """
    overlap = reports.source_overlap(session)
    assert overlap.ties == 1
    assert overlap.first_by["linkedin"] == 1  # the genuine win, not the tie
    assert overlap.first_by["indeed"] == 0


def test_single_board_postings_are_not_contested(session):
    """Two of the four postings carry one board each; they have no race to win
    and must not dilute the first-surfacer denominator."""
    overlap = reports.source_overlap(session)
    assert overlap.contested == 2
    assert overlap.total == 4


def test_per_board_counts_every_posting_carrying_that_board(session):
    overlap = reports.source_overlap(session)
    assert overlap.per_site == {"indeed": 3, "linkedin": 3}


def test_combinations_separate_shared_roles_from_unique_coverage(session):
    overlap = reports.source_overlap(session)
    assert dict(overlap.combinations) == {
        ("indeed", "linkedin"): 2,
        ("indeed",): 1,
        ("linkedin",): 1,
    }


def test_a_posting_with_no_provenance_timestamps_is_not_contested(session):
    """Provenance predating the `first_seen` key must not be counted as a race
    with no winner — it is an absence of evidence, not a tie."""
    session.add(
        Posting(
            fingerprint="e" * 64,
            employer_id=1,
            title="Legacy",
            normalised_title="legacy",
            first_seen_at=datetime(2026, 7, 2),
            sources={"indeed": {"url": "https://i/5"}, "linkedin": {"url": "https://l/5"}},
        )
    )
    session.commit()

    overlap = reports.source_overlap(session)
    assert overlap.total == 5
    assert overlap.contested == 2  # unchanged
    assert overlap.ties == 1  # unchanged


def test_empty_database_does_not_divide_by_zero(session):
    session.query(Posting).delete()
    session.commit()

    overlap = reports.source_overlap(session)
    assert overlap.total == 0
    assert overlap.contested == 0
    assert reports.employer_activity(session, now=NOW) == []
