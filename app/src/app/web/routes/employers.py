"""Employer blacklist routes (US3)."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.services import blacklist as blacklist_service
from app.services import queries
from app.web.deps import TEMPLATES, get_db

router = APIRouter()


@router.get("/blacklist", response_class=HTMLResponse)
def blacklist_page(request: Request, db: Session = Depends(get_db)):
    """List blacklisted employers with the option to remove each (US3, FR-010)."""
    return TEMPLATES.TemplateResponse(
        request=request,
        name="blacklist.html",
        context={"employers": queries.blacklisted_employers(db)},
    )


@router.post("/employers/{employer_id}/blacklist")
def blacklist_employer(
    employer_id: int,
    return_to: str = Form("/blacklist"),
    db: Session = Depends(get_db),
):
    """Blacklist an employer and immediately reject their postings (US3).

    Rejected postings are retained (D9). Callable from the blacklist page or from
    a posting (FR-012); `return_to` sends the operator back where they were.
    """
    try:
        blacklist_service.blacklist(db, employer_id)
    except blacklist_service.EmployerNotFoundError:
        raise HTTPException(status_code=404, detail="employer not found") from None

    return RedirectResponse(url=return_to, status_code=303)


@router.post("/employers/{employer_id}/unblacklist")
def unblacklist_employer(
    employer_id: int,
    return_to: str = Form("/blacklist"),
    db: Session = Depends(get_db),
):
    """Remove a blacklist. Future postings are no longer auto-rejected; previously
    rejected postings are NOT reinstated (US3, FR-011)."""
    try:
        blacklist_service.lift(db, employer_id)
    except blacklist_service.EmployerNotFoundError:
        raise HTTPException(status_code=404, detail="employer not found") from None

    return RedirectResponse(url=return_to, status_code=303)
