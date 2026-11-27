"""The CLI contract: the parameters of the commands that the Prefect migration moves
onto step functions keep their names, types, defaults and environment variables (see
``prefect-migration-docs/ROADMAP.md``, principle 11). Only the parameters listed in
``ADDED`` may be new.

The snapshot was taken from the commands before Phase 1 changed them. To take it again,
e.g. for a later phase's commands, run this module as a script::

    .venv/bin/python -m accessionflow.cli.tests.test_cli_contract
"""

import enum
import json
import typing as ty
from pathlib import Path

import click
import pytest

SNAPSHOT = Path(__file__).parent / "snapshots" / "cli_contract.json"

# The commands in the snapshot, by name, and the module and attribute each is
# defined by
COMMANDS: dict[str, tuple[str, str]] = {
    "collate folder": ("accessionflow.sources.folder.cli", "collate_cmd"),
    "collate orthanc": ("accessionflow.sources.orthanc.cli", "collate_cmd"),
    "label xnat": ("accessionflow.stores.xnat.cli.label_cli", "label_cmd"),
    "label folder": ("accessionflow.stores.folder.cli.label_cli", "label_cmd"),
}

# The parameters added since the snapshot was taken, by command
ADDED: dict[str, set[str]] = {
    # Phase 1, CLI: the combiner's primary label and the run directories. Store-neutral
    # labels, N1: the store-neutral label options, named as in 'label xnat'
    "collate folder": {
        "--primary-label",
        "--runs-dir",
        "--working-dir",
        "--unprocessed-dir",
        "--error-dir",
        "--project",
        "--subject",
        "--session",
        "--scan",
        "--constant-project-id",
    },
    "collate orthanc": set(),
    "label xnat": set(),
    "label folder": set(),
}


def _jsonable(value: ty.Any) -> ty.Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return repr(value)


def _type_name(param_type: click.ParamType) -> ty.Any:
    """The parameter type, with the class an accessionflow 'cli_type' parses into, and
    a choice's choices"""
    wrapped = getattr(param_type, "type", None)
    if isinstance(wrapped, type):
        return f"{type(param_type).__name__}[{wrapped.__name__}]"
    if isinstance(param_type, click.Choice):
        return ["Choice", _jsonable(list(param_type.choices))]
    if isinstance(param_type, click.Tuple):
        return ["Tuple", [_type_name(t) for t in param_type.types]]
    return type(param_type).__name__


def describe(param: click.Parameter) -> dict[str, ty.Any]:
    """The parts of a parameter that the contract fixes"""
    return {
        "kind": type(param).__name__,
        "opts": sorted(param.opts),
        "secondary_opts": sorted(param.secondary_opts),
        "type": _type_name(param.type),
        "nargs": param.nargs,
        "multiple": param.multiple,
        "default": _jsonable(param.default),
        "envvar": _jsonable(param.envvar),
        "required": param.required,
        "hidden": getattr(param, "hidden", False),
    }


def command(name: str) -> click.Command:
    import importlib

    module, attr = COMMANDS[name]
    return ty.cast(click.Command, getattr(importlib.import_module(module), attr))


def contract(name: str) -> dict[str, dict[str, ty.Any]]:
    """The parameters of a command, keyed by their first option string, or by name for
    an argument. The name of an option's Python parameter isn't part of the contract"""
    return {param.opts[0]: describe(param) for param in command(name).params}


def take_snapshot() -> None:
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(
        json.dumps({name: contract(name) for name in COMMANDS}, indent=2) + "\n"
    )


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_cli_contract_is_kept(name: str) -> None:
    snapshot = json.loads(SNAPSHOT.read_text())[name]
    current = contract(name)
    for param, expected in snapshot.items():
        assert param in current, f"'{name}' lost its parameter '{param}'"
        assert current[param] == expected, f"'{name}' changed its parameter '{param}'"
    assert set(current) - set(snapshot) == ADDED[name]


if __name__ == "__main__":
    take_snapshot()
