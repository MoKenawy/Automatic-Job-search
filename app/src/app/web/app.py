"""Triage interface (ADR-0004).

Minimum scope per the §11 time-box: a list, a detail view, a status transition
and a run-health view. Server-rendered; HTMX handles the status transitions so a
triage action does not reload the page.

Route bodies live in web/routes/, one module per resource; this file is the
app factory, the dashboard landing page, and the container healthcheck
(refactor-plan.md §7.1).
"""

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import queries
from app.web.deps import TEMPLATES, get_db
from app.web.routes import employers, postings, profiles, reports, settings

app = FastAPI(title="Job discovery", docs_url=None, redoc_url=None)

app.include_router(postings.router)
app.include_router(employers.router)
app.include_router(profiles.router)
app.include_router(settings.router)
app.include_router(reports.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={"totals": queries.totals(db), "health": queries.source_health(db)},
    )


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    """Container healthcheck: proves the process is up *and* the database is reachable."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
