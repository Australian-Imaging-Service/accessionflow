import functools
import hashlib
import json
import logging
import os
import typing as ty
from pathlib import Path

import pydicom
import pytest
import yaml
from fileformats.application import Json
from fileformats.core import FileSet, Loaded, extra_implementation, from_mime
from fileformats.generic import File, SetOf
from fileformats.image import Png
from fileformats.medimage import DicomSeries, MedicalImagingData
from fileformats.vendor.siemens.medimage import (
    SyngoMi_Vr20b_CountRate,
    SyngoMi_Vr20b_ListMode,
    SyngoMi_Vr20b_RawData,
)
from frametree.common import FileSystem  # type: ignore[import-untyped]
from frametree.core.frameset import FrameSet  # type: ignore[import-untyped]
from medimages4tests.dummy.dicom.ct.ac.siemens.biograph_vision.vr20b import (
    get_image as get_ac_image,
)  # type: ignore[import-untyped]
from medimages4tests.dummy.dicom.pet.statistics.siemens.biograph_vision.vr20b import (
    get_image as get_statistics_image,
)  # type: ignore[import-untyped]
from medimages4tests.dummy.dicom.pet.topogram.siemens.biograph_vision.vr20b import (
    get_image as get_topogram_image,
)  # type: ignore[import-untyped]
from medimages4tests.dummy.dicom.pet.wholebody.siemens.biograph_vision.vr20b import (
    get_image as get_pet_image,
)  # type: ignore[import-untyped]

from accessionflow.helpers.arg_types import (
    AttachedFiles,
    ClashSpec,
    IDSpec,
    PathMetadataRegex,
)
from accessionflow.helpers.metadata import Metadata
from accessionflow.model.accession import (
    Accession,
    Acquisition,
    _datatype_resource_label,
    _load_recipe,
    _metadata_diff,
)
from accessionflow.model.mock_store import DummyAxes
from conftest import get_raw_data_files

FIRST_NAME = "Given Name"
LAST_NAME = "FamilyName"

DICOM_COLUMNS: ty.List[ty.Tuple[str, str, str]] = [
    ("pet", "medimage/dicom-series", "PET SWB 8MIN"),
    ("topogram", "medimage/dicom-series", "Topogram.*"),
    ("atten_corr", "medimage/dicom-series", "AC CT.*"),
]

RAW_COLUMNS: ty.List[ty.Tuple[str, str, str]] = [
    (
        "listmode",
        "medimage/vnd.siemens.syngo-mi.vr20b.list-mode",
        ".*/PET_LISTMODE",
    ),
    # (
    #     "sinogram",
    #     "medimage/vnd.siemens.syngo-mi.vr20b.sinogram",
    #     ".*/PET_EM_SINO",
    # ),
    (
        "countrate",
        "medimage/vnd.siemens.syngo-mi.vr20b.count-rate",
        ".*/PET_COUNTRATE",
    ),
]


@pytest.fixture
def imaging_session() -> Accession:
    dicoms = [
        DicomSeries(d.iterdir())
        for d in (
            get_pet_image(
                first_name=FIRST_NAME,
                last_name=LAST_NAME,
            ),
            get_ac_image(
                first_name=FIRST_NAME,
                last_name=LAST_NAME,
            ),
            get_topogram_image(
                first_name=FIRST_NAME,
                last_name=LAST_NAME,
            ),
            get_statistics_image(
                first_name=FIRST_NAME,
                last_name=LAST_NAME,
            ),
        )
    ]
    scans = [
        Acquisition(
            id=str(d.metadata["SeriesNumber"]),
            type=str(d.metadata["SeriesDescription"]),
            resources={"DICOM": d},
        )
        for d in dicoms
    ]
    return Accession(
        uid="12345",
        labels={"project": "PROJECTID", "subject": "SUBJECTID", "session": "SESSIONID"},
        acquisitions=scans,
    )


@pytest.fixture
def dataset(tmp_path: Path) -> FrameSet:
    """For use in tests, this method creates a test dataset from the provided
    blueprint

    Parameters
    ----------
    store: DataStore
        the store to make the dataset within
    dataset_id : str
        the ID of the project/directory within the store to create the dataset
    name : str, optional
        the name to give the dataset. If provided the dataset is also saved in the
        datastore
    source_data : Path, optional
        path to a directory containing source data to use instead of the dummy
        data
    **kwargs
        passed through to create_dataset
    """
    dataset_path = tmp_path / "a-dataset"
    store = FileSystem()
    dataset = store.create_dataset(
        id=dataset_path,
        leaves=[],
        hierarchy=[],
        axes=DummyAxes,
    )
    for col_name, col_type, col_pattern in DICOM_COLUMNS + RAW_COLUMNS:
        dataset.add_source(col_name, from_mime(col_type), col_pattern, is_regex=True)
    return dataset


@pytest.fixture
def raw_frameset(tmp_path: Path) -> FrameSet:
    """For use in tests, this method creates a test dataset from the provided
    blueprint

    Parameters
    ----------
    store: DataStore
        the store to make the dataset within
    dataset_id : str
        the ID of the project/directory within the store to create the dataset
    name : str, optional
        the name to give the dataset. If provided the dataset is also saved in the
        datastore
    source_data : Path, optional
        path to a directory containing source data to use instead of the dummy
        data
    **kwargs
        passed through to create_dataset
    """
    dataset_path = tmp_path / "a-dataset"
    store = FileSystem()
    dataset = store.create_dataset(
        id=dataset_path,
        leaves=[],
        hierarchy=[],
        axes=DummyAxes,
    )
    for col_name, col_type, col_pattern in RAW_COLUMNS:
        dataset.add_source(col_name, from_mime(col_type), col_pattern, is_regex=True)
    return dataset


# @pytest.mark.xfail(
#     condition=platform.system() == "Linux", reason="Not working on ubuntu"
# )
def test_session_select_resources(
    imaging_session: Accession, dataset: FrameSet, tmp_path: Path
) -> None:

    assoc_dir = tmp_path / "assoc"
    assoc_dir.mkdir()

    get_raw_data_files(
        out_dir=assoc_dir, first_name=FIRST_NAME.replace(" ", "_"), last_name=LAST_NAME
    )

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    imaging_session.attach_files(
        patterns=[
            AttachedFiles(
                SyngoMi_Vr20b_RawData,
                str(assoc_dir)
                + "/{PatientName.family_name}_{PatientName.given_name}*.ptd",
                r".*/[^\.]+.[^\.]+.[^\.]+.(?P<id>\d+)\.(?P<resource>[^\.]+).*",
            )
        ],
        spaces_to_underscores=True,
    )

    saved_session, saved_dir = imaging_session.save(staging_dir)

    resources_iter = saved_session.select_resources(dataset)
    resources = list(resources_iter)

    assert len(resources) == 5  # 6
    assert set([r.acquisition.id for r in resources]) == set(
        ("1", "2", "4", "602")
    )  # , "603"))
    assert set([r.acquisition.type for r in resources]) == set(
        [
            "AC CT 30  SWB HD_FoV",
            "PET SWB 8MIN",
            "Topogram 06 Tr60",
            "602",
            # "603",
        ]
    )
    assert set([r.name for r in resources]) == set(
        ("DICOM", "PET_LISTMODE", "PET_COUNTRATE")
    )  # , "PET_EM_SINO"
    assert set([r.datatype for r in resources]) == set(
        [
            DicomSeries,
            SyngoMi_Vr20b_ListMode,
            SyngoMi_Vr20b_CountRate,
            # SyngoMi_Vr20b_Sinogram,
        ]
    )


