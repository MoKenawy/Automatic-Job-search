"""The coarse title filter (design D6, SRS FR-16).

Two operator-authored regular expressions, applied to the job title and nothing
else. D6 is explicit that this is a pre-filter to reduce model invocations and is
"unsuitable for requirement analysis, where unstructured phrasing produces false
negatives" — so the description is deliberately out of reach here, and judging
genuine fit remains the scorer's job.

Two properties matter more than the matching itself:

**An empty pattern disables its criterion, decided before anything is compiled.**
`re.search("", title)` matches every string, and both patterns ship empty
(`config.py`, D6). Compiling the default and asking "did the exclude pattern
match?" would therefore reject the entire corpus on the first run after
installation — the highest-consequence bug available in this feature, and one
that any test which only checks that rejection works would pass (SC-006).

**A malformed pattern disables its criterion and reports.** The operator writes
these by hand in a web form; a bad one must leave the run intact and reject
nothing (FR-008, US2 scenario 4).
"""

import re
from dataclasses import dataclass

__all__ = ["TitleRules"]


@dataclass(frozen=True)
class TitleRules:
    """Compiled title criteria, or deliberately disabled ones.

    `errors` is empty when nothing went wrong. A pattern that failed to compile
    disables only itself: an unusable exclude rule must not take a working
    include rule down with it.
    """

    include: re.Pattern[str] | None = None
    exclude: re.Pattern[str] | None = None
    errors: tuple[str, ...] = ()

    @classmethod
    def compile(
        cls, include: str | None = "", exclude: str | None = "", *, source: str | None = None
    ) -> "TitleRules":
        """Compile both patterns, treating empty or whitespace-only as disabled.

        Case-insensitive, so the operator need not think about it. Emptiness is
        decided on the string rather than on a match result — see the module
        docstring; this is the ordering the whole corpus depends on. `None` is
        the same as empty: a search profile that sets no pattern stores NULL.

        `source` names where the patterns came from, and is prefixed to any fault.
        The global patterns are read at `/settings`; a profile's are read on
        `/profiles`, and an operator with several profiles cannot act on "a
        pattern is invalid" without being told which one (ADR-0018).
        """
        where = f"profile {source!r}: " if source else ""
        compiled: dict[str, re.Pattern[str] | None] = {"include": None, "exclude": None}
        errors: list[str] = []

        for name, pattern in (("include", include), ("exclude", exclude)):
            if not pattern or not pattern.strip():
                continue
            try:
                compiled[name] = re.compile(pattern, flags=re.IGNORECASE)
            except re.error as exc:
                # Reported, never raised: the run completes and this criterion
                # simply does not apply (FR-008).
                errors.append(f"{where}title_{name}_pattern is not a valid expression: {exc}")

        return cls(include=compiled["include"], exclude=compiled["exclude"], errors=tuple(errors))

    @property
    def enabled(self) -> bool:
        """Whether either pattern is usable. False means the criterion is absent."""
        return self.include is not None or self.exclude is not None

    def verdict(self, title: str | None) -> bool | None:
        """Admit, reject, or decline to judge.

        `None` means the criterion was not applied — no usable pattern — and is
        what keeps installation a no-op (SC-006) and the verdict column's NULL
        honest (ADR-0016).

        A missing or empty title is **admitted**: absence of evidence is not
        evidence of mismatch (FR-005). It is also vanishingly rare, since
        `postings.title` is NOT NULL.

        Exclude is tested before include so that an explicit "never show me
        this" wins over a permissive include rule.
        """
        if not self.enabled:
            return None
        if not title:
            return True
        if self.exclude is not None and self.exclude.search(title):
            return False
        return self.include is None or bool(self.include.search(title))
