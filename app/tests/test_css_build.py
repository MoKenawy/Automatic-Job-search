"""The authored stylesheet and its build output agree (spec 006 FR-010, FR-013, SC-005).

Stdlib only and binary-free (clarification Q1): it reads the committed, minified app.css,
so the default suite needs neither the Tailwind binary nor a browser.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.web.app import app, get_db
from visual_seed import seed

WEB = Path(__file__).resolve().parents[1] / "src" / "app" / "web"
INPUT_CSS = (WEB / "styles" / "input.css").read_text(encoding="utf-8")
BUILT_CSS = (WEB / "static" / "css" / "app.css").read_text(encoding="utf-8")

# Classes a template may emit that are not defined in the stylesheet: behaviour hooks only
# (contracts/class-contract.md section 3). Anything else rendered must exist in app.css.
# `selrow` is selected by the bulk-select script; `info` is the default banner kind, which
# takes the base `.banner` style. Neither has a rule on 49de3dd either.
HOOK_ONLY: set[str] = {"selrow", "info"}

PAGES = [
    "/", "/postings", "/postings/{id}", "/reports", "/reports/sources",
    "/reports/employers", "/reports/profiles", "/profiles", "/blacklist", "/settings", "/runs",
]  # fmt: skip


class _Classes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "class" and value:
                self.found.update(value.split())


def _defined_classes(css: str) -> set[str]:
    names = set()
    for raw in re.findall(r"\.((?:\\.|[A-Za-z0-9_-])+)", css):
        names.add(re.sub(r"\\(.)", r"\1", raw))
    return names


@pytest.fixture(scope="module")
def client():
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
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
    yield TestClient(app), detail_id
    app.dependency_overrides.pop(get_db, None)


def test_every_rendered_class_is_defined(client):
    http, detail_id = client
    bodies = [http.get(p.format(id=detail_id)).text for p in PAGES]
    # htmx fragments C-1 (row) and C-2 (detail) of the 004 contract.
    for variant in ("row", "detail"):
        r = http.post(
            f"/postings/{detail_id}/status",
            data={"status": "shortlist", "variant": variant},
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 200
        bodies.append(r.text)

    parser = _Classes()
    for body in bodies:
        parser.feed(body)
    missing = parser.found - _defined_classes(BUILT_CSS) - HOOK_ONLY
    assert not missing, f"rendered but not defined in app.css: {sorted(missing)}"


def test_every_authored_token_is_built():
    declared = set(re.findall(r"(--[a-z0-9-]+):\s*[^;]+;", _root_blocks(INPUT_CSS)))
    assert declared, "no tokens found in input.css :root blocks"
    built = set(re.findall(r"(--[a-z0-9-]+):", BUILT_CSS))
    assert declared <= built, f"tokens missing from app.css: {sorted(declared - built)}"


def _root_blocks(css: str) -> str:
    # Light block, then the dark block; both are authored verbatim at column 0 / 2 (FR-010).
    light = re.search(r"\n:root \{(.*?)\n\}", css, re.S).group(1)
    dark = re.search(r"prefers-color-scheme: dark\) \{\s*:root \{(.*?)\n  \}", css, re.S).group(1)
    return light + dark


def test_declared_source_paths_exist():
    paths = re.findall(r'@source\s+"([^"]+)"', INPUT_CSS)
    assert paths, "input.css declares no @source"
    for rel in paths:
        assert (WEB / "styles" / rel).resolve().is_dir(), f"@source path missing: {rel}"
