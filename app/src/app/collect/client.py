"""Stage 1 — collection.

Wraps JobSpy so that a source failing is recorded rather than raised. The dominant
failure mode is not an exception but a run that succeeds while returning
progressively less (design §7.4), so per-source counts are returned alongside the
records and are meant to be persisted.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from jobspy import scrape_jobs

from app.collect.sites import extra_kwargs
from app.config import RunConfig, SearchSpec, settings

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


def collect_one(spec: SearchSpec, config: RunConfig) -> CollectionResult:
    """Run a single search spec across its configured sources.

    `config` is a resolved `RunConfig` (services.settings → environment →
    code default, ADR-0005) — never the `settings` singleton directly, so two
    runs can carry different configurations (refactor-plan.md §3).
    """
    result = CollectionResult()

    for index, site in enumerate(spec.sites):
        if index > 0 and config.request_delay_seconds > 0:
            # Etiquette delay between successive requests to the boards (design
            # §9.3). JobSpy itself takes no such parameter, so this is enforced
            # here rather than passed through as a kwarg.
            time.sleep(config.request_delay_seconds)

        kwargs: dict[str, Any] = {
            "site_name": [site],
            "search_term": spec.term,
            "location": spec.location,
            "is_remote": spec.is_remote,
            "results_wanted": config.results_per_search,
            "hours_old": config.hours_old,
            "verbose": 1,
        }
        kwargs.update(extra_kwargs(site, spec, config))
        if config.proxies:
            kwargs["proxies"] = config.proxies

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


def collect_all(specs: list[SearchSpec] | None, config: RunConfig) -> CollectionResult:
    """Run every configured search spec and merge the outcomes.

    `specs=None` falls back to the environment `SEARCHES` list — unrelated to
    `config`, which governs how each search is run rather than what is searched.
    """
    specs = specs if specs is not None else settings.searches
    merged = CollectionResult()

    for spec in specs:
        outcome = collect_one(spec, config)
        merged.records.extend(outcome.records)
        for site, count in outcome.counts_by_site.items():
            merged.counts_by_site[site] = merged.counts_by_site.get(site, 0) + count
        merged.errors.update(outcome.errors)

    log.info(
        "collection complete: %d records, by_site=%s, errors=%s",
        merged.total, merged.counts_by_site, merged.errors or "none",
    )
    return merged