def test_session_save_roundtrip(tmp_path: Path, imaging_session: Accession) -> None:

    # Save imaging sessions to a temporary directory
    saved, _ = imaging_session.save(tmp_path)
    assert saved is not imaging_session

    # Calculate where the session should have been saved to
    session_dir = tmp_path.joinpath(*imaging_session.staging_relpath)
    reloaded = Accession.load(session_dir)

    # Check that reloaded session matches saved session, should match the original just
    # the paths should be different
    assert reloaded == saved

    # Save again to the same location (files shouldn't be overwritten)
    reloaded.save(tmp_path)
    rereloaded = Accession.load(session_dir)
    assert rereloaded == saved

    # # Load from saved directory, this time only using directory structure instead of
    # # manifest. Should be the same with the exception of the detected fileformats
    # loaded_no_manifest = Accession.load(session_dir, require_manifest=False)
    # for scan in loaded_no_manifest.acquisitions.values():
    #     for key, resource in list(scan.resources.items()):
    #         if key == "DICOM":
    #             assert isinstance(resource, FileSet)
    #             scan.resources[key] = DicomSeries(resource)
    # assert loaded_no_manifest == saved


def test_unlink_keep_metadata(tmp_path: Path, imaging_session: Accession) -> None:
    """unlink(keep_metadata=True) should remove resource directories in their
    entirety, while leaving the scan/session-level metadata behind so the session
    can still be reloaded (e.g. by 'attach' to work out which scan a
    late-arriving file belongs to) without its underlying data"""

    # Force each scan's metadata to be read from its resources before saving, as
    # 'label' would do in production when resolving a scan description from
    # metadata — otherwise the lazily-populated Metadata objects are still empty
    # at save time and nothing meaningful ends up in '__METADATA__.json'
    for scan in imaging_session.acquisitions.values():
        assert "SeriesDescription" in scan.metadata

    saved, session_dir = imaging_session.save(tmp_path)

    # Sanity check: resource directories exist with data before unlinking, and are
    # direct children of their scan's own directory
    resource_dirs = [
        resource.fileset.parent
        for scan in saved.acquisitions.values()
        for resource in scan.resources.values()
    ]
    scan_dirs = {resource_dir.parent for resource_dir in resource_dirs}
    assert resource_dirs
    for resource_dir in resource_dirs:
        assert resource_dir.exists()
        assert any(resource_dir.iterdir())

    saved.unlink(keep_metadata=True)

    # Resource directories should be gone entirely, scan/session metadata should remain
    for resource_dir in resource_dirs:
        assert not resource_dir.exists()
    for scan_dir in scan_dirs:
        assert (scan_dir / Metadata.FNAME).exists()
    assert (session_dir / Metadata.FNAME).exists()

    # The skeleton should still be loadable, with scan-level metadata intact but no
    # resources
    reloaded = Accession.load(session_dir)
    assert reloaded.uid == saved.uid
    assert reloaded.labels["project"] == saved.labels["project"]
    for scan_id, scan in reloaded.acquisitions.items():
        assert scan.resources == {}
        assert (
            scan.metadata["SeriesDescription"]
            == imaging_session.acquisitions[scan_id].metadata["SeriesDescription"]
        )


def test_stage_raw_data_directly(raw_frameset: FrameSet, tmp_path: Path) -> None:

    raw_data_dir = tmp_path / "raw"
    raw_data_dir.mkdir()

    num_sessions = 2

    for i in range(num_sessions):
        sess_dir = raw_data_dir / str(i)
        sess_dir.mkdir()
        get_raw_data_files(
            out_dir=sess_dir,
            first_name=FIRST_NAME + str(i),
            last_name=LAST_NAME + str(i),
            StudyID=f"Study{i}",
            PatientID=f"Patient{i}",
            AccessionNumber=f"AccessionNumber{i}",
            StudyInstanceUID=f"StudyInstanceUID{i}",
        )

    imaging_sessions = Accession.from_paths(
        sorted(raw_data_dir.rglob("*.ptd")),
        datatypes=[
            SyngoMi_Vr20b_ListMode,
            SyngoMi_Vr20b_CountRate,
        ],
        accession_uid_field=[IDSpec("StudyInstanceUID")],
        acquisition_id_field=[IDSpec("SeriesNumber")],
        resource_field=[IDSpec("ImageType[2:]")],
    )

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    staged_sessions = []

    for imaging_session in imaging_sessions:
        imaging_session.label(
            label_fields={
                "project": "StudyID",
                "subject": "PatientID",
                "session": "StudyInstanceUID",
            },
            acquisition_field="SeriesDescription",
        )
        staged_sessions.append(
            imaging_session.save(
                staging_dir,
            )[0]
        )

    for staged_session in staged_sessions:
        resources = list(staged_session.select_resources(raw_frameset))

        assert len(resources) == 2
        assert set([r.acquisition.id for r in resources]) == set(["602"])
        assert set([r.acquisition.type for r in resources]) == set(["PET Raw Data"])
        assert set(r.name for r in resources) == set(("PET_LISTMODE", "PET_COUNTRATE"))
        assert set(type(r.fileset) for r in resources) == set(
            [
                SyngoMi_Vr20b_ListMode,
                SyngoMi_Vr20b_CountRate,
            ]
        )


def test_path_metadata_regex_extracts_named_groups(tmp_path: Path) -> None:
    raw_data_dir = tmp_path / "raw" / "cohort-A"
    raw_data_dir.mkdir(parents=True)
    get_pet_image(out_dir=raw_data_dir)

    sessions = Accession.from_paths(
        sorted(p for p in raw_data_dir.rglob("*") if p.is_file()),
        datatypes=[DicomSeries],
        accession_uid_field=[IDSpec("StudyInstanceUID")],
        acquisition_id_field=[IDSpec("SeriesNumber")],
        resource_field=[IDSpec("ImageType[2:]")],
        path_metadata_regex=[
            PathMetadataRegex(r".*/(?P<cohort>[^/]+)$", DicomSeries),
        ],
    )

    assert len(sessions) == 1
    scan = next(iter(sessions[0].acquisitions.values()))
    resource = next(iter(scan.resources.values()))
    assert resource.metadata["cohort"] == "cohort-A"


