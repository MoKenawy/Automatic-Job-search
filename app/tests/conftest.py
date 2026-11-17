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


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="run tests marked `live`, which make real requests to the job boards",
    )


def pytest_collection_modifyitems(config, items):
    """Skip `live` tests unless `--live` is given.

    The suite's promise is that it runs without Docker or a network; the live
    contract tests (tests/test_jobspy_contract.py) are the one deliberate
    exception and must be asked for.
    """
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="makes real requests to the job boards; run with --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
