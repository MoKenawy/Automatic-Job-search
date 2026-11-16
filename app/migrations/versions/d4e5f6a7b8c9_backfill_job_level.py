"""backfill postings.job_level from the landed payloads

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-16 00:00:00.000002

"""
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.filters import merge_labels

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

BATCH_SIZE = 1000


def upgrade() -> None:
    """Fill `postings.job_level` for rows that predate the column (c3d4e5f6a7b8).

    Reads every contributing payload for each posting through
    `raw_posting_normalizations` and applies `app.filters.merge_labels` — the
    **same** rule stage 2 and the filter stage use, imported rather than
    restated. That is the precedent b2c3d4e5f6a7 set when it imported
    `build_fingerprint` instead of reimplementing the digest, and the reason is
    sharper here: a rule restated in a migration can diverge from the rule in
    the application, and then installation and the first re-apply would disagree
    about the stored label while every test passed. Spec 003's SC-007 would fail
    on day one, through a divergence nothing would be looking for.

    The merge takes the **minimum** seniority across contributing rows, ties
    broken lexicographically, so the result depends on the set of boards that
    surfaced the role and not on row order (FR-009). A posting whose rows all
    declared nothing — every row from the board that supplies no label, or
    `not applicable`, or the empty string the collector emits when LinkedIn
    descriptions were not fetched — is left NULL rather than stamped: NULL
    already means "no board supplied a level".

    Writes no verdict. Spec 003 is explicit that existing postings are not
    retroactively filtered on installation; applying the filter to already
    collected postings is an operator action (`filter --all`), not an install
    step. This migration therefore changes what is *known* about a posting and
    nothing about whether the operator sees it.

    Re-runnable: a posting that already holds a label is skipped, so an
    interrupted upgrade can be repeated.
    """
    bind = op.get_bind()
    metadata = sa.MetaData()
    postings = sa.Table("postings", metadata, autoload_with=bind)
    raw_postings = sa.Table("raw_postings", metadata, autoload_with=bind)
    links = sa.Table("raw_posting_normalizations", metadata, autoload_with=bind)

    labels_by_posting: dict[int, list[str | None]] = {}
    for posting_id, payload in bind.execute(
        sa.select(links.c.posting_id, raw_postings.c.payload).join(
            raw_postings, raw_postings.c.id == links.c.raw_posting_id
        )
    ):
        labels_by_posting.setdefault(posting_id, []).append((payload or {}).get("job_level"))

    already_set = {
        posting_id
        for posting_id, in bind.execute(
            sa.select(postings.c.id).where(postings.c.job_level.isnot(None))
        )
    }

    updates: list[dict] = []
    for posting_id, labels in labels_by_posting.items():
        if posting_id in already_set:
            continue
        merged = merge_labels(labels)
        if merged is not None:
            updates.append({"pid": posting_id, "level": merged})

    statement = (
        postings.update()
        .where(postings.c.id == sa.bindparam("pid"))
        .values(job_level=sa.bindparam("level"))
    )
    for start in range(0, len(updates), BATCH_SIZE):
        bind.execute(statement, updates[start : start + BATCH_SIZE])

    unlabelled = len(labels_by_posting) - len(already_set) - len(updates)
    log.info(
        "d4e5f6a7b8c9: promoted job_level onto %d posting(s); %d had no informative "
        "label on any contributing row",
        len(updates),
        max(unlabelled, 0),
    )


def downgrade() -> None:
    """No-op: the labels this writes are indistinguishable from ones stage 2
    would have written itself, so there is nothing migration-specific to undo.
    Dropping the column is c3d4e5f6a7b8's downgrade."""
    pass
