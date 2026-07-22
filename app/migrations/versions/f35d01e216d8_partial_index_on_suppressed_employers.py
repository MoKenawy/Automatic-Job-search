"""partial index on suppressed employers

Revision ID: f35d01e216d8
Revises: dc0d779245f2
Create Date: 2026-07-21 02:34:16.192046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f35d01e216d8'
down_revision: Union[str, Sequence[str], None] = 'dc0d779245f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Partial index supporting the blacklist suppression query (US3).

    Only suppressed employers are ever scanned by suppression; a partial index
    keeps it small since the vast majority of employers are not blacklisted.
    """
    op.create_index(
        "ix_employers_suppressed",
        "employers",
        ["suppressed"],
        unique=False,
        postgresql_where=sa.text("suppressed"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_employers_suppressed", table_name="employers")
