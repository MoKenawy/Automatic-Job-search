"""Postings tab counts (spec 007 step 3).

Each tab's count must equal the total of the list that tab opens, under every
combination of the operator's query axes. Checked against `list_postings` itself
rather than against hand-counted numbers, so a future condition added to one and
not the other fails here. Two hand-counted cases pin the expected values too.
"""

import itertools

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import STATUSES, Base, Employer, Posting
from app.services import queries

ROWS = [
    # employer, title, status, country, remote, sources, published, title_ok
    ("Acme", "Data Engineer", "new", "EG", False, ("linkedin",), False, True),
    ("Acme", "Senior Data Engineer", "shortlist", "EG", False, ("linkedin", "indeed"), True, True),
    ("Acme", "Analytics Engineer", "applied", "AE", True, ("indeed",), False, True),
    ("Beta", "Data Analyst", "rejected", None, False, ("indeed",), False, True),
    ("Beta", "Data Director", "new", "EG", False, ("linkedin",), False, False),  # filtered out
    ("Gone", "Data Engineer", "new", "EG", False, ("linkedin",), False, True),  # blacklisted
]


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        employers = {
            name: Employer(name=name, normalised_name=name.lower(), suppressed=name == "Gone")
            for name in ("Acme", "Beta", "Gone")
        }
        s.add_all(employers.values())
        s.flush()
        for i, (emp, title, status, country, remote, sources, published, title_ok) in enumerate(
            ROWS
        ):
            s.add(
                Posting(
                    fingerprint=chr(97 + i) * 64,
                    employer_id=employers[emp].id,
                    title=title,
                    normalised_title=title.lower(),
                    sources={site: {"url": "https://x"} for site in sources},
                    status=status,
                    country_code=country,
                    is_remote=remote,
                    published=published,
                    title_filter_passed=title_ok,
                    experience_filter_passed=True,
                )
            )
        s.commit()
        yield s


AXES = {
    "search": [None, "engineer", "beta"],
    "country": [None, "EG", queries.COUNTRY_UNKNOWN],
    "remote": [None, True],
    "source": [None, "indeed"],
    "published_only": [False, True],
}


@pytest.mark.parametrize(
    "query", [dict(zip(AXES, combo, strict=True)) for combo in itertools.product(*AXES.values())]
)
def test_every_tab_count_equals_the_total_of_the_list_it_opens(session, query):
    counts = queries.status_counts(session, **query)
    assert counts.all == queries.list_postings(session, **query).total
    for status in STATUSES:
        listed = queries.list_postings(session, status=status, **query).total
        assert counts.by_status[status] == listed
    assert (
        counts.filtered_out
        == queries.list_postings(session, verdict=queries.VERDICT_REJECTED, **query).total
    )


def test_counts_without_a_query(session):
    counts = queries.status_counts(session)
    # Blacklisted and filtered-out postings are not in the queue.
    assert counts.by_status == {"new": 1, "shortlist": 1, "applied": 1, "rejected": 1}
    assert counts.all == 4
    assert counts.filtered_out == 1


def test_counts_follow_the_search(session):
    counts = queries.status_counts(session, search="engineer")
    assert counts.by_status == {"new": 1, "shortlist": 1, "applied": 1, "rejected": 0}
    assert counts.all == 3
    assert counts.filtered_out == 0
