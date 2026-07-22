"""US4 — runtime settings store: resolution order, validation, apply."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.models import Base
from app.settings_store import store


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


def test_get_falls_back_to_env_default(session):
    """No DB row → the environment/code default (FR: resolution order)."""
    assert store.get(session, "publish_threshold") == settings.publish_threshold


def test_db_value_overrides_default(session):
    store.set_many(session, store.coerce_form({"publish_threshold": "75"}))
    assert store.get(session, "publish_threshold") == 75
    assert store.get(session, "publish_threshold") != settings.publish_threshold


def test_invalid_value_rejected_and_prior_stands(session):
    store.set_many(session, store.coerce_form({"publish_threshold": "60"}))
    with pytest.raises(store.ValidationError):
        store.set_many(session, store.coerce_form({"publish_threshold": "150"}))
    # Prior value retained (FR-015)
    assert store.get(session, "publish_threshold") == 60


def test_negative_delay_rejected(session):
    with pytest.raises(store.ValidationError):
        store.set_many(session, store.coerce_form({"request_delay_seconds": "-5"}))


def test_zero_results_rejected(session):
    with pytest.raises(store.ValidationError):
        store.set_many(session, store.coerce_form({"results_per_search": "0"}))


def test_all_effective_covers_every_editable_key(session):
    eff = store.all_effective(session)
    assert set(eff.keys()) == set(store.EDITABLE_KEYS)


def test_apply_to_settings_overlays_singleton(session):
    original = settings.publish_threshold
    try:
        store.set_many(session, store.coerce_form({"publish_threshold": "42"}))
        store.apply_to_settings(session)
        assert settings.publish_threshold == 42
    finally:
        settings.publish_threshold = original  # don't leak into other tests


def test_proxies_parsed_from_multiline(session):
    store.set_many(session, store.coerce_form({"proxies": "http://a\nhttp://b"}))
    assert store.get(session, "proxies") == ["http://a", "http://b"]


def test_linkedin_fetch_toggle(session):
    store.set_many(session, store.coerce_form({"linkedin_fetch_description": "on"}))
    assert store.get(session, "linkedin_fetch_description") is True


def test_readonly_keys_are_not_editable(session):
    for key in store.READONLY_KEYS:
        assert key not in store.EDITABLE_KEYS
