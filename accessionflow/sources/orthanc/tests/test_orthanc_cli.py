"""CLI-level plumbing tests for `accessionflow collate orthanc`.

stage_studies is mocked here (its behaviour, including the
to_process_label/processed_label filtering, is covered directly against a
faked Orthanc REST API in test_orthanc_staging.py) -- this just
checks that the "collate orthanc" command actually runs and passes the CLI options
through to the api/model layers unchanged.

This command used to crash unconditionally: cli/collate.py called
`collate_orthanc(..., wait_period=wait_period)` but api/collate_.py's
collate_orthanc() has no `wait_period` parameter, so every invocation raised
`TypeError: collate_orthanc() got an unexpected keyword argument
'wait_period'` before any Orthanc/network code ran. There was no test
coverage of this command at all, which is how it went unnoticed.
"""

import typing as ty
from pathlib import Path
from unittest.mock import patch

from fileformats.medimage import DicomSeries, NiftiGzX

from accessionflow.sources.orthanc.cli import collate_cmd as collate_orthanc_cmd
from conftest import show_cli_trace


def test_collate_orthanc_cli_runs_and_passes_labels_through(
    cli_runner: ty.Any, tmp_path: Path
) -> None:
    store_dir = tmp_path / "orthanc-store"
    store_dir.mkdir()
    output_dir = tmp_path / "staged"

    with patch(
        "accessionflow.sources.orthanc.api.collate_api.stage_studies", return_value=[]
    ) as mock_stage_studies:
        result = cli_runner(
            collate_orthanc_cmd,
            [
                "http://orthanc.example.org:8042",
                str(store_dir),
                str(output_dir),
                "orthanc-user",
                "orthanc-pass",
                "--to-process-label",
                "ready-for-xnat",
                "--processed-label",
                "sent-to-xnat",
                "--wait-period",
                "300",
            ],
        )

    assert result.exit_code == 0, show_cli_trace(result)
    assert mock_stage_studies.call_count == 1
    _, kwargs = mock_stage_studies.call_args
    assert kwargs["to_process_label"] == "ready-for-xnat"
    assert kwargs["processed_label"] == "sent-to-xnat"
    assert kwargs["wait_period"] == 300


def test_collate_orthanc_cli_defaults_to_no_to_process_label(
    cli_runner: ty.Any, tmp_path: Path
) -> None:
    """Without --to-process-label, every non-processed study is a
    candidate -- stage_studies must be called with to_process_label=None
    rather than the option being silently dropped or defaulted wrong."""
    store_dir = tmp_path / "orthanc-store"
    store_dir.mkdir()
    output_dir = tmp_path / "staged"

    with patch(
        "accessionflow.sources.orthanc.api.collate_api.stage_studies", return_value=[]
    ) as mock_stage_studies:
        result = cli_runner(
            collate_orthanc_cmd,
            [
                "http://orthanc.example.org:8042",
                str(store_dir),
                str(output_dir),
                "orthanc-user",
                "orthanc-pass",
            ],
        )

    assert result.exit_code == 0, show_cli_trace(result)
    _, kwargs = mock_stage_studies.call_args
    assert kwargs["to_process_label"] is None


def test_collate_orthanc_cli_passes_conversions_through(
    cli_runner: ty.Any, tmp_path: Path
) -> None:
    store_dir = tmp_path / "orthanc-store"
    store_dir.mkdir()
    output_dir = tmp_path / "staged"

    with patch(
        "accessionflow.sources.orthanc.api.collate_api.stage_studies", return_value=[]
    ) as mock_stage_studies:
        result = cli_runner(
            collate_orthanc_cmd,
            [
                "http://orthanc.example.org:8042",
                str(store_dir),
                str(output_dir),
                "orthanc-user",
                "orthanc-pass",
                "--convert",
                "medimage/dicom-series",
                "medimage/nifti-gz-x:compress=y",
            ],
        )

    assert result.exit_code == 0, show_cli_trace(result)
    _, kwargs = mock_stage_studies.call_args
    assert kwargs["conversion_map"] == {DicomSeries: (NiftiGzX, {"compress": "y"})}
