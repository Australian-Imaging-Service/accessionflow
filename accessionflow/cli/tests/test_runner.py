from unittest.mock import MagicMock

import pytest

from accessionflow.cli import runner
from accessionflow.cli.runner import (
    check_loop_options,
    log_stage_summary,
    run_on_interval,
)


class StopLoop(Exception):
    pass


def test_run_on_interval_runs_once_without_loop() -> None:
    run_once = MagicMock()
    sleep = MagicMock()
    run_on_interval(run_once, -1, "Test", sleep=sleep)
    run_once.assert_called_once_with()
    sleep.assert_not_called()


@pytest.mark.parametrize("elapsed,loop,expected_sleep", [(2, 10, 8), (12, 10, 0)])
def test_run_on_interval_keeps_start_to_start_interval(
    elapsed: float,
    loop: int,
    expected_sleep: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [100.0]
    sleeps: list[float] = []
    runs = []

    def run_once() -> None:
        runs.append(now[0])
        now[0] += elapsed

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop
        now[0] += seconds

    log = MagicMock()
    monkeypatch.setattr(runner, "logger", log)
    with pytest.raises(StopLoop):
        run_on_interval(run_once, loop, "Test", monotonic=lambda: now[0], sleep=sleep)
    assert sleeps == [expected_sleep, expected_sleep]
    assert runs == [100.0, 100.0 + max(elapsed, loop)]
    message, *args = log.info.call_args.args
    assert message.startswith("Test took ")
    assert args == [elapsed, expected_sleep, loop]


def test_check_loop_options() -> None:
    check_loop_options(raise_errors=True, loop=-1)
    check_loop_options(raise_errors=False, loop=10)
    with pytest.raises(ValueError, match="--raise-errors and --loop"):
        check_loop_options(raise_errors=True, loop=0)


def test_log_stage_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    log = MagicMock()
    monkeypatch.setattr(runner, "logger", log)
    log_stage_summary([], "Collate")
    log.info.assert_called_once_with("%s completed successfully", "Collate")
    log_stage_summary(["first", "second"], "Collate")
    log.error.assert_called_once_with(
        "%s completed with %s errors:\n\n%s", "Collate", 2, "first\nsecond"
    )
