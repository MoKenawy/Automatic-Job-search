"""Posting list, detail, and triage status routes (US1, US2)."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import STATUSES
from app.services import queries
from app.services import triage as triage_service
from app.web.deps import TEMPLATES, get_db

router = APIRouter()


@router.get("/postings", response_class=HTMLResponse)
def postings(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    published: bool = False,
    db: Session = Depends(get_db),
):
    rows = queries.list_postings(
        db, status=status, search=q, published_only=published
    )
    return TEMPLATES.TemplateResponse(
        request=request,
        name="postings.html",
        context={
            "rows": rows,
            "status": status,
            "q": q or "",
            "published": published,
            "statuses": STATUSES,
            "totals": queries.totals(db),
        },
    )


@router.get("/postings/{posting_id}", response_class=HTMLResponse)
def posting_detail(request: Request, posting_id: int, db: Session = Depends(get_db)):
    row = queries.get_posting(db, posting_id)
    if row is None:
        raise HTTPException(status_code=404, detail="posting not found")
    posting, employer = row
    return TEMPLATES.TemplateResponse(
        request=request,
        name="detail.html",
        context={"p": posting, "employer": employer, "statuses": STATUSES},
    )


@router.post("/postings/{posting_id}/status", response_class=HTMLResponse)
def set_status(
    request: Request,
    posting_id: int,
    status: str = Form(...),
    variant: str = Form("detail"),
    db: Session = Depends(get_db),
):
    """Transition triage state. Returns the control fragment for HTMX to swap in.

    `variant` selects the fragment and the no-HTMX redirect target: 'row' for the
    list (US1), 'detail' for the detail page. One endpoint serves both.
    """
    try:
        posting = triage_service.set_status(db, posting_id, status)
    except triage_service.UnknownStatusError:
        raise HTTPException(status_code=400, detail=f"unknown status: {status}") from None
    if posting is None:
        raise HTTPException(status_code=404, detail="posting not found")

    # HTMX swaps the control in place. Without it — script blocked, CDN
    # unreachable — the plain form still posts, so redirect back instead of
    # returning a bare fragment.
    if request.headers.get("HX-Request") != "true":
        target = "/postings" if variant == "row" else f"/postings/{posting_id}"
        return RedirectResponse(url=target, status_code=303)

    fragment = "_row_status.html" if variant == "row" else "_status_control.html"
    return TEMPLATES.TemplateResponse(
        request=request,
        name=fragment,
        context={"p": posting, "statuses": STATUSES},
    )


@router.post("/postings/status", response_class=HTMLResponse)
def set_status_bulk(
    request: Request,
    ids: list[int] = Form(default=[]),
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    """Apply one status to several postings at once (US2).

    Selected rows only (research Q5). Updates in a single transaction, then
    re-renders the list so every changed row is reflected together.
    """
    if not ids:
        raise HTTPException(status_code=400, detail="no postings selected")
    try:
        updated = triage_service.set_status_bulk(db, ids, status)
    except triage_service.UnknownStatusError:
        raise HTTPException(status_code=400, detail=f"unknown status: {status}") from None

    # Re-render the full list so all changes show at once. Without HTMX the plain
    # form posts and this same render is returned as a normal page.
    rows = queries.list_postings(db)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="postings.html",
        context={
            "rows": rows,
            "status": None,
            "q": "",
            "published": False,
            "statuses": STATUSES,
            "totals": queries.totals(db),
            "flash": f"{updated} posting(s) set to {status}",
        },
    )
