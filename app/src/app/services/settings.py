"""Runtime-editable operational settings (US4, ADR-0005).

Resolution order on read: `app_settings` value → environment/`.env` default →
code default (the last two are already resolved by the `Settings` singleton).
Only the keys in EDITABLE may be stored; secrets and restart-only settings are
never written here.
"""

import logging
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AppSetting

log = logging.getLogger(__name__)


class _EditableModel(BaseModel):
    """Validates the editable settings. Field names must match Settings fields."""

    results_per_search: int
    hours_old: int
    request_delay_seconds: float
    publish_threshold: int
    scoring_model: str
    linkedin_fetch_description: bool
    title_include_pattern: str
    title_exclude_pattern: str
    proxies: list[str]

    @field_validator("results_per_search", "hours_old")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    @field_validator("request_delay_seconds")
    @classmethod
    def _non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must not be negative")
        return v

    @field_validator("publish_threshold")
    @classmethod
    def _percent(cls, v: int) -> int:
        if not 0 <= v <= 100:
            raise ValueError("must be between 0 and 100")
        return v


# The keys the UI may edit, in a stable display order.
EDITABLE_KEYS: tuple[str, ...] = tuple(_EditableModel.model_fields.keys())

# Shown but not editable (restart-affecting).
READONLY_KEYS: tuple[str, ...] = ("timezone", "web_host", "web_port")

# Every editable key must appear in exactly one of these two sets. An editable
# setting that is neither read by a named consumer nor explicitly pending is a
# setting that silently does nothing — `request_delay_seconds` was exactly this
# until it was wired into app.collect.client. See test_every_editable_
# key_is_consumed_or_pending, which fails the moment a key falls through the gap.
CONSUMED_KEYS: frozenset[str] = frozenset({
    "results_per_search",           # collect_one -> results_wanted
    "hours_old",                    # collect_one -> hours_old
    "request_delay_seconds",        # collect_one -> time.sleep between sites
    "linkedin_fetch_description",   # collect_one -> linkedin kwarg
    "proxies",                      # collect_one -> proxies kwarg
})

# Declared and validated ahead of the stage that will read them (stages 3-4 are
# not yet implemented). Listed here rather than silently unconsumed.
PENDING_KEYS: frozenset[str] = frozenset({
    "publish_threshold",     # stage 4 - publication
    "scoring_model",         # stage 3 - scoring
    "title_include_pattern",  # stage 3 - title filter
    "title_exclude_pattern",  # stage 3 - title filter
})


def get(session: Session, key: str) -> Any:
    """Effective value: DB override if present, else the environment/code default."""
    if key not in EDITABLE_KEYS:
        return getattr(settings, key)
    row = session.get(AppSetting, key)
    if row is not None:
        return row.value
    return getattr(settings, key)


def all_effective(session: Session) -> dict[str, Any]:
    """Every editable key resolved to its effective value."""
    return {key: get(session, key) for key in EDITABLE_KEYS}


def set_many(session: Session, values: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist a full set of editable values.

    Validates the whole set together (so cross-field rules could be added), then
    upserts each key. Raises ValidationError on invalid input; the caller reports
    it and the prior values stand (FR-015).
    """
    validated = _EditableModel(**values).model_dump()
    for key, value in validated.items():
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    session.commit()
    log.info("settings updated: %s", ", ".join(validated))
    return validated


def coerce_form(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn HTML form strings into the types the validator expects.

    Kept separate from validation so a bad type surfaces as a validation error
    rather than a coercion crash.
    """

    def _as_bool(v: Any) -> bool:
        return str(v).lower() in {"1", "true", "on", "yes"}

    def _as_list(v: Any) -> list[str]:
        if isinstance(v, list):
            return [s.strip() for s in v if str(s).strip()]
        return [s.strip() for s in str(v).splitlines() if s.strip()]

    return {
        "results_per_search": int(raw.get("results_per_search", settings.results_per_search)),
        "hours_old": int(raw.get("hours_old", settings.hours_old)),
        "request_delay_seconds": float(
            raw.get("request_delay_seconds", settings.request_delay_seconds)
        ),
        "publish_threshold": int(raw.get("publish_threshold", settings.publish_threshold)),
        "scoring_model": str(raw.get("scoring_model", settings.scoring_model)).strip(),
        "linkedin_fetch_description": _as_bool(raw.get("linkedin_fetch_description", False)),
        "title_include_pattern": str(raw.get("title_include_pattern", "")),
        "title_exclude_pattern": str(raw.get("title_exclude_pattern", "")),
        "proxies": _as_list(raw.get("proxies", [])),
    }


__all__ = [
    "CONSUMED_KEYS",
    "EDITABLE_KEYS",
    "PENDING_KEYS",
    "READONLY_KEYS",
    "ValidationError",
    "all_effective",
    "coerce_form",
    "get",
    "set_many",
]
