"""The 'collate' stage's subcommands are provided by the source plugins"""

import os

import pytest
from click.testing import CliRunner

from accessionflow.cli import cli, collate_group
from accessionflow.model.source import get_source, source_plugins
from accessionflow.sources.folder.cli import collate_cmd as folder_collate_cmd
from accessionflow.sources.orthanc.cli import collate_cmd as orthanc_collate_cmd

CLEAN_ENV = {key: None for key in os.environ if key.startswith("ACFLOW_")}


def test_source_plugins_are_found() -> None:
    assert {"folder", "orthanc"} <= set(source_plugins())
    assert get_source("folder").name == "folder"
    assert get_source("orthanc").title == "Orthanc"


def test_get_source_names_the_installed_plugins() -> None:
    with pytest.raises(ValueError, match="No source plugin named 'not-a-source'"):
        get_source("not-a-source")


def test_collate_lists_the_sources() -> None:
    result = CliRunner().invoke(cli, ["collate", "--help"], env=CLEAN_ENV)
    assert result.exit_code == 0, result.output
    assert "folder" in result.output and "orthanc" in result.output
    assert collate_group.commands["folder"] is folder_collate_cmd
    assert collate_group.commands["orthanc"] is orthanc_collate_cmd


def test_collate_with_unknown_source_names_the_available_ones() -> None:
    result = CliRunner().invoke(cli, ["collate", "nope", "in", "out"], env=CLEAN_ENV)
    assert result.exit_code != 0
    assert "no source plugin named 'nope' is installed" in result.output
    assert "sources available for 'collate': folder, orthanc" in result.output


@pytest.mark.parametrize("source", ["folder", "orthanc"])
def test_sources_share_the_collate_options(source: str) -> None:
    result = CliRunner().invoke(cli, ["collate", source, "--help"], env=CLEAN_ENV)
    assert result.exit_code == 0, result.output
    for option in [
        "--loop",
        "--copy-mode",
        "--convert",
        "--logger",
        "--additional-logger",
        "--raise-errors",
    ]:
        assert option in result.output
