"""WCAG contrast over the design-token pairs (spec 004 SC-002, FR-008a; constitution VI).

Parses the light `:root` block and the dark `prefers-color-scheme` block of app.css, so a
palette edit that breaks a pair fails here.
"""

import re
from pathlib import Path

import pytest

CSS = (
    Path(__file__).resolve().parents[1] / "src" / "app" / "web" / "static" / "css" / "app.css"
).read_text(encoding="utf-8")

_PROP = re.compile(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;")


def _light() -> dict[str, str]:
    block = re.search(r"\n:root \{(.*?)\n\}", CSS, re.S).group(1)
    return dict(_PROP.findall(block))


def _dark() -> dict[str, str]:
    block = re.search(r"prefers-color-scheme: dark\) \{\s*:root \{(.*?)\n  \}", CSS, re.S).group(1)
    return {**_light(), **dict(_PROP.findall(block))}


def _lum(hex_colour: str) -> float:
    def chan(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


SURFACES = [
    "surface",
    "surface-container-lowest",
    "surface-container-low",
    "surface-container",
    "surface-container-high",
    "surface-container-highest",
]
CONTROL_BG = ["surface", "surface-container-lowest"]

# (foreground, background, minimum)
PAIRS: list[tuple[str, str, float]] = (
    [(fg, bg, 4.5) for fg in ("on-surface", "on-surface-variant") for bg in SURFACES]
    + [
        ("primary", bg, 4.5)
        for bg in ("surface", "surface-container-lowest", "surface-container-low")
    ]
    + [("error", bg, 4.5) for bg in ("surface", "surface-container-lowest")]
    + [("outline", bg, 3.0) for bg in CONTROL_BG + ["surface-container-high"]]
    + [("focus-ring", bg, 3.0) for bg in ("surface", "surface-container-lowest")]
    + [("success", bg, 3.0) for bg in CONTROL_BG]
    + [
        ("on-primary-container", "primary-container", 4.5),
        ("on-primary", "primary", 4.5),
        ("on-success-container", "success-container", 4.5),
        ("on-error-container", "error-container", 4.5),
        ("on-secondary-container", "secondary-container", 4.5),
        ("inverse-on-surface", "inverse-surface", 4.5),
        ("primary", "secondary-container", 4.5),
    ]
)


def _resolve(palette: dict[str, str], name: str) -> str:
    # --focus-ring is declared as var(--primary), which the hex regex does not capture.
    if name == "focus-ring":
        return palette["primary"]
    return palette[name]


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS)
def test_contrast(scheme, fg, bg, minimum):
    palette = _light() if scheme == "light" else _dark()
    got = ratio(_resolve(palette, fg), _resolve(palette, bg))
    assert got >= minimum, f"{scheme}: {fg} on {bg} is {got:.2f}, needs {minimum}"
