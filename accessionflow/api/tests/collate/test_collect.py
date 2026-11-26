"""What the collate steps collect from the files, up to the accessions: the tests that
were run on both ``Accession.from_paths`` and the steps until ``from_paths`` was removed
(see ``prefect-migration-docs/ROADMAP.md``, Phase 1, Removed)"""

import functools
import shutil
import typing as ty
from pathlib import Path

import pytest
from fileformats.core import from_mime
from fileformats.generic import File
from fileformats.medimage import DicomSeries
from fileformats.vendor.siemens.medimage import (
    SyngoMi_Vr20b_CountRate,
    SyngoMi_Vr20b_ListMode,
)
from frametree.common import FileSystem  # type: ignore[import-untyped]
from frametree.core.frameset import FrameSet  # type: ignore[import-untyped]
from medimages4tests.dummy.dicom.pet.wholebody.siemens.biograph_vision.vr20b import (
    get_image as get_pet_image,
)  # type: ignore[import-untyped]

from accessionflow.api.tests.collate.collect import collect_files
from accessionflow.helpers.arg_types import IDSpec, MetadataTable, PathMetadataRegex
from accessionflow.model.accession import Accession
from accessionflow.model.mock_store import DummyAxes
from conftest import get_raw_data_files

FIRST_NAME = "Given Name"
LAST_NAME = "FamilyName"

RAW_COLUMNS: ty.List[ty.Tuple[str, str, str]] = [
    (
        "listmode",
        "medimage/vnd.siemens.syngo-mi.vr20b.list-mode",
        ".*/PET_LISTMODE",
    ),
    (
        "countrate",
        "medimage/vnd.siemens.syngo-mi.vr20b.count-rate",
        ".*/PET_COUNTRATE",
    ),
]

# The ID specs of the DICOM tests
ACCESSION_UID_FIELD = [IDSpec("StudyInstanceUID", "medimage/dicom-collection")]
ACQUISITION_ID_FIELD = [IDSpec("SeriesNumber", "medimage/dicom-collection")]
RESOURCE_FIELD = [IDSpec("ImageType[2:]", "medimage/dicom-collection")]

CollectFn = ty.Callable[..., list[Accession]]


@pytest.fixture
def collect(tmp_path: Path) -> CollectFn:
    """`collect_files`, claiming the input files into ``tmp_path / "__processing__"``"""
    return functools.partial(collect_files, working_dir=tmp_path / "__processing__")


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


