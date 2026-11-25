"""US4 — settings and profiles web routes."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.services import profiles
from app.services import settings as settings_service
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
        data={
            "publish_threshold": "72",
            "results_per_search": "20",
            "hours_old": "48",
            "request_delay_seconds": "10",
            "scoring_model": "qwen2.5:7b-instruct",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with factory() as s:
        assert settings_service.get(s, "publish_threshold") == 72


def test_settings_invalid_shows_error_and_keeps_prior(client, factory):
    r = client.post(
        "/settings",
        data={
            "publish_threshold": "150",
            "results_per_search": "20",
            "hours_old": "48",
            "request_delay_seconds": "10",
            "scoring_model": "x",
        },
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
        data={
            "name": "Remote DE",
            "term": "data engineer",
            "sites": ["indeed", "linkedin"],
            "is_remote": "on",
            "schedule_hour": "7",
            "schedule_minute": "30",
        },
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
            s,
            name="P",
            term="data engineer",
            sites=["indeed"],
            schedule_hour="6",
            schedule_minute="0",
        )
        pid = p.id
    client.post(f"/profiles/{pid}/enabled", data={"enabled": "false"}, follow_redirects=False)
    with factory() as s:
        assert profiles.enabled_specs(s) == []


def test_delete_profile(client, factory):
    with factory() as s:
        p = profiles.create(
            s,
            name="P",
            term="data engineer",
            sites=["indeed"],
            schedule_hour="6",
            schedule_minute="0",
        )
        pid = p.id
    client.post(f"/profiles/{pid}/delete", follow_redirects=False)
    with factory() as s:
        assert profiles.list_all(s) == []


# --- ADR-0018: per-profile filter rules ----------------------------------------


def _make_profile(factory, **over) -> int:
    fields = {
        "name": "P",
        "term": "data engineer",
        "sites": ["indeed"],
        "schedule_hour": "6",
        "schedule_minute": "0",
    }
    fields.update(over)
    with factory() as s:
        return profiles.create(s, **fields).id


def test_the_filter_rules_form_saves_the_three_fields(client, factory):
    pid = _make_profile(factory)
    r = client.post(
        f"/profiles/{pid}/filters",
        data={
            "experience": "entry level",
            "title_include_pattern": "engineer",
            "title_exclude_pattern": "senior",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" not in r.headers["location"]
    with factory() as s:
        p = profiles.list_all(s)[0]
        assert (p.experience, p.title_include_pattern, p.title_exclude_pattern) == (
            "entry level",
            "engineer",
            "senior",
        )


def test_the_filter_rules_form_does_not_re_enable_a_disabled_profile(client, factory):
    """The hazard that ruled out posting a form to the generic update route."""
    pid = _make_profile(factory)
    client.post(f"/profiles/{pid}/enabled", data={"enabled": "false"}, follow_redirects=False)

    client.post(
        f"/profiles/{pid}/filters",
        data={"experience": "junior", "title_include_pattern": "", "title_exclude_pattern": ""},
        follow_redirects=False,
    )

    with factory() as s:
        assert profiles.list_all(s)[0].enabled is False
        assert profiles.enabled_specs(s) == []


def test_the_filter_rules_form_reports_a_malformed_pattern_and_saves_nothing(client, factory):
    pid = _make_profile(factory, experience="senior")
    r = client.post(
        f"/profiles/{pid}/filters",
        data={
            "experience": "entry level",
            "title_include_pattern": "",
            "title_exclude_pattern": "developer(",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]
    with factory() as s:
        assert profiles.list_all(s)[0].experience == "senior"


def test_the_filter_rules_form_on_a_missing_profile_reports_an_error(client):
    r = client.post(
        "/profiles/999/filters",
        data={"experience": "", "title_include_pattern": "", "title_exclude_pattern": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]


def test_the_profiles_page_shows_each_profiles_rules_and_the_form(client, factory):
    _make_profile(
        factory, name="Has rules", experience="junior", title_exclude_pattern="intern|sales"
    )
    _make_profile(factory, name="No rules")
    html = client.get("/profiles").text
    assert "intern|sales" in html
    assert "none set" in html  # the profile with nothing says so
    assert "Save filter rules" in html
    assert "/filters" in html


def test_the_profiles_page_states_how_the_levels_combine(client):
    """The operator-facing statement of the rules (ADR-0018), kept on the page the
    rules are edited on rather than only in the docs."""
    html = client.get("/profiles").text
    assert "in addition to" in html
    assert "exclude always beats include" in html
    assert "filter --all" in html


def test_the_add_form_says_how_to_word_the_search_term(client):
    """ADR-0020: JobSpy has no experience parameter, so the term is the only
    collection lever — and seniority in it loses roles unrecoverably (FR-012)."""
    html = client.get("/profiles").text
    assert 'id="term-hint"' in html
    assert "plain keyword search" in html
    assert "can't be recovered later" in html
    assert "<strong>second</strong> profile" in html


def test_the_experience_hint_appears_on_both_forms(client, factory):
    pid = _make_profile(factory, name="Has a form")
    html = client.get("/profiles").text
    assert 'id="experience-hint"' in html  # the add form
    assert f'id="exp-{pid}-hint"' in html  # the per-profile filter rules form
    assert "it never narrows the search" in html
    assert "Indeed postings on title words only" in html


def test_every_experience_word_the_hint_lists_is_understood(client, factory):
    """Keeps the help text honest: if a synonym is dropped from filters.levels,
    the page must stop advertising it."""
    import re

    from app.filters.levels import parse_requested

    html = client.get("/profiles").text
    hint = re.search(r'<p [^>]*id="experience-hint">(.*?)</p>', html, re.S).group(1)
    words = re.findall(r"<code>(.*?)</code>", hint)

    assert len(words) == 9
    unreadable = [w for w in words if parse_requested(w) is None]
    assert not unreadable, unreadable


def test_the_add_form_accepts_title_patterns(client, factory):
    r = client.post(
        "/profiles",
        data={
            "name": "With rules",
            "term": "x",
            "sites": ["indeed"],
            "schedule_hour": "6",
            "schedule_minute": "0",
            "title_exclude_pattern": "intern",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with factory() as s:
        assert profiles.list_all(s)[0].title_exclude_pattern == "intern"


def test_settings_page_never_shows_the_database_url(client):
    """FR-012: the URL, even partly, never reaches the page."""
    from app.config import settings

    html = client.get("/settings").text
    assert "hidden — environment only" in html
    assert "postgresql://" not in html
    assert settings.database_url not in html
