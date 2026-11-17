"""per-profile title rules

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-17 00:00:00.000001

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Two nullable, additive columns on `search_profiles` (ADR-0018).

    A profile's title include/exclude patterns, applied in addition to the global
    ones at `/settings`. Nullable with **no server default**, deliberately: NULL
    means "this profile adds nothing", which is what every existing profile
    already does, so installing the columns changes no verdict (SC-006). A NOT NULL
    column with an empty-string default would say the same thing less honestly and
    would have to be told apart from "set to the empty pattern" forever after.

    `Text`, not a bounded string: the global patterns are unbounded
    (`app_settings.value` is JSONB), and a cap here would refuse a pattern the
    global setting accepts.

    No backfill and no index. The table holds a handful of rows and is read in
    full by the stage; correctness must not depend on an index.
    """
    op.add_column("search_profiles", sa.Column("title_include_pattern", sa.Text(), nullable=True))
    op.add_column("search_profiles", sa.Column("title_exclude_pattern", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop both columns.

    Loses any patterns operators have set on profiles, which are not recoverable
    from anywhere else. The verdicts already written stay as they are — they are
    derived from the patterns but do not reference them — and the next
    `filter --all` recomputes them under the global rules alone.
    """
    op.drop_column("search_profiles", "title_exclude_pattern")
    op.drop_column("search_profiles", "title_include_pattern")
