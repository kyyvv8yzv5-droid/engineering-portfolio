import json
import logging
import os
import time
from contextlib import contextmanager


# Uvicorn configures this logger in both normal and reload workers. Using its
# handler keeps development diagnostics visible without changing production
# logging configuration or adding response fields.
LOGGER = logging.getLogger("uvicorn.error")


def development_timing_enabled():
    return os.getenv(
        "AUTHENTICITY_DEV_TIMING",
        "false",
    ).strip().lower() == "true"


def log_timing(stage, duration_seconds, **details):
    if not development_timing_enabled():
        return
    LOGGER.info(
        json.dumps(
            {
                "event": "analysis_timing",
                "stage": stage,
                "duration_ms": round(duration_seconds * 1000.0, 3),
                **details,
            },
            sort_keys=True,
        )
    )


@contextmanager
def timed_stage(stage, **details):
    started = time.perf_counter()
    try:
        yield
    finally:
        log_timing(stage, time.perf_counter() - started, **details)
