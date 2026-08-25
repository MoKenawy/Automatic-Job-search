"""retrieval date, decoupled from generic row bookkeeping

Revision ID: cb39b32a6843
Revises: e2494af987ca
Create Date: 2026-07-27 19:32:21.361102

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb39b32a6843'
down_revision: Union[str, Sequence[str], None] = 'e2494af987ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Splits `last_seen_at` into two columns carrying its two conflated
    meanings (ADR-0012), the same move e2494af987ca already made once for
    status_changed_at:

    - `updated_at` keeps the column's actual, always-had-it behaviour — moves
      on any UPDATE, for any reason. Renamed rather than left as
      `last_seen_at` because that name is what let the behaviour go unnoticed:
      it reads as "a board last saw this", which it never reliably meant.
    - `last_retrieved_at` is new, and is the column that actually means "a
      board last confirmed this posting still exists" — written only by
      `Posting.observe()`, no `onupdate`.

    Backfilled from `first_seen_at`, each row's own known creation time,
    rather than from a single migration-time `now()` for every row — the
    latter would silently claim every historical posting was re-observed at
    the moment this migration ran, which is not a fact this system has.
    `first_seen_at` is the best fact actually on hand: every row was at least
    retrieved then, and nothing about it since is known, which is exactly
    what §5 R2's collection-lag caveat already expects reports to state.
    """
    op.alter_column("postings", "last_seen_at", new_column_name="updated_at")

    op.add_column(
        "postings", sa.Column("last_retrieved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE postings SET last_retrieved_at = first_seen_at")
    op.alter_column("postings", "last_retrieved_at", nullable=False)
    op.alter_column("postings", "last_retrieved_at", server_default=sa.text("now()"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("postings", "last_retrieved_at")
    op.alter_column("postings", "updated_at", new_column_name="last_seen_at")
