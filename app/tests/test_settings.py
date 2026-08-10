"""US4 — runtime settings: resolution order, validation, RunConfig."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.models import Base
from app.services import settings as settings_service


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
    assert settings_service.get(session, "publish_threshold") == settings.publish_threshold


def test_db_value_overrides_default(session):
    settings_service.set_many(session, settings_service.coerce_form({"publish_threshold": "75"}))
    assert settings_service.get(session, "publish_threshold") == 75
    assert settings_service.get(session, "publish_threshold") != settings.publish_threshold


def test_invalid_value_rejected_and_prior_stands(session):
    settings_service.set_many(session, settings_service.coerce_form({"publish_threshold": "60"}))
    with pytest.raises(settings_service.ValidationError):
        settings_service.set_many(
            session, settings_service.coerce_form({"publish_threshold": "150"})
        )
    # Prior value retained (FR-015)
    assert settings_service.get(session, "publish_threshold") == 60


def test_negative_delay_rejected(session):
    with pytest.raises(settings_service.ValidationError):
        settings_service.set_many(
            session, settings_service.coerce_form({"request_delay_seconds": "-5"})
        )


def test_zero_results_rejected(session):
    with pytest.raises(settings_service.ValidationError):
        settings_service.set_many(
            session, settings_service.coerce_form({"results_per_search": "0"})
        )


def test_all_effective_covers_every_editable_key(session):
    eff = settings_service.all_effective(session)
    assert set(eff.keys()) == set(settings_service.EDITABLE_KEYS)


def test_run_config_resolves_db_override_without_touching_the_singleton(session):
    """Replaces the old apply_to_settings() overlay (refactor-plan.md §3): a DB
    override must reach RunConfig without mutating the process-wide `settings`
    singleton, so two runs can hold different configurations."""
    from app.config import RunConfig

    original = settings.publish_threshold
    settings_service.set_many(session, settings_service.coerce_form({"publish_threshold": "42"}))

    config = RunConfig.resolve(session)

    assert config.publish_threshold == 42
    assert settings.publish_threshold == original  # singleton untouched


def test_run_config_falls_back_to_code_default_with_no_overrides(session):
    from app.config import RunConfig

    config = RunConfig.resolve(session)
    assert config.results_per_search == settings.results_per_search
    assert config.request_delay_seconds == settings.request_delay_seconds


def test_proxies_parsed_from_multiline(session):
    settings_service.set_many(
        session, settings_service.coerce_form({"proxies": "http://a\nhttp://b"})
    )
    assert settings_service.get(session, "proxies") == ["http://a", "http://b"]


def test_linkedin_fetch_toggle(session):
    settings_service.set_many(
        session, settings_service.coerce_form({"linkedin_fetch_description": "on"})
    )
    assert settings_service.get(session, "linkedin_fetch_description") is True


def test_readonly_keys_are_not_editable(session):
    for key in settings_service.READONLY_KEYS:
        assert key not in settings_service.EDITABLE_KEYS


def test_every_editable_key_is_consumed_or_pending():
    """An editable key that is neither consumed nor pending drives nothing —
    exactly the state `request_delay_seconds` was silently in. This must fail
    the moment a new setting is added without also declaring where it is read."""
    accounted = settings_service.CONSUMED_KEYS | settings_service.PENDING_KEYS
    assert set(settings_service.EDITABLE_KEYS) == accounted
    assert not (settings_service.CONSUMED_KEYS & settings_service.PENDING_KEYS)
