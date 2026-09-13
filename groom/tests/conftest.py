"""Suite-wide isolation that no single test file can give itself."""
from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _logging_handlers_do_not_outlive_the_test() -> Iterator[None]:
    """Put every logger's handlers back the way the test found them.

    Starting a Litestar app — every `TestClient` — installs a queue handler on the root
    logger whose listener writes to the `sys.stderr` of that moment. Inside a `capsys`
    test that is the capture stream, which is closed when the test ends; the next test
    that logs (a websocket server's `connection open`) then prints a logging traceback
    into *its* stderr, and fails whichever assertion reads it.
    """
    loggers = [logging.getLogger(), *(
        logger for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )]
    saved = {logger: list(logger.handlers) for logger in loggers}
    yield
    for logger in [logging.getLogger(), *logging.Logger.manager.loggerDict.values()]:
        if isinstance(logger, logging.Logger):
            logger.handlers[:] = saved.get(logger, [])
