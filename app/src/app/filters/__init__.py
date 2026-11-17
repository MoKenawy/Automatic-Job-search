"""Relevance and experience criteria (design D6, ADR-0016).

Pure transforms, like `normalise/` and `collect/`: nothing here imports the
database, a session, or configuration, so the rules that decide whether the
operator ever sees a posting are testable without infrastructure
(`CLAUDE.md`, `Docs/development-guide.md` §9).

Persistence lives in `pipeline/filter_stage.py`; read-time withholding lives in
`db/visibility.py`.
"""

from app.filters.levels import (
    BOARD_LABELS,
    Level,
    admits,
    admits_any,
    level_from_title,
    merge_labels,
    parse_level,
    parse_requested,
)
from app.filters.titles import TitleRules
from app.filters.verdict import SOURCE_BOARD, SOURCE_TITLE, Criteria, Verdict, evaluate

__all__ = [
    "BOARD_LABELS",
    "SOURCE_BOARD",
    "SOURCE_TITLE",
    "Criteria",
    "Level",
    "TitleRules",
    "Verdict",
    "admits",
    "admits_any",
    "evaluate",
    "level_from_title",
    "merge_labels",
    "parse_level",
    "parse_requested",
]