def test_path_metadata_regex_no_match_raises(tmp_path: Path) -> None:
    raw_data_dir = tmp_path / "raw" / "cohort-A"
    raw_data_dir.mkdir(parents=True)
    get_pet_image(out_dir=raw_data_dir)

    with pytest.raises(ValueError, match="Could not extract metadata"):
        Accession.from_paths(
            sorted(p for p in raw_data_dir.rglob("*") if p.is_file()),
            datatypes=[DicomSeries],
            accession_uid_field=[IDSpec("StudyInstanceUID")],
            acquisition_id_field=[IDSpec("SeriesNumber")],
            resource_field=[IDSpec("ImageType[2:]")],
            path_metadata_regex=[
                PathMetadataRegex(r"^/nonexistent/(?P<cohort>.+)$", DicomSeries),
            ],
        )


def test_from_paths_injects_datatype_metadata_field(tmp_path: Path) -> None:
    """The resolved fileset type name is exposed as the '__datatype__' metadata
    field and is usable from an IDSpec (including a format string)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    sessions = Accession.from_paths(
        [src / "a.txt"],
        datatypes=[File],
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("sess")],
        resource_field=[IDSpec("res_{__datatype__}")],
        path_metadata_regex=[PathMetadataRegex(r".*/(?P<sess>[^/]+)\.txt", File)],
    )

    scan = next(iter(sessions[0].acquisitions.values()))
    assert list(scan.resources) == ["res_File"]
    resource = next(iter(scan.resources.values()))
    assert resource.fileset.metadata["__datatype__"] == "File"


def test_from_paths_resource_label_defaults_to_mime_like_type_name(
    tmp_path: Path,
) -> None:
    """With no resource_field, each resource is labelled with the mime-like
    rendering of its fileset's type name ('-' kept, '.'/'+' collapsed to '_')."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    sessions = Accession.from_paths(
        [src / "a.txt"],
        datatypes=[File],
        accession_uid_field=[IDSpec("__datatype__")],
        acquisition_id_field=[IDSpec("__datatype__")],
        # resource_field omitted -> mime-like(type_name)
    )

    assert list(next(iter(sessions[0].acquisitions.values())).resources) == ["file"]


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


def test_from_paths_rejects_directory_datatypes(tmp_path: Path) -> None:
    from fileformats.application import Json
    from fileformats.generic import DirectoryOf

    (tmp_path / "a.txt").write_text("x")
    with pytest.raises(ValueError, match="Directory datatypes are not supported"):
        Accession.from_paths(
            [tmp_path / "a.txt"],
            datatypes=[DirectoryOf[Json]],
            accession_uid_field=[IDSpec("__datatype__")],
        )


def test_from_paths_rejects_directory_paths(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")
    with pytest.raises(ValueError, match="not files"):
        Accession.from_paths(
            [src],
            datatypes=[File],
            accession_uid_field=[IDSpec("__datatype__")],
        )


def test_from_paths_rejects_missing_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="do not exist"):
        Accession.from_paths(
            [tmp_path / "missing.txt"],
            datatypes=[File],
            accession_uid_field=[IDSpec("__datatype__")],
        )


def test_from_paths_scan_id_defaults_to_resource_label(tmp_path: Path) -> None:
    """With no scan_field, each resource sits in a scan of the same name."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    sessions = Accession.from_paths(
        [src / "a.txt"],
        datatypes=[File],
        accession_uid_field=[IDSpec("__datatype__")],
        # scan_field / resource_field omitted
    )

    scan = next(iter(sessions[0].acquisitions.values()))
    assert scan.id == "file"
    assert list(scan.resources) == ["file"]


def test_from_paths_datatype_scoped_scan_spec_falls_through(tmp_path: Path) -> None:
    """A datatype-scoped --acquisition-id spec that doesn't apply to a fileset's type (the
    DICOM 'SeriesNumber' default vs a plain File) names the scan after the resource
    rather than raising."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    sessions = Accession.from_paths(
        [src / "a.txt"],
        datatypes=[File],
        accession_uid_field=[IDSpec("__datatype__")],
        acquisition_id_field=[IDSpec("SeriesNumber", "medimage/dicom-collection")],
    )

    assert next(iter(sessions[0].acquisitions.values())).id == "file"


