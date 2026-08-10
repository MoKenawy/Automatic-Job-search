"""Scheduler reload (Phase 1, refactor-plan.md §2.2).

`web` and `scheduler` are separate containers (docker-compose.yml); a profile
edited through the UI can only reach the scheduler process by having it poll
the database. These tests exercise the poll directly rather than through
BlockingScheduler.start(), since job execution itself is APScheduler's concern,
not this application's.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, SearchProfile
from app.scheduler import _RELOAD_JOB_ID, _register_jobs, build_scheduler


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture
def fake_session_scope(session_factory, monkeypatch):
    """Stand in for app.db.session_scope, bound to the in-memory engine."""

    @contextmanager
    def _scope():
        session = session_factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr("app.scheduler.session_scope", _scope)
    return _scope


def _add_profile(session_factory, **over) -> int:
    base = {
        "name": "Data eng Cairo",
        "term": "data engineer",
        "country": "egypt",
        "sites": ["indeed"],
        "schedule_hour": 6,
        "schedule_minute": 0,
        "enabled": True,
    }
    base.update(over)
    with session_factory() as session:
        profile = SearchProfile(**base)
        session.add(profile)
        session.commit()
        return profile.id


def test_register_jobs_creates_one_job_per_enabled_profile(fake_session_scope, session_factory):
    _add_profile(session_factory, name="a")
    _add_profile(session_factory, name="b", enabled=False)

    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    count = _register_jobs(scheduler, lambda profile_id: None)

    assert count == 1
    assert [j.id for j in scheduler.get_jobs()] == ["profile-1"]


def test_register_jobs_preserves_non_profile_jobs(fake_session_scope, session_factory):
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    scheduler.add_job(lambda: None, "interval", minutes=5, id=_RELOAD_JOB_ID)

    _register_jobs(scheduler, lambda profile_id: None)

    assert scheduler.get_job(_RELOAD_JOB_ID) is not None


def test_reload_picks_up_a_profile_added_after_startup(fake_session_scope, session_factory):
    """The live gap this closes: editing/adding a profile through the web
    container previously had no effect until the scheduler container restarted."""
    scheduler = build_scheduler(lambda profile_id: None, reload_interval_minutes=5)
    assert [j.id for j in scheduler.get_jobs() if j.id.startswith("profile-")] == []

    _add_profile(session_factory, name="added later")

    reload_job = scheduler.get_job(_RELOAD_JOB_ID)
    reload_job.func()

    assert [j.id for j in scheduler.get_jobs() if j.id.startswith("profile-")] == ["profile-1"]


def test_reload_is_a_noop_when_nothing_changed(fake_session_scope, session_factory, monkeypatch):
    _add_profile(session_factory)
    scheduler = build_scheduler(lambda profile_id: None, reload_interval_minutes=5)

    calls = []
    import app.scheduler as scheduler_module

    monkeypatch.setattr(
        scheduler_module,
        "_register_jobs",
        lambda *a, **k: calls.append(1),
    )

    scheduler.get_job(_RELOAD_JOB_ID).func()

    assert calls == []
