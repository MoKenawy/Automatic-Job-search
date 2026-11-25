"""Visual gate (006 FR-026, research R7): 11 pages x 2 widths x 2 palettes = 44 snapshots.

Opt-in: `uv sync --group visual`, `uv run playwright install chromium`, then
`uv run pytest --visual`. Baselines are Windows-rendered (spec Assumptions) and live in
tests/__snapshots__/. Regenerate only by a recorded decision (FR-003):
`--update-snapshots`.
"""

import socket
import threading
import time
from datetime import datetime

import pytest

pytest.importorskip("playwright")
pytest.importorskip("pytest_playwright_visual_snapshot")

import uvicorn  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.web.app import app, get_db  # noqa: E402
from visual_seed import ANCHOR, seed  # noqa: E402

pytestmark = pytest.mark.visual

WIDTHS = {"375": (375, 812), "1280": (1280, 800)}
SCHEMES = ("light", "dark")
# Content that changes between renders is masked (R7).
MASKS = [".last-run"]


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return ANCHOR.astimezone(tz) if tz else ANCHOR.replace(tzinfo=None)


@pytest.fixture(scope="module")
def base_url():
    # Freeze the shell clock so relative ages ("2d ago") are stable (R7), and the reports clock
    # so the employer report's "days quiet" does not grow by one every day (006-4).
    mp = pytest.MonkeyPatch()
    mp.setattr("app.web.deps.datetime", _FrozenDatetime)
    mp.setattr("app.services.reports.datetime", _FrozenDatetime)
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as db:
        detail_id = seed(db)

    def _get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", detail_id
    server.should_exit = True
    thread.join(timeout=5)
    app.dependency_overrides.pop(get_db, None)
    mp.undo()


PAGES = {
    "index": "/",
    "postings": "/postings",
    "detail": "/postings/{detail_id}",
    "reports": "/reports",
    "reports-sources": "/reports/sources",
    "reports-employers": "/reports/employers",
    "reports-profiles": "/reports/profiles",
    "profiles": "/profiles",
    "blacklist": "/blacklist",
    "settings": "/settings",
    "runs": "/runs",
}


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("page_name", PAGES)
def test_page_matches_baseline(browser, base_url, assert_snapshot, page_name, width, scheme):
    url, detail_id = base_url
    w, h = WIDTHS[width]
    context = browser.new_context(
        viewport={"width": w, "height": h}, color_scheme=scheme, reduced_motion="reduce"
    )
    page = context.new_page()
    try:
        page.goto(url + PAGES[page_name].format(detail_id=detail_id))
        page.evaluate("document.fonts.ready")
        shot = page.screenshot(
            full_page=True,
            animations="disabled",
            mask=[page.locator(sel) for sel in MASKS],
        )
    finally:
        context.close()
    assert_snapshot(shot, name=f"{page_name}-{width}-{scheme}.png", threshold=0.05)
