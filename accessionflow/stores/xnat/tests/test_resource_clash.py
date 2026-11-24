"""--on-resource-clash of the XNAT store.

An upload of the missing files cannot repair a package on XNAT (for example a
zip of a series). When a late series makes the package stage build the zip
again, the new zip has the same name and other content. With "merge", the
default, the store stage logs the difference and skips the resource as
uploaded. With "error" it changes nothing on XNAT, and the session is not
reported as uploaded. An operator deletes the old resource on XNAT, and the
next pass uploads the new one.
"""

import logging
import typing as ty
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fileformats.application import Zip
from fileformats.generic import FileSet
from fileformats.medimage import DicomSeries

from accessionflow.exceptions import IncompleteCheckumsException
from accessionflow.helpers.arg_types import ClashSpec
from accessionflow.stores.xnat.api.store_api import store
from accessionflow.stores.xnat.cli import store_cmd
from accessionflow.stores.xnat.remotes import get_xnat_resource, resource_clash_policy
from conftest import show_cli_trace

PACKAGES_NEED_AN_OPERATOR = (
    ClashSpec("merge", "medimage/dicom-series"),
    ClashSpec("error", "all"),
)


class FakeResourceOnXnat:
    """The resource XNAT already holds."""


class FakeScan:
    def __init__(self, resources: dict[str, ty.Any]) -> None:
        self.resources = resources
        self.files = ["something"]  # non-empty: skip the catalog-refresh branch


class FakeXnatSession:
    label = "SESS"

    def __init__(self, scan_resources: dict[str, ty.Any]) -> None:
        self.scans = {"2": FakeScan(scan_resources)}
        self.resources = dict(scan_resources)
        self.xnat_session = MagicMock()


class FakeStagedScan:
    id = "2"
    path = "test_project:SUBJ:SESS:2-t1_mprage_ax"


class FakeStagedResource:
    """The resource as staged: a zip made by the package stage."""

    name = "DICOM-zip"
    metadata: dict[str, object] = {}

    def __init__(
        self, fileset: FileSet, checksums: dict[str, str], scan: bool = True
    ) -> None:
        self.fileset = fileset
        self.checksums = checksums
        self.acquisition = FakeStagedScan() if scan else None
        self.path = (
            f"{FakeStagedScan.path}:{self.name}" if scan else f"SESS:{self.name}"
        )


@pytest.fixture
def zip_fileset(tmp_path: Path) -> Zip:
    fspath = tmp_path / "series.zip"
    with zipfile.ZipFile(fspath, "w") as zf:
        zf.writestr("1.dcm", b"dicom")
    return Zip(fspath)


def _call(
    fileset: FileSet,
    staged: dict[str, str],
    on_xnat: dict[str, str],
    specs: ty.Sequence[ClashSpec] = (),
    scan: bool = True,
) -> ty.Any:
    resource = FakeStagedResource(fileset, staged, scan=scan)
    xsession = FakeXnatSession({"DICOM-zip": FakeResourceOnXnat()})
    with patch(
        "accessionflow.stores.xnat.remotes.get_xnat_checksums", return_value=on_xnat
    ):
        return get_xnat_resource(resource, xsession, specs)


def test_policy_is_the_first_spec_that_covers_the_datatype(zip_fileset: Zip) -> None:
    resource = FakeStagedResource(zip_fileset, {})
    assert resource_clash_policy((), resource) == "merge"
    assert resource_clash_policy(PACKAGES_NEED_AN_OPERATOR, resource) == "error"
    assert (
        resource_clash_policy([ClashSpec("merge", "application/zip")], resource)
        == "merge"
    )
    # Not covered by any spec: a person decides.
    assert (
        resource_clash_policy([ClashSpec("merge", "medimage/dicom-series")], resource)
        == "error"
    )