def test_from_paths_session_spec_not_matching_type_raises_clearly(
    tmp_path: Path,
) -> None:
    """The session UID has no auto-fallback: a session spec whose datatype doesn't
    apply to a fileset (the DICOM-scoped default vs a plain File) raises an
    actionable error rather than a bare 'resource label' TypeError."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    with pytest.raises(TypeError, match="apply to a File"):
        Accession.from_paths(
            [src / "a.txt"],
            datatypes=[File],
            accession_uid_field=[
                IDSpec("StudyInstanceUID", "medimage/dicom-collection")
            ],
        )


CLASH_SCAN_ID = "1"
CLASH_SCAN_TYPE = "a-type"
CLASH_RESOURCE_NAME = "FILE"


def test_clash_duplicate(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:

    logger = logging.getLogger("accessionflow")
    logger.setLevel(logging.DEBUG)

    file1 = File.sample(seed=1)
    file1_cpy = file1.copy(tmp_path / "file1")

    session = Accession(
        uid="12345",
        labels={"project": "PROJECTID", "subject": "SUBJECTID", "session": "SESSIONID"},
        acquisitions=[
            Acquisition(
                id=CLASH_SCAN_ID,
                type=CLASH_SCAN_TYPE,
                resources={CLASH_RESOURCE_NAME: file1},
            )
        ],
    )

    session.add_resource(
        scan_id=CLASH_SCAN_ID,
        scan_type=CLASH_SCAN_TYPE,
        resource_name=CLASH_RESOURCE_NAME,
        fileset=file1_cpy,
    )
    assert "as it is identical to a resource that is already present" in caplog.text


def test_clash_overwrite(caplog: pytest.LogCaptureFixture) -> None:

    logger = logging.getLogger("accessionflow")
    logger.setLevel(logging.DEBUG)

    file1 = File.sample(seed=1)
    file2 = File.sample(seed=2)

    session = Accession(
        uid="12345",
        labels={"project": "PROJECTID", "subject": "SUBJECTID", "session": "SESSIONID"},
        acquisitions=[
            Acquisition(
                id=CLASH_SCAN_ID,
                type=CLASH_SCAN_TYPE,
                resources={CLASH_RESOURCE_NAME: file1},
            )
        ],
    )

    with pytest.raises(KeyError) as exc:
        session.add_resource(
            scan_id=CLASH_SCAN_ID,
            scan_type=CLASH_SCAN_TYPE,
            resource_name=CLASH_RESOURCE_NAME,
            fileset=file2,
        )

    assert "Clash between resource names" in str(exc.value)

    session.add_resource(
        scan_id=CLASH_SCAN_ID,
        scan_type=CLASH_SCAN_TYPE,
        resource_name=CLASH_RESOURCE_NAME,
        fileset=file2,
        on_clash="overwrite",
    )
    assert "Overwriting existing resource" in caplog.text


def test_clash_avoid(caplog: pytest.LogCaptureFixture) -> None:

    logger = logging.getLogger("accessionflow")
    logger.setLevel(logging.DEBUG)

    file1 = File.sample(seed=1)
    file2 = File.sample(seed=2)

    session = Accession(
        uid="12345",
        labels={"project": "PROJECTID", "subject": "SUBJECTID", "session": "SESSIONID"},
        acquisitions=[
            Acquisition(
                id=CLASH_SCAN_ID,
                type=CLASH_SCAN_TYPE,
                resources={CLASH_RESOURCE_NAME: file1},
            )
        ],
    )

    session.add_resource(
        scan_id=CLASH_SCAN_ID,
        scan_type=CLASH_SCAN_TYPE,
        resource_name=CLASH_RESOURCE_NAME,
        fileset=file2,
        on_clash="avoid",
    )
    assert "to avoid clash with existing resources" in caplog.text
    assert sorted(session.acquisitions[CLASH_SCAN_ID].resources) == [
        CLASH_RESOURCE_NAME,
        CLASH_RESOURCE_NAME + "__2",
    ]


def _clash_session() -> Accession:
    return Accession(
        uid="12345",
        labels={"project": "PROJECTID", "subject": "SUBJECTID", "session": "SESSIONID"},
        acquisitions=[
            Acquisition(
                id=CLASH_SCAN_ID,
                type=CLASH_SCAN_TYPE,
                resources={CLASH_RESOURCE_NAME: File.sample(seed=1)},
            )
        ],
    )


def test_add_resource_clash_hint_in_error() -> None:
    with pytest.raises(KeyError, match="auto-derived from its fileset type"):
        _clash_session().add_resource(
            scan_id=CLASH_SCAN_ID,
            scan_type=CLASH_SCAN_TYPE,
            resource_name=CLASH_RESOURCE_NAME,
            fileset=File.sample(seed=2),
            on_clash="error",
            clash_hint=(
                "the --acquisition-id and --resource ID(s) for this resource were "
                "auto-derived from its fileset type; pass explicit --acquisition-id / "
                "--resource specifier(s) to control collation"
            ),
        )


def test_add_resource_clash_hint_in_avoid_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logging.getLogger("accessionflow").setLevel(logging.WARNING)
    _clash_session().add_resource(
        scan_id=CLASH_SCAN_ID,
        scan_type=CLASH_SCAN_TYPE,
        resource_name=CLASH_RESOURCE_NAME,
        fileset=File.sample(seed=2),
        on_clash="avoid",
        clash_hint="pass explicit --acquisition-id / --resource specifier(s) to control collation",
    )
    assert "pass explicit --acquisition-id / --resource specifier(s)" in caplog.text


def test_clash_merge(caplog: pytest.LogCaptureFixture) -> None:

    logger = logging.getLogger("accessionflow")
    logger.setLevel(logging.DEBUG)

    file1 = File.sample(seed=1)
    file2 = File.sample(seed=2)

    session = Accession(
        uid="12345",
        labels={"project": "PROJECTID", "subject": "SUBJECTID", "session": "SESSIONID"},
        acquisitions=[
            Acquisition(
                id=CLASH_SCAN_ID,
                type=CLASH_SCAN_TYPE,
                resources={CLASH_RESOURCE_NAME: file1},
            )
        ],
    )

    session.add_resource(
        scan_id=CLASH_SCAN_ID,
        scan_type=CLASH_SCAN_TYPE,
        resource_name=CLASH_RESOURCE_NAME,
        fileset=file2,
        on_clash="merge",
    )
    assert "Merging resource" in caplog.text
    merged = session.acquisitions[CLASH_SCAN_ID].resources[CLASH_RESOURCE_NAME]
    assert isinstance(merged.fileset, SetOf)
    assert merged.fileset.content_types == (File,)
    assert set(merged.fileset.fspaths) == set(file1.fspaths) | set(file2.fspaths)


def test_clash_merge_saves_combined_resource(tmp_path: Path) -> None:
    """A merged resource combines the files of both filesets into a single
    ``SetOf[...]``, collates the members' metadata (scalar where they agree,
    aligned list where they differ), and round-trips through ``save()``/``load()``."""

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    view1 = src_dir / "lesion-dermoscopy.dat"
    view2 = src_dir / "lesion-clinical.dat"
    view1.write_text("first view")
    view2.write_text("second view")
    fileset1 = File(view1)
    fileset2 = File(view2)
    # 'LesionID' agrees across the two views, 'View' differs
    fileset1.metadata.update({"LesionID": "L1", "View": "dermoscopy"})
    fileset2.metadata.update({"LesionID": "L1", "View": "clinical"})

    session = Accession(
        uid="12345",
        labels={"project": "PROJECTID", "subject": "SUBJECTID", "session": "SESSIONID"},
        acquisitions=[
            Acquisition(
                id=CLASH_SCAN_ID,
                type=CLASH_SCAN_TYPE,
                resources={CLASH_RESOURCE_NAME: fileset1},
            )
        ],
    )

    session.add_resource(
        scan_id=CLASH_SCAN_ID,
        scan_type=CLASH_SCAN_TYPE,
        resource_name=CLASH_RESOURCE_NAME,
        fileset=fileset2,
        on_clash="merge",
    )

    merged = session.acquisitions[CLASH_SCAN_ID].resources[CLASH_RESOURCE_NAME]
    assert isinstance(merged.fileset, SetOf)
    assert merged.fileset.content_types == (File,)
    assert sorted(p.name for p in merged.fileset.fspaths) == [
        "lesion-clinical.dat",
        "lesion-dermoscopy.dat",
    ]
    # agreed field stays scalar, differing field is collated into an aligned list
    assert merged.metadata["LesionID"] == "L1"
    assert merged.metadata["View"] == ["dermoscopy", "clinical"]

    saved, _ = session.save(tmp_path / "staged")
    session_dir = (tmp_path / "staged").joinpath(*session.staging_relpath)
    reloaded = Accession.load(session_dir)

    reloaded_resource = reloaded.acquisitions[CLASH_SCAN_ID].resources[
        CLASH_RESOURCE_NAME
    ]
    assert sorted(p.name for p in reloaded_resource.fileset.fspaths) == [
        "lesion-clinical.dat",
        "lesion-dermoscopy.dat",
    ]
    assert reloaded_resource.metadata["LesionID"] == "L1"
    assert reloaded_resource.metadata["View"] == ["dermoscopy", "clinical"]
    assert (
        reloaded_resource.checksums
        == saved.acquisitions[CLASH_SCAN_ID].resources[CLASH_RESOURCE_NAME].checksums
    )


def _png(path: Path) -> Path:
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )
    return path


def _jpg(path: Path) -> Path:
    path.write_bytes(
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    )
    return path


def _png_clash_session(tmp_path: Path) -> tuple[Accession, ty.Any]:
    from fileformats.image.raster import Png

    fileset1 = Png(_png(tmp_path / "a.png"))
    session = Accession(
        uid="12345",
        labels={"project": "P", "subject": "S", "session": "V"},
        acquisitions=[
            Acquisition(
                id=CLASH_SCAN_ID,
                type=CLASH_SCAN_TYPE,
                resources={CLASH_RESOURCE_NAME: fileset1},
            )
        ],
    )
    return session, fileset1


def test_add_resource_clash_spec_union_scope_merges_cross_type(tmp_path: Path) -> None:
    """A Png clashing with a Jpeg is merged into ``SetOf[Png, Jpeg]`` when a single
    ``ClashSpec`` scope (``image/png|image/jpeg``) covers both."""
    from fileformats.generic import SetOf
    from fileformats.image.raster import Jpeg, Png

    session, _ = _png_clash_session(tmp_path)
    session.add_resource(
        scan_id=CLASH_SCAN_ID,
        scan_type=CLASH_SCAN_TYPE,
        resource_name=CLASH_RESOURCE_NAME,
        fileset=Jpeg(_jpg(tmp_path / "b.jpg")),
        on_clash=[ClashSpec("merge", "image/png|image/jpeg")],
    )
    merged = session.acquisitions[CLASH_SCAN_ID].resources[CLASH_RESOURCE_NAME].fileset
    assert isinstance(merged, SetOf)
    assert set(merged.content_types) == {Png, Jpeg}


def test_add_resource_clash_spec_separate_specs_raise_cross_type(
    tmp_path: Path,
) -> None:
    """Two single-type ``ClashSpec``s don't jointly cover a Png-vs-Jpeg clash - no
    single spec's scope covers both, so it raises."""
    from fileformats.image.raster import Jpeg

    session, _ = _png_clash_session(tmp_path)
    with pytest.raises(KeyError, match="no --on-resource-clash spec"):
        session.add_resource(
            scan_id=CLASH_SCAN_ID,
            scan_type=CLASH_SCAN_TYPE,
            resource_name=CLASH_RESOURCE_NAME,
            fileset=Jpeg(_jpg(tmp_path / "b.jpg")),
            on_clash=[
                ClashSpec("merge", "image/png"),
                ClashSpec("merge", "image/jpeg"),
            ],
        )


