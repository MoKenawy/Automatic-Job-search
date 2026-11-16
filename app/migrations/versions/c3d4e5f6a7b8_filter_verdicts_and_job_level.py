"""filter verdicts and promoted job_level

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-16 00:00:00.000001

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Two nullable, additive columns on `postings` (ADR-0016).

    `job_level` promotes the board's declared seniority out of the verbatim
    payload, which `raw_postings` has been holding against exactly this decision
    since the initial schema ("a later decision to promote a field costs a
    backfill rather than a re-scrape"). It is the experience filter's primary
    input. Backfilled by the revision that follows this one, not here: the DDL
    should be reviewable separately from a rule that may change.

    `experience_filter_passed` joins `title_filter_passed`, which has existed
    since ff6adc50ab28 and has never been written. One column per criterion,
    with the grounds for a rejection derived from the pair rather than stored —
    a stored reason would be stale precisely when the operator reads it, since
    they read it in order to change the rule that produced it.

    Both nullable, with **no server default**, and both deliberately so:

    - `job_level` is absent on every row from one of the two working boards, so
      any default would be a claim about data that does not exist.
    - For the verdict columns NULL is load-bearing. It means "the criterion was
      not applied", which is a different fact from "applied and admitted", and
      the distinction is what makes installing the filter observably a no-op
      (spec 003 SC-006). A NOT NULL column with a default would destroy it, and
      would also make every existing posting claim a verdict it never received.

    No index. At the volume NFR-1 budgets for — under a hundred postings — the
    plan difference is not measurable, and the read-time predicate's correctness
    must not depend on one.
    """
    op.add_column("postings", sa.Column("job_level", sa.String(length=64), nullable=True))
    op.add_column(
        "postings", sa.Column("experience_filter_passed", sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    """Drops both columns, losing the promoted labels and any verdicts.

    Lossless in the sense that matters: every label is still in
    `raw_postings.payload`, so re-upgrading and re-running the backfill restores
    `job_level` exactly, and `filter --all` restores the verdicts. Nothing
    unrecoverable lives only in these columns — by design, since triage state
    was deliberately kept out of them.
    """
    op.drop_column("postings", "experience_filter_passed")
    op.drop_column("postings", "job_level")
