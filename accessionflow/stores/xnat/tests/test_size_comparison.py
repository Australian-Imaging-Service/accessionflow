"""A file that XNAT lists without a checksum is compared by size as well as name.

Some XNAT instances keep no checksums: each row of a file listing has a "Size"
and an empty "digest". A package made again with a late series (for example a
zip) keeps its name. With a comparison by name only, the old zip on XNAT looked
complete. Each pass skipped the session as uploaded, and --on-resource-clash
did not see the clash.
"""

import logging
import typing as ty
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fileformats.application import Zip

from accessionflow.exceptions import IncompleteCheckumsException
from accessionflow.stores.xnat import remotes
from accessionflow.stores.xnat.api import store_api
from accessionflow.stores.xnat.remotes import (
    XnatChecksums,
    XnatLocalSessionListing,
    XnatS3SessionListing,
    _files_held_in,
    compare_resource_with_xnat,
    get_xnat_checksums_at,
    get_xnat_resource,
)
from accessionflow.stores.xnat.tests.test_all_uploaded_completeness import (
    FakeResponse,
    FakeXnat,
)
from accessionflow.stores.xnat.tests.test_resource_clash import (
    PACKAGES_NEED_AN_OPERATOR,
    FakeStagedResource,
    FakeXnatSession,
)
from accessionflow.stores.xnat.tests.test_upload_repair_completed_event import (
    FakeExperiment,
    FakeRepo,
)

RESOURCE_PATH = "1.scan_one/DICOM-zip"


@pytest.fixture(autouse=True)
def report_checksum_support_again(monkeypatch: pytest.MonkeyPatch) -> None:
    # The first file listing sets this for the process. Keep it in this test.
    monkeypatch.setattr(remotes, "_xnat_has_checksums", None, raising=False)


def _listing_rows(files_uri: str, size: int) -> dict[str, ty.Any]:
    """A file listing from an XNAT that keeps no checksums."""
    row = {
        "Name": "series.zip",
        "URI": f"{files_uri}/series.zip",
        "Size": str(size),
        "digest": "",
    }
    return {"ResultSet": {"Result": [row]}}


def _on_xnat(size: int) -> XnatChecksums:
    checksums = XnatChecksums()
    checksums["series.zip"] = ""
    checksums.sizes["series.zip"] = size
    return checksums


def _staged_zip(tmp_path: Path) -> Zip:
    fspath = tmp_path / "series.zip"
    with zipfile.ZipFile(fspath, "w") as zf:
        zf.writestr("1.dcm", b"first part")
        zf.writestr("2.dcm", b"late series")
    return Zip(fspath)


def test_the_file_listing_keeps_the_sizes() -> None:
    files_uri = "/data/experiments/E1/scans/1/resources/7/files"
    rows = _listing_rows(files_uri, 120)
    rows["ResultSet"]["Result"].append(
        {"Name": "b.dcm", "URI": f"{files_uri}/b.dcm", "Size": "", "digest": ""}
    )
    connection = SimpleNamespace(get=lambda uri: FakeResponse(rows))
    checksums = get_xnat_checksums_at(connection, files_uri)
    assert checksums == {"series.zip": "", "b.dcm": ""}
    assert checksums.sizes == {"series.zip": 120}


def test_another_size_without_a_checksum_differs() -> None:
    comparison = compare_resource_with_xnat(
        {"series.zip": "new"}, _on_xnat(100), {"series.zip": 150}
    )
    assert comparison.differing == {"series.zip"}
    assert not comparison.complete
    assert not comparison.repairable


def test_the_same_size_without_a_checksum_is_complete() -> None:
    comparison = compare_resource_with_xnat(
        {"series.zip": "new"}, _on_xnat(150), {"series.zip": 150}
    )
    assert comparison.complete
    assert comparison.without_checksums == {"series.zip"}


def test_a_checksum_decides_before_a_size() -> None:
    on_xnat = _on_xnat(100)
    on_xnat["series.zip"] = "new"
    assert compare_resource_with_xnat(
        {"series.zip": "new"}, on_xnat, {"series.zip": 150}
    ).complete


def test_without_sizes_the_name_decides() -> None:
    assert compare_resource_with_xnat(
        {"series.zip": "new"}, {"series.zip": ""}
    ).complete
    assert compare_resource_with_xnat({"series.zip": "new"}, _on_xnat(100)).complete


@pytest.mark.parametrize(
    "digest, local_size, held",
    [("", 150, False), ("", 100, True), ("", None, True), ("new", 150, True)],
)
def test_the_match_across_resources_compares_sizes(
    digest: str, local_size: int | None, held: bool
) -> None:
    on_xnat = _on_xnat(100)
    on_xnat["series.zip"] = digest
    sizes = {} if local_size is None else {"series.zip": local_size}
    assert _files_held_in({"series.zip": "new"}, [on_xnat], sizes) is held


def test_the_s3_listing_reads_the_sizes_from_the_bucket_listing(
    tmp_path: Path,
) -> None:
    def obj(size: int) -> SimpleNamespace:
        return SimpleNamespace(key="k", size=size)

    # bucket=None: a download would fail
    listing = XnatS3SessionListing(
        name="proj.subj.sess",
        objects=[
            (["1.scan_one", "DICOM-zip", "series.zip"], obj(150)),
            (["1.scan_one", "DICOM-zip", "sub", "a.txt"], obj(9)),
            (["1.scan_one", "DICOM-zip-2", "other.zip"], obj(5)),
            (["2.scan_two", "DICOM-zip", "other.zip"], obj(5)),
        ],
        bucket=None,
        cache_path=tmp_path,
    )
    assert listing.resource_file_sizes(RESOURCE_PATH) == {
        "series.zip": 150,
        "sub/a.txt": 9,
    }


