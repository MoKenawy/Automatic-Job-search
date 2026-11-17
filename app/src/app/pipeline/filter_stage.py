"""The filter — relevance and experience, applied after deduplication (ADR-0016).

Extracted from what the design records as the front of stage 3: D6's coarse title
filter exists to reduce model invocations, and the stage that would make those
invocations does not exist yet. Its own re-runnable step is what FR-011 needs
anyway — re-evaluating under changed criteria without re-collecting — and it means
the per-run funnel the counts were designed to expose stops being flat now rather
than whenever scoring arrives.

Reads `postings`, writes two verdict columns and two run counters, and touches
nothing else. In particular it never writes `status` (a verdict is about criteria,
a status is about the operator's judgement — ADR-0015's separation, extended),
never writes `last_retrieved_at` (a verdict is not an observation — ADR-0012), and
never touches a landed row (FR-012, which is what makes a criteria change
re-appliable to history instead of a reason to re-scrape).

Re-runnable, and more strongly than that: **a converged re-application writes
nothing at all.** Every assignment is guarded by a comparison, because
`postings.updated_at` carries `onupdate` and a blind write would move every row's
timestamp without changing a verdict — which SC-007 ("byte-identical") forbids in
the letter. The guard is also what makes the property observable: the stage
reports how many verdicts it changed, and on a second pass that number is zero.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import RunConfig
from app.db.attribution import contributors_by_posting, posting_ids_for_run
from app.db.models import Posting, Run
from app.filters import (
    Contributor,
    ProfileInput,
    TitleRules,
    build_criteria,
    evaluate,
)

log = logging.getLogger(__name__)

# Postings loaded per batch when re-applying to the whole corpus. The live corpus
# is in the tens; this exists so that a growing one does not turn into a single
# unbounded result set.
BATCH_SIZE = 1000


@dataclass
class FilterOutcome:
    """What one application of the filter did.

    `changed` is the count SC-007 is checked against: zero on a converged
    re-application. `unreadable_experience` and `errors` are the faults FR-002a
    and FR-008 require to reach the operator.
    """

    passed: int = 0
    rejected: int = 0
    changed: int = 0
    unreadable_experience: set[str] = field(default_factory=set)
    # A set, not a tuple assigned once: pattern faults now come from the global
    # rule *and* from every contributing profile, and the last assignment winning
    # would lose all but one of them. Reported sorted, so a fault reads the same
    # on every application of the same data.
    errors: set[str] = field(default_factory=set)

    @property
    def evaluated(self) -> int:
        return self.passed + self.rejected

    @property
    def faults(self) -> list[str]:
        """Everything the operator should be told, in one list (FR-002a, FR-008)."""
        faults = sorted(self.errors)
        if self.unreadable_experience:
            values = ", ".join(sorted(repr(v) for v in self.unreadable_experience))
            faults.append(
                f"unreadable requested experience ({values}) — the experience "
                f"criterion did not apply to the profiles holding it"
            )
        return faults


def _apply(
    session: Session,
    posting_ids: list[int] | None,
    config: RunConfig,
    *,
    dry_run: bool,
) -> FilterOutcome:
    """Evaluate the postings in scope and record the verdicts.

    `posting_ids` of `None` means every posting.

    Compilation is hoisted out of the posting loop: the global patterns once per
    application, and each contributing profile's once per *distinct profile*, via
    the cache passed to `build_criteria`. A per-posting compile would waste work
    and, worse, give an operator's malformed pattern one chance per posting to be
    reported differently. The set of profiles is tiny and bounded, so the hoisting
    still holds with profiles in the picture; it is now keyed by profile rather
    than global.

    The verdicts are a function of the posting, the criteria **and the set of
    profiles that currently contribute to it** (ADR-0018). A posting surfaced for
    the first time by a second profile can therefore change verdict with no
    criteria change at all, and this stage will then write it. The converged
    re-application property (SC-007) holds for a fixed set of contributors.
    """
    outcome = FilterOutcome()
    titles = TitleRules.compile(config.title_include_pattern, config.title_exclude_pattern)
    # Recorded before the early return below, so a malformed global pattern is
    # reported even when nothing is in scope.
    outcome.errors.update(titles.errors)

    contributors_by_id = contributors_by_posting(session, posting_ids)
    resolved: dict[ProfileInput, Contributor] = {}

    stmt = select(Posting).order_by(Posting.id)
    if posting_ids is not None:
        if not posting_ids:
            return outcome
        stmt = stmt.where(Posting.id.in_(posting_ids))

    for posting in session.scalars(stmt.execution_options(yield_per=BATCH_SIZE)):
        criteria = build_criteria(titles, contributors_by_id.get(posting.id, []), resolved=resolved)
        outcome.errors.update(criteria.errors)
        outcome.unreadable_experience.update(
            c.unreadable_experience for c in criteria.contributors if c.unreadable_experience
        )
        verdict = evaluate(
            title=posting.title,
            normalised_title=posting.normalised_title,
            job_level=posting.job_level,
            criteria=criteria,
        )

        if verdict.rejected:
            outcome.rejected += 1
        else:
            outcome.passed += 1

        # Guarded, not blind: an unchanged verdict must not emit an UPDATE, or
        # `updated_at` moves on every row and a re-application stops being
        # byte-identical (SC-007).
        if (
            posting.title_filter_passed is not verdict.title_passed
            or posting.experience_filter_passed is not verdict.experience_passed
        ):
            outcome.changed += 1
            if not dry_run:
                posting.title_filter_passed = verdict.title_passed
                posting.experience_filter_passed = verdict.experience_passed

    # Nothing to undo on a dry run: the loop above assigns nothing when
    # `dry_run` is set, so no row is dirty and no rollback is needed — and a
    # rollback here would discard work the caller had not committed yet.
    return outcome


def _report(outcome: FilterOutcome, scope: str) -> None:
    log.info(
        "filter stage complete (%s): %d passed, %d rejected, %d verdict(s) changed",
        scope,
        outcome.passed,
        outcome.rejected,
        outcome.changed,
    )
    for fault in outcome.faults:
        log.warning("filter criteria fault: %s", fault)


def run_filter(
    session: Session, run: Run, config: RunConfig | None = None, *, dry_run: bool = False
) -> FilterOutcome:
    """Evaluate the postings this run surfaced, and record the funnel on it.

    Scoped to the distinct postings the run's landed rows folded into — exactly
    the set `run_normalise` counted — so that
    `filter_passed_count + filter_rejected_count == deduplicated_count` (SC-003).

    The verdicts are computed under **current** criteria, not the criteria in
    force when the run executed (FR-011). Re-running this against an old run
    therefore overwrites that run's figures: the counters are the verdict as of
    the last application, not an audit trail. `data-model.md` says so, because a
    reader would otherwise take the funnel for history.

    `config` is resolved here if the caller has not already done so, so the stage
    can be run on its own from the CLI (the `run_collect` precedent).
    """
    if config is None:
        config = RunConfig.resolve(session)

    posting_ids = posting_ids_for_run(session, run.id)
    outcome = _apply(session, posting_ids, config, dry_run=dry_run)

    if not dry_run:
        run.filter_passed_count = outcome.passed
        run.filter_rejected_count = outcome.rejected
        for fault in outcome.faults:
            _record_fault(run, fault)
        session.commit()

    _report(outcome, f"run {run.id}")

    # A criterion that turns away a run's entire haul is indistinguishable, in
    # the aggregate counts alone, from a board that has stopped responding — the
    # specification's own edge case. `counts_by_site` can tell them apart, but
    # only if somebody looks, so say it plainly here.
    if outcome.rejected and outcome.rejected == outcome.evaluated:
        log.warning(
            "filter rejected every one of run %d's %d posting(s) — check the criteria "
            "before concluding a board has stopped returning results",
            run.id,
            outcome.evaluated,
        )

    return outcome


def filter_all(
    session: Session, config: RunConfig | None = None, *, dry_run: bool = False
) -> FilterOutcome:
    """Re-apply the criteria to every posting, without contacting any board (FR-011).

    This is how a criteria change reaches already-collected postings (SC-004), and
    how a posting withheld under criteria the operator then loosens comes back —
    with its triage status intact, because nothing here writes it (FR-013).

    Writes **no** run counters. FR-015's counts belong to a run that evaluated
    postings during an execution; attaching a whole-corpus re-application's totals
    to some arbitrary run would decouple them from that run's `collected_count`
    and break the sum invariant `run_filter` maintains.
    """
    if config is None:
        config = RunConfig.resolve(session)

    outcome = _apply(session, None, config, dry_run=dry_run)
    if not dry_run:
        session.commit()
    _report(outcome, "all postings")
    return outcome


def _record_fault(run: Run, fault: str) -> None:
    """Put a criteria fault where the operator will see it.

    `runs.error` is rendered on the runs view, so it is the one place a fault
    reaches the operator rather than only the log — which is what FR-002a and
    FR-008 ask for. Appended rather than assigned: stage 1 records a non-fatal
    board failure here too (`run_collect`), and a filter fault must not erase it.
    """
    message = f"filter: {fault}"
    if run.error:
        if message in run.error:
            return
        run.error = f"{run.error}; {message}"
    else:
        run.error = message
