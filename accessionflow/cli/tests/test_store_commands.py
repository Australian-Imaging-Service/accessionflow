"""The stages whose subcommands are provided by store plugins"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from accessionflow.cli import cli, label_group, make_label_command
from accessionflow.model.store import (
    LabelLevel,
    Store,
    get_store,
    store_plugins,
)

CLEAN_ENV = {key: None for key in os.environ if key.startswith("ACFLOW_")}


def test_xnat_plugin_is_found() -> None:
    assert "xnat" in store_plugins()
    xnat = get_store("xnat")
    assert [level.name for level in xnat.labels] == ["project", "subject", "session"]
    assert xnat.acquisition is not None and xnat.acquisition.name == "scan"


def test_get_store_names_the_installed_plugins() -> None:
    with pytest.raises(ValueError, match="installed: .*xnat"):
        get_store("not-a-store")


def test_store_needs_a_label_level() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Store(name="flat", title="Flat", labels=())
    # Any number of levels, or levels named when labelling, are fine
    Store(name="flat", title="Flat", labels=(LabelLevel("dataset"),))
    Store(name="free", title="Free", labels=None)


def test_store_rejects_repeated_label_names() -> None:
    with pytest.raises(ValueError, match="repeated"):
        Store(
            name="dup",
            title="Dup",
            labels=(LabelLevel("a"), LabelLevel("b"), LabelLevel("c")),
            acquisition=LabelLevel("a"),
        )


def test_stages_list_the_plugin_subcommands() -> None:
    runner = CliRunner()
    for stage in ("label", "store", "check-store"):
        result = runner.invoke(cli, [stage, "--help"], env=CLEAN_ENV)
        assert result.exit_code == 0, result.output
        assert "xnat" in result.output


def test_missing_store_plugin_is_explained() -> None:
    result = CliRunner().invoke(cli, ["store", "nope", "x"], env=CLEAN_ENV)
    assert result.exit_code == 2
    assert "no store plugin named 'nope' is installed" in result.output
    assert "accessionflow.stores.nope" in result.output
    assert "xnat" in result.output  # the stores that are available


def test_label_xnat_maps_scan_to_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import accessionflow.cli.label_cli as label_cli

    label = MagicMock(return_value=[])
    monkeypatch.setattr(label_cli, "label", label)
    (tmp_path / "in").mkdir()
    result = CliRunner().invoke(
        cli,
        [
            "label",
            "xnat",
            str(tmp_path / "in"),
            str(tmp_path / "out"),
            "--subject",
            "{PatientID}_{StudyDate:%Y%m%d}",
            "--scan",
            "ProtocolName",
            "--constant-project-id",
            "PROJ",
        ],
        env=CLEAN_ENV,
    )
    assert result.exit_code == 0, result.output
    kwargs = label.call_args.kwargs
    assert kwargs["label_fields"] == {
        "project": "StudyComments",
        "subject": "{PatientID}_{StudyDate:%Y%m%d}",
        "session": "AccessionNumber",
    }
    assert list(kwargs["label_fields"]) == ["project", "subject", "session"]
    assert kwargs["acquisition_field"] == "ProtocolName"
    assert kwargs["constant_labels"] == {"project": "PROJ"}
    assert kwargs["store_type"] == "xnat"
    assert kwargs["single_resource"] is False  # XNAT scans hold several resources


def test_label_single_resource_follows_store_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import accessionflow.cli.label_cli as label_cli

    label = MagicMock(return_value=[])
    monkeypatch.setattr(label_cli, "label", label)
    data_store = Store(
        name="singleres",
        title="Single",
        labels=(LabelLevel("a", "A"), LabelLevel("b", "B"), LabelLevel("c", "C")),
        multiple_resources=False,
    )
    make_label_command(data_store)
    try:
        (tmp_path / "in").mkdir()
        result = CliRunner().invoke(
            cli,
            ["label", "singleres", str(tmp_path / "in"), str(tmp_path / "out")],
            env=CLEAN_ENV,
        )
        assert result.exit_code == 0, result.output
        assert label.call_args.kwargs["single_resource"] is True
    finally:
        del label_group.commands["singleres"]


def test_label_xnat_options_keep_their_env_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import accessionflow.cli.label_cli as label_cli

    label = MagicMock(return_value=[])
    monkeypatch.setattr(label_cli, "label", label)
    (tmp_path / "in").mkdir()
    env = dict(
        CLEAN_ENV,
        ACFLOW_PROJECT="StudyID",
        ACFLOW_SESSION="StudyInstanceUID",
        ACFLOW_SCAN="SeriesNumber",
        ACFLOW_CONSTANT_PROJECT_ID="PROJ",
    )
    result = CliRunner().invoke(
        cli, ["label", "xnat", str(tmp_path / "in"), str(tmp_path / "out")], env=env
    )
    assert result.exit_code == 0, result.output
    kwargs = label.call_args.kwargs
    assert kwargs["label_fields"]["project"] == "StudyID"
    assert kwargs["label_fields"]["session"] == "StudyInstanceUID"
    assert kwargs["acquisition_field"] == "SeriesNumber"
    assert kwargs["constant_labels"] == {"project": "PROJ"}


def test_label_command_follows_store_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store with no acquisition label, and a level without a default"""
    import accessionflow.cli.label_cli as label_cli

    label = MagicMock(return_value=[])
    monkeypatch.setattr(label_cli, "label", label)
    data_store = Store(
        name="testrepo",
        title="Test",
        labels=(
            LabelLevel("study", default="StudyID"),
            LabelLevel("participant"),
            LabelLevel("visit", default="AccessionNumber"),
        ),
        envvar_prefix="TESTREPO_",
    )
    command = make_label_command(data_store)
    try:
        assert label_group.commands["testrepo"] is command
        options = {opt for param in command.params for opt in param.opts}
        assert {"--study", "--participant", "--visit", "--constant-study-id"} <= (
            options
        )
        assert "--scan" not in options
        (tmp_path / "in").mkdir()
        args = ["label", "testrepo", str(tmp_path / "in"), str(tmp_path / "out")]
        result = CliRunner().invoke(cli, args, env=CLEAN_ENV)
        assert result.exit_code == 2  # --participant has no default
        assert "--participant" in result.output
        result = CliRunner().invoke(
            cli, args, env=dict(CLEAN_ENV, TESTREPO_PARTICIPANT="PatientID")
        )
        assert result.exit_code == 0, result.output
        kwargs = label.call_args.kwargs
        assert kwargs["label_fields"] == {
            "study": "StudyID",
            "participant": "PatientID",
            "visit": "AccessionNumber",
        }
        assert kwargs["acquisition_field"] is None
        assert kwargs["store_type"] == "testrepo"
        assert kwargs["single_resource"] is False
    finally:
        del label_group.commands["testrepo"]