def test_stage_raw_data_directly(
    collect: CollectFn, raw_frameset: FrameSet, tmp_path: Path
) -> None:

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

    imaging_sessions = collect(
        f"{raw_data_dir}/**/*.ptd",
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


def test_path_metadata_regex_extracts_named_groups(
    collect: CollectFn, tmp_path: Path
) -> None:
    raw_data_dir = tmp_path / "raw" / "cohort-A"
    raw_data_dir.mkdir(parents=True)
    get_pet_image(out_dir=raw_data_dir)

    sessions = collect(
        f"{raw_data_dir}/**/*",
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


def test_path_metadata_regex_no_match_raises(
    collect: CollectFn, tmp_path: Path
) -> None:
    raw_data_dir = tmp_path / "raw" / "cohort-A"
    raw_data_dir.mkdir(parents=True)
    get_pet_image(out_dir=raw_data_dir)

    with pytest.raises(ValueError, match="Could not extract metadata"):
        collect(
            f"{raw_data_dir}/**/*",
            datatypes=[DicomSeries],
            accession_uid_field=[IDSpec("StudyInstanceUID")],
            acquisition_id_field=[IDSpec("SeriesNumber")],
            resource_field=[IDSpec("ImageType[2:]")],
            path_metadata_regex=[
                PathMetadataRegex(r"^/nonexistent/(?P<cohort>.+)$", DicomSeries),
            ],
        )


def test_collect_injects_datatype_metadata_field(
    collect: CollectFn, tmp_path: Path
) -> None:
    """The resolved fileset type name is exposed as the '__datatype__' metadata
    field and is usable from an IDSpec (including a format string)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    sessions = collect(
        src,
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


def test_collect_resource_label_defaults_to_mime_like_type_name(
    collect: CollectFn,
    tmp_path: Path,
) -> None:
    """With no resource_field, each resource is labelled with the mime-like
    rendering of its fileset's type name ('-' kept, '.'/'+' collapsed to '_')."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    sessions = collect(
        src,
        datatypes=[File],
        accession_uid_field=[IDSpec("__datatype__")],
        acquisition_id_field=[IDSpec("__datatype__")],
        # resource_field omitted -> mime-like(type_name)
    )

    assert list(next(iter(sessions[0].acquisitions.values())).resources) == ["file"]


def _tree(root: Path) -> Path:
    """A VectraExport-shaped tree for the recursive-directory tests:
    ``analysis/`` holds a .json (the wanted nested dir), ``lesion/`` holds a .csv
    (an ignored sibling dir), plus a loose file at the top."""
    (root / "analysis").mkdir(parents=True)
    (root / "analysis" / "result.json").write_text("{}")
    (root / "analysis" / "notes.txt").write_text("inside the wanted dir")
    (root / "lesion").mkdir()
    (root / "lesion" / "data.csv").write_text("a,b\n1,2\n")
    (root / "plain").mkdir()
    (root / "plain" / "deep").mkdir()
    (root / "plain" / "deep" / "result.json").write_text("{}")
    (root / "scan.txt").write_text("a loose file")
    return root


def test_collect_recursive_pulls_nested_directory_datatype(
    collect: CollectFn, tmp_path: Path
) -> None:
    from fileformats.application import Json
    from fileformats.generic import DirectoryOf
    from fileformats.text import Csv, Plain

    root = _tree(tmp_path / "export")
    sessions = collect(
        root,
        datatypes=[DirectoryOf[Json]],
        accession_uid_field=[IDSpec("__datatype__")],
        acquisition_id_field=[IDSpec("name")],
        resource_field=[IDSpec("name")],
        recursive=True,
        path_metadata_regex=[
            PathMetadataRegex(r".*/(?P<name>[^/]+)$", DirectoryOf[Json])
        ],
        ignore_datatypes=[DirectoryOf[Csv], Plain],
    )

    assert len(sessions) == 1
    scans = sessions[0].acquisitions
    # both DirectoryOf[Json] dirs (analysis/ and plain/deep/) pulled, nothing else
    assert set(scans) == {"analysis", "deep"}


def test_collect_recursive_allow_unrecognised_wildcard_pulls_only_wanted_dirs(
    collect: CollectFn,
    tmp_path: Path,
) -> None:
    """The wanted directory formats are nested inside larger 'clutter' directories
    whose internal structure we don't want to track. ``allow_unrecognised=['.*']`` mops
    up every non-matching path so only the requested nested dirs come through - no
    ``ignore_datatypes`` enumeration needed."""
    from fileformats.application import Json
    from fileformats.generic import DirectoryOf

    root = tmp_path / "export"
    # WholeBodyCapture-shaped clutter dir with the wanted analysis dir buried in it
    capture = root / "WBcapture"
    (capture / "analysis").mkdir(parents=True)
    (capture / "analysis" / "result.json").write_text("{}")
    (capture / "raw1.bin").write_bytes(b"junk")
    (capture / "thumbs").mkdir()
    (capture / "thumbs" / "t1.jpg").write_bytes(b"junk")
    # LesionAnalysis-shaped clutter dir with the wanted dexi dir buried in it
    lesion = root / "lesionAnalysis"
    (lesion / "dexi").mkdir(parents=True)
    (lesion / "dexi" / "meta.json").write_text("{}")
    (lesion / "report.csv").write_text("a,b\n1,2\n")
    (root / "loose_at_root.txt").write_text("junk")

    sessions = collect(
        root,
        datatypes=[DirectoryOf[Json]],
        accession_uid_field=[IDSpec("__datatype__")],
        acquisition_id_field=[IDSpec("name")],
        resource_field=[IDSpec("name")],
        recursive=True,
        allow_unrecognised=[".*"],
        path_metadata_regex=[
            PathMetadataRegex(r".*/(?P<name>[^/]+)$", DirectoryOf[Json])
        ],
    )

    assert len(sessions) == 1
    assert set(sessions[0].acquisitions) == {"analysis", "dexi"}


def test_collect_recursive_raises_on_unlisted_type(
    collect: CollectFn, tmp_path: Path
) -> None:
    from fileformats.application import Json
    from fileformats.core.exceptions import FormatMismatchError
    from fileformats.generic import DirectoryOf
    from fileformats.text import Csv

    root = _tree(tmp_path / "export")
    (root / "mystery.unknownext").write_text("not a recognised type")

    with pytest.raises(FormatMismatchError, match="mystery"):
        collect(
            root,
            datatypes=[DirectoryOf[Json]],
            accession_uid_field=[IDSpec("__datatype__")],
            acquisition_id_field=[IDSpec("__datatype__")],
            recursive=True,
            ignore_datatypes=[DirectoryOf[Csv]],  # doesn't cover the loose files
        )


def test_collect_recursive_rejects_bare_generic_directory(
    collect: CollectFn, tmp_path: Path
) -> None:
    from fileformats.generic import Directory

    root = _tree(tmp_path / "export")
    with pytest.raises(ValueError, match="generic/directory"):
        collect(
            root,
            datatypes=[Directory],
            accession_uid_field=[IDSpec("__datatype__")],
            acquisition_id_field=[IDSpec("__datatype__")],
            recursive=True,
        )


def test_collect_exclude_path_drops_recognised_by_relative_depth(
    collect: CollectFn,
    tmp_path: Path,
) -> None:
    """--exclude-path matches the path *relative to the input dir* and is applied
    before classification, so it drops a file even though a --datatype claims it
    (a 3-deep .txt here) while sparing the same type 2 deep."""
    from fileformats.generic import File

    root = tmp_path / "root"
    (root / "subject").mkdir(parents=True)
    (root / "subject" / "shallow.txt").write_text("keep")  # relative depth 2
    (root / "uuid" / "stamp").mkdir(parents=True)
    (root / "uuid" / "stamp" / "deep.txt").write_text("drop")  # relative depth 3

    sessions = collect(
        root,
        datatypes=[File],
        accession_uid_field=[IDSpec("__datatype__")],
        acquisition_id_field=[IDSpec("name")],
        resource_field=[IDSpec("name")],
        recursive=True,
        exclude_paths=["*/*/*.txt"],
        path_metadata_regex=[PathMetadataRegex(r".*/(?P<name>[^/]+)\.txt$", File)],
    )

    resources = [
        r for s in sessions for sc in s.acquisitions.values() for r in sc.resources
    ]
    assert resources == ["shallow"]


def _canfield_shaped_tree(root: Path) -> Path:
    """A stripped-down stand-in for a Canfield Vectra export: a session directory
    holding several 'capture' directories, each of which buries a nested analysis
    directory (two different formats) among loose files, plus sibling clutter
    directories and loose files at every level. Generic ``DirectoryOf`` types
    stand in for the real vendor formats:

    - ``DirectoryOf[Json]`` == the photogrammetry lesion-analysis dir (has a .json)
    - ``DirectoryOf[Csv]``  == the dexi-analysis dir (has a .csv), 2 instances
    """
    session = root / "SESSION-abc"

    # photogrammetry capture: loads of loose files + the wanted analysis dir + a
    # non-wanted sibling 'calib' directory
    photo = session / "20260805133937"
    photo.mkdir(parents=True)
    for name in ("a1A.CR2", "a1B.CR2", "f1A.CR2", "capture.cptr", "addtexture-log.txt"):
        (photo / name).write_bytes(b"raw")
    (photo / "analysis").mkdir()
    (photo / "analysis" / "lesion_data.json").write_text("{}")
    (photo / "analysis" / "exitstatus.txt").write_text("ok")  # not descended -> unseen
    (photo / "calib").mkdir()
    (photo / "calib" / "a1A.sfcm").write_bytes(b"cal")  # unrecognised, in a clutter dir

    # two dexi captures, each burying a DexiData dir among loose files
    for stamp in ("20260805135303357", "20260805135325459"):
        dexi_capture = session / stamp
        dexi_capture.mkdir()
        (dexi_capture / "captureinfo_scope").write_bytes(b"info")
        (dexi_capture / "XP.png").write_bytes(b"png")
        (dexi_capture / "DexiData_2.1").mkdir()
        (dexi_capture / "DexiData_2.1" / "result.csv").write_text("a,b\n1,2\n")
        (dexi_capture / "DexiData_2.1" / "heatmap.jpg").write_bytes(b"jpg")  # unseen

    # loose files hanging directly off the session dir, and a sibling of it
    (session / "lesion.t2k").write_bytes(b"t2k")
    (session / "DermX Report.pdf").write_bytes(b"pdf")
    (root / "testExternalID.db").write_bytes(b"SQLite format 3\x00")
    return root


def test_collect_recursive_extracts_nested_dirs_from_canfield_shaped_tree(
    collect: CollectFn,
    tmp_path: Path,
) -> None:
    """End-to-end on the Canfield-shaped tree: two distinct nested directory
    formats are pulled from wherever they are buried, one of them appearing more
    than once, while every loose file and every non-matching directory (the
    capture dirs, ``calib/``, the session dir, the sibling ``.db``) is left alone
    via ``allow_unrecognised=['.*']`` - no ``ignore_datatypes`` enumeration."""
    from fileformats.application import Json
    from fileformats.generic import DirectoryOf
    from fileformats.text import Csv

    root = _canfield_shaped_tree(tmp_path / "raw")

    sessions = collect(
        root,
        datatypes=[DirectoryOf[Json], DirectoryOf[Csv]],
        accession_uid_field=[IDSpec("session")],
        acquisition_id_field=[IDSpec("capture")],
        resource_field=[IDSpec("name")],
        recursive=True,
        allow_unrecognised=[".*"],
        path_metadata_regex=[
            PathMetadataRegex(
                r".*/(?P<session>SESSION-[^/]+)/(?P<capture>[^/]+)/(?P<name>[^/]+)$",
                DirectoryOf,
            )
        ],
    )

    assert len(sessions) == 1
    scans = sessions[0].acquisitions
    assert set(scans) == {"20260805133937", "20260805135303357", "20260805135325459"}
    assert list(scans["20260805133937"].resources) == ["analysis"]
    # '.' in 'DexiData_2.1' is escaped to '_' like any other ID/label
    assert list(scans["20260805135303357"].resources) == ["DexiData_2_1"]
    assert list(scans["20260805135325459"].resources) == ["DexiData_2_1"]
    resources = [r for s in scans.values() for r in s.resources.values()]
    assert {type(r.fileset).__name__ for r in resources} == {
        DirectoryOf[Json].__name__,
        DirectoryOf[Csv].__name__,
    }


def test_collect_scan_id_defaults_to_resource_label(
    collect: CollectFn, tmp_path: Path
) -> None:
    """With no scan_field, each resource sits in a scan of the same name."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    sessions = collect(
        src,
        datatypes=[File],
        accession_uid_field=[IDSpec("__datatype__")],
        # scan_field / resource_field omitted
    )

    scan = next(iter(sessions[0].acquisitions.values()))
    assert scan.id == "file"
    assert list(scan.resources) == ["file"]


def test_collect_datatype_scoped_scan_spec_falls_through(
    collect: CollectFn, tmp_path: Path
) -> None:
    """A datatype-scoped --acquisition spec that doesn't apply to a fileset's type (the
    DICOM 'SeriesNumber' default vs a plain File) names the scan after the resource
    rather than raising."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    sessions = collect(
        src,
        datatypes=[File],
        accession_uid_field=[IDSpec("__datatype__")],
        acquisition_id_field=[IDSpec("SeriesNumber", "medimage/dicom-collection")],
    )

    assert next(iter(sessions[0].acquisitions.values())).id == "file"