def test_changed_zip_with_error_policy_raises(zip_fileset: Zip) -> None:
    """THE CASE: the zip made again with a late series has other content."""
    with pytest.raises(IncompleteCheckumsException) as excinfo:
        _call(
            zip_fileset,
            {"series.zip": "new"},
            {"series.zip": "old"},
            PACKAGES_NEED_AN_OPERATOR,
        )
    msg = excinfo.value.msg
    assert "1 different file(s)" in msg, msg
    assert "Delete the resource on XNAT" in msg, msg


def test_changed_zip_with_default_policy_is_skipped_as_before(
    zip_fileset: Zip,
) -> None:
    assert _call(zip_fileset, {"series.zip": "new"}, {"series.zip": "old"}) == (
        None,
        None,
    )


def test_error_policy_does_not_repair_a_short_resource(zip_fileset: Zip) -> None:
    staged = {"a.zip": "1", "b.zip": "2"}
    on_xnat = {"a.zip": "1"}
    xresource, only_files = _call(zip_fileset, staged, on_xnat)  # merge
    assert only_files == {"b.zip"}
    with pytest.raises(IncompleteCheckumsException):
        _call(zip_fileset, staged, on_xnat, PACKAGES_NEED_AN_OPERATOR)


def test_identical_resource_with_error_policy_is_skipped(zip_fileset: Zip) -> None:
    staged = {"series.zip": "same"}
    assert _call(zip_fileset, staged, dict(staged), PACKAGES_NEED_AN_OPERATOR) == (
        None,
        None,
    )


def test_session_resource_with_error_policy_raises(zip_fileset: Zip) -> None:
    with pytest.raises(IncompleteCheckumsException):
        _call(
            zip_fileset,
            {"series.zip": "new"},
            {"series.zip": "old"},
            PACKAGES_NEED_AN_OPERATOR,
            scan=False,
        )


def test_clash_log_line_carries_an_event(
    zip_fileset: Zip, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="accessionflow"):
        with pytest.raises(IncompleteCheckumsException):
            _call(
                zip_fileset,
                {"series.zip": "new"},
                {"series.zip": "old"},
                PACKAGES_NEED_AN_OPERATOR,
            )
    (record,) = [r for r in caplog.records if hasattr(r, "event")]
    assert record.event == "xnat_resource_clash"
    assert record.policy == "error"
    assert record.resource.endswith(":DICOM-zip")
    assert "already exists on XNAT with different checksums" in record.getMessage()


def test_store_refuses_the_policies_it_does_not_support() -> None:
    for policy in ("avoid", "overwrite"):
        with pytest.raises(ValueError, match="'merge' and 'error'"):
            store("/staged", MagicMock(), on_resource_clash=[ClashSpec(policy, "all")])


@pytest.mark.parametrize(
    "flags, env_value, expected",
    [
        ([], None, []),
        (
            [
                "--on-resource-clash",
                "merge",
                "medimage/dicom-series",
                "--on-resource-clash",
                "error",
                "all",
            ],
            None,
            [("merge", DicomSeries), ("error", FileSet)],
        ),
        ([], "error all", [("error", FileSet)]),
    ],
)
def test_store_xnat_passes_on_resource_clash(
    cli_runner: ty.Any,
    flags: list[str],
    env_value: ty.Optional[str],
    expected: list[tuple[str, type]],
) -> None:
    with (
        patch("accessionflow.stores.xnat.cli.store_cli.Xnat") as mock_xnat_cls,
        patch("accessionflow.stores.xnat.cli.store_cli.store") as mock_store,
    ):
        mock_xnat_cls.return_value = MagicMock()
        mock_store.return_value = []
        result = cli_runner(
            store_cmd,
            ["/staged", "https://xnat.example.org", "--user", "u", "--password", "p"]
            + flags,
            env={
                "ACFLOW_ON_RESOURCE_CLASH": env_value,
                "ACFLOW_HOST": None,
                "ACFLOW_USER": None,
                "ACFLOW_PASS": None,
                "ACFLOW_LOOP": None,
            },
        )
    assert result.exit_code == 0, show_cli_trace(result)
    specs = mock_store.call_args.kwargs["on_resource_clash"]
    assert [(s.policy, s.scope) for s in specs] == expected
