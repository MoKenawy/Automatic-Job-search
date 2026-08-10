"""status_changed_at on postings

Revision ID: e2494af987ca
Revises: 3374777f0db4
Create Date: 2026-07-22 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2494af987ca'
down_revision: Union[str, Sequence[str], None] = '3374777f0db4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Separates a triage-status transition from a board re-surfacing the
    same posting (refactor-plan.md §5). Both previously stamped last_seen_at,
    which made it impossible for Posting.transition_to() to say honestly what
    it had changed. Nullable and additive: existing rows carry no history to
    backfill, so null means 'never transitioned since this column existed'.
    """
    op.add_column(
        "postings", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("postings", "status_changed_at")
