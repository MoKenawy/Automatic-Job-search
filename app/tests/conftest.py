"""Suite-wide fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Never actually wait during tests.

    `request_delay_seconds` defaults to 10.0 (design §9.3); without this the
    collector's etiquette delay would add real wall-clock time to every test
    that exercises more than one site.
    """
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)