@pytest.mark.parametrize("old", ["upload", "check-upload", "fields", "collate-orthanc"])
def test_former_command_names_are_gone(old: str) -> None:
    """The names the stages had before they were renamed aren't kept as aliases"""
    result = CliRunner().invoke(cli, [old, "--help"], env=CLEAN_ENV)
    assert result.exit_code != 0
    assert f"No such command '{old}'" in result.output


@pytest.fixture
def free_store_label(monkeypatch: pytest.MonkeyPatch):
    """A 'label' subcommand for a store whose levels are named when labelling"""
    import accessionflow.cli.label_cli as label_cli

    label = MagicMock(return_value=[])
    monkeypatch.setattr(label_cli, "label", label)
    data_store = Store(
        name="freestore",
        title="Free",
        labels=None,
        acquisition=LabelLevel("acquisition", default="SeriesDescription"),
    )
    make_label_command(data_store)
    yield label
    del label_group.commands["freestore"]


def test_label_levels_named_by_user(tmp_path: Path, free_store_label) -> None:
    (tmp_path / "in").mkdir()
    args = ["label", "freestore", str(tmp_path / "in"), str(tmp_path / "out")]
    result = CliRunner().invoke(
        cli,
        args
        + [
            "--level",
            "site",
            "SiteID",
            "--level",
            "subject",
            "PatientID",
            "--level",
            "visit",
            "{StudyDate:%Y%m%d}",
            "--constant-label",
            "site",
            "SYD",
        ],
        env=CLEAN_ENV,
    )
    assert result.exit_code == 0, result.output
    kwargs = free_store_label.call_args.kwargs
    assert list(kwargs["label_fields"].items()) == [
        ("site", "SiteID"),
        ("subject", "PatientID"),
        ("visit", "{StudyDate:%Y%m%d}"),
    ]
    assert kwargs["constant_labels"] == {"site": "SYD"}
    assert kwargs["acquisition_field"] == "SeriesDescription"
    assert kwargs["store_type"] == "freestore"


def test_label_levels_from_env(tmp_path: Path, free_store_label) -> None:
    (tmp_path / "in").mkdir()
    result = CliRunner().invoke(
        cli,
        ["label", "freestore", str(tmp_path / "in"), str(tmp_path / "out")],
        env=dict(CLEAN_ENV, ACFLOW_LEVELS="site SiteID subject PatientID"),
    )
    assert result.exit_code == 0, result.output
    assert free_store_label.call_args.kwargs["label_fields"] == {
        "site": "SiteID",
        "subject": "PatientID",
    }


@pytest.mark.parametrize(
    "extra,message",
    [
        ([], "--level"),
        (["--level", "site", "A", "--level", "site", "B"], "repeated"),
        (["--level", "acquisition", "A"], "repeated"),
        (["--level", "site", "A", "--constant-label", "visit", "X"], "visit"),
        (["--level", "not a name", "A"], "valid identifiers"),
    ],
)
def test_label_levels_named_by_user_are_checked(
    tmp_path: Path, free_store_label, extra: list[str], message: str
) -> None:
    (tmp_path / "in").mkdir()
    result = CliRunner().invoke(
        cli,
        ["label", "freestore", str(tmp_path / "in"), str(tmp_path / "out")] + extra,
        env=CLEAN_ENV,
    )
    assert result.exit_code != 0
    assert message in result.output or message in str(result.exception)
    free_store_label.assert_not_called()
