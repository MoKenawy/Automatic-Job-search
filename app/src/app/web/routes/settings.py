"""Runtime settings view/save (US4, ADR-0005)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.services import settings as settings_service
from app.web.deps import TEMPLATES, get_db

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, saved: bool = False, db: Session = Depends(get_db)):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "values": settings_service.all_effective(db),
            "editable_keys": settings_service.EDITABLE_KEYS,
            "readonly": {k: getattr(settings, k) for k in settings_service.READONLY_KEYS},
            "saved": saved,
            "error": None,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_save(request: Request, db: Session = Depends(get_db)):
    form = dict(await request.form())
    try:
        settings_service.set_many(db, settings_service.coerce_form(form))
    except (settings_service.ValidationError, ValueError) as exc:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "values": {**settings_service.all_effective(db), **form},
                "editable_keys": settings_service.EDITABLE_KEYS,
                "readonly": {k: getattr(settings, k) for k in settings_service.READONLY_KEYS},
                "saved": False,
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(url="/settings?saved=1", status_code=303)
