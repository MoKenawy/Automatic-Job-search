"""Promoting the board's seniority label out of the raw payload (FR-018, FR-019).

Stage 2 behaviour, so it lives apart from the filter stage's own tests: the label
is *data*, promoted whether or not any criterion will ever read it.

The merge rule is the point. Where several collected rows fold into one posting
the stored label is the **minimum** seniority among them, so the value depends on
the set of boards that surfaced the role rather than on which row happened to be
processed first (FR-009). Every test here that lowers a label has a partner that
proves a higher one does not raise it.

Payload values marked OBSERVED are verbatim from the live corpus, 16 November
2026: LinkedIn declares the label on every row, lowercased; Indeed declares none.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import STATUS_SHORTLIST, Base, Employer, Posting, RawPosting, Run
from app.pipeline.normalise_stage import run_normalise


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


def _land(session, run, site, *, job_level=None, title="Data Engineer"):
    """Land one raw row shaped like the collector's output."""
    session.add(
        RawPosting(
            run_id=run.id,
            site=site,
            payload={
                "company": "Acme",
                "title": title,
                "location": "Cairo, Egypt",
                "job_url": f"https://{site}/1",
                "job_level": job_level,
            },
        )
    )


def _run(session) -> Run:
    run = Run(status="running")
    session.add(run)
    session.flush()
    return run


# --- a first sighting -------------------------------------------------------


def test_the_boards_label_is_stored_verbatim(session):
    run = _run(session)
    _land(session, run, "linkedin", job_level="mid-senior level")  # OBSERVED
    session.commit()

    run_normalise(session, run)

    assert session.query(Posting).one().job_level == "mid-senior level"


@pytest.mark.parametrize(
    "job_level",
    [
        None,  # OBSERVED — every Indeed row
        "",  # OBSERVED — LinkedIn, description not fetched
        "not applicable",  # OBSERVED — LinkedIn, in the board's own vocabulary
    ],
)
def test_an_uninformative_label_is_not_promoted(session, job_level):
    """NULL already says "no board supplied a level"; storing 'not applicable'
    would say the same thing twice, in a column the filter reads."""
    run = _run(session)
    _land(session, run, "linkedin", job_level=job_level)
    session.commit()

    run_normalise(session, run)

    assert session.query(Posting).one().job_level is None


def test_a_payload_with_no_job_level_key_at_all_is_tolerated(session):
    """Older landed rows predate the field being read."""
    run = _run(session)
    session.add(
        RawPosting(
            run_id=run.id,
            site="indeed",
            payload={"company": "Acme", "title": "Data Engineer", "job_url": "https://x"},
        )
    )
    session.commit()

    run_normalise(session, run)

    assert session.query(Posting).one().job_level is None


# --- a label the filter cannot read -----------------------------------------


def test_an_unrecognised_label_is_logged_and_kept_in_the_payload(session, caplog):
    """Vocabulary drift must be visible. The label is not promoted — the column
    stays NULL and the filter falls back to the title — but it is not lost
    either: the raw payload keeps it verbatim, so a later BOARD_LABELS entry and
    a backfill recover it without a re-scrape."""
    run = _run(session)
    _land(session, run, "linkedin", job_level="senior level")
    session.commit()

    with caplog.at_level("WARNING", logger="app.pipeline.normalise_stage"):
        run_normalise(session, run)

    assert session.query(Posting).one().job_level is None
    assert session.query(RawPosting).one().payload["job_level"] == "senior level"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "senior level" in warnings[0].getMessage()
    assert "BOARD_LABELS" in warnings[0].getMessage()


def test_unrecognised_labels_are_counted_in_one_warning(session, caplog):
    run = _run(session)
    _land(session, run, "linkedin", job_level="senior level", title="Data Engineer")
    _land(session, run, "linkedin", job_level="senior level", title="Data Analyst")
    _land(session, run, "linkedin", job_level="premier emploi", title="Data Scientist")
    session.commit()

    with caplog.at_level("WARNING", logger="app.pipeline.normalise_stage"):
        run_normalise(session, run)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "3 row(s)" in message
    assert "'senior level': 2" in message
    assert "'premier emploi': 1" in message


@pytest.mark.parametrize(
    "job_level",
    [
        "mid-senior level",  # OBSERVED
        "entry level",  # OBSERVED
        "associate",  # OBSERVED
        "director",  # OBSERVED
        "",  # OBSERVED — description not fetched
        None,  # OBSERVED — every Indeed row
        "not applicable",  # OBSERVED
    ],
)
def test_a_known_or_uninformative_label_raises_no_warning(session, caplog, job_level):
    run = _run(session)
    _land(session, run, "linkedin", job_level=job_level)
    session.commit()

    with caplog.at_level("WARNING", logger="app.pipeline.normalise_stage"):
        run_normalise(session, run)

    assert not [r for r in caplog.records if r.levelname == "WARNING"]


