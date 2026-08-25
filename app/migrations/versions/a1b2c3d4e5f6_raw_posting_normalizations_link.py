"""raw_posting_normalizations link

Revision ID: a1b2c3d4e5f6
Revises: 64c8f2ca9cfe
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '64c8f2ca9cfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Traces which raw_postings row(s) folded into which posting.

    A separate insert-only table rather than a column on `raw_postings`:
    that table is append-only and the link is only known once Stage 2 runs,
    asynchronously and later than the Stage 1 insert, so a column would
    require updating an already-written raw row. One raw row links to
    exactly one posting (unique constraint); a posting may accumulate links
    from many raw rows over time.
    """
    op.create_table(
        "raw_posting_normalizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "raw_posting_id",
            sa.Integer(),
            sa.ForeignKey("raw_postings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "posting_id",
            sa.Integer(),
            sa.ForeignKey("postings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_raw_posting_normalizations_posting_id", "raw_posting_normalizations", ["posting_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_raw_posting_normalizations_posting_id", table_name="raw_posting_normalizations")
    op.drop_table("raw_posting_normalizations")
