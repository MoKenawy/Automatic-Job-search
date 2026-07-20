"""Triage interface (ADR-0004).

Minimum scope per the §11 time-box: a list, a detail view, a status transition
and a run-health view. Server-rendered; HTMX handles the status transitions so a
triage action does not reload the page.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import STATUSES, Posting
from app.db.session import SessionFactory
from app.web import queries

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

app = FastAPI(title="Job discovery", docs_url=None, redoc_url=None)


def get_db():
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={"totals": queries.totals(db), "health": queries.source_health(db)},
    )


@app.get("/postings", response_class=HTMLResponse)
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


@app.get("/postings/{posting_id}", response_class=HTMLResponse)
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


@app.post("/postings/{posting_id}/status", response_class=HTMLResponse)
def set_status(
    request: Request,
    posting_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    """Transition triage state. Returns the badge fragment for HTMX to swap in."""
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status: {status}")

    posting = db.get(Posting, posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail="posting not found")

    posting.status = status
    posting.last_seen_at = datetime.now(UTC)
    db.commit()

    # HTMX swaps the control in place. Without it — script blocked, CDN
    # unreachable — the plain form still posts, so redirect back instead of
    # returning a bare fragment.
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=f"/postings/{posting_id}", status_code=303)

    return TEMPLATES.TemplateResponse(
        request=request,
        name="_status_control.html",
        context={"p": posting, "statuses": STATUSES},
    )


@app.get("/runs", response_class=HTMLResponse)
def runs(request: Request, db: Session = Depends(get_db)):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="runs.html",
        context={"runs": queries.recent_runs(db), "health": queries.source_health(db)},
    )


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    """Container healthcheck: proves the process is up *and* the database is reachable."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
