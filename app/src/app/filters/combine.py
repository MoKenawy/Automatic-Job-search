"""Tri-state combinators — the two ways a verdict is assembled from parts (ADR-0016, ADR-0018).

Every criterion's verdict is `True` (applied, admitted), `False` (applied,
rejected) or `None` (not applied), and the three are different facts. Two rules
for combining them recur, and each is written once, here, so that "how do several
profiles' opinions merge" has a single answer rather than one per criterion.

Pure and dependency-free on purpose: `levels.py` and `verdict.py` both import it.
"""

from collections.abc import Iterable

__all__ = ["all_of", "any_of"]


def all_of(verdicts: Iterable[bool | None]) -> bool | None:
    """Conjunction that ignores what was not applied.

    Used where two rules **both** bind — the global title rule and the combined
    profile rules. A rule that was not applied cannot withhold anything, so it is
    skipped rather than counted as a pass: `False` if any applied rule rejected,
    `True` if at least one applied and none rejected, `None` if nothing applied.

    The last case is what keeps installation a no-op (SC-006): with no criteria
    anywhere, the verdict stays NULL rather than becoming a claim of "admitted".
    """
    decided = [verdict for verdict in verdicts if verdict is not None]
    if not decided:
        return None
    return all(decided)


def any_of(verdicts: Iterable[bool | None]) -> bool | None:
    """Disjunction across contributors — admitted if **any** of them admits it.

    The rule `levels.admits_any` introduced for the experience criterion
    (ADR-0016, decision 1), lifted here so the title criterion cannot grow a
    subtly different one. Commutative, associative and idempotent, so the result
    is order-independent by construction, which is what FR-010 and SC-007 need.

    An entry of `None` is a contributor that imposes no requirement, and it
    admits unconditionally: it cannot withhold anything. When *every* contributor
    is like that — or there are none — the criterion was never applied: `None`.

    The consequence is stated rather than hidden: one contributor with nothing to
    say defeats another's rejection. That is accepted because the alternative lets
    a profile the operator is not thinking about conceal a posting another profile
    asked for, and a posting wrongly concealed cannot be recovered by looking
    harder (spec 003, governing constraint).
    """
    collected = list(verdicts)
    if not collected or all(verdict is None for verdict in collected):
        return None
    # `is not False` is True-or-None. At least one entry is decided here, since
    # the all-None case returned above.
    return any(verdict is not False for verdict in collected)