def test_add_resource_clash_spec_no_covering_spec_raises(tmp_path: Path) -> None:
    from fileformats.image.raster import Png

    session, _ = _png_clash_session(tmp_path)
    with pytest.raises(KeyError, match="no --on-resource-clash spec"):
        session.add_resource(
            scan_id=CLASH_SCAN_ID,
            scan_type=CLASH_SCAN_TYPE,
            resource_name=CLASH_RESOURCE_NAME,
            fileset=Png(_png(tmp_path / "b.png")),
            on_clash=[ClashSpec("avoid", "image/jpeg")],
        )


def test_add_resource_clash_spec_avoid_within_scope(tmp_path: Path) -> None:
    from fileformats.image.raster import Png

    session, _ = _png_clash_session(tmp_path)
    session.add_resource(
        scan_id=CLASH_SCAN_ID,
        scan_type=CLASH_SCAN_TYPE,
        resource_name=CLASH_RESOURCE_NAME,
        fileset=Png(_png(tmp_path / "b.png")),
        on_clash=[ClashSpec("avoid", "image/png|image/jpeg")],
    )
    assert sorted(session.acquisitions[CLASH_SCAN_ID].resources) == [
        CLASH_RESOURCE_NAME,
        CLASH_RESOURCE_NAME + "__2",
    ]


def test_add_resource_clash_spec_remerge_into_existing_setof(tmp_path: Path) -> None:
    """A 3rd fileset merged into an existing ``SetOf[Png, Jpeg]`` is still covered by
    an ``image/png|image/jpeg`` scope (``_fileset_in_scope`` checks content types)."""
    from fileformats.generic import SetOf
    from fileformats.image.raster import Jpeg, Png

    session, _ = _png_clash_session(tmp_path)
    spec = [ClashSpec("merge", "image/png|image/jpeg")]
    session.add_resource(
        CLASH_SCAN_ID,
        CLASH_SCAN_TYPE,
        CLASH_RESOURCE_NAME,
        Jpeg(_jpg(tmp_path / "b.jpg")),
        on_clash=spec,
    )
    session.add_resource(
        CLASH_SCAN_ID,
        CLASH_SCAN_TYPE,
        CLASH_RESOURCE_NAME,
        Png(_png(tmp_path / "c.png")),
        on_clash=spec,
    )
    merged = session.acquisitions[CLASH_SCAN_ID].resources[CLASH_RESOURCE_NAME].fileset
    assert isinstance(merged, SetOf)
    assert len(merged.fspaths) == 3


def test_from_metadata_yaml(tmp_path: Path) -> None:
    metadata = {
        Accession.UID_METADATA_KEY: "12345",
        "PatientName": "FamilyName_GivenName",
        "PatientID": "PID001",
        "StudyDate": "20230101",
    }
    yaml_path = tmp_path / "PROJ.SUBJ.VIS.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(metadata, f)

    session = Accession.from_metadata_yaml(yaml_path)

    assert session.labels["project"] == "PROJ"
    assert session.labels["subject"] == "SUBJ"
    assert session.labels["session"] == "VIS"
    assert session.acquisitions == {}
    assert dict(session.metadata) == metadata


