"""Search-profile CRUD and conversion to collector specs (US4, ADR-0005)."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import WORKING_SITES, SearchSpec
from app.db.models import SearchProfile

log = logging.getLogger(__name__)


class ProfileError(ValueError):
    """Raised on invalid profile input; the caller reports it to the operator."""


def list_all(session: Session) -> list[SearchProfile]:
    return list(session.scalars(select(SearchProfile).order_by(SearchProfile.name)).all())


def list_enabled(session: Session) -> list[SearchProfile]:
    return list(
        session.scalars(
            select(SearchProfile).where(SearchProfile.enabled.is_(True)).order_by(SearchProfile.id)
        ).all()
    )


def to_spec(profile: SearchProfile) -> SearchSpec:
    """Convert a stored profile into a collector SearchSpec."""
    return SearchSpec(
        term=profile.term,
        location=profile.location,
        country=profile.country,
        is_remote=profile.is_remote,
        sites=list(profile.sites or WORKING_SITES),
    )


def enabled_specs(session: Session) -> list[SearchSpec]:
    return [to_spec(p) for p in list_enabled(session)]


def _validate(name, term, sites, hour, minute) -> None:
    if not name or not name.strip():
        raise ProfileError("name is required")
    if not term or not term.strip():
        raise ProfileError("role/term is required")
    if not sites:
        raise ProfileError("at least one site must be selected")
    unknown = [s for s in sites if s not in WORKING_SITES]
    if unknown:
        raise ProfileError(f"unsupported site(s): {', '.join(unknown)}")
    if not 0 <= hour <= 23:
        raise ProfileError("hour must be 0–23")
    if not 0 <= minute <= 59:
        raise ProfileError("minute must be 0–59")


def create(session: Session, **fields) -> SearchProfile:
    data = _clean(fields)
    _validate(
        data["name"], data["term"], data["sites"], data["schedule_hour"], data["schedule_minute"]
    )
    if session.scalar(select(SearchProfile).where(SearchProfile.name == data["name"])):
        raise ProfileError(f"a profile named {data['name']!r} already exists")
    profile = SearchProfile(**data)
    session.add(profile)
    session.commit()
    log.info("profile created: %s", profile.name)
    return profile


def update(session: Session, profile_id: int, **fields) -> SearchProfile:
    profile = session.get(SearchProfile, profile_id)
    if profile is None:
        raise ProfileError("profile not found")
    data = _clean(fields)
    _validate(
        data["name"], data["term"], data["sites"], data["schedule_hour"], data["schedule_minute"]
    )
    clash = session.scalar(
        select(SearchProfile).where(
            SearchProfile.name == data["name"], SearchProfile.id != profile_id
        )
    )
    if clash:
        raise ProfileError(f"a profile named {data['name']!r} already exists")
    for k, v in data.items():
        setattr(profile, k, v)
    session.commit()
    return profile


def set_enabled(session: Session, profile_id: int, enabled: bool) -> SearchProfile:
    profile = session.get(SearchProfile, profile_id)
    if profile is None:
        raise ProfileError("profile not found")
    profile.enabled = enabled
    session.commit()
    return profile


def delete(session: Session, profile_id: int) -> None:
    profile = session.get(SearchProfile, profile_id)
    if profile is None:
        raise ProfileError("profile not found")
    session.delete(profile)
    session.commit()
    log.info("profile deleted: %s", profile.name)


def _clean(fields: dict) -> dict:
    """Normalise raw form input into typed profile fields."""
    sites = fields.get("sites")
    if isinstance(sites, str):
        sites = [sites]
    sites = [s.strip() for s in (sites or []) if str(s).strip()]

    def _as_bool(v) -> bool:
        return str(v).lower() in {"1", "true", "on", "yes"}

    return {
        "name": str(fields.get("name", "")).strip(),
        "term": str(fields.get("term", "")).strip(),
        "location": (str(fields.get("location")).strip() or None)
        if fields.get("location")
        else None,
        "country": str(fields.get("country", "egypt")).strip() or "egypt",
        "is_remote": _as_bool(fields.get("is_remote", False)),
        "sites": sites,
        "experience": (str(fields.get("experience")).strip() or None)
        if fields.get("experience")
        else None,
        "schedule_hour": int(fields.get("schedule_hour", 6)),
        "schedule_minute": int(fields.get("schedule_minute", 0)),
        "enabled": _as_bool(fields.get("enabled", True)),
    }
