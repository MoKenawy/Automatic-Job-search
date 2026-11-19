"""Presentation helpers for templates (spec 004, research R13)."""

from datetime import date, datetime

from markupsafe import Markup, escape

_ABSOLUTE_AFTER_DAYS = 60


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def relative_age(value: date | datetime | None, now: date | datetime) -> Markup:
    """Render "2d ago" style age, keeping the exact date available.

    "today", "1d ago".."6d ago", "1w ago".."8w ago" (up to 60 days), then the absolute
    date. `now` is passed in by the template (`shell.now`) so tests are deterministic.
    None renders "—".
    """
    if value is None:
        return Markup("—")
    posted = _as_date(value)
    days = (_as_date(now) - posted).days
    absolute = f"{posted.day:02d} {posted:%b %Y}"
    if days < 0 or days > _ABSOLUTE_AFTER_DAYS:
        text = absolute
    elif days == 0:
        text = "today"
    elif days < 7:
        text = f"{days}d ago"
    else:
        text = f"{days // 7}w ago"
    return Markup('<time datetime="{}" title="{}">{}</time>').format(
        posted.isoformat(), absolute, escape(text)
    )