# --- a second sighting ------------------------------------------------------


def test_a_lower_label_from_another_board_lowers_it(session):
    """The admitting direction: when boards disagree, the lower label is the one
    that keeps the posting in front of the operator (FR-009)."""
    first = _run(session)
    _land(session, first, "linkedin", job_level="mid-senior level")
    session.commit()
    run_normalise(session, first)

    second = _run(session)
    _land(session, second, "indeed", job_level="entry level")
    session.commit()
    run_normalise(session, second)

    assert session.query(Posting).one().job_level == "entry level"


def test_a_higher_label_from_another_board_does_not_raise_it(session):
    first = _run(session)
    _land(session, first, "linkedin", job_level="entry level")
    session.commit()
    run_normalise(session, first)

    second = _run(session)
    _land(session, second, "indeed", job_level="director")
    session.commit()
    run_normalise(session, second)

    assert session.query(Posting).one().job_level == "entry level"


def test_a_board_that_declares_nothing_leaves_the_label_alone(session):
    """The common case: one board supplies the label on every row, the other on
    none, and the same role surfaced by both must keep what it was told."""
    first = _run(session)
    _land(session, first, "linkedin", job_level="associate")
    session.commit()
    run_normalise(session, first)

    second = _run(session)
    _land(session, second, "indeed", job_level=None)
    session.commit()
    run_normalise(session, second)

    assert session.query(Posting).one().job_level == "associate"


def test_a_label_arriving_later_fills_an_empty_one(session):
    first = _run(session)
    _land(session, first, "indeed", job_level=None)
    session.commit()
    run_normalise(session, first)

    second = _run(session)
    _land(session, second, "linkedin", job_level="entry level")
    session.commit()
    run_normalise(session, second)

    assert session.query(Posting).one().job_level == "entry level"


def test_re_observing_the_same_label_changes_nothing(session):
    """Idempotence — a re-scrape of the same role converges (FR-015 for stage 2).

    Expressed as a second run rather than a second call against the same run:
    `run_normalise` re-adds link rows unconditionally, so calling it twice for
    one run id trips `raw_posting_normalizations`' unique constraint. That is a
    pre-existing property of stage 2, whose convergence guarantee is over
    `postings` and not over the link table, and changing it is out of scope here.
    """
    first = _run(session)
    _land(session, first, "linkedin", job_level="entry level")
    session.commit()
    run_normalise(session, first)

    second = _run(session)
    _land(session, second, "linkedin", job_level="entry level")
    session.commit()
    run_normalise(session, second)

    assert session.query(Posting).one().job_level == "entry level"


# --- what promotion must not touch -----------------------------------------


def test_promotion_does_not_disturb_triage_or_retrieval_state(session):
    """A verdict is not an observation and a label is not a judgement. The
    timestamps ADR-0012 separated must stay separate: `observe()` owns
    last_retrieved_at, and nothing here owns `status`."""
    first = _run(session)
    _land(session, first, "linkedin", job_level="director")
    session.commit()
    run_normalise(session, first)

    posting = session.query(Posting).one()
    posting.status = STATUS_SHORTLIST
    session.commit()
    before = posting.status_changed_at

    second = _run(session)
    _land(session, second, "indeed", job_level="entry level")
    session.commit()
    run_normalise(session, second)

    session.refresh(posting)
    assert posting.job_level == "entry level"
    assert posting.status == STATUS_SHORTLIST
    assert posting.status_changed_at == before


def test_promotion_writes_no_verdict(session):
    """Phase separation, asserted rather than assumed: stage 2 promotes data and
    judges nothing, so both verdict columns stay NULL until the filter runs."""
    run = _run(session)
    _land(session, run, "linkedin", job_level="director")
    session.commit()

    run_normalise(session, run)

    posting = session.query(Posting).one()
    assert posting.title_filter_passed is None
    assert posting.experience_filter_passed is None


def test_merge_job_level_is_a_no_op_for_an_uninformative_label(session):
    """Unit-level counterpart to the stage tests above, for the method's own
    contract: an uninformative label can never clear an informative one."""
    employer = Employer(name="Acme", normalised_name="acme")
    session.add(employer)
    session.flush()
    posting = Posting(
        fingerprint="f" * 64,
        employer_id=employer.id,
        title="Data Engineer",
        normalised_title="data engineer",
        sources={},
        job_level="entry level",
    )

    for label in (None, "", "not applicable"):
        posting.merge_job_level(label)
        assert posting.job_level == "entry level"
