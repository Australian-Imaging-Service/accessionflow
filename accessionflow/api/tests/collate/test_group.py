from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fileformats.application import Json
from fileformats.core import FileSet
from fileformats.generic import File, SetOf
from fileformats.image import Png
from fileformats.medimage import DicomSeries
from fileformats.vendor.siemens.medimage import SyngoMi_Vr20b_ListMode

from accessionflow.api.collate import (
    ClaimedFiles,
    ClaimInputFiles,
    acquisition_id_for,
    apply_path_metadata,
    clash_hint_for,
    classify_paths,
    drop_ignored_filesets,
    expand_claimed_paths,
    group_into_accessions,
    plan_recursion,
    resource_label_for,
    tag_fileset_types,
)
from accessionflow.api.collate.group import _datatype_resource_label
from accessionflow.helpers.arg_types import IDSpec, PathMetadataRegex
from accessionflow.model.accession import dicom_image_type_to_resource_label

RUN_UID = "20261124010203_abc123"


def _filesets(
    tmp_path: Path,
    files: dict[str, str],
    datatypes: list[type[FileSet]],
    path_metadata: list[PathMetadataRegex] = [],
    ignore_datatypes: list[type[FileSet]] = [],
    recursive: bool = True,
) -> list[FileSet]:
    """Claims the files, then runs the steps up to grouping on them. Recursive by
    default, so files in subdirectories are classified one by one"""
    inbox = tmp_path / "inbox"
    paths = []
    for relpath, content in files.items():
        path = inbox / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        paths.append(path)
    claimed: ClaimedFiles = ClaimInputFiles(tmp_path / "proc").act(
        paths, RUN_UID, [inbox]
    )
    plan = plan_recursion(datatypes, ignore_datatypes, recursive)
    fspaths = expand_claimed_paths(claimed, datatypes, plan, recursive)
    filesets = classify_paths(fspaths, datatypes, plan.ignore_datatypes)
    filesets = drop_ignored_filesets(filesets, datatypes, plan.ignore_datatypes)
    filesets = apply_path_metadata(filesets, path_metadata, claimed)
    return tag_fileset_types(filesets)


def _dicom(metadata: dict[str, object]) -> MagicMock:
    fileset = MagicMock(spec=DicomSeries)
    fileset.contents = [MagicMock(metadata=metadata)]
    return fileset


# resource_label_for ---------------------------------------------------------------


def test_resource_label_for_dicom() -> None:
    image_type = ["ORIGINAL", "PRIMARY", "AXIAL"]
    assert resource_label_for(_dicom({"ImageType": image_type})) == (
        dicom_image_type_to_resource_label(image_type),
        False,
    )
    assert resource_label_for(_dicom({})) == ("DICOM", False)


def test_resource_label_for_derived_from_type(tmp_path: Path) -> None:
    (fileset,) = _filesets(tmp_path, {"a.json": "{}"}, [Json])
    assert resource_label_for(fileset) == (_datatype_resource_label(Json), True)
    assert resource_label_for(fileset) == ("json", True)


@pytest.mark.parametrize(
    "datatype, expected",
    [
        (DicomSeries, "dicom-series"),
        (SyngoMi_Vr20b_ListMode, "syngo-mi_vr20b_list-mode"),
        (SetOf[Png], "png_set-of"),
        (File, "file"),
    ],
)
def test_datatype_resource_label(datatype: type[FileSet], expected: str) -> None:
    assert _datatype_resource_label(datatype) == expected


def test_resource_label_for_from_spec(tmp_path: Path) -> None:
    (fileset,) = _filesets(tmp_path, {"a.txt": "x"}, [File])
    assert resource_label_for(fileset, [IDSpec("res_{__datatype__}")]) == (
        "res_File",
        False,
    )


# acquisition_id_for ---------------------------------------------------------------


def test_acquisition_id_for(tmp_path: Path) -> None:
    (fileset,) = _filesets(
        tmp_path,
        {"a.json": "{}"},
        [Json],
        [PathMetadataRegex(r".*/(?P<name>[^/]+)\.json$", Json)],
    )
    assert acquisition_id_for(fileset, [IDSpec("name")], "json") == ("a", False)
    # A spec for another datatype doesn't apply, so the resource's label is used
    assert acquisition_id_for(
        fileset, [IDSpec("SeriesNumber", "medimage/dicom-series")], "json"
    ) == ("json", True)


# clash_hint_for -------------------------------------------------------------------


def test_clash_hint_for() -> None:
    assert clash_hint_for(False, False) is None
    acquisition = clash_hint_for(True, False)
    assert acquisition is not None
    assert "--acquisition" in acquisition and "--resource" not in acquisition
    resource = clash_hint_for(False, True)
    assert resource is not None
    assert "--resource" in resource and "--acquisition" not in resource
    both = clash_hint_for(True, True)
    assert both is not None and "--acquisition and --resource" in both


# group_into_accessions ------------------------------------------------------------

SESS_AND_NAME = [
    PathMetadataRegex(r".*/(?P<sess>[^/]+)/(?P<name>[^/]+)\.json$", Json),
]


def test_group_into_accessions(tmp_path: Path) -> None:
    filesets = _filesets(
        tmp_path,
        {"s1/a.json": '{"a": 1}', "s1/b.json": '{"b": 1}', "s2/a.json": '{"a": 2}'},
        [Json],
        SESS_AND_NAME,
    )
    accessions = group_into_accessions(
        filesets,
        [IDSpec("sess")],
        [IDSpec("name")],
        run_uid=RUN_UID,
    )
    assert [a.uid for a in accessions] == ["s1", "s2"]
    assert all(a.run_uid == RUN_UID for a in accessions)
    assert sorted(accessions[0].acquisitions) == ["a", "b"]
    assert list(accessions[1].acquisitions) == ["a"]
    assert list(accessions[0].acquisitions["a"].resources) == ["json"]


def test_group_into_accessions_derives_acquisition_from_resource(
    tmp_path: Path,
) -> None:
    filesets = _filesets(tmp_path, {"s1/a.json": "{}"}, [Json], SESS_AND_NAME)
    (accession,) = group_into_accessions(filesets, [IDSpec("sess")])
    assert list(accession.acquisitions) == ["json"]
    assert list(accession.acquisitions["json"].resources) == ["json"]


def test_group_into_accessions_clash(tmp_path: Path) -> None:
    files = {"s1/a.json": '{"a": 1}', "s1/b.json": '{"b": 2}'}
    filesets = _filesets(tmp_path, files, [Json], SESS_AND_NAME)
    with pytest.raises(KeyError, match="auto-derived from its fileset type"):
        group_into_accessions(filesets, [IDSpec("sess")])

    filesets = _filesets(tmp_path / "again", files, [Json], SESS_AND_NAME)
    (accession,) = group_into_accessions(
        filesets, [IDSpec("sess")], on_resource_clash="avoid"
    )
    assert sorted(accession.acquisitions["json"].resources) == ["json", "json__2"]


def test_group_into_accessions_no_matching_accession_spec(tmp_path: Path) -> None:
    filesets = _filesets(tmp_path, {"a.json": "{}"}, [Json])
    with pytest.raises(TypeError):
        # The only spec is scoped to CSV files
        group_into_accessions(filesets, [IDSpec("sess", "text/csv")])
