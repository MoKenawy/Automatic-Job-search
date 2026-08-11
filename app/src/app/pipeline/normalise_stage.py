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

from app.db.models import Employer, Posting, RawPosting, RawPostingNormalization, Run
from app.normalise import build_fingerprint, normalise_employer

log = logging.getLogger(__name__)


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

    now = datetime.now(UTC)
    unresolved_country = 0

    # Fingerprint every row up front so the batch lookups below can be built
    # from the complete set of digests and employer names this run touches,
    # rather than querying once per row (refactor-plan.md §4.3 — this was
    # ~2 queries x raw row count, roughly 200 round trips on a typical run).
    parsed: list[tuple[RawPosting, Any, dict]] = []
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
        parsed.append((raw, parts, payload))

    digests = {parts.digest for _, parts, _ in parsed}
    postings_by_fingerprint: dict[str, Posting] = {}
    if digests:
        postings_by_fingerprint = {
            p.fingerprint: p
            for p in session.scalars(select(Posting).where(Posting.fingerprint.in_(digests)))
        }

    normalised_names = {normalise_employer(payload.get("company")) for _, _, payload in parsed}
    employers_by_name: dict[str, Employer] = {}
    if normalised_names:
        employers_by_name = {
            e.normalised_name: e
            for e in session.scalars(
                select(Employer).where(Employer.normalised_name.in_(normalised_names))
            )
        }

    touched: set[str] = set()

    for raw, parts, payload in parsed:
        posting = postings_by_fingerprint.get(parts.digest)
        provenance = {
            "url": payload.get("job_url"),
            "job_id": payload.get("id"),
            "first_seen": now.isoformat(),
        }

        if posting is None:
            normalised_name = normalise_employer(payload.get("company"))
            employer = employers_by_name.get(normalised_name)
            if employer is None:
                employer = Employer(
                    name=(payload.get("company") or "").strip() or "(unknown)",
                    normalised_name=normalised_name,
                )
                session.add(employer)
                session.flush()
                employers_by_name[normalised_name] = employer
            employer.enrich_from(payload)

            posting = Posting.create(
                fingerprint=parts.digest,
                employer=employer,
                title=payload.get("title") or "",
                normalised_title=parts.title,
                location_raw=(payload.get("location") or None),
                country_code=(parts.location if parts.country_resolved else None),
                is_remote=bool(payload.get("is_remote")),
                description=payload.get("description"),
                date_posted=_parse_date(payload.get("date_posted")),
                job_type=(payload.get("job_type") or None),
                site=raw.site,
                provenance=provenance,
            )
            session.add(posting)
            postings_by_fingerprint[parts.digest] = posting
        else:
            # Seen again. observe() merges provenance and backfills a missing
            # description without disturbing scoring or publication state.
            posting.observe(
                site=raw.site,
                provenance=provenance,
                description=payload.get("description"),
                now=now,
            )

        # `posting` here relies on SQLAlchemy's relationship-based FK resolution:
        # a newly created posting has no `id` yet until flush, so the link is
        # made via the `posting` relationship rather than `posting_id` directly.
        session.add(RawPostingNormalization(raw_posting_id=raw.id, posting=posting))
        touched.add(parts.digest)

    run.deduplicated_count = len(touched)
    session.commit()

    log.info(
        "stage 2 complete: %d raw rows -> %d distinct postings (%d unresolved country)",
        len(raw_rows), len(touched), unresolved_country,
    )
    return len(raw_rows), len(touched)
