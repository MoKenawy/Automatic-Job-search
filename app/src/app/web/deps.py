"""Shared web dependencies: DB session and template environment.

Split out of app.py so both the app factory and the route modules can import
these without app.py importing the routers importing app.py back
(refactor-plan.md §7.1).
"""

import hashlib
from datetime import datetime
from importlib import metadata
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db.session import SessionFactory
from app.services import queries
from app.web.formatting import relative_age

_STATIC_DIR = Path(__file__).parent / "static"


def _asset_version() -> str:
    """Short hash of the static files' names, sizes and mtimes, for cache-busting
    (`?v=`). Computed once at import (ADR-0021, research R5)."""
    digest = hashlib.sha1()
    for path in sorted(p for p in _STATIC_DIR.rglob("*") if p.is_file()):
        stat = path.stat()
        digest.update(f"{path.relative_to(_STATIC_DIR)}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()[:10]


ASSET_VERSION = _asset_version()


def _app_version() -> str:
    """The installed package version, for the footer (spec 007 FR-003)."""
    try:
        return metadata.version("job-discovery")
    except metadata.PackageNotFoundError:
        return "dev"


APP_VERSION = _app_version()

# What the shell shows when a page was rendered without the dependency (e.g. /healthz).
EMPTY_SHELL = {"last_run": None, "now": None, "timezone": None}


def _shell_processor(request: Request) -> dict:
    """Expose `shell` (latest run, now) to every template (FR-013, plan R8)."""
    return {"shell": getattr(request.state, "shell", EMPTY_SHELL)}


TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"),
    context_processors=[_shell_processor],
)
TEMPLATES.env.globals["asset_version"] = ASSET_VERSION
TEMPLATES.env.globals["app_version"] = APP_VERSION
TEMPLATES.env.filters["relative_age"] = relative_age


def get_db():
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


def shell_context(request: Request, db=Depends(get_db)) -> None:
    """App-level dependency: gives every page the latest run for the shell (FR-013).

    Depends on `get_db`, so test overrides apply and FastAPI reuses the request's session.
    """
    request.state.shell = {
        "last_run": queries.latest_run(db),
        "now": datetime.now(ZoneInfo(settings.timezone)),
        "timezone": settings.timezone,
    }
