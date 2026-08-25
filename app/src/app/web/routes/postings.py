"""Posting list, detail, and triage status routes (US1, US2)."""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import STATUSES
from app.services import queries
from app.services import triage as triage_service
from app.web.deps import TEMPLATES, get_db

router = APIRouter()


def _render_list(
    request: Request,
    db: Session,
    *,
    status: str | None,
    q: str | None,
    published: bool,
    country: str | None,
    source: str | None,
    page: int,
    flash: str | None = None,
):
    """Render the posting list under a set of filters.

    Shared by the list route and the bulk-status route so the two cannot drift:
    after a bulk change the operator must land back on the same filtered page
    they acted from, which means rendering it the same way.
    """
    # A single "location" selector covers both axes: `country` doubles as the
    # sentinel 'remote' (design normalise/country.py — city is not comparable
    # across boards, so remote/country is the only location split on offer).
    remote_filter = True if country == "remote" else None
    country_filter = None if country == "remote" else country
    pager = queries.list_postings(
        db,
        status=status,
        search=q,
        published_only=published,
        country=country_filter,
        remote=remote_filter,
        source=source,
        page=page,
    )

    # Pager links must carry the active filters, or paging would quietly widen
    # the result set. Built here as a callable so the template asks for a page
    # number and gets a whole URL, rather than concatenating one three times.
    active = {
        k: v
        for k, v in (("status", status), ("q", q), ("country", country), ("source", source))
        if v
    }
    if published:
        active["published"] = "true"

    def page_url(n: int) -> str:
        return "/postings?" + urlencode({**active, "page": n})

    return TEMPLATES.TemplateResponse(
        request=request,
        name="postings.html",
        context={
            "pager": pager,
            "page_url": page_url,
            "status": status,
            "q": q or "",
            "published": published,
            "country": country or "",
            "source": source or "",
            "statuses": STATUSES,
            "totals": queries.totals(db),
            "facets": queries.facets(db),
            "flash": flash,
        },
    )


@router.get("/postings", response_class=HTMLResponse)
def postings(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    published: bool = False,
    country: str | None = None,
    source: str | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    return _render_list(
        request,
        db,
        status=status,
        q=q,
        published=published,
        country=country,
        source=source,
        page=page,
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
    # The list's own filter and page state, echoed back by hidden inputs on the
    # bulk form. `list_status` rather than `status` because `status` is already
    # taken by the status being applied. Without these the re-render would drop
    # the operator back on an unfiltered page 1 after every bulk action.
    list_status: str | None = Form(default=None),
    q: str | None = Form(default=None),
    published: bool = Form(default=False),
    country: str | None = Form(default=None),
    source: str | None = Form(default=None),
    page: int = Form(default=1),
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
    return _render_list(
        request,
        db,
        status=list_status,
        q=q,
        published=published,
        country=country,
        source=source,
        page=page,
        flash=f"{updated} posting(s) set to {status}",
    )