def test_attach_files_metadata_only(tmp_path: Path) -> None:
    metadata = {
        Accession.UID_METADATA_KEY: "12345",
        "PatientName": "FamilyName_Given_Name",
        "PatientID": "PID001",
    }
    yaml_path = tmp_path / "PROJ.SUBJ.VIS.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(metadata, f)

    session = Accession.from_metadata_yaml(yaml_path)

    # Verify metadata-only session
    assert session.acquisitions == {}
    assert len(session.primary_parents) == 0

    # Generate dummy .ptd files
    assoc_dir = tmp_path / "assoc"
    assoc_dir.mkdir()
    get_raw_data_files(
        out_dir=assoc_dir,
        first_name="Given_Name",
        last_name="FamilyName",
    )

    session.attach_files(
        patterns=[
            AttachedFiles(
                SyngoMi_Vr20b_RawData,
                str(assoc_dir) + "/{PatientName}*.ptd",
                r".*/[^\.]+\.[^\.]+\.[^\.]+\.(?P<id>\d+)\.(?P<resource>[^\.]+).*",
            )
        ],
        spaces_to_underscores=False,
    )

    # Scans should now have been populated from the attached files
    assert len(session.acquisitions) > 0
    assert "602" in session.acquisitions
    assert set(session.acquisitions["602"].resources.keys()) == {
        "PET_LISTMODE",
        "PET_COUNTRATE",
    }


def test_session_resource_save_roundtrip(tmp_path: Path) -> None:
    """Session-level resources (no-dot dirs) survive a save/load roundtrip."""
    pdf = File.sample(seed=42)

    session = Accession(
        uid="12345",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "VIS"},
        acquisitions=[],
    )
    session.add_session_resource("radiology-doc-report", pdf)

    saved, _ = session.save(tmp_path)
    assert "radiology-doc-report" in saved.session_resources

    session_dir = tmp_path.joinpath(*session.staging_relpath)
    reloaded = Accession.load(session_dir)

    assert "radiology-doc-report" in reloaded.session_resources
    assert (
        reloaded.session_resources["radiology-doc-report"].checksums
        == saved.session_resources["radiology-doc-report"].checksums
    )


def test_session_save_filters_scan_and_session_resources(
    tmp_path: Path, imaging_session: Accession
) -> None:
    imaging_session.add_session_resource("report", File.sample(seed=42))

    dicom_saved, _ = imaging_session.save(tmp_path / "dicom", include=[DicomSeries])
    report_saved, _ = imaging_session.save(tmp_path / "report", include=[File])

    assert dicom_saved.acquisitions
    assert dicom_saved.session_resources == {}
    assert all(
        isinstance(resource.fileset, DicomSeries) for resource in dicom_saved.resources
    )
    assert report_saved.acquisitions == {}
    assert set(report_saved.session_resources) == {"report"}
    assert isinstance(report_saved.session_resources["report"].fileset, File)


def test_session_save_include_requires_a_matching_resource(
    tmp_path: Path, imaging_session: Accession
) -> None:
    with pytest.raises(ValueError, match="No resources .* match"):
        imaging_session.save(tmp_path, include=[SyngoMi_Vr20b_ListMode])

    assert not (tmp_path / imaging_session.name).exists()


def test_id_escape(tmp_path: Path) -> None:
    raw_data_dir = tmp_path / "raw"
    raw_data_dir.mkdir()
    get_raw_data_files(
        out_dir=raw_data_dir,
        first_name="GivenName",
        last_name="FamilyName",
        PatientID="INSTRUMENT_SURNAME^FIRST_NAME",
        StudyID="Study1",
        AccessionNumber="Accession1",
        StudyInstanceUID="StudyInstanceUID1",
    )

    sessions = Accession.from_paths(
        sorted(raw_data_dir.rglob("*.ptd")),
        datatypes=[SyngoMi_Vr20b_ListMode, SyngoMi_Vr20b_CountRate],
        accession_uid_field=[IDSpec("StudyInstanceUID")],
        acquisition_id_field=[IDSpec("SeriesNumber")],
        resource_field=[IDSpec("ImageType[2:]")],
    )

    assert len(sessions) == 1

    sessions[0].label(
        label_fields={
            "project": "StudyID",
            "subject": "PatientID",
            "session": "AccessionNumber",
        },
    )
    assert sessions[0].labels["subject"] == "INSTRUMENT_SURNAME_FIRST_NAME"


def test_label_unresolvable_field_uses_placeholder_instead_of_raising(
    imaging_session: Accession,
) -> None:
    """A project/subject/session field that can't be resolved from the session's
    metadata should produce a placeholder ID (and flag the session via
    'invalid_ids'), rather than raising and losing the session entirely"""
    imaging_session.label(
        label_fields={
            "project": "ThisFieldDoesNotExistInTheMetadata",
            "subject": "PatientID",
            "session": "AccessionNumber",
        },
    )
    assert imaging_session.labels["project"].startswith(
        "INVALID_MISSING_THISFIELDDOESNOTEXISTINTHEMETADATA_"
    )
    assert imaging_session.invalid_ids
    # the other, resolvable fields are unaffected
    assert not imaging_session.labels["subject"].startswith("INVALID_MISSING_")


# ---------------------------------------------------------------------------
# _metadata_diff tests
# ---------------------------------------------------------------------------


def test_metadata_diff_identical_returns_empty() -> None:
    orig = {"PatientName": "John Doe", "DOB": "19800101"}
    assert _metadata_diff(orig, dict(orig)) == {}


def test_metadata_diff_missing_key_included() -> None:
    """A key present in `orig` but absent from `new` is reported (KeyError branch)."""
    orig = {"PatientName": "John Doe", "DOB": "19800101"}
    new = {"DOB": "19800101"}
    assert _metadata_diff(orig, new) == {"PatientName": "John Doe"}


def test_metadata_diff_changed_value_included() -> None:
    """A key present in both but with a different value is reported (elif branch)."""
    orig = {"PatientName": "John Doe", "DOB": "19800101"}
    new = {"PatientName": "Anonymous", "DOB": "19800101"}
    assert _metadata_diff(orig, new) == {"PatientName": "John Doe"}


def test_metadata_diff_unchanged_value_excluded() -> None:
    orig = {"PatientName": "John Doe", "DOB": "19800101"}
    new = {"PatientName": "John Doe", "DOB": "19790101"}
    assert _metadata_diff(orig, new) == {"DOB": "19800101"}


def test_metadata_diff_nested_mapping_recurses() -> None:
    """Nested mappings are diffed recursively rather than compared wholesale."""
    orig = {"PatientInfo": {"Name": "John Doe", "Sex": "M"}}
    new = {"PatientInfo": {"Name": "Anonymous", "Sex": "M"}}
    assert _metadata_diff(orig, new) == {"PatientInfo": {"Name": "John Doe"}}


