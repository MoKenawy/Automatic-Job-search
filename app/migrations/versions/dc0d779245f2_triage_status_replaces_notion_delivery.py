"""triage status replaces notion delivery

Revision ID: dc0d779245f2
Revises: ff6adc50ab28
Create Date: 2026-07-20 22:29:49.634643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc0d779245f2'
down_revision: Union[str, Sequence[str], None] = 'ff6adc50ab28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A server default is required here: the column is NOT NULL and the table
    # already holds rows. It is dropped immediately afterwards so the schema
    # matches the model, where the default is applied by the ORM.
    op.add_column(
        'postings',
        sa.Column('status', sa.String(length=16), nullable=False, server_default='new'),
    )
    op.alter_column('postings', 'status', server_default=None)

    # Carry the suppression flag across before the column is dropped: a
    # suppressed posting is a rejected one under the new model (design §8.1).
    op.execute("UPDATE postings SET status = 'rejected' WHERE suppressed = true")

    op.drop_index(op.f('ix_postings_publish_queue'), table_name='postings')
    op.create_index(op.f('ix_postings_status'), 'postings', ['status'], unique=False)
    op.create_index('ix_postings_triage_queue', 'postings', ['published', 'status', 'score'], unique=False)
    op.drop_column('postings', 'notion_page_id')
    op.drop_column('postings', 'suppressed')


def downgrade() -> None:
    """Downgrade schema."""
    # Same constraint in reverse: NOT NULL against populated rows needs a default
    op.add_column(
        'postings',
        sa.Column('suppressed', sa.BOOLEAN(), autoincrement=False,
                  nullable=False, server_default=sa.false()),
    )
    # Restore the flag from triage state before it is lost
    op.execute("UPDATE postings SET suppressed = true WHERE status = 'rejected'")
    op.alter_column('postings', 'suppressed', server_default=None)

    op.add_column('postings', sa.Column('notion_page_id', sa.VARCHAR(length=64), autoincrement=False, nullable=True))
    op.drop_index('ix_postings_triage_queue', table_name='postings')
    op.drop_index(op.f('ix_postings_status'), table_name='postings')
    op.create_index(op.f('ix_postings_publish_queue'), 'postings', ['published', 'score', 'suppressed'], unique=False)
    op.drop_column('postings', 'status')
