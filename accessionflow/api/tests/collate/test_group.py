from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fileformats.application import Json
from fileformats.core import FileSet
from fileformats.generic import DirectoryOf, File
from fileformats.medimage import DicomSeries
from fileformats.text import Csv

from accessionflow.api.collate import (
    ClaimedFiles,
    acquisition_id_for,
    apply_path_metadata,
    claim_input_files,
    clash_hint_for,
    classify_paths,
    drop_ignored_filesets,
    expand_claimed_paths,
    group_into_accessions,
    plan_recursion,
    resource_label_for,
    tag_fileset_types,
)
from accessionflow.helpers.arg_types import IDSpec, PathMetadataRegex
from accessionflow.model.accession import (
    _datatype_resource_label,
    dicom_image_type_to_resource_label,
)

RUN_UID = "abc12320261124010203"


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
    claimed: ClaimedFiles = claim_input_files(
        paths, tmp_path / "proc", RUN_UID, [inbox]
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


def test_steps_7_to_14_like_from_paths_datatype_field(tmp_path: Path) -> None:
    """Mirrors model/tests/test_accession.py::
    test_from_paths_injects_datatype_metadata_field"""
    filesets = _filesets(
        tmp_path,
        {"src/a.txt": "x"},
        [File],
        [PathMetadataRegex(r".*/(?P<sess>[^/]+)\.txt", File)],
    )
    (accession,) = group_into_accessions(
        filesets,
        [IDSpec("sess")],
        [IDSpec("sess")],
        [IDSpec("res_{__datatype__}")],
    )
    acquisition = next(iter(accession.acquisitions.values()))
    assert list(acquisition.resources) == ["res_File"]
    resource = next(iter(acquisition.resources.values()))
    assert resource.fileset.metadata["__datatype__"] == "File"


def test_steps_7_to_14_like_from_paths_recursive(tmp_path: Path) -> None:
    """Mirrors model/tests/test_accession.py::
    test_from_paths_recursive_pulls_nested_directory_datatype"""
    from fileformats.text import Plain

    filesets = _filesets(
        tmp_path,
        {
            "analysis/result.json": "{}",
            "analysis/notes.txt": "inside the wanted dir",
            "lesion/data.csv": "a,b\n1,2\n",
            "plain/deep/result.json": "{}",
            "scan.txt": "a loose file",
        },
        [DirectoryOf[Json]],
        [PathMetadataRegex(r".*/(?P<name>[^/]+)$", DirectoryOf[Json])],
        ignore_datatypes=[DirectoryOf[Csv], Plain],
        recursive=True,
    )
    (accession,) = group_into_accessions(
        filesets,
        [IDSpec("__datatype__")],
        [IDSpec("name")],
        [IDSpec("name")],
    )
    assert set(accession.acquisitions) == {"analysis", "deep"}
