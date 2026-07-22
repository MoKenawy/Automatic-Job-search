"""Typed configuration, loaded from environment or .env."""

import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Measured working sources as of 20 July 2026 (design §4.3, D11).
# Bayt returns 403, Glassdoor has no Egyptian coverage, Google returns no cursor.
WORKING_SITES = ["indeed", "linkedin"]


class SearchSpec(BaseModel):
    """One collector invocation.

    Searches are expressed explicitly rather than as a term x location product:
    `country_indeed` takes a single country per call, so international and remote
    searches need separate invocations with differing parameters (design D14).
    """

    term: str
    location: str | None = None
    # Maps to JobSpy's `country_indeed`; governs Indeed and Glassdoor only
    country: str = "egypt"
    is_remote: bool = False
    sites: list[str] = Field(default_factory=lambda: list(WORKING_SITES))
    # Google ignores `term` and needs a natural-language query of its own
    google_term: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Storage
    database_url: str = "postgresql+psycopg://jobs:jobs@localhost:5432/jobs"

    # Stage 1 — collection
    searches: list[SearchSpec] = Field(
        default_factory=lambda: [
            SearchSpec(term="data engineer", location="Cairo, Egypt", country="egypt"),
            SearchSpec(term="data engineer", location="Egypt", country="egypt", is_remote=True),
        ]
    )
    results_per_search: int = 50
    hours_old: int = 72
    # Design §9.3 — conservative by default; raising this is the first remedy
    # for restriction, proxy provision the last
    request_delay_seconds: float = 10.0
    proxies: list[str] = Field(default_factory=list)
    # LinkedIn returns no description in its list results; fetching one costs an
    # extra request per posting (slower), but the description is what the detail
    # view and the stage 3 scorer both need. Also yields the direct job URL.
    linkedin_fetch_description: bool = True

    # Stage 3 — scoring
    ollama_host: str = "http://localhost:11434"
    scoring_model: str = "qwen2.5:7b-instruct"
    cv_path: str = "data/cv.txt"
    # Design D6 — coarse pre-filter on title only, to reduce model invocations
    title_include_pattern: str = ""
    title_exclude_pattern: str = ""

    # Stage 4 — publication. After D15 this is a state transition, not an
    # external write, so no credentials are involved.
    # Design D7 — deliberately permissive at outset; tighten after a week
    publish_threshold: int = 60

    # Triage interface (ADR-0004)
    web_host: str = "0.0.0.0"
    web_port: int = 8000

    # Scheduling
    schedule_hour: int = 6
    schedule_minute: int = 0
    timezone: str = "Africa/Cairo"

    @field_validator("searches", mode="before")
    @classmethod
    def _parse_searches(cls, v: Any) -> Any:
        """Allow SEARCHES to be supplied as a JSON string in .env."""
        if isinstance(v, str):
            return json.loads(v)
        return v


settings = Settings()


class RunConfig(BaseModel):
    """Effective configuration for one pipeline run.

    Resolved once via `resolve()` and passed down as an argument to the stages
    that need it. Replaces the previous pattern of overlaying database
    overrides onto the `settings` singleton and reading it back through
    `settings.x` call sites — that overlay meant two runs could not hold
    different configurations, and it leaked between tests (refactor-plan.md
    §3). Frozen: a run's configuration is fixed for its duration.

    Every field here is one of `settings_store.store.EDITABLE_KEYS`; the
    defaults below mirror the code defaults on `Settings` so a bare
    `RunConfig()` is a valid unresolved fallback, matching the bottom tier of
    the DB → env → code default resolution order (ADR-0005).
    """

    model_config = ConfigDict(frozen=True)

    results_per_search: int = Field(default_factory=lambda: settings.results_per_search)
    hours_old: int = Field(default_factory=lambda: settings.hours_old)
    request_delay_seconds: float = Field(
        default_factory=lambda: settings.request_delay_seconds
    )
    linkedin_fetch_description: bool = Field(
        default_factory=lambda: settings.linkedin_fetch_description
    )
    proxies: list[str] = Field(default_factory=lambda: list(settings.proxies))
    publish_threshold: int = Field(default_factory=lambda: settings.publish_threshold)
    scoring_model: str = Field(default_factory=lambda: settings.scoring_model)
    title_include_pattern: str = Field(
        default_factory=lambda: settings.title_include_pattern
    )
    title_exclude_pattern: str = Field(
        default_factory=lambda: settings.title_exclude_pattern
    )

    @classmethod
    def resolve(cls, session: "Session") -> "RunConfig":
        """DB override, else environment/.env, else code default (ADR-0005)."""
        # Local import: settings_store.store imports app.config, so importing it
        # at module scope here would be circular.
        from app.settings_store import store

        return cls(**{key: store.get(session, key) for key in store.EDITABLE_KEYS})