def test_the_local_listing_reads_the_sizes_from_the_files(tmp_path: Path) -> None:
    resource_dir = tmp_path / "proj.subj.sess" / RESOURCE_PATH
    (resource_dir / "sub").mkdir(parents=True)
    (resource_dir / "series.zip").write_bytes(b"x" * 150)
    (resource_dir / "sub" / "a.txt").write_bytes(b"x" * 9)
    listing = XnatLocalSessionListing(fspath=tmp_path / "proj.subj.sess")
    assert listing.resource_file_sizes(RESOURCE_PATH) == {
        "series.zip": 150,
        "sub/a.txt": 9,
    }


class FakeXnatWithoutChecksums(FakeXnat):
    """FakeXnat, with a size in each file row and no digest."""

    def __init__(self, size: int, scan_type: str = "scan_one") -> None:
        super().__init__([("1", scan_type, {"DICOM-zip": {"series.zip": ""}})])
        self.size = size

    def get(self, uri: str, format: ty.Any = None, **kwargs: ty.Any) -> FakeResponse:
        response = super().get(uri, format=format, **kwargs)
        if format != "json":
            for row in response.json()["ResultSet"]["Result"]:
                row["Size"] = str(self.size)
        return response


@pytest.mark.parametrize("size_on_xnat, uploaded", [(100, False), (150, True)])
@pytest.mark.parametrize("scan_type", ["scan_one", "another_type"])
def test_all_uploaded_sees_a_changed_zip_without_checksums(
    tmp_path: Path, size_on_xnat: int, uploaded: bool, scan_type: str
) -> None:
    """The staged zip has 150 bytes. The old zip on XNAT has 100. With another
    scan type on XNAT, the staged path does not match, and the files are found
    by name in the resources of scan 1."""

    class Listing(XnatS3SessionListing):
        @property
        def resource_manifests(self) -> ty.Dict[str, ty.Dict[str, ty.Any]]:
            return {RESOURCE_PATH: {"checksums": {"series.zip": "new"}}}

    listing = Listing(
        name="proj.subj.sess",
        objects=[
            (
                ["1.scan_one", "DICOM-zip", "series.zip"],
                SimpleNamespace(key="k", size=150),
            )
        ],
        bucket=None,
        cache_path=tmp_path,
    )
    xnat = FakeXnatWithoutChecksums(size_on_xnat, scan_type)
    assert listing.all_uploaded(xnat) is uploaded


class FakeResourceWithoutChecksums:
    """A resource on an XNAT that keeps no checksums."""

    uri = "/data/experiments/E1/scans/2/resources/7"
    id = "7"

    def __init__(self, size: int) -> None:
        rows = _listing_rows(self.uri + "/files", size)
        self.xnat_session = SimpleNamespace(get=lambda uri: FakeResponse(rows))


def _get_xnat_resource(
    tmp_path: Path, size_change: int, specs: ty.Any, scan: bool = True
) -> ty.Any:
    fileset = _staged_zip(tmp_path)
    size_on_xnat = fileset.fspath.stat().st_size + size_change
    resource = FakeStagedResource(fileset, {"series.zip": "new"}, scan=scan)
    xsession = FakeXnatSession(
        {"DICOM-zip": FakeResourceWithoutChecksums(size_on_xnat)}
    )
    return get_xnat_resource(resource, xsession, on_resource_clash=specs)


@pytest.mark.parametrize("scan", [True, False])
def test_a_smaller_zip_on_xnat_without_checksums_is_a_clash(
    tmp_path: Path, scan: bool
) -> None:
    with pytest.raises(IncompleteCheckumsException, match="1 different file"):
        _get_xnat_resource(tmp_path, -40, PACKAGES_NEED_AN_OPERATOR, scan=scan)


@pytest.mark.parametrize("scan", [True, False])
def test_the_same_size_without_checksums_is_uploaded(
    tmp_path: Path, scan: bool
) -> None:
    result = _get_xnat_resource(tmp_path, 0, PACKAGES_NEED_AN_OPERATOR, scan=scan)
    assert result == (None, None)


def test_with_the_default_policy_the_size_change_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="accessionflow"):
        assert _get_xnat_resource(tmp_path, -40, ()) == (None, None)
    assert "already exists on XNAT with different checksums" in caplog.text
    assert "Differing paths: ['series.zip']" in caplog.text


class FakeXResourceWithAnOldCopy:
    """XNAT answers the upload, but it keeps an old copy of another size."""

    def upload(self, *args: ty.Any, **kwargs: ty.Any) -> None:
        pass

    def upload_dir(self, *args: ty.Any, **kwargs: ty.Any) -> None:
        pass


def test_the_check_after_upload_compares_sizes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    staging = tmp_path / "staging"
    resource_dir = staging / "proj.subj.sess" / "1.scan_one" / "DICOM-zip"
    resource_dir.mkdir(parents=True)
    _staged_zip(resource_dir)
    with (
        mock.patch.object(store_api.FrameSet, "load", side_effect=KeyError("none")),
        mock.patch.object(store_api, "get_xnat_session", return_value=FakeExperiment()),
        mock.patch.object(
            store_api,
            "get_xnat_resource",
            return_value=(FakeXResourceWithAnOldCopy(), None),
        ),
        mock.patch.object(store_api, "get_xnat_checksums", return_value=_on_xnat(100)),
        caplog.at_level(logging.INFO, logger="accessionflow"),
    ):
        errors = store_api.store(
            input_dir=str(staging),
            xnat_repo=FakeRepo(),
            always_include=["all"],
            require_manifest=False,
            check_checksums=True,
            wait_period=0,
        )
    assert errors
    assert "Successfully uploaded all files in" not in caplog.text