def test_metadata_diff_nested_mapping_unchanged_excluded() -> None:
    """A nested mapping with no internal differences is omitted entirely."""
    orig = {"PatientInfo": {"Name": "John Doe"}}
    new = {"PatientInfo": {"Name": "John Doe"}}
    assert _metadata_diff(orig, new) == {}


def test_metadata_diff_mapping_replaced_by_non_mapping() -> None:
    """When `orig`'s value is a mapping but `new`'s isn't, fall back to a plain
    equality comparison rather than recursing."""
    orig = {"PatientInfo": {"Name": "John Doe"}}
    new = {"PatientInfo": "stripped"}
    assert _metadata_diff(orig, new) == {"PatientInfo": {"Name": "John Doe"}}


# ---------------------------------------------------------------------------
# Accession.deidentify tests
# ---------------------------------------------------------------------------

DEIDENTIFY_REID_MDATA = {"PatientName": "John Doe", "DOB": "19800101"}


class DeidTestFile(File, MedicalImagingData):
    """Generic file containing PHI, with a registered deidentify implementation (whose
    signature determines the format the recipe is loaded from), which is overridden
    per-instance by the stand-ins below"""

    contains_phi = True


@extra_implementation(MedicalImagingData.deidentify)
def deid_test_file_deidentify(
    fileset: DeidTestFile,
    out_dir: os.PathLike[str],
    recipe: Loaded[Json] | None = None,
    **kwargs: ty.Any,
) -> DeidTestFile:
    raise NotImplementedError("overridden per-instance in tests")


@pytest.fixture
def recipe_file(tmp_path: Path) -> Path:
    fspath = tmp_path / "recipe.json"
    fspath.write_text(json.dumps({"remove": ["PatientName"]}))
    return fspath


def _deidentify_test_impl(
    fileset: File,
    out_dir: Path,
    recipe: ty.Any = None,
    **kwargs: ty.Any,
) -> File:
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    deidentified = fileset.copy(dest)
    # session.deidentify() now reconstructs reid metadata itself by diffing
    # `metadata` before/after calling deidentify(), so the stand-in "stripped"
    # fileset needs to actually report different metadata to the original. A fresh
    # copy of a generic ``File`` has no metadata reader, so its metadata is already
    # empty - nothing to strip here.
    return deidentified


def _make_deid_fileset(seed: int, expected_reid: dict) -> DeidTestFile:
    """Return a DeidTestFile instance (contains_phi=True) with an injected deidentify().

    contains_phi=True routes it through the deidentify branch in
    session.deidentify(). expected_reid is written to the fileset's metadata overlay
    so that session.deidentify()'s before/after diff reconstructs it. The injected
    method is a functools.partial binding a module-level function (not a closure),
    just for consistency/reuse across the fixtures in this module.
    """
    f = DeidTestFile.sample(seed=seed)
    f.metadata.update(expected_reid)
    f.deidentify = functools.partial(_deidentify_test_impl, f)
    return f


def test_deidentify_empty_session(tmp_path: Path) -> None:
    session = Accession(
        uid="12345",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "SESS"},
        acquisitions=[],
    )
    deid_session, reid_mdata = session.deidentify(tmp_path / "dest")
    assert deid_session.labels["project"] == "PROJ"
    assert deid_session.acquisitions == {}
    assert reid_mdata == {}


def test_deidentify_no_phi_copies_files(tmp_path: Path) -> None:
    """Resources without contains_phi are copied as-is; no reid metadata collected."""
    f = File.sample(seed=1)  # no contains_phi attr → getattr returns False → copy path
    session = Accession(
        uid="12345",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "SESS"},
        acquisitions=[Acquisition(id="1", type="test-scan", resources={"FILE": f})],
    )
    deid_session, reid_mdata = session.deidentify(tmp_path / "dest")
    assert "1" in deid_session.acquisitions
    assert reid_mdata == {}
    for scan in deid_session.acquisitions.values():
        for resource in scan.resources.values():
            for fspath in resource.fileset.fspaths:
                assert fspath.exists()


def test_deidentify_collects_reid_metadata(tmp_path: Path, recipe_file: Path) -> None:
    """deidentify() returns reid metadata from resources that implement deidentify."""
    f = _make_deid_fileset(seed=1, expected_reid=DEIDENTIFY_REID_MDATA)
    session = Accession(
        uid="12345",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "SESS"},
        acquisitions=[Acquisition(id="1", type="test-scan", resources={"FILE": f})],
    )
    deid_session, reid_mdata = session.deidentify(
        tmp_path / "dest", recipe_files={DeidTestFile: recipe_file}
    )
    assert reid_mdata == DEIDENTIFY_REID_MDATA
    assert "1" in deid_session.acquisitions


def test_deidentify_missing_recipe_file_raises(tmp_path: Path) -> None:
    """No recipe files with require_matching_recipe_file=True raises KeyError."""
    f = _make_deid_fileset(seed=1, expected_reid=DEIDENTIFY_REID_MDATA)
    session = Accession(
        uid="12345",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "SESS"},
        acquisitions=[Acquisition(id="1", type="test-scan", resources={"FILE": f})],
    )
    with pytest.raises(KeyError):
        session.deidentify(
            tmp_path / "dest", recipe_files={}, require_matching_recipe_file=True
        )


