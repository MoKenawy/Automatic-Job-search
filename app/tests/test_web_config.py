"""US4 — settings and profiles web routes."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.settings_store import profiles, store
from app.web.app import app, get_db


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture
def client(factory):
    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- settings --------------------------------------------------------------


def test_settings_page_renders(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert "publish_threshold" in r.text


def test_settings_save_persists_and_redirects(client, factory):
    r = client.post(
        "/settings",
        data={"publish_threshold": "72", "results_per_search": "20", "hours_old": "48",
              "request_delay_seconds": "10", "scoring_model": "qwen2.5:7b-instruct"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with factory() as s:
        assert store.get(s, "publish_threshold") == 72


def test_settings_invalid_shows_error_and_keeps_prior(client, factory):
    r = client.post(
        "/settings",
        data={"publish_threshold": "150", "results_per_search": "20", "hours_old": "48",
              "request_delay_seconds": "10", "scoring_model": "x"},
    )
    assert r.status_code == 400
    with factory() as s:
        # nothing persisted
        from app.db.models import AppSetting
        assert s.get(AppSetting, "publish_threshold") is None


# --- profiles --------------------------------------------------------------


def test_profiles_page_renders(client):
    assert client.get("/profiles").status_code == 200


def test_create_profile_via_form(client, factory):
    r = client.post(
        "/profiles",
        data={"name": "Remote DE", "term": "data engineer", "sites": ["indeed", "linkedin"],
              "is_remote": "on", "schedule_hour": "7", "schedule_minute": "30"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with factory() as s:
        all_p = profiles.list_all(s)
        assert len(all_p) == 1
        assert all_p[0].is_remote is True
        assert all_p[0].schedule_hour == 7


def test_create_profile_no_sites_reports_error(client, factory):
    r = client.post(
        "/profiles",
        data={"name": "Bad", "term": "x", "schedule_hour": "6", "schedule_minute": "0"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]
    with factory() as s:
        assert profiles.list_all(s) == []


def test_disable_profile_excludes_from_scheduling(client, factory):
    with factory() as s:
        p = profiles.create(
            s, name="P", term="data engineer", sites=["indeed"],
            schedule_hour="6", schedule_minute="0",
        )
        pid = p.id
    client.post(f"/profiles/{pid}/enabled", data={"enabled": "false"}, follow_redirects=False)
    with factory() as s:
        assert profiles.enabled_specs(s) == []


def test_delete_profile(client, factory):
    with factory() as s:
        p = profiles.create(
            s, name="P", term="data engineer", sites=["indeed"],
            schedule_hour="6", schedule_minute="0",
        )
        pid = p.id
    client.post(f"/profiles/{pid}/delete", follow_redirects=False)
    with factory() as s:
        assert profiles.list_all(s) == []