def test_collect_session_spec_not_matching_type_raises_clearly(
    collect: CollectFn,
    tmp_path: Path,
) -> None:
    """The session UID has no auto-fallback: a session spec whose datatype doesn't
    apply to a fileset (the DICOM-scoped default vs a plain File) raises an
    actionable error rather than a bare 'resource label' TypeError."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")

    with pytest.raises(TypeError, match="apply to a File"):
        collect(
            src,
            datatypes=[File],
            accession_uid_field=[
                IDSpec("StudyInstanceUID", "medimage/dicom-collection")
            ],
        )


def test_id_escape(collect: CollectFn, tmp_path: Path) -> None:
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

    sessions = collect(
        f"{raw_data_dir}/**/*.ptd",
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


@pytest.fixture(scope="module")
def dicom_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A DICOM directory shared by the module's tests. The steps claim (move) their
    input, so each test collects a copy of it"""
    dicom_dir = tmp_path_factory.mktemp("dicom")
    get_pet_image(out_dir=dicom_dir)
    return dicom_dir


@pytest.fixture
def patient_id(dicom_dir: Path, tmp_path: Path) -> str:
    """The PatientID of the dummy dataset, discovered by a throwaway load so the
    metadata-table tests don't have to hard-code it"""
    copy = shutil.copytree(dicom_dir, tmp_path / "patient_id" / "dicom")
    sessions = collect_files(
        copy,
        [DicomSeries],
        ACCESSION_UID_FIELD,
        ACQUISITION_ID_FIELD,
        RESOURCE_FIELD,
        working_dir=tmp_path / "patient_id" / "__processing__",
    )
    resource = next(
        iter(next(iter(sessions[0].acquisitions.values())).resources.values())
    )
    return str(resource.fileset.metadata["PatientID"])


def test_collect_injects_resource_metadata_from_table(
    collect: CollectFn, dicom_dir: Path, patient_id: str, tmp_path: Path
) -> None:
    table = tmp_path / "clinical.csv"
    table.write_text(f"PatientID,Radiotracer\n{patient_id},FDG\nother,ignored\n")

    sessions = collect(
        shutil.copytree(dicom_dir, tmp_path / "input" / "dicom"),
        [DicomSeries],
        ACCESSION_UID_FIELD,
        ACQUISITION_ID_FIELD,
        RESOURCE_FIELD,
        metadata_tables=[
            MetadataTable(str(table), "resource", "PatientID=PatientID"),
        ],
    )

    resource = next(
        iter(next(iter(sessions[0].acquisitions.values())).resources.values())
    )
    assert resource.metadata["Radiotracer"] == "FDG"
