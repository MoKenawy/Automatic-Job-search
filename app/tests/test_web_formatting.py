"""relative_age filter (spec 004, research R13)."""

from datetime import UTC, date, datetime

from app.web.formatting import relative_age

NOW = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)


def _text(value):
    return str(relative_age(value, NOW))


def test_today():
    assert ">today<" in _text(date(2026, 11, 19))


def test_days():
    assert ">1d ago<" in _text(date(2026, 11, 18))
    assert ">6d ago<" in _text(date(2026, 11, 13))


def test_weeks():
    assert ">3w ago<" in _text(date(2026, 10, 29))


def test_absolute_beyond_sixty_days():
    out = _text(date(2026, 8, 1))
    assert ">01 Aug 2026<" in out


def test_exact_date_stays_available():
    out = _text(date(2026, 11, 18))
    assert 'datetime="2026-11-18"' in out
    assert 'title="18 Nov 2026"' in out


def test_none_is_a_dash():
    assert _text(None) == "—"
