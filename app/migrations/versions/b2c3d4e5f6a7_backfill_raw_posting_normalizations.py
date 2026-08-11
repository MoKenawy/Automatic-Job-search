"""backfill raw_posting_normalizations

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-10 00:00:00.000001

"""
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.normalise import build_fingerprint

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

BATCH_SIZE = 1000


def upgrade() -> None:
    """Populates raw_posting_normalizations for rows written before that table
    existed (a1b2c3d4e5f6).

    The link cannot be reconstructed from anything already stored on
    `raw_postings` or `postings` — recomputes each raw row's fingerprint with
    the same `build_fingerprint` Stage 2 uses at ingest time, then matches it
    against `postings.fingerprint`. Since `postings.fingerprint` is unique,
    the digest -> posting_id lookup is one-to-one; several raw rows landing
    on the same digest (a re-scrape, or the same role seen on another board)
    correctly produce several link rows pointing at that one posting — this
    table's only uniqueness constraint is on raw_posting_id, matching the
    many-raw-rows-to-one-posting shape Stage 2 already assumes.

    A raw row whose recomputed digest matches no posting is left unlinked
    and logged rather than guessed at: that can happen if build_fingerprint's
    normalisation rules changed since the row was processed, and a wrong
    link would be worse than a missing one.
    """
    bind = op.get_bind()
    metadata = sa.MetaData()
    raw_postings = sa.Table("raw_postings", metadata, autoload_with=bind)
    postings = sa.Table("postings", metadata, autoload_with=bind)
    links = sa.Table("raw_posting_normalizations", metadata, autoload_with=bind)

    posting_id_by_fingerprint = {
        fingerprint: posting_id
        for posting_id, fingerprint in bind.execute(
            sa.select(postings.c.id, postings.c.fingerprint)
        )
    }

    already_linked = {
        row[0] for row in bind.execute(sa.select(links.c.raw_posting_id))
    }

    unmatched = 0
    to_insert: list[dict] = []

    for raw_id, payload, collected_at in bind.execute(
        sa.select(raw_postings.c.id, raw_postings.c.payload, raw_postings.c.collected_at)
    ):
        if raw_id in already_linked:
            continue

        payload = payload or {}
        parts = build_fingerprint(
            employer=payload.get("company"),
            title=payload.get("title"),
            location_raw=payload.get("location"),
            is_remote=bool(payload.get("is_remote")),
        )
        posting_id = posting_id_by_fingerprint.get(parts.digest)
        if posting_id is None:
            unmatched += 1
            continue

        to_insert.append(
            {"raw_posting_id": raw_id, "posting_id": posting_id, "linked_at": collected_at}
        )
        if len(to_insert) >= BATCH_SIZE:
            bind.execute(links.insert(), to_insert)
            to_insert.clear()

    if to_insert:
        bind.execute(links.insert(), to_insert)

    if unmatched:
        log.warning(
            "b2c3d4e5f6a7: %d raw_postings row(s) had no matching posting fingerprint "
            "and were left unlinked", unmatched,
        )


def downgrade() -> None:
    """No-op: the rows this migration inserts are indistinguishable from ones
    Stage 2 would have written itself, so there is nothing migration-specific
    to remove. Dropping the table entirely is a1b2c3d4e5f6's downgrade."""
    pass