def test_deidentify_missing_recipe_file_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No recipe files with require_matching_recipe_file=False logs a warning and
    proceeds."""
    f = _make_deid_fileset(seed=1, expected_reid=DEIDENTIFY_REID_MDATA)
    session = Accession(
        uid="12345",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "SESS"},
        acquisitions=[Acquisition(id="1", type="test-scan", resources={"FILE": f})],
    )
    with caplog.at_level(logging.WARNING, logger="accessionflow"):
        deid_session, reid_mdata = session.deidentify(
            tmp_path / "dest", recipe_files={}, require_matching_recipe_file=False
        )
    assert "No deidentification recipe file" in caplog.text
    assert "1" in deid_session.acquisitions
    assert reid_mdata == DEIDENTIFY_REID_MDATA


def test_deidentify_merges_reid_metadata_across_resources(
    tmp_path: Path, recipe_file: Path
) -> None:
    """Reid metadata from multiple resources is collated into a single dict."""
    f1 = _make_deid_fileset(seed=1, expected_reid={"PatientName": "Alice"})
    f2 = _make_deid_fileset(seed=2, expected_reid={"DOB": "19901201"})
    session = Accession(
        uid="12345",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "SESS"},
        acquisitions=[
            Acquisition(id="1", type="scan-a", resources={"FILE": f1}),
            Acquisition(id="2", type="scan-b", resources={"FILE": f2}),
        ],
    )
    _, reid_mdata = session.deidentify(
        tmp_path / "dest", recipe_files={DeidTestFile: recipe_file}
    )
    assert reid_mdata == {"PatientName": "Alice", "DOB": "19901201"}


def test_deidentify_passes_max_workers_to_resource(
    tmp_path: Path, recipe_file: Path
) -> None:
    """max_workers passed to session.deidentify() should reach each resource's
    own FileSet.deidentify() call unchanged.
    """
    received_max_workers: list = []

    def _capturing_deidentify_impl(
        fileset: File,
        out_dir: Path,
        recipe: ty.Any = None,
        **kwargs: ty.Any,
    ) -> File:
        received_max_workers.append(kwargs.get("max_workers"))
        return _deidentify_test_impl(fileset, out_dir, recipe=recipe, **kwargs)

    f = _make_deid_fileset(seed=1, expected_reid=DEIDENTIFY_REID_MDATA)
    f.deidentify = functools.partial(_capturing_deidentify_impl, f)
    session = Accession(
        uid="12345",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "SESS"},
        acquisitions=[Acquisition(id="1", type="test-scan", resources={"FILE": f})],
    )
    session.deidentify(
        tmp_path / "dest", recipe_files={DeidTestFile: recipe_file}, max_workers=3
    )
    assert received_max_workers == [3]


def test_deidentify_carries_session_level_resources(tmp_path: Path) -> None:
    """A resource attached to the SESSION must survive de-identification.

    deidentify() builds its output from new_empty(), which copies the ids and
    nothing else, and then walks self.acquisitions. Session-level resources were in
    neither, so they were silently dropped: not de-identified, not copied, and
    nothing reported.

    It is worse than a plain loss. The per-session completeness gate in
    deidentify_api counts data files on both sides, so a session carrying one
    comes out short, is reported incomplete, and correctly refuses to unlink its
    input -- for ever, because the next run drops it again.
    """
    from accessionflow.model.accession import Accession
    from accessionflow.model.acquisition import Acquisition

    session = Accession(
        uid="PROJ.SUBJ.SESS",
        labels={"project": "PROJ", "subject": "SUBJ", "session": "SESS"},
        acquisitions=[
            Acquisition(id="1", type="T", resources={"RES": File.sample(seed=1)})
        ],
    )
    session.add_session_resource("report", File.sample(seed=42))
    assert "report" in session.session_resources

    deid, _ = session.deidentify(tmp_path / "out", require_matching_recipe_file=False)

    assert "report" in deid.session_resources, (
        "the session-level resource was dropped by deidentify(), so it never "
        "reaches XNAT and the completeness gate refuses the unlink for ever"
    )
    assert set(deid.acquisitions) == set(session.acquisitions), (
        "scans must be unaffected"
    )


def test_load_recipe_dicom(tmp_path: Path) -> None:
    """A recipe file is loaded into the type given by the ``Loaded[...]`` annotation
    of the ``recipe`` argument of the deidentify implementation for the fileset"""
    deid = pytest.importorskip("deid.config")
    from fileformats.core import check_loaded
    from fileformats.medimage import DeidRecipe

    recipe_file = tmp_path / "deid.dicom"
    recipe_file.write_text("FORMAT dicom\n\n%header\n\nREMOVE PatientName\n")
    series = DicomSeries(get_ac_image().iterdir())

    recipe = _load_recipe(series, recipe_file)

    assert isinstance(recipe, deid.DeidRecipe)
    check_loaded(DeidRecipe, recipe)


def test_load_recipe_dicom_with_side_cars(tmp_path: Path) -> None:
    """A recipe file with side-cars is loaded as the format that includes them
    (DeidRecipeX), so its transforms (salted with the key in the salt side-car) are
    bundled into the loaded recipe"""
    pytest.importorskip("deid.config")

    recipe_file = tmp_path / "dicom-series.deid"
    recipe_file.write_text(
        "FORMAT dicom\n\n%header\n\nREPLACE PatientName var:anon_patient_name\n"
    )
    (tmp_path / "dicom-series.transforms.yaml").write_text(
        'version: "0.1"\n'
        "variables:\n"
        "  anon_patient_name: {tag: PatientID, apply: [{hash: {length: 16}}]}\n"
    )
    salt_file = tmp_path / "dicom-series.salt"
    salt_file.write_bytes(b"secret\n")
    salt_file.chmod(0o600)
    series = DicomSeries(get_ac_image().iterdir())

    recipe = _load_recipe(series, recipe_file)

    assert set(recipe.transforms) == {"anon_patient_name"}
    # salted with the key in the salt side-car (stripped of surrounding whitespace)
    dataset = pydicom.Dataset()
    dataset.PatientID = "P001"
    expected = hashlib.sha256(b"secret" + b"P001").hexdigest()[:16]
    assert recipe.transforms["anon_patient_name"](dataset) == expected


def test_load_recipe_test_format(recipe_file: Path) -> None:
    assert _load_recipe(DeidTestFile.sample(), recipe_file) == {
        "remove": ["PatientName"]
    }
    assert _load_recipe(DeidTestFile.sample(), None) is None


def test_load_recipe_not_a_path() -> None:
    with pytest.raises(TypeError, match="Expected a path"):
        _load_recipe(DeidTestFile.sample(), {"already": "loaded"})  # type: ignore[arg-type]


def test_load_recipe_no_implementation(recipe_file: Path) -> None:
    with pytest.raises(NotImplementedError, match="No deidentify implementation"):
        _load_recipe(File.sample(), recipe_file)


def test_load_recipe_implementation_without_recipe(tmp_path: Path) -> None:
    """Implementations whose recipe argument is annotated ``None`` can only be passed
    None"""
    pytest.importorskip("fileformats.extras.vendor.canfield.medimage")
    from fileformats.vendor.canfield.medimage import TomSeedLog

    log_file = tmp_path / "capture.tom-seed.log"
    log_file.write_text("log")
    recipe_file = tmp_path / "recipe"
    recipe_file.write_text("recipe")

    assert _load_recipe(TomSeedLog(log_file), None) is None
    with pytest.raises(ValueError, match="doesn't accept a recipe"):
        _load_recipe(TomSeedLog(log_file), recipe_file)


def test_load_recipe_no_matching_format(tmp_path: Path) -> None:
    """A recipe file that doesn't match any of the formats accepted by the
    implementation (e.g. a deid recipe without a FORMAT line) raises"""
    from fileformats.core.exceptions import FormatMismatchError

    recipe_file = tmp_path / "dicom-series.deid"
    recipe_file.write_text("%header\n\nREMOVE PatientName\n")
    series = DicomSeries(get_ac_image().iterdir())

    with pytest.raises(FormatMismatchError, match="doesn't match any of the recipe"):
        _load_recipe(series, recipe_file)
