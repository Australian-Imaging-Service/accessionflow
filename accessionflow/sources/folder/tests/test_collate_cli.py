"""Tests of 'collate folder' on the collate steps and the combiner (see
``prefect-migration-docs/ROADMAP.md``, Phase 1, CLI), on small JSON trees"""

import os
import typing as ty
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner, Result

from accessionflow.api.collate import combine as combine_module
from accessionflow.helpers.remotes import list_session_dirs
from accessionflow.model.accession import Accession
from accessionflow.sources.folder.cli import collate_cli
from accessionflow.sources.folder.cli.collate_cli import collate_cmd

CLEAN_ENV: dict[str, str | None] = {
    key: None for key in os.environ if key.startswith("ACFLOW_")
}

# Collates each JSON file in a session directory, '<sess>/<name>.json', into an
# accession of its session, with an acquisition per file
JSON_ARGS = [
    "--datatype",
    "application/json",
    "--recursive",
    "--accession",
    "sess",
    "application/json",
    "--acquisition",
    "name",
    "application/json",
    "--path-metadata",
    "{sess}/{name}.json",
    "application/json",
]
XNAT_ARGS = ["--constant-project-id", "P", "--subject", "sess", "--session", "sess"]


def _inbox(tmp_path: Path, *relpaths: str) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    for relpath in relpaths:
        path = inbox / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"a": 1}')
    return inbox


def _run(
    args: ty.Sequence[str], env: ty.Mapping[str, str | None] | None = None
) -> Result:
    return CliRunner().invoke(collate_cmd, list(args), env={**CLEAN_ENV, **(env or {})})


def _names(directory: Path) -> list[str]:
    return sorted(d.name for d in list_session_dirs(directory))


def test_collate_folder_delivers_labelled_combined_accessions(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, "s1/a.json", "s1/b.json", "s2/a.json")
    out = tmp_path / "out"
    result = _run([str(inbox), str(out), *JSON_ARGS, *XNAT_ARGS, "--raise-errors"])
    assert result.exit_code == 0, result.output
    assert _names(out) == ["P.s1.s1_combined", "P.s2.s2_combined"]
    # The run accessions were combined, and the files consumed
    assert _names(out / "__runs__") == []
    assert not list(inbox.rglob("*.json"))


