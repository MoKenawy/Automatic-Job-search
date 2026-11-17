"""US4 — search-profile CRUD, validation, and scheduling read model."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.services import profiles


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        yield s


def _valid(**over):
    base = {
        "name": "Data eng Cairo",
        "term": "data engineer",
        "location": "Cairo, Egypt",
        "country": "egypt",
        "sites": ["indeed", "linkedin"],
        "schedule_hour": "6",
        "schedule_minute": "0",
    }
    base.update(over)
    return base


def test_create_and_list(session):
    profiles.create(session, **_valid())
    assert len(profiles.list_all(session)) == 1


def test_create_rejects_no_sites(session):
    with pytest.raises(profiles.ProfileError):
        profiles.create(session, **_valid(sites=[]))


def test_create_rejects_unknown_site(session):
    with pytest.raises(profiles.ProfileError):
        profiles.create(session, **_valid(sites=["monster"]))


def test_create_rejects_blank_term(session):
    with pytest.raises(profiles.ProfileError):
        profiles.create(session, **_valid(term="  "))


def test_create_rejects_bad_schedule(session):
    with pytest.raises(profiles.ProfileError):
        profiles.create(session, **_valid(schedule_hour="25"))


def test_duplicate_name_rejected(session):
    profiles.create(session, **_valid())
    with pytest.raises(profiles.ProfileError):
        profiles.create(session, **_valid())


def test_update(session):
    p = profiles.create(session, **_valid())
    profiles.update(session, p.id, **_valid(term="senior data engineer"))
    assert profiles.list_all(session)[0].term == "senior data engineer"


def test_enable_disable_controls_scheduling(session):
    p = profiles.create(session, **_valid())
    assert len(profiles.list_enabled(session)) == 1
    profiles.set_enabled(session, p.id, False)
    assert len(profiles.list_enabled(session)) == 0
    # Retained for re-enabling (FR: disable, not delete)
    assert len(profiles.list_all(session)) == 1


def test_delete(session):
    p = profiles.create(session, **_valid())
    profiles.delete(session, p.id)
    assert profiles.list_all(session) == []


def test_enabled_specs_convert_to_searchspecs(session):
    profiles.create(session, **_valid(name="a"))
    profiles.create(session, **_valid(name="b", is_remote="on", sites=["linkedin"]))
    specs = profiles.enabled_specs(session)
    assert len(specs) == 2
    assert any(s.is_remote for s in specs)
    assert all(s.term == "data engineer" for s in specs)


def test_only_enabled_profiles_produce_specs(session):
    p = profiles.create(session, **_valid())
    profiles.set_enabled(session, p.id, False)
    assert profiles.enabled_specs(session) == []


# --- ADR-0018: per-profile filter rules ----------------------------------------


def test_a_new_profile_carries_no_rules_by_default(session):
    """Installing the columns changes nothing: NULL means 'this profile adds nothing'."""
    p = profiles.create(session, **_valid())
    assert p.title_include_pattern is None
    assert p.title_exclude_pattern is None


def test_create_stores_patterns_when_supplied(session):
    p = profiles.create(
        session,
        **_valid(title_include_pattern="engineer", title_exclude_pattern="  intern|sales  "),
    )
    assert p.title_include_pattern == "engineer"
    assert p.title_exclude_pattern == "intern|sales"  # stripped


def test_create_refuses_a_malformed_pattern_and_names_the_field(session):
    with pytest.raises(profiles.ProfileError) as excinfo:
        profiles.create(session, **_valid(title_exclude_pattern="developer("))
    assert "title_exclude_pattern" in str(excinfo.value)
    assert profiles.list_all(session) == []  # nothing half-created


def test_create_refuses_a_malformed_include_pattern_too(session):
    with pytest.raises(profiles.ProfileError):
        profiles.create(session, **_valid(title_include_pattern="engineer["))


def test_an_empty_pattern_is_not_an_error_and_is_stored_as_null(session):
    """The empty pattern is the shipped default and means 'off' — it must never
    be refused, and never stored as a pattern that matches everything."""
    p = profiles.create(session, **_valid(title_include_pattern="", title_exclude_pattern="  "))
    assert p.title_include_pattern is None
    assert p.title_exclude_pattern is None


def test_update_without_the_pattern_keys_leaves_the_patterns_alone(session):
    """`update()` writes whatever `_clean` returns, and `_clean` defaults every
    other field it is not sent. The patterns deliberately do not inherit that:
    a form that has never heard of them must not erase them by omission."""
    p = profiles.create(session, **_valid(title_exclude_pattern="intern"))
    profiles.update(session, p.id, **_valid(term="data scientist"))
    session.refresh(p)
    assert p.term == "data scientist"
    assert p.title_exclude_pattern == "intern"


def test_update_can_still_clear_a_pattern_when_it_is_sent_empty(session):
    p = profiles.create(session, **_valid(title_exclude_pattern="intern"))
    profiles.update(session, p.id, **_valid(title_exclude_pattern=""))
    session.refresh(p)
    assert p.title_exclude_pattern is None


def test_set_filter_rules_writes_the_three_fields(session):
    p = profiles.create(session, **_valid())
    profiles.set_filter_rules(
        session,
        p.id,
        experience="entry level",
        title_include_pattern="engineer",
        title_exclude_pattern="senior",
    )
    session.refresh(p)
    assert (p.experience, p.title_include_pattern, p.title_exclude_pattern) == (
        "entry level",
        "engineer",
        "senior",
    )


def test_set_filter_rules_touches_nothing_else(session):
    """The reason it exists. A form routed through `update()` would reset country
    and schedule, blank the location, and re-enable a disabled profile."""
    p = profiles.create(
        session,
        **_valid(location="Cairo, Egypt", country="germany", schedule_hour="9", is_remote="on"),
    )
    profiles.set_enabled(session, p.id, False)

    profiles.set_filter_rules(
        session, p.id, experience="junior", title_include_pattern="", title_exclude_pattern=""
    )

    session.refresh(p)
    assert p.enabled is False  # NOT silently re-enabled
    assert p.location == "Cairo, Egypt"
    assert p.country == "germany"
    assert p.schedule_hour == 9
    assert p.is_remote is True
    assert p.name == "Data eng Cairo"
    assert p.term == "data engineer"
    assert p.sites == ["indeed", "linkedin"]


def test_set_filter_rules_turns_blanks_into_null(session):
    p = profiles.create(session, **_valid(experience="senior", title_exclude_pattern="intern"))
    profiles.set_filter_rules(
        session, p.id, experience="  ", title_include_pattern="", title_exclude_pattern=""
    )
    session.refresh(p)
    assert (p.experience, p.title_include_pattern, p.title_exclude_pattern) == (None, None, None)


def test_set_filter_rules_refuses_a_malformed_pattern_and_changes_nothing(session):
    p = profiles.create(session, **_valid(experience="senior", title_exclude_pattern="intern"))
    with pytest.raises(profiles.ProfileError):
        profiles.set_filter_rules(
            session,
            p.id,
            experience="entry level",
            title_include_pattern="ok",
            title_exclude_pattern="bad(",
        )
    session.refresh(p)
    # All-or-nothing: the valid fields were not applied either.
    assert (p.experience, p.title_include_pattern, p.title_exclude_pattern) == (
        "senior",
        None,
        "intern",
    )


def test_set_filter_rules_on_a_missing_profile_is_an_error(session):
    with pytest.raises(profiles.ProfileError):
        profiles.set_filter_rules(
            session, 999, experience=None, title_include_pattern=None, title_exclude_pattern=None
        )


def test_set_filter_rules_accepts_an_unrecognised_experience_like_the_add_form(session):
    """Not validated here: an unreadable value is reported by the filter stage
    (FR-002a) rather than refused, matching how the add form already behaves."""
    p = profiles.create(session, **_valid())
    profiles.set_filter_rules(
        session, p.id, experience="whatever", title_include_pattern="", title_exclude_pattern=""
    )
    session.refresh(p)
    assert p.experience == "whatever"
