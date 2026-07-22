"""Stage 1 — collect and land raw output verbatim.

No transformation or deduplication is applied here (design §8). Holding the
complete row means a later decision to promote a field costs a backfill rather
than a re-scrape.
"""

import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.collect import collect_all
from app.config import SearchSpec
from app.db.models import RawPosting, Run

log = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    """Coerce a JobSpy cell into something JSONB accepts.

    JobSpy returns `datetime.date` for date_posted and numpy scalars for numeric
    columns; neither survives JSON serialisation untouched. NaN is not valid JSON
    and must become null rather than the literal NaN psycopg would otherwise emit.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    # numpy scalars and anything else exotic
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _jsonable(item())
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def run_collect(session: Session, run: Run, specs: list[SearchSpec] | None = None) -> int:
    """Collect across configured searches and land every row in `raw_postings`.

    Specs come from enabled search profiles (US4, ADR-0005). If none are provided
    and no profiles exist, fall back to the environment `SEARCHES` so a fresh,
    un-migrated deployment still works.
    """
    if specs is None:
        from app.settings_store import profiles

        specs = profiles.enabled_specs(session) or None

    result = collect_all(specs)

    for record in result.records:
        payload = {k: _jsonable(v) for k, v in record.items()}
        session.add(
            RawPosting(
                run_id=run.id,
                site=str(record.get("site") or "unknown"),
                site_job_id=(str(record["id"]) if record.get("id") is not None else None),
                payload=payload,
            )
        )

    run.collected_count = result.total
    run.counts_by_site = result.counts_by_site
    if result.errors:
        # Recorded but not fatal: one source failing must not end the run
        run.error = "; ".join(f"{site}: {msg}" for site, msg in result.errors.items())

    session.commit()
    log.info("stage 1 complete: %d raw records landed", result.total)
    return result.total
