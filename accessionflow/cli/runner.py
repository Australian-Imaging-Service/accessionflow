"""Helpers shared by the CLI commands for running a stage, once or on an interval.

These are CLI concerns only: a stage's API functions don't loop, sleep or summarise
their errors, so that they can be wrapped as Prefect tasks elsewhere (see
``prefect-migration-docs/ROADMAP.md``).
"""

import time
import typing as ty

from accessionflow.helpers.logging import logger

__all__ = ["check_loop_options", "log_stage_summary", "run_on_interval"]


def check_loop_options(raise_errors: bool, loop: int) -> None:
    """Refuse --raise-errors with --loop, since raising would end the loop"""
    if raise_errors and loop >= 0:
        raise ValueError(
            "Cannot use --raise-errors and --loop together as the loop will "
            "continue to run even if an error occurs"
        )


def log_stage_summary(errors: ty.Sequence[str], stage: str) -> None:
    """Logs the outcome of one run of a stage

    Parameters
    ----------
    errors : Sequence[str]
        the error messages the run returned, one per accession that failed
    stage : str
        the name of the stage, e.g. 'Collate', at the start of the message
    """
    if errors:
        logger.error(
            "%s completed with %s errors:\n\n%s",
            stage,
            len(errors),
            "\n".join(errors),
        )
    else:
        logger.info("%s completed successfully", stage)


def run_on_interval(
    run_once: ty.Callable[[], object],
    loop: int,
    name: str,
    monotonic: ty.Callable[[], float] = time.monotonic,
    sleep: ty.Callable[[float], object] = time.sleep,
) -> None:
    """Runs a stage once, or, if ``loop`` isn't negative, again and again with
    ``loop`` seconds from the start of one run to the start of the next. A run that
    takes longer than ``loop`` is followed straight away by the next one.

    Parameters
    ----------
    run_once : Callable[[], object]
        runs the stage once. Its return value is ignored
    loop : int
        the number of seconds between the starts of the runs, or a negative number to
        run the stage once
    name : str
        the name of the stage, e.g. 'Collate', for the log messages
    monotonic : Callable[[], float], optional
        the clock the run times are measured with. A monotonic clock, so that a change
        to the wall clock doesn't change the interval
    sleep : Callable[[float], object], optional
        waits for the given number of seconds
    """
    while True:
        start_time = monotonic()
        run_once()
        if loop < 0:
            return
        elapsed_seconds = monotonic() - start_time
        sleep_time = max(loop - elapsed_seconds, 0)
        # The name is fixed by the caller, so it is put in the format string to keep
        # the timings as the first arguments
        logger.info(
            f"{name} took %s seconds, waiting another %s seconds before running "
            "again (loop every %s seconds)",
            elapsed_seconds,
            sleep_time,
            loop,
        )
        sleep(sleep_time)
