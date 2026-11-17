"""The filter stage: verdicts, the run funnel, and what it must not disturb.

In-memory SQLite, matching the other pipeline and web tests.

**Criteria are always passed explicitly.** `RunConfig()`'s defaults come from the
process settings, and this installation's `.env` already carries a title exclude
pattern — so a test that relied on the default would pass or fail according to a
file outside the suite.

SC-002 governs the balance here as it does the pure-core modules: the assertions
proving the filter admits what it should outnumber those proving it rejects.
"""

import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import RunConfig
from app.db.models import (
    STATUS_NEW,
    STATUS_SHORTLIST,
    AppSetting,
    Base,
    Employer,
    Posting,
    RawPosting,
    RawPostingNormalization,
    Run,
    SearchProfile,
)
from app.pipeline.filter_stage import filter_all, run_filter
from app.services.queries import current_verdict

NO_CRITERIA = RunConfig(title_include_pattern="", title_exclude_pattern="")


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


def _config(*, include: str = "", exclude: str = "") -> RunConfig:
    return RunConfig(title_include_pattern=include, title_exclude_pattern=exclude)


def _profile(
    session,
    name: str,
    experience: str | None = None,
    *,
    include: str | None = None,
    exclude: str | None = None,
) -> SearchProfile:
    # The pattern keywords are additive: every existing caller passes only the
    # first two arguments and gets a profile with no rules of its own.
    profile = SearchProfile(
        name=name,
        term="data engineer",
        experience=experience,
        title_include_pattern=include,
        title_exclude_pattern=exclude,
        sites=[],
    )
    session.add(profile)
    session.flush()
    return profile


def _run(session, profile: SearchProfile | None = None) -> Run:
    run = Run(status="running", profile_id=profile.id if profile else None)
    session.add(run)
    session.flush()
    return run


def _posting(
    session,
    run: Run,
    *,
    title: str = "Data Engineer",
    job_level: str | None = None,
    status: str = STATUS_NEW,
    site: str = "linkedin",
) -> Posting:
    """A posting attributed to `run`, as stage 2 would have left it."""
    employer = session.query(Employer).filter_by(normalised_name="acme").one_or_none()
    if employer is None:
        employer = Employer(name="Acme", normalised_name="acme")
        session.add(employer)
        session.flush()

    posting = Posting(
        fingerprint=f"{title}-{job_level}-{status}".ljust(64, "0")[:64],
        employer_id=employer.id,
        title=title,
        normalised_title=title.lower(),
        job_level=job_level,
        sources={site: {"url": "https://x"}},
        status=status,
    )
    session.add(posting)
    raw = RawPosting(run_id=run.id, site=site, payload={"title": title})
    session.add(raw)
    session.flush()
    session.add(RawPostingNormalization(raw_posting_id=raw.id, posting_id=posting.id))
    run.deduplicated_count = (run.deduplicated_count or 0) + 1
    session.commit()
    return posting


def _attribute(session, run: Run, posting: Posting, site: str = "indeed") -> None:
    """Add a second run's claim on an existing posting (the multi-profile case)."""
    raw = RawPosting(run_id=run.id, site=site, payload={"title": posting.title})
    session.add(raw)
    session.flush()
    session.add(RawPostingNormalization(raw_posting_id=raw.id, posting_id=posting.id))
    run.deduplicated_count = (run.deduplicated_count or 0) + 1
    session.commit()


# --- US1: a profile's experience level is honoured --------------------------


def test_us1_a_posting_above_the_requested_level_is_rejected(session):
    """US1 scenario 1 — the largest measured source of noise."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    posting = _posting(session, run, job_level="mid-senior level")  # OBSERVED

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is False
    assert run.filter_rejected_count == 1


def test_us1_a_posting_at_the_requested_level_is_admitted(session):
    """US1 scenario 2."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    posting = _posting(session, run, job_level="entry level")  # OBSERVED

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is True
    assert run.filter_passed_count == 1