def test_collate_folder_combines_after_the_wait_period(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = _inbox(tmp_path, "s1/a.json")
    out = tmp_path / "out"
    args = [str(inbox), str(out), *JSON_ARGS, *XNAT_ARGS, "--wait-period", "60"]
    result = _run(args)
    assert result.exit_code == 0, result.output
    # The run accession is delivered at once, but not yet combined
    (run_accession,) = _names(out / "__runs__")
    assert run_accession.startswith("P.s1.s1_")
    assert _names(out) == []

    # More data arrives for the same session in the next run
    _inbox(tmp_path, "s1/b.json")
    result = _run(args)
    assert result.exit_code == 0, result.output
    assert len(_names(out / "__runs__")) == 2
    assert _names(out) == []

    class Later(datetime):
        @classmethod
        def now(cls, tz: ty.Any = None) -> datetime:  # type: ignore[override]
            return datetime.now(tz) + timedelta(seconds=61)

    monkeypatch.setattr(combine_module, "datetime", Later)
    result = _run(args)
    assert result.exit_code == 0, result.output
    assert _names(out) == ["P.s1.s1_combined"]
    assert _names(out / "__runs__") == []


def test_collate_folder_reports_an_accession_that_cant_be_labelled(
    tmp_path: Path,
) -> None:
    inbox = _inbox(tmp_path, "s1/a.json")
    out = tmp_path / "out"
    # XNAT's default project field, StudyComments, isn't in the metadata
    result = _run([str(inbox), str(out), *JSON_ARGS, "--subject", "sess"])
    assert result.exit_code == 0, result.output
    assert _names(out) == []
    (run_dir,) = (out / "__unprocessed__").iterdir()
    assert (run_dir / "files" / "s1" / "a.json").exists()


@pytest.mark.parametrize(
    "option",
    [
        ["--store", "folder"],
        ["--level", "site", "sess"],
        ["--constant-label", "site", "X"],
        ["--folder-acquisition", "ProtocolName"],
    ],
)
def test_collate_folder_has_no_store_options(tmp_path: Path, option: list[str]) -> None:
    """Collate labels project, subject and session, whatever store the accessions are
    going to, so the store options of the CLI step are gone"""
    inbox = _inbox(tmp_path, "s1/a.json")
    out = tmp_path / "out"
    result = _run([str(inbox), str(out), *JSON_ARGS, *option])
    assert result.exit_code == 2
    assert f"No such option '{option[0]}'" in result.output
    assert not out.exists()
    assert (inbox / "s1" / "a.json").exists()


def test_collate_folder_ignores_store_options_in_the_environment(
    tmp_path: Path,
) -> None:
    """The environment is shared with 'label folder', whose variables collate doesn't
    read"""
    inbox = _inbox(tmp_path, "s1/a.json")
    out = tmp_path / "out"
    result = _run(
        [str(inbox), str(out), *JSON_ARGS, *XNAT_ARGS],
        env={"ACFLOW_STORE": "folder", "ACFLOW_LEVELS": "site sess"},
    )
    assert result.exit_code == 0, result.output
    (name,) = _names(out)
    assert name == "P.s1.s1_combined"
    accession = Accession.load(out / name)
    assert accession.store_type is None
    assert accession.labels == {"project": "P", "subject": "s1", "session": "s1"}


@pytest.mark.parametrize("primary_label", ["", "a_b", "20261126010000_aaaaaa"])
def test_collate_folder_refuses_a_bad_primary_label(
    tmp_path: Path, primary_label: str
) -> None:
    inbox = _inbox(tmp_path, "s1/a.json")
    out = tmp_path / "out"
    result = _run([str(inbox), str(out), *JSON_ARGS, "--primary-label", primary_label])
    assert result.exit_code != 0
    assert "Primary label" in str(result.exception)
    assert not out.exists()
    assert (inbox / "s1" / "a.json").exists()


def test_collate_folder_warns_that_unlink_source_has_no_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = MagicMock()
    monkeypatch.setattr(collate_cli, "logger", log)
    inbox = _inbox(tmp_path, "s1/a.json")
    out = tmp_path / "out"
    result = _run(
        [str(inbox), str(out), *JSON_ARGS, *XNAT_ARGS, "--unlink-source", "all"]
    )
    assert result.exit_code == 0, result.output
    assert "deprecated" in log.warning.call_args.args[0]
    assert _names(out) == ["P.s1.s1_combined"]
    assert not (inbox / "s1" / "a.json").exists()


@pytest.fixture
def mocked_api(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    collate = MagicMock(return_value=[])
    combine = MagicMock(return_value=[])
    monkeypatch.setattr(collate_cli, "collate", collate)
    monkeypatch.setattr(collate_cli, "combine_run_accessions", combine)
    return collate, combine


def test_collate_folder_passes_the_defaults(
    tmp_path: Path, mocked_api: tuple[MagicMock, MagicMock]
) -> None:
    collate, combine = mocked_api
    inbox = _inbox(tmp_path, "s1/a.json")
    out = tmp_path / "out"
    result = _run([str(inbox), str(out)])
    assert result.exit_code == 0, result.output

    files, runs, working, unprocessed, errors, label_fields = collate.call_args.args
    assert files == [inbox / "s1" / "a.json"]
    assert runs == out / "__runs__"
    assert working == out / "__processing__"
    assert unprocessed == out / "__unprocessed__"
    assert errors == out / "__error__"
    assert label_fields == {
        "project": "StudyComments",
        "subject": "PatientID",
        "session": "AccessionNumber",
    }
    kwargs = collate.call_args.kwargs
    assert "store_type" not in kwargs
    assert kwargs["acquisition_field"] == "SeriesDescription"
    assert kwargs["constant_labels"] == {}
    assert kwargs["source_roots"] == [inbox.absolute()]

    assert combine.call_args.args == (
        out / "__runs__",
        out,
        out / "__error__",
        timedelta(0),
        "combined",
    )


def test_collate_folder_reads_its_options_from_the_environment(
    tmp_path: Path, mocked_api: tuple[MagicMock, MagicMock]
) -> None:
    collate, combine = mocked_api
    inbox = _inbox(tmp_path, "s1/a.json")
    out = tmp_path / "out"
    result = _run(
        [str(inbox), str(out)],
        env={
            "ACFLOW_PROJECT": "StudyID",
            "ACFLOW_SUBJECT": "{PatientID}_{SiteID}",
            "ACFLOW_SESSION": "StudyDate",
            "ACFLOW_SCAN": "ProtocolName",
            "ACFLOW_CONSTANT_PROJECT_ID": "PROJ",
            "ACFLOW_PRIMARY_LABEL": "final",
            "ACFLOW_WAIT_PERIOD": "30",
            "ACFLOW_RUNS_DIR": str(tmp_path / "runs"),
            "ACFLOW_WORKING_DIR": str(tmp_path / "work"),
            "ACFLOW_UNPROCESSED_DIR": str(tmp_path / "left"),
            "ACFLOW_ERROR_DIR": str(tmp_path / "failed"),
        },
    )
    assert result.exit_code == 0, result.output

    _, runs, working, unprocessed, errors, label_fields = collate.call_args.args
    assert (runs, working, unprocessed, errors) == (
        tmp_path / "runs",
        tmp_path / "work",
        tmp_path / "left",
        tmp_path / "failed",
    )
    assert label_fields == {
        "project": "StudyID",
        "subject": "{PatientID}_{SiteID}",
        "session": "StudyDate",
    }
    kwargs = collate.call_args.kwargs
    assert "store_type" not in kwargs
    assert kwargs["acquisition_field"] == "ProtocolName"
    assert kwargs["constant_labels"] == {"project": "PROJ"}

    assert combine.call_args.args == (
        tmp_path / "runs",
        out,
        tmp_path / "failed",
        timedelta(seconds=30),
        "final",
    )
