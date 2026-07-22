"""Stage 2 — fingerprint and deduplicate.

Reads the raw landing zone, derives a fingerprint per row, and upserts one
`postings` record per real-world role. Where several boards surface the same
role, each board's URL is merged into `sources` rather than creating a second
record (design §7.3).

Re-runnable: processing the same raw rows again converges on the same state.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import STATUS_NEW, STATUS_REJECTED, Employer, Posting, RawPosting, Run
from app.normalise import build_fingerprint, normalise_employer

log = logging.getLogger(__name__)


def _get_or_create_employer(session: Session, raw_name: str | None, payload: dict) -> Employer:
    """Resolve an employer by normalised name, enriching it opportunistically."""
    normalised = normalise_employer(raw_name)

    employer = session.scalar(
        select(Employer).where(Employer.normalised_name == normalised)
    )
    if employer is None:
        employer = Employer(
            name=(raw_name or "").strip() or "(unknown)",
            normalised_name=normalised,
        )
        session.add(employer)
        session.flush()

    # Indeed carries company detail that LinkedIn does not; fill gaps only, never
    # overwrite a value already held
    for column, key in (
        ("url", "company_url"),
        ("logo_url", "company_logo"),
        ("num_employees", "company_num_employees"),
        ("revenue", "company_revenue"),
        ("description", "company_description"),
    ):
        if getattr(employer, column) is None and payload.get(key):
            setattr(employer, column, str(payload[key])[:1024])

    return employer


def _parse_date(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


def run_normalise(session: Session, run: Run) -> tuple[int, int]:
    """Fold this run's raw rows into deduplicated postings.

    Returns (rows processed, distinct postings touched).
    """
    raw_rows = session.scalars(
        select(RawPosting).where(RawPosting.run_id == run.id)
    ).all()

    touched: set[str] = set()
    unresolved_country = 0
    now = datetime.now(UTC)

    for raw in raw_rows:
        payload = raw.payload or {}

        parts = build_fingerprint(
            employer=payload.get("company"),
            title=payload.get("title"),
            location_raw=payload.get("location"),
            is_remote=bool(payload.get("is_remote")),
        )
        if not parts.country_resolved and not payload.get("is_remote"):
            unresolved_country += 1

        posting = session.scalar(
            select(Posting).where(Posting.fingerprint == parts.digest)
        )

        provenance = {
            "url": payload.get("job_url"),
            "job_id": payload.get("id"),
            "first_seen": now.isoformat(),
        }

        if posting is None:
            employer = _get_or_create_employer(session, payload.get("company"), payload)
            # A new posting from a blacklisted employer is born Rejected, so it is
            # never published (US3, FR-007). The suppression pass is the general
            # mechanism; this catches the row at creation without a second sweep.
            born_status = STATUS_REJECTED if employer.suppressed else STATUS_NEW
            posting = Posting(
                fingerprint=parts.digest,
                employer_id=employer.id,
                title=(payload.get("title") or "")[:512],
                normalised_title=parts.title[:512],
                location_raw=(payload.get("location") or None),
                country_code=(parts.location if parts.country_resolved else None),
                is_remote=bool(payload.get("is_remote")),
                description=payload.get("description"),
                date_posted=_parse_date(payload.get("date_posted")),
                job_type=(payload.get("job_type") or None),
                sources={raw.site: provenance},
                status=born_status,
            )
            session.add(posting)
        else:
            # Seen again. Merge provenance without disturbing scoring or
            # publication state, and without resetting an existing first_seen.
            sources = dict(posting.sources or {})
            if raw.site not in sources:
                sources[raw.site] = provenance
            else:
                sources[raw.site] = {**sources[raw.site], "url": provenance["url"]}
            posting.sources = sources
            posting.last_seen_at = now

            # Backfill a description if the board that first surfaced the role
            # omitted one and another board supplies it
            if not posting.description and payload.get("description"):
                posting.description = payload["description"]

        touched.add(parts.digest)

    run.deduplicated_count = len(touched)
    session.commit()

    log.info(
        "stage 2 complete: %d raw rows -> %d distinct postings (%d unresolved country)",
        len(raw_rows), len(touched), unresolved_country,
    )
    return len(raw_rows), len(touched)