@pytest.mark.parametrize("job_level", [None, "", "not applicable"])
def test_us1_a_posting_with_no_seniority_signal_is_admitted(session, job_level):
    """US1 scenario 3 — the operator would rather judge these personally than
    have them silently withheld. One board supplies no label on any row, so this
    is the common case."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    posting = _posting(session, run, title="Data Engineer", job_level=job_level)

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is True


def test_us1_a_profile_with_no_experience_rejects_nothing(session):
    """US1 scenario 4 — the queue is exactly what it is today."""
    profile = _profile(session, "any", None)
    run = _run(session, profile)
    for level in ("entry level", "mid-senior level", "director", "executive"):
        _posting(session, run, title=f"Engineer {level}", job_level=level)

    run_filter(session, run, NO_CRITERIA)

    assert run.filter_rejected_count == 0
    assert all(p.experience_filter_passed is None for p in session.query(Posting))


def test_a_title_can_stand_in_where_the_board_declared_nothing(session):
    """FR-006 — the fallback, at stage level: no label, but the title says senior."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    posting = _posting(session, run, title="Senior Data Engineer", job_level=None)

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is False


def test_the_board_label_outranks_the_title(session):
    """A title saying `senior` must not override a board declaring `entry level`:
    the declaration is the stronger evidence, and the fallback exists only for
    its absence."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    posting = _posting(session, run, title="Senior Data Engineer", job_level="entry level")

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is True


# --- the multi-profile verdict (ADR-0016) -----------------------------------


@pytest.mark.parametrize("reversed_order", [False, True])
def test_a_posting_two_profiles_surfaced_gets_the_same_verdict_either_way(session, reversed_order):
    """The property reading `run.profile_id` would have broken: one posting,
    two profiles with opposite requirements, and a verdict that must not depend
    on which run was filtered last (FR-010, SC-007)."""
    strict = _profile(session, "fresh", "entry level")
    loose = _profile(session, "senior", "senior")
    strict_run = _run(session, strict)
    loose_run = _run(session, loose)

    posting = _posting(session, strict_run, job_level="mid-senior level")
    _attribute(session, loose_run, posting)

    first, second = (loose_run, strict_run) if reversed_order else (strict_run, loose_run)
    run_filter(session, first, NO_CRITERIA)
    run_filter(session, second, NO_CRITERIA)

    session.refresh(posting)
    # The senior profile admits it, so the posting is admitted — whichever run
    # was filtered last.
    assert posting.experience_filter_passed is True


def test_a_profile_less_run_cannot_withhold_a_posting(session):
    """A manual `run-all` records no profile, so there is no requested level to
    compare against — the specification's own assumption."""
    run = _run(session, None)
    posting = _posting(session, run, job_level="executive")

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is None
    assert run.filter_rejected_count == 0


