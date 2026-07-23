"""Search-profile CRUD, run-now, and run history (US4, ADR-0005)."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import WORKING_SITES
from app.services import profiles as profile_store
from app.services import queries
from app.web.deps import TEMPLATES, get_db

router = APIRouter()


@router.get("/profiles", response_class=HTMLResponse)
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


@router.post("/profiles", response_class=HTMLResponse)
async def profiles_create(request: Request, db: Session = Depends(get_db)):
    form = _multi_form(await request.form())
    try:
        profile_store.create(db, **form)
    except profile_store.ProfileError as exc:
        return RedirectResponse(url=f"/profiles?error={exc}", status_code=303)
    return RedirectResponse(url="/profiles", status_code=303)


@router.post("/profiles/{profile_id}/update")
async def profiles_update(request: Request, profile_id: int, db: Session = Depends(get_db)):
    form = _multi_form(await request.form())
    try:
        profile_store.update(db, profile_id, **form)
    except profile_store.ProfileError as exc:
        return RedirectResponse(url=f"/profiles?error={exc}", status_code=303)
    return RedirectResponse(url="/profiles", status_code=303)


@router.post("/profiles/{profile_id}/enabled")
def profiles_set_enabled(
    profile_id: int, enabled: str = Form("false"), db: Session = Depends(get_db)
):
    profile_store.set_enabled(db, profile_id, enabled.lower() in {"1", "true", "on", "yes"})
    return RedirectResponse(url="/profiles", status_code=303)


@router.post("/profiles/{profile_id}/delete")
def profiles_delete(profile_id: int, db: Session = Depends(get_db)):
    try:
        profile_store.delete(db, profile_id)
    except profile_store.ProfileError as exc:
        return RedirectResponse(url=f"/profiles?error={exc}", status_code=303)
    return RedirectResponse(url="/profiles", status_code=303)


@router.post("/profiles/{profile_id}/run")
def profiles_run_now(profile_id: int):
    """Run this profile's full pipeline immediately (research Q3)."""
    from app.pipeline.runner import run_one_profile

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


@router.get("/runs", response_class=HTMLResponse)
def runs(request: Request, db: Session = Depends(get_db)):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="runs.html",
        context={"runs": queries.recent_runs(db), "health": queries.source_health(db)},
    )
