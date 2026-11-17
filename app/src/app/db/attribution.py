"""Which run, and which profile, surfaced a posting (ADR-0016).

A `Posting` carries no direct link to a `Run` or a `SearchProfile`. The path is
`Posting -> RawPostingNormalization -> RawPosting -> Run -> SearchProfile`
(design §8), and `services/reports.py` already walks it — but `pipeline/` may not
import `services/`, so a stage that needs the traversal cannot reach that copy.
This module sits in `db/`, which both `services/` and `pipeline/` may import, for
the same reason `visibility.py` does (002 research R1): a helper the pipeline is
structurally forbidden to use is a helper the pipeline will grow its own copy of.
`services/reports.py` could adopt these later; it is not changed here.

**The fan-out is the point, not an inconvenience.** A posting can be surfaced by
several profiles' runs, or by none at all through a manual `run-all`, and
`reports.postings_by_profile_status` records the same fact when it refuses to pick
one profile to credit. The filter therefore asks "what did *every* contributing
profile ask for?" rather than reading one run's profile, because the second would
make a posting's verdict depend on which run was filtered last — alternating
rather than converging, which FR-010 and SC-007 forbid.

Both queries are single grouped statements. The per-row version of this traversal
was ~200 round trips on a typical run (`refactor-plan.md` §4.3), and
`normalise_stage.py` batches for the same reason.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RawPosting, RawPostingNormalization, Run, SearchProfile

__all__ = ["posting_ids_for_run", "requested_experience_by_posting"]


def posting_ids_for_run(session: Session, run_id: int) -> list[int]:
    """The distinct postings a run's landed rows folded into.

    Exactly the set `run_normalise` counted into `runs.deduplicated_count`, which
    is what lets the filter's two counts sum to it (SC-003). Ordered by id so a
    run's verdicts are written in a stable order — not required for correctness,
    but it makes two runs of the stage comparable in a log or a diff.
    """
    return list(
        session.scalars(
            select(RawPostingNormalization.posting_id)
            .join(RawPosting, RawPosting.id == RawPostingNormalization.raw_posting_id)
            .where(RawPosting.run_id == run_id)
            .distinct()
            .order_by(RawPostingNormalization.posting_id)
        ).all()
    )


def requested_experience_by_posting(
    session: Session, posting_ids: list[int] | None = None
) -> dict[int, list[str | None]]:
    """For each posting, the experience text of every profile that surfaced it.

    A `None` entry is a contributor that imposes no requirement: a profile-less
    run (a manual `run-all`), or a profile whose `experience` field is empty.
    Both admit unconditionally, so both are the same thing to the criterion — see
    `filters.levels.admits_any`.

    A posting absent from the result has no contributing run at all, which the
    caller must read as "no experience criterion applies" rather than as a
    rejection. Returning nothing for it, rather than an empty list, keeps that
    distinction with the caller instead of encoding it here.

    `posting_ids` of `None` means every posting — the whole-corpus re-apply.
    Passing an empty list means no postings, and returns nothing.
    """
    if posting_ids is not None and not posting_ids:
        return {}

    stmt = (
        select(
            RawPostingNormalization.posting_id,
            Run.profile_id,
            SearchProfile.experience,
        )
        .select_from(RawPostingNormalization)
        .join(RawPosting, RawPosting.id == RawPostingNormalization.raw_posting_id)
        .join(Run, Run.id == RawPosting.run_id)
        .outerjoin(SearchProfile, SearchProfile.id == Run.profile_id)
        # DISTINCT so a profile that surfaced the same posting across many runs
        # contributes one requirement rather than one per run. The verdict is a
        # disjunction, so repetition could not change it — but it would make the
        # log, and any later per-profile diagnosis, misleading.
        .distinct()
    )
    if posting_ids is not None:
        stmt = stmt.where(RawPostingNormalization.posting_id.in_(posting_ids))

    requested: dict[int, list[str | None]] = defaultdict(list)
    for posting_id, profile_id, experience in session.execute(stmt).all():
        # A profile-less run and a profile with no experience recorded are the
        # same fact here: a contributor that cannot withhold anything.
        requested[posting_id].append(experience if profile_id is not None else None)
    return dict(requested)
