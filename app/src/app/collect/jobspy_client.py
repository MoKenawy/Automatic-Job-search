"""Stage 1 — collection.

Wraps JobSpy so that a source failing is recorded rather than raised. The dominant
failure mode is not an exception but a run that succeeds while returning
progressively less (design §7.4), so per-source counts are returned alongside the
records and are meant to be persisted.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from jobspy import scrape_jobs

from app.config import SearchSpec, settings

log = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    """Outcome of collecting across every configured search."""

    records: list[dict[str, Any]] = field(default_factory=list)
    # Per-source row counts, e.g. {"indeed": 40, "linkedin": 0}
    counts_by_site: dict[str, int] = field(default_factory=dict)
    # Source -> error message, for sources that failed outright
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.records)


def _rows_from_frame(df: pd.DataFrame | None, site: str) -> list[dict[str, Any]]:
    """Convert a JobSpy frame to plain records, tolerating its empty shapes.

    A total failure returns a DataFrame of shape (0, 0) — no columns, not merely
    no rows (design §4.3). Checking `.empty` before touching `.columns` keeps that
    a recorded empty result rather than an AttributeError mid-run.
    """
    if df is None or df.empty:
        return []

    # Normalise pandas' mixed null sentinels: object columns carry both None and
    # float NaN, which would otherwise serialise inconsistently into JSONB.
    df = df.astype(object).where(pd.notna(df), None)

    records = df.to_dict(orient="records")
    for record in records:
        record.setdefault("site", site)
    return records


def collect_one(spec: SearchSpec) -> CollectionResult:
    """Run a single search spec across its configured sources."""
    result = CollectionResult()

    for site in spec.sites:
        kwargs: dict[str, Any] = {
            "site_name": [site],
            "search_term": spec.term,
            "location": spec.location,
            "is_remote": spec.is_remote,
            "results_wanted": settings.results_per_search,
            "hours_old": settings.hours_old,
            "verbose": 1,
        }
        # country_indeed governs Indeed and Glassdoor only; harmless elsewhere but
        # passed narrowly to keep the call surface honest
        if site in {"indeed", "glassdoor"}:
            kwargs["country_indeed"] = spec.country
        if site == "google":
            kwargs["google_search_term"] = spec.google_term or spec.term
        if site == "linkedin" and settings.linkedin_fetch_description:
            # LinkedIn omits the description from list results; this fetches each
            # posting's page to obtain it (and the direct job URL). Slower, but the
            # description feeds both the detail view and the stage 3 scorer.
            kwargs["linkedin_fetch_description"] = True
        if settings.proxies:
            kwargs["proxies"] = settings.proxies

        try:
            df = scrape_jobs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a failing source must not end the run
            log.warning("collection failed: site=%s term=%r: %s", site, spec.term, exc)
            result.errors[site] = f"{type(exc).__name__}: {exc}"
            result.counts_by_site[site] = result.counts_by_site.get(site, 0)
            continue

        rows = _rows_from_frame(df, site)
        if not rows:
            log.warning("collection empty: site=%s term=%r", site, spec.term)

        result.records.extend(rows)
        result.counts_by_site[site] = result.counts_by_site.get(site, 0) + len(rows)

    return result


def collect_all(specs: list[SearchSpec] | None = None) -> CollectionResult:
    """Run every configured search spec and merge the outcomes."""
    specs = specs if specs is not None else settings.searches
    merged = CollectionResult()

    for spec in specs:
        outcome = collect_one(spec)
        merged.records.extend(outcome.records)
        for site, count in outcome.counts_by_site.items():
            merged.counts_by_site[site] = merged.counts_by_site.get(site, 0) + count
        merged.errors.update(outcome.errors)

    log.info(
        "collection complete: %d records, by_site=%s, errors=%s",
        merged.total, merged.counts_by_site, merged.errors or "none",
    )
    return merged
