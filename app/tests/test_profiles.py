"""US4 — search-profile CRUD, validation, and scheduling read model."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.settings_store import profiles


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
