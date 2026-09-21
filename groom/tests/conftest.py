"""Suite-wide isolation that no single test file can give itself."""
from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _logging_handlers_do_not_outlive_the_test() -> Iterator[None]:
    """Put every logger's handlers back the way the test found them."""
    loggers = [logging.getLogger(), *(
        logger for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )]
    saved = {logger: list(logger.handlers) for logger in loggers}
    yield
    for logger in [logging.getLogger(), *logging.Logger.manager.loggerDict.values()]:
        if isinstance(logger, logging.Logger):
            logger.handlers[:] = saved.get(logger, [])
