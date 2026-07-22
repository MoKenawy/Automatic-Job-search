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

from app.config import WORKING_SITES, settings
from app.db.models import STATUSES, Employer, Posting
from app.db.session import SessionFactory
from app.pipeline import suppress_employer
from app.settings_store import profiles as profile_store
from app.settings_store import store
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
    variant: str = Form("detail"),
    db: Session = Depends(get_db),
):
    """Transition triage state. Returns the control fragment for HTMX to swap in.

    `variant` selects the fragment and the no-HTMX redirect target: 'row' for the
    list (US1), 'detail' for the detail page. One endpoint serves both.
    """
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
        target = "/postings" if variant == "row" else f"/postings/{posting_id}"
        return RedirectResponse(url=target, status_code=303)

    fragment = "_row_status.html" if variant == "row" else "_status_control.html"
    return TEMPLATES.TemplateResponse(
        request=request,
        name=fragment,
        context={"p": posting, "statuses": STATUSES},
    )


@app.post("/postings/status", response_class=HTMLResponse)
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
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status: {status}")
    if not ids:
        raise HTTPException(status_code=400, detail="no postings selected")

    now = datetime.now(UTC)
    updated = 0
    for posting in db.query(Posting).filter(Posting.id.in_(ids)).all():
        posting.status = status
        posting.last_seen_at = now
        updated += 1
    db.commit()

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


@app.get("/blacklist", response_class=HTMLResponse)
def blacklist(request: Request, db: Session = Depends(get_db)):
    """List blacklisted employers with the option to remove each (US3, FR-010)."""
    return TEMPLATES.TemplateResponse(
        request=request,
        name="blacklist.html",
        context={"employers": queries.blacklisted_employers(db)},
    )


@app.post("/employers/{employer_id}/blacklist")
def blacklist_employer(
    employer_id: int,
    return_to: str = Form("/blacklist"),
    db: Session = Depends(get_db),
):
    """Blacklist an employer and immediately reject their postings (US3).

    Rejected postings are retained (D9). Callable from the blacklist page or from
    a posting (FR-012); `return_to` sends the operator back where they were.
    """
    employer = db.get(Employer, employer_id)
    if employer is None:
        raise HTTPException(status_code=404, detail="employer not found")

    employer.suppressed = True
    db.commit()
    suppress_employer(db, employer_id)

    return RedirectResponse(url=return_to, status_code=303)


@app.post("/employers/{employer_id}/unblacklist")
def unblacklist_employer(
    employer_id: int,
    return_to: str = Form("/blacklist"),
    db: Session = Depends(get_db),
):
    """Remove a blacklist. Future postings are no longer auto-rejected; previously
    rejected postings are NOT reinstated (US3, FR-011)."""
    employer = db.get(Employer, employer_id)
    if employer is None:
        raise HTTPException(status_code=404, detail="employer not found")

    employer.suppressed = False
    db.commit()

    return RedirectResponse(url=return_to, status_code=303)


# --- US4: settings -----------------------------------------------------------


@app.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, saved: bool = False, db: Session = Depends(get_db)):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "values": store.all_effective(db),
            "editable_keys": store.EDITABLE_KEYS,
            "readonly": {k: getattr(settings, k) for k in store.READONLY_KEYS},
            "saved": saved,
            "error": None,
        },
    )


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(request: Request, db: Session = Depends(get_db)):
    form = dict(await request.form())
    try:
        store.set_many(db, store.coerce_form(form))
    except (store.ValidationError, ValueError) as exc:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "values": {**store.all_effective(db), **form},
                "editable_keys": store.EDITABLE_KEYS,
                "readonly": {k: getattr(settings, k) for k in store.READONLY_KEYS},
                "saved": False,
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(url="/settings?saved=1", status_code=303)


# --- US4: search profiles ----------------------------------------------------


@app.get("/profiles", response_class=HTMLResponse)
def profiles_view(request: Request, error: str | None = None, db: Session = Depends(get_db)):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="profiles.html",
        context={
            "profiles": profile_store.list_all(db),
            "sites": WORKING_SITES,
            "error": error,
        },
    )


@app.post("/profiles", response_class=HTMLResponse)
async def profiles_create(request: Request, db: Session = Depends(get_db)):
    form = _multi_form(await request.form())
    try:
        profile_store.create(db, **form)
    except profile_store.ProfileError as exc:
        return RedirectResponse(url=f"/profiles?error={exc}", status_code=303)
    return RedirectResponse(url="/profiles", status_code=303)


@app.post("/profiles/{profile_id}/update")
async def profiles_update(request: Request, profile_id: int, db: Session = Depends(get_db)):
    form = _multi_form(await request.form())
    try:
        profile_store.update(db, profile_id, **form)
    except profile_store.ProfileError as exc:
        return RedirectResponse(url=f"/profiles?error={exc}", status_code=303)
    return RedirectResponse(url="/profiles", status_code=303)


@app.post("/profiles/{profile_id}/enabled")
def profiles_set_enabled(
    profile_id: int, enabled: str = Form("false"), db: Session = Depends(get_db)
):
    profile_store.set_enabled(db, profile_id, enabled.lower() in {"1", "true", "on", "yes"})
    return RedirectResponse(url="/profiles", status_code=303)


@app.post("/profiles/{profile_id}/delete")
def profiles_delete(profile_id: int, db: Session = Depends(get_db)):
    try:
        profile_store.delete(db, profile_id)
    except profile_store.ProfileError as exc:
        return RedirectResponse(url=f"/profiles?error={exc}", status_code=303)
    return RedirectResponse(url="/profiles", status_code=303)


@app.post("/profiles/{profile_id}/run")
def profiles_run_now(profile_id: int):
    """Run this profile's full pipeline immediately (research Q3)."""
    from app.pipeline.orchestrate import run_one_profile

    try:
        run_one_profile(profile_id)
    except ValueError as exc:
        return RedirectResponse(url=f"/profiles?error={exc}", status_code=303)
    return RedirectResponse(url="/runs", status_code=303)


def _multi_form(form) -> dict:
    """Flatten a form, keeping `sites` as a list of all selected checkboxes."""
    data = {k: v for k, v in form.items() if k != "sites"}
    data["sites"] = form.getlist("sites") if hasattr(form, "getlist") else form.get("sites")
    return data


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
