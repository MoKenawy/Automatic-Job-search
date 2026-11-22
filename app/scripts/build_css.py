"""Build the served stylesheet from its authored source (ADR-0022, spec 006 R1).

One entry point for the maintainer and for CI, so the two cannot drift apart. The
Tailwind version is pinned in `[tool.app.tailwind] version` in pyproject.toml, the only
place it is recorded. pytailwindcss keeps one binary per version, so a changed pin simply
downloads the new one on first use.

    uv run python scripts/build_css.py            # one-off minified build
    uv run python scripts/build_css.py --watch    # rebuild while authoring
"""

import sys
import tomllib
from pathlib import Path

from pytailwindcss import run

APP_DIR = Path(__file__).resolve().parents[1]
SOURCE = Path("src/app/web/styles/input.css")
OUTPUT = Path("src/app/web/static/css/app.css")


def pinned_version() -> str:
    data = tomllib.loads((APP_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["app"]["tailwind"]["version"]


def main(argv: list[str]) -> int:
    watch = "--watch" in argv
    args = ["-i", str(SOURCE), "-o", str(OUTPUT)]
    args.append("--watch") if watch else args.append("--minify")
    done = run(args, version=pinned_version(), cwd=APP_DIR, auto_install=True, live_output=True)
    return done.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
