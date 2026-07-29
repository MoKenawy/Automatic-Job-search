"""Report routes (ADR-0008).

One handler per report, plus an index. Registered in `web/app.py` alongside the
other routers (refactor-plan.md §7.1).

Each handler passes a `caveat` describing that report's sampling bias.
`reports/_caveat.html` renders it under a sentence shared by every report. This
is not decoration: ADR-0008 §1 admits these reports *on condition* the bias is
shown with the output, so the text is part of the report rather than a note
about it.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.services import queries, reports
from app.web.deps import TEMPLATES, get_db

router = APIRouter(prefix="/reports")

# Drives the index cards. Adding a report is an entry here plus a handler and a
# template, so the index cannot silently fall out of step with what exists.
REPORTS = [
    (
        "/reports/employers",
        "Employer hiring activity",
        "Who is hiring, and who fills the same few roles again and again.",
    ),
    (
        "/reports/sources",
        "Source coverage and overlap",
        "What each board contributes, and which one surfaces a role first.",
    ),
]


@router.get("", response_class=HTMLResponse)
def index(request: Request):
    return TEMPLATES.TemplateResponse(
        request=request, name="reports/index.html", context={"reports": REPORTS}
    )


@router.get("/employers", response_class=HTMLResponse)
def employers(request: Request, show_suppressed: bool = False, db: Session = Depends(get_db)):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="reports/employers.html",
        context={
            "rows": reports.employer_activity(db, include_suppressed=show_suppressed),
            "show_suppressed": show_suppressed,
            "caveat": (
                "Counts are of roles matching your search profiles — not of "
                "everything these employers are hiring for."
            ),
        },
    )


@router.get("/sources", response_class=HTMLResponse)
def sources(request: Request, db: Session = Depends(get_db)):
    # `health` supplies which boards recent runs actually queried. Without it the
    # coverage figures read as board behaviour when they may be search-profile
    # configuration — the caveat below needs evidence next to it, not just prose.
    return TEMPLATES.TemplateResponse(
        request=request,
        name="reports/sources.html",
        context={
            "overlap": reports.source_overlap(db),
            "health": queries.source_health(db),
            "caveat": (
                "A role missing from a board may mean the board did not have it, "
                "or that no search profile ever queried that board — the board "
                "list is set per profile."
            ),
        },
    )
