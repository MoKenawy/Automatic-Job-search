"""Shared web dependencies: DB session and template environment.

Split out of app.py so both the app factory and the route modules can import
these without app.py importing the routers importing app.py back
(refactor-plan.md §7.1).
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.db.session import SessionFactory

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def get_db():
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
