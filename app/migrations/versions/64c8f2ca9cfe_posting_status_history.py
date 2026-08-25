"""posting status history

Revision ID: 64c8f2ca9cfe
Revises: cb39b32a6843
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64c8f2ca9cfe'
down_revision: Union[str, Sequence[str], None] = 'cb39b32a6843'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Introduces a transactional audit trail for triage status transitions.

    `postings.status` / `status_changed_at` remain the columns every query
    reads (unchanged, so no caller needs to move) — this table is additive,
    recording *every* transition rather than only the latest one.

    Every existing posting gets one synthetic baseline row so history is
    never empty for a row that predates this migration: `previous_status`
    NULL (genuinely unknown), `new_status` = the posting's current status,
    `changed_at` = `status_changed_at` if it was ever stamped, else
    `first_seen_at` (the same fallback cb39b32a6843 used for
    `last_retrieved_at`, for the same reason — it is the best fact actually
    on hand, not a claim that a transition happened at migration time).
    """
    op.create_table(
        "posting_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "posting_id",
            sa.Integer(),
            sa.ForeignKey("postings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(length=16), nullable=True),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_posting_status_history_posting_id", "posting_status_history", ["posting_id"]
    )
    op.create_index(
        "ix_posting_status_history_posting_id_changed_at",
        "posting_status_history",
        ["posting_id", "changed_at"],
    )

    op.execute(
        """
        INSERT INTO posting_status_history (posting_id, previous_status, new_status, changed_at, actor, reason)
        SELECT id, NULL, status, COALESCE(status_changed_at, first_seen_at), 'migration',
               'baseline row backfilled by 64c8f2ca9cfe'
        FROM postings
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_posting_status_history_posting_id_changed_at", table_name="posting_status_history")
    op.drop_index("ix_posting_status_history_posting_id", table_name="posting_status_history")
    op.drop_table("posting_status_history")