def test_a_profile_less_contribution_rescues_a_posting_another_profile_rejects(session):
    """The disjunction's sharpest consequence, and ADR-0016 records it as
    accepted: once a profile-less run has touched a posting, no profile's
    experience criterion can withhold it."""
    strict = _profile(session, "fresh", "entry level")
    strict_run = _run(session, strict)
    manual_run = _run(session, None)

    posting = _posting(session, strict_run, job_level="director")
    _attribute(session, manual_run, posting)

    run_filter(session, strict_run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is True


# --- US2: obviously off-topic postings stop arriving ------------------------


def test_us2_an_excluded_title_is_rejected(session):
    """US2 scenario 1 — `QA Analyst` under a web-developer search (OBSERVED)."""
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst")

    run_filter(session, run, _config(exclude="qa analyst|boomi"))

    session.refresh(posting)
    assert posting.title_filter_passed is False
    assert run.filter_rejected_count == 1


def test_us2_a_title_failing_the_include_rule_is_rejected(session):
    """US2 scenario 2."""
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst")

    run_filter(session, run, _config(include="developer|engineer"))

    session.refresh(posting)
    assert posting.title_filter_passed is False


def test_us2_a_matching_title_is_admitted(session):
    run = _run(session)
    posting = _posting(session, run, title="Web Developer")

    run_filter(session, run, _config(include="developer|engineer", exclude="qa analyst"))

    session.refresh(posting)
    assert posting.title_filter_passed is True


def test_us2_no_title_rules_reject_nothing(session):
    """US2 scenario 3 — the system behaves exactly as it does today."""
    run = _run(session)
    for title in ("QA Analyst", "Boomi Technical Consultant", "Web Developer"):
        _posting(session, run, title=title)

    run_filter(session, run, NO_CRITERIA)

    assert run.filter_rejected_count == 0
    assert all(p.title_filter_passed is None for p in session.query(Posting))


def test_us2_an_unusable_rule_completes_the_run_and_rejects_nothing(session):
    """US2 scenario 4, FR-008 — the run completes, the fault is reported, and no
    posting is rejected on the strength of a rule that could not be applied."""
    run = _run(session)
    for title in ("QA Analyst", "Web Developer"):
        _posting(session, run, title=title)

    outcome = run_filter(session, run, _config(exclude="developer("))

    assert run.filter_rejected_count == 0
    assert outcome.faults
    assert "not a valid expression" in outcome.faults[0]
    # Reported where the operator will see it, not only in the log (FR-008).
    assert "filter:" in (run.error or "")
    assert all(p.title_filter_passed is None for p in session.query(Posting))


# --- SC-006: no criteria, nothing changes -----------------------------------


def test_sc006_with_no_criteria_at_all_no_verdict_is_written(session):
    """Installing the filter changes no operator-visible outcome. Both columns
    stay NULL, which is the fact the read-time predicate depends on."""
    profile = _profile(session, "any", None)
    run = _run(session, profile)
    posting = _posting(session, run, title="QA Analyst", job_level="director")

    outcome = run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is None
    assert posting.experience_filter_passed is None
    assert outcome.changed == 0
    assert run.filter_rejected_count == 0


def test_an_unreadable_requested_experience_disables_and_reports(session):
    """FR-002a — it must not reject anything, and it must reach the operator."""
    profile = _profile(session, "vague", "whenever you like")
    run = _run(session, profile)
    posting = _posting(session, run, job_level="executive")

    outcome = run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is None
    assert run.filter_rejected_count == 0
    assert any("unreadable requested experience" in fault for fault in outcome.faults)
    assert "filter:" in (run.error or "")


def test_an_unreadable_experience_does_not_stop_the_title_criterion(session):
    """FR-002a is explicit: a bad experience value must not prevent the title
    criteria from applying."""
    profile = _profile(session, "vague", "whenever you like")
    run = _run(session, profile)
    posting = _posting(session, run, title="QA Analyst")

    run_filter(session, run, _config(exclude="qa analyst"))

    session.refresh(posting)
    assert posting.title_filter_passed is False
    assert posting.experience_filter_passed is None


# --- the funnel (SC-003) ----------------------------------------------------


def test_the_two_counts_account_for_every_posting_evaluated(session):
    """SC-003, contract C1 — the invariant that pins the stage's scope to the
    set stage 2 counted."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    for level in ("entry level", "mid-senior level", "director", None):
        _posting(session, run, title=f"Engineer {level}", job_level=level)

    run_filter(session, run, _config(exclude="nothing matches this"))

    assert run.filter_passed_count + run.filter_rejected_count == run.deduplicated_count


def test_a_run_whose_whole_haul_is_rejected_says_so(session, caplog):
    """The specification's edge case: in the aggregate this is indistinguishable
    from a board that has stopped responding."""
    run = _run(session)
    for title in ("QA Analyst", "QA Engineer"):
        _posting(session, run, title=title)

    with caplog.at_level(logging.WARNING):
        run_filter(session, run, _config(exclude="qa"))

    assert run.filter_rejected_count == 2
    assert any("rejected every one" in record.message for record in caplog.records)


def test_filtering_a_run_that_surfaced_nothing_is_harmless(session):
    run = _run(session)
    outcome = run_filter(session, run, _config(exclude="qa"))
    assert outcome.evaluated == 0
    assert run.filter_passed_count == 0


# --- idempotence and SC-007 -------------------------------------------------


def test_a_second_application_changes_nothing(session):
    """FR-010 — the same criteria over the same data converge."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    _posting(session, run, title="QA Analyst", job_level="director")

    first = run_filter(session, run, _config(exclude="qa analyst"))
    second = run_filter(session, run, _config(exclude="qa analyst"))

    assert first.passed == second.passed
    assert first.rejected == second.rejected


def test_sc007_a_converged_re_application_writes_nothing_at_all(session):
    """SC-007 to the letter. `postings.updated_at` carries `onupdate`, so a blind
    write would move every row's timestamp without changing a verdict. The
    changed count is zero, and the timestamp proves no UPDATE was emitted."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    posting = _posting(session, run, title="QA Analyst", job_level="director")

    run_filter(session, run, _config(exclude="qa analyst"))
    session.refresh(posting)
    stamped = posting.updated_at

    second = run_filter(session, run, _config(exclude="qa analyst"))

    session.refresh(posting)
    assert second.changed == 0
    assert posting.updated_at == stamped


def test_loosening_the_criteria_restores_a_posting(session):
    """FR-011 and FR-013 — the verdict follows the current criteria, and a
    rejection is not a one-way door."""
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst")

    run_filter(session, run, _config(exclude="qa analyst"))
    session.refresh(posting)
    assert posting.title_filter_passed is False

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is None


def test_tightening_the_criteria_rejects_without_re_collecting(session):
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst")

    run_filter(session, run, NO_CRITERIA)
    run_filter(session, run, _config(exclude="qa analyst"))

    session.refresh(posting)
    assert posting.title_filter_passed is False


# --- --dry-run (contract C4) ------------------------------------------------


def test_a_dry_run_writes_no_verdict_and_no_counter(session):
    """The only safe way to measure the criteria against real data before
    anything can be hidden."""
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst")

    outcome = run_filter(session, run, _config(exclude="qa analyst"), dry_run=True)

    session.refresh(posting)
    assert outcome.rejected == 1
    assert outcome.changed == 1
    assert posting.title_filter_passed is None
    assert run.filter_rejected_count == 0


def test_a_dry_run_leaves_updated_at_alone(session):
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst")
    stamped = posting.updated_at

    run_filter(session, run, _config(exclude="qa analyst"), dry_run=True)

    session.refresh(posting)
    assert posting.updated_at == stamped


# --- what the stage must not touch (FR-012, FR-014) ------------------------


def test_filtering_never_changes_a_triage_status(session):
    """FR-014 — rejection and operator judgement are separate facts, as employer
    suppression already establishes."""
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst", status=STATUS_SHORTLIST)
    changed_at = posting.status_changed_at

    run_filter(session, run, _config(exclude="qa analyst"))

    session.refresh(posting)
    assert posting.title_filter_passed is False
    assert posting.status == STATUS_SHORTLIST
    assert posting.status_changed_at == changed_at
    assert posting.status_history == []


def test_filtering_never_moves_the_retrieval_timestamp(session):
    """A verdict is not an observation — the distinction ADR-0012 exists for."""
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst")
    retrieved = posting.last_retrieved_at

    run_filter(session, run, _config(exclude="qa analyst"))

    session.refresh(posting)
    assert posting.last_retrieved_at == retrieved


def test_filtering_leaves_the_landing_zone_untouched(session):
    """FR-012 — every row a board returned stays landed verbatim whatever the
    verdict, which is what makes a criteria change re-appliable to history."""
    run = _run(session)
    _posting(session, run, title="QA Analyst")
    before = [(r.id, r.site, dict(r.payload)) for r in session.query(RawPosting)]

    run_filter(session, run, _config(exclude="qa analyst"))

    after = [(r.id, r.site, dict(r.payload)) for r in session.query(RawPosting)]
    assert after == before


def test_filtering_does_not_delete_a_rejected_posting(session):
    """Rejection hides rather than deletes (FR-013). No invisibility assertion
    can tell "withheld" from "gone", so the row's survival needs its own test."""
    run = _run(session)
    posting = _posting(session, run, title="QA Analyst")

    run_filter(session, run, _config(exclude="qa analyst"))

    assert session.get(Posting, posting.id) is not None


# --- filter_all (contract C2) ----------------------------------------------


def test_filter_all_evaluates_postings_from_every_run(session):
    profile = _profile(session, "fresh", "entry level")
    first = _run(session, profile)
    second = _run(session, profile)
    _posting(session, first, title="Engineer A", job_level="director")
    _posting(session, second, title="Engineer B", job_level="entry level")

    outcome = filter_all(session, NO_CRITERIA)

    assert outcome.evaluated == 2
    assert outcome.rejected == 1


def test_filter_all_writes_no_run_counters(session):
    """C2 — FR-015's counts belong to a run that evaluated postings during an
    execution; attaching a re-application's totals to a past run would decouple
    them from its collected_count."""
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    _posting(session, run, job_level="director")

    filter_all(session, NO_CRITERIA)

    session.refresh(run)
    assert run.filter_passed_count == 0
    assert run.filter_rejected_count == 0


def test_filter_all_still_records_the_verdict(session):
    profile = _profile(session, "fresh", "entry level")
    run = _run(session, profile)
    posting = _posting(session, run, job_level="director")

    filter_all(session, NO_CRITERIA)

    session.refresh(posting)
    assert posting.experience_filter_passed is False


def test_filter_all_judges_a_posting_no_run_accounts_for(session):
    """An orphan posting has no contributing profile, so the experience criterion
    cannot apply — but the global title rules still can."""
    employer = Employer(name="Orphan", normalised_name="orphan")
    session.add(employer)
    session.flush()
    posting = Posting(
        fingerprint="o" * 64,
        employer_id=employer.id,
        title="QA Analyst",
        normalised_title="qa analyst",
        sources={},
    )
    session.add(posting)
    session.commit()

    filter_all(session, _config(exclude="qa analyst"))

    session.refresh(posting)
    assert posting.title_filter_passed is False
    assert posting.experience_filter_passed is None


# --- ADR-0018: per-profile title rules ---------------------------------------
#
# SC-002 governs the balance: the cases proving nothing is wrongly withheld are
# the majority here, as they are everywhere else in the filter's tests.


def test_sc006_a_profile_with_no_patterns_writes_no_title_verdict(session):
    """Installing the columns is a no-op: a profile that sets nothing adds nothing,
    so with no global rule either the verdict column stays NULL."""
    run = _run(session, _profile(session, "plain"))
    posting = _posting(session, run)

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is None


def test_a_profile_with_no_patterns_leaves_the_global_rule_exactly_as_it_was(session):
    """Pins today's behaviour: global set, profile blank. The profile must not
    switch the global rule off, which is the failure a per-contributor
    conjunction would have (and the reason the shape is AND(global, OR(profiles)))."""
    run = _run(session, _profile(session, "plain"))
    excluded = _posting(session, run, title="QA Analyst")
    kept = _posting(session, run, title="Data Engineer")

    run_filter(session, run, _config(exclude="qa analyst"))

    session.refresh(excluded)
    session.refresh(kept)
    assert excluded.title_filter_passed is False
    assert kept.title_filter_passed is True


def test_a_profile_exclude_applies_when_there_is_no_global_rule(session):
    run = _run(session, _profile(session, "no-interns", exclude="intern"))
    excluded = _posting(session, run, title="Data Intern")
    kept = _posting(session, run, title="Data Engineer")

    run_filter(session, run, NO_CRITERIA)

    session.refresh(excluded)
    session.refresh(kept)
    assert excluded.title_filter_passed is False
    assert kept.title_filter_passed is True


def test_a_profile_include_admits_what_matches_and_only_that(session):
    run = _run(session, _profile(session, "engineers-only", include="engineer"))
    matching = _posting(session, run, title="Data Engineer")
    other = _posting(session, run, title="Account Manager")

    run_filter(session, run, NO_CRITERIA)

    session.refresh(matching)
    session.refresh(other)
    assert matching.title_filter_passed is True
    assert other.title_filter_passed is False


def test_a_profile_rule_does_not_reach_a_posting_it_did_not_surface(session):
    """The two-sided check: profile A excludes 'analyst', but only B found this
    posting, so A's rule must not touch it."""
    _profile(session, "A", exclude="analyst")
    run_b = _run(session, _profile(session, "B"))
    posting = _posting(session, run_b, title="Data Analyst")

    run_filter(session, run_b, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is None


def test_a_global_exclude_cannot_be_lifted_by_a_profile_include(session):
    """Both rules bind. A profile that asks for 'senior' does not get it past a
    house rule that says never to show 'senior'."""
    run = _run(session, _profile(session, "wants-senior", include="senior"))
    posting = _posting(session, run, title="Senior Data Engineer")

    run_filter(session, run, _config(exclude="senior"))

    session.refresh(posting)
    assert posting.title_filter_passed is False


def test_exclude_beats_include_when_the_two_come_from_different_levels(session):
    """The precedence question, answered across levels: profile include 'engineer',
    global exclude 'data' — the exclude wins."""
    run = _run(session, _profile(session, "engineers", include="engineer"))
    posting = _posting(session, run, title="Data Engineer")

    run_filter(session, run, _config(exclude="data"))

    session.refresh(posting)
    assert posting.title_filter_passed is False


def test_exclude_beats_include_within_a_single_profile(session):
    run = _run(session, _profile(session, "both", include="engineer", exclude="data"))
    posting = _posting(session, run, title="Data Engineer")

    run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is False


def test_a_global_rule_still_binds_a_posting_whose_only_contributor_is_profile_less(session):
    run = _run(session)  # a manual run-all: no profile
    posting = _posting(session, run, title="QA Analyst")

    run_filter(session, run, _config(exclude="qa analyst"))

    session.refresh(posting)
    assert posting.title_filter_passed is False


def test_two_profiles_one_excluding_and_one_silent_admit_the_posting_deliberately(session):
    """DELIBERATE, not an oversight (ADR-0018). A contributor with nothing to say
    cannot withhold anything, so it defeats another contributor's exclude. The
    alternative lets a profile the operator is not thinking about conceal a
    posting another profile asked for, and a concealed posting is unrecoverable."""
    run_a = _run(session, _profile(session, "excluding", exclude="analyst"))
    run_b = _run(session, _profile(session, "silent"))
    posting = _posting(session, run_a, title="Data Analyst")
    _attribute(session, run_b, posting)

    run_filter(session, run_a, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is True


def test_two_profiles_that_both_exclude_reject_the_posting(session):
    run_a = _run(session, _profile(session, "A", exclude="analyst"))
    run_b = _run(session, _profile(session, "B", exclude="data"))
    posting = _posting(session, run_a, title="Data Analyst")
    _attribute(session, run_b, posting)

    run_filter(session, run_a, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is False


@pytest.mark.parametrize("reversed_order", [False, True])
def test_the_title_verdict_does_not_depend_on_which_run_is_filtered(session, reversed_order):
    """FR-010 for the title column: order-independent, because disjunction is."""
    run_a = _run(session, _profile(session, "A", exclude="analyst"))
    run_b = _run(session, _profile(session, "B"))
    posting = _posting(session, run_a, title="Data Analyst")
    _attribute(session, run_b, posting)

    for run in (run_b, run_a) if reversed_order else (run_a, run_b):
        run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is True


def test_a_second_profile_surfacing_a_rejected_posting_changes_its_verdict(session):
    """DOCUMENTED, not a bug (ADR-0018). The verdict is a function of the criteria
    *and the set of contributing profiles*, so a posting one profile's exclude
    rejected is admitted once a silent profile also surfaces it, with no criteria
    change at all. The converged re-application property holds for a fixed set of
    contributors."""
    run_a = _run(session, _profile(session, "A", exclude="analyst"))
    posting = _posting(session, run_a, title="Data Analyst")
    run_filter(session, run_a, NO_CRITERIA)
    session.refresh(posting)
    assert posting.title_filter_passed is False

    run_b = _run(session, _profile(session, "B"))
    _attribute(session, run_b, posting)
    outcome = run_filter(session, run_b, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is True
    assert outcome.changed == 1


def test_a_malformed_profile_pattern_rejects_nothing_and_names_the_profile(session):
    """FR-008, per profile. The fault must say *which* profile, or an operator
    with several cannot tell which to fix, and it must be reported once even
    though that profile surfaced several postings."""
    run = _run(session, _profile(session, "Backend developer", exclude="developer("))
    postings = [_posting(session, run, title=f"Role {n}") for n in range(3)]

    outcome = run_filter(session, run, NO_CRITERIA)

    assert run.filter_rejected_count == 0
    for posting in postings:
        session.refresh(posting)
        assert posting.title_filter_passed is None
    mine = [fault for fault in outcome.faults if "Backend developer" in fault]
    assert len(mine) == 1
    assert "not a valid expression" in mine[0]
    assert "Backend developer" in (run.error or "")


def test_a_malformed_profile_pattern_does_not_disable_the_global_rule(session):
    run = _run(session, _profile(session, "broken", exclude="developer("))
    excluded = _posting(session, run, title="QA Analyst")

    run_filter(session, run, _config(exclude="qa analyst"))

    session.refresh(excluded)
    assert excluded.title_filter_passed is False


def test_two_profiles_with_malformed_patterns_are_both_reported(session):
    """An assignment instead of an accumulation would keep only the last."""
    run_a = _run(session, _profile(session, "first", exclude="a("))
    run_b = _run(session, _profile(session, "second", include="b["))
    posting = _posting(session, run_a)
    _attribute(session, run_b, posting)

    outcome = run_filter(session, run_a, NO_CRITERIA)

    text = " | ".join(outcome.faults)
    assert "first" in text
    assert "second" in text


def test_a_converged_re_application_with_profile_rules_writes_nothing(session):
    """SC-007 survives per-profile rules: the guard compares before it writes."""
    run = _run(session, _profile(session, "P", exclude="analyst"))
    posting = _posting(session, run, title="Data Analyst")
    run_filter(session, run, NO_CRITERIA)
    session.refresh(posting)
    stamped = posting.updated_at

    second = run_filter(session, run, NO_CRITERIA)

    session.refresh(posting)
    assert second.changed == 0
    assert posting.updated_at == stamped


def test_loosening_a_profile_rule_restores_the_posting_without_re_collecting(session):
    profile = _profile(session, "P", exclude="analyst")
    run = _run(session, profile)
    posting = _posting(session, run, title="Data Analyst")
    run_filter(session, run, NO_CRITERIA)
    session.refresh(posting)
    assert posting.title_filter_passed is False

    profile.title_exclude_pattern = None
    session.commit()
    filter_all(session, NO_CRITERIA)

    session.refresh(posting)
    assert posting.title_filter_passed is None  # not applied, rather than "passed"


# --- the stage and the detail page must reach the same verdict ----------------


def _pin_global_rules(session, *, include: str = "", exclude: str = "") -> None:
    """`current_verdict` resolves criteria through `RunConfig.resolve`, which reads
    `app_settings`; pin both keys so this installation's .env cannot decide the test."""
    session.add(AppSetting(key="title_include_pattern", value=include))
    session.add(AppSetting(key="title_exclude_pattern", value=exclude))
    session.commit()


@pytest.mark.parametrize(
    ("global_exclude", "a_exclude", "b_exclude", "title"),
    [
        ("", "", "", "Data Analyst"),  # nothing set anywhere -> NULL
        ("analyst", "", "", "Data Analyst"),  # global only
        ("", "analyst", "", "Data Analyst"),  # one profile excludes, one silent
        ("", "analyst", "data", "Data Analyst"),  # both profiles exclude
        ("data", "analyst", "", "Data Analyst"),  # global + a silent profile
        ("", "", "", "Data Engineer"),
    ],
)
def test_the_detail_page_and_the_stage_reach_the_same_verdict(
    session, global_exclude, a_exclude, b_exclude, title
):
    """Both go through `filters.build_criteria`, and this is the test that says so.
    Without it the stored verdict and the displayed one could drift apart with
    every other test still green, and the page would then tell the operator that
    their criteria had changed when only the code had."""
    _pin_global_rules(session, exclude=global_exclude)
    run_a = _run(session, _profile(session, "A", exclude=a_exclude or None))
    run_b = _run(session, _profile(session, "B", exclude=b_exclude or None))
    posting = _posting(session, run_a, title=title)
    _attribute(session, run_b, posting)

    filter_all(session, _config(exclude=global_exclude))
    session.refresh(posting)
    live = current_verdict(session, posting)

    assert live.title_passed is posting.title_filter_passed
    assert live.experience_passed is posting.experience_filter_passed
