"""Shared web dependencies: DB session and template environment.

Split out of app.py so both the app factory and the route modules can import
these without app.py importing the routers importing app.py back
(refactor-plan.md §7.1).
"""

import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.db.session import SessionFactory

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

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.globals["asset_version"] = ASSET_VERSION


def get_db():
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
