"""Per-site request-kwarg builders for JobSpy.

A dict of `site -> builder function` rather than a class hierarchy: a Strategy
hierarchy was considered and withdrawn (refactor-plan.md §1) — each board's
quirk is a handful of kwargs, not enough behavioural variance to justify
polymorphism. New boards add an entry here, not a subclass.
"""

from typing import Any

from app.config import RunConfig, SearchSpec

SiteKwargBuilder = Any  # Callable[[SearchSpec, RunConfig], dict[str, Any]]


def _country_governed(spec: SearchSpec, config: RunConfig) -> dict[str, Any]:
    """country_indeed governs Indeed and Glassdoor only; harmless elsewhere
    but passed narrowly to keep the call surface honest."""
    return {"country_indeed": spec.country}


def _google(spec: SearchSpec, config: RunConfig) -> dict[str, Any]:
    """Google ignores `term` and needs a natural-language query of its own."""
    return {"google_search_term": spec.google_term or spec.term}


def _linkedin(spec: SearchSpec, config: RunConfig) -> dict[str, Any]:
    """LinkedIn omits the description from list results; this fetches each
    posting's page to obtain it (and the direct job URL). Slower, but the
    description feeds both the detail view and the stage 3 scorer."""
    if config.linkedin_fetch_description:
        return {"linkedin_fetch_description": True}
    return {}


_BUILDERS: dict[str, SiteKwargBuilder] = {
    "indeed": _country_governed,
    "glassdoor": _country_governed,
    "google": _google,
    "linkedin": _linkedin,
}


def extra_kwargs(site: str, spec: SearchSpec, config: RunConfig) -> dict[str, Any]:
    """The site-specific `scrape_jobs` kwargs for one site, or none."""
    builder = _BUILDERS.get(site)
    return builder(spec, config) if builder else {}
