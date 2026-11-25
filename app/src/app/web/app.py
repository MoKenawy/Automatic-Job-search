"""Triage interface (ADR-0004).

Minimum scope per the §11 time-box: a list, a detail view, a status transition
and a run-health view. Server-rendered; HTMX handles the status transitions so a
triage action does not reload the page.

Route bodies live in web/routes/, one module per resource; this file is the
app factory, the dashboard landing page, and the container healthcheck
(refactor-plan.md §7.1).
"""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.services import queries
from app.services import settings as settings_service
from app.web.deps import TEMPLATES, get_db, shell_context
from app.web.routes import employers, postings, profiles, reports, settings

app = FastAPI(title="Job discovery", docs_url=None, redoc_url=None)

# Vendored htmx, Inter and the icon sprite are served from here so no page needs a
# third-party origin (constitution II, ADR-0021, research R5).
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

app.include_router(postings.router, dependencies=[Depends(shell_context)])
app.include_router(employers.router, dependencies=[Depends(shell_context)])
app.include_router(profiles.router, dependencies=[Depends(shell_context)])
app.include_router(settings.router, dependencies=[Depends(shell_context)])
app.include_router(reports.router, dependencies=[Depends(shell_context)])


RECENT_ON_OVERVIEW = 5


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(shell_context)])
def index(request: Request, db: Session = Depends(get_db)):
    # Everything here comes from existing read paths (spec 007 D4): no new queries.
    return TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "totals": queries.totals(db),
            "health": queries.source_health(db),
            "sites": queries.known_sites(db),
            "recent": queries.list_postings(db, per_page=RECENT_ON_OVERVIEW),
            "threshold": settings_service.get(db, "publish_threshold"),
            "scoring_model": settings_service.get(db, "scoring_model"),
            "cv_path": app_settings.cv_path,
        },
    )


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    """Container healthcheck: proves the process is up *and* the database is reachable."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
