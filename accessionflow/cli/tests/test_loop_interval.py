"""CLI loops keep a start-to-start interval despite work time or clock changes."""

import datetime
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner


class StopLoop(Exception):
    pass


# (the module the command is defined in, the command, the module the API it calls
# is looked up in, the API, its arguments besides INPUT/OUTPUT, and whether INPUT
# and OUTPUT come first)
CASES = [
    (
        "accessionflow.stores.xnat.cli.label_cli",
        "label_cmd",
        "accessionflow.cli.label_cli",
        "label",
        [],
        True,
    ),
    (
        "accessionflow.cli.attach_cli",
        "attach_cmd",
        "accessionflow.cli.attach_cli",
        "attach",
        ["generic/file", "*", ".*"],
        True,
    ),
    (
        "accessionflow.cli.deidentify_cli",
        "deidentify_cmd",
        "accessionflow.cli.deidentify_cli",
        "deidentify",
        ["{spec}"],
        True,
    ),
    (
        "accessionflow.sources.folder.cli.collate_cli",
        "collate_cmd",
        "accessionflow.sources.folder.cli.collate_cli",
        "collate",
        [],
        True,
    ),
    (
        "accessionflow.sources.orthanc.cli.collate_cli",
        "collate_cmd",
        "accessionflow.sources.orthanc.cli.collate_cli",
        "collate",
        ["http://orthanc.test", "{in}", "{out}", "user", "password"],
        False,
    ),
    (
        "accessionflow.stores.xnat.cli.store_cli",
        "store_cmd",
        "accessionflow.stores.xnat.cli.store_cli",
        "store",
        ["{in}", "https://xnat.test", "--user", "user", "--password", "password"],
        False,
    ),
]


@pytest.mark.parametrize(
    "command_module,command_name,api_module,api_name,extra,in_out_first", CASES
)
@pytest.mark.parametrize(
    "elapsed,loop,expected_sleep", [(2, 10, 8), (12, 10, 0), (2, -1, None)]
)
def test_loop_interval(
    command_module,
    command_name,
    api_module,
    api_name,
    extra,
    in_out_first,
    elapsed,
    loop,
    expected_sleep,
    tmp_path,
    monkeypatch,
):
    command = getattr(importlib.import_module(command_module), command_name)
    module = importlib.import_module(api_module)
    paths = {name: str(tmp_path / name) for name in ["in", "out", "spec"]}
    for name in ["in", "spec"]:
        (tmp_path / name).mkdir()
    args = [arg.format(**paths) for arg in extra]
    if in_out_first:
        args = [paths["in"], paths["out"]] + args
    args += ["--loop", str(loop)]
    now = [100.0]
    sleeps = []

    def work(**kwargs):
        now[0] += elapsed
        return []

    def sleep(seconds):
        sleeps.append(seconds)
        raise StopLoop

    monkeypatch.setattr(module, api_name, MagicMock(side_effect=work))
    monkeypatch.setattr(
        module, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=sleep)
    )
    # A backwards wall-clock adjustment must not affect the elapsed duration.
    wall = MagicMock()
    wall.now.side_effect = [
        datetime.datetime(2026, 1, 1, 0, 10),
        datetime.datetime(2026, 1, 1),
    ]
    monkeypatch.setattr(
        module, "datetime", SimpleNamespace(datetime=wall), raising=False
    )
    log = MagicMock()
    monkeypatch.setattr(module, "logger", log)
    if api_name == "store":
        monkeypatch.setattr(module, "Xnat", MagicMock())
    # Keep a developer's ACFLOW_* environment out of this CLI invocation.
    import os

    env = {key: None for key in os.environ if key.startswith("ACFLOW_")}
    result = CliRunner().invoke(command, args, env=env)
    assert getattr(module, api_name).call_count == 1, result.output
    if expected_sleep is None:
        assert result.exit_code == 0, result.exception
        assert sleeps == []
    else:
        assert isinstance(result.exception, StopLoop), (result.output, result.exception)
        assert sleeps == [expected_sleep]
        timing = log.info.call_args.args
        assert timing[1:3] == (elapsed, expected_sleep)
