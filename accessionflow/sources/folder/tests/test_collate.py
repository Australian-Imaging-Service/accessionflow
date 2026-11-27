"""Tests of `collate`, the folder source's run on the collate steps (see
``prefect-migration-docs/ROADMAP.md``, Phase 1, Composites step C4)"""

import json
import shutil
import typing as ty
from pathlib import Path

import pytest
from fileformats.application import Json, Zip
from fileformats.core import FileSet
from fileformats.core.exceptions import FormatMismatchError
from fileformats.generic import Directory, DirectoryOf
from fileformats.medimage import DicomDir, DicomSeries
from fileformats.text import Csv
from medimages4tests.dummy.dicom.pet.wholebody.siemens.biograph_vision.vr20b import (
    get_image as get_pet_image,  # type: ignore[import-untyped]
)

from accessionflow.api.collate import (
    CLAIMED_FILES_DIRNAME,
    CLAIMED_MANIFEST,
    ERROR_MANIFEST,
    UNPROCESSED_MANIFEST,
    BuildFilesets,
    list_input_files,
)
from accessionflow.api.collate import claim as claim_module
from accessionflow.api.staging import BUILD_NAME_DEFAULT
from accessionflow.helpers.arg_types import IDSpec, MetadataTable, PathMetadataPattern
from accessionflow.helpers.run_uid import RUN_UID_RE
from accessionflow.model.accession import Accession
from accessionflow.model.resource import Resource
from accessionflow.sources.folder.api.collate_api import collate

LABEL_FIELDS = {"project": "project", "subject": "sess", "session": "visit"}
SESS_NAME = [PathMetadataPattern("{sess}/{name}.json", Json)]


class Dirs(ty.NamedTuple):
    inbox: Path
    output: Path
    working: Path
    unprocessed: Path
    error: Path


@pytest.fixture
def dirs(tmp_path: Path) -> Dirs:
    output = tmp_path / "out"
    return Dirs(
        inbox=tmp_path / "inbox",
        output=output,
        working=output / "__processing__",
        unprocessed=tmp_path / "unprocessed",
        error=tmp_path / "error",
    )


def _write(root: Path, files: dict[str, str]) -> None:
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _visit_table(tmp_path: Path, *sessions: str) -> MetadataTable:
    """An accession table that gives a visit to the given sessions only"""
    path = tmp_path / "tables" / "visits.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Session,visit\n" + "".join(f"{s},v1\n" for s in sessions))
    return MetadataTable(str(path), "accession", "Session=sess")


def _run(dirs: Dirs, **kwargs: ty.Any) -> list[str]:
    """Lists the inbox and collates its files, as the CLI will"""
    options: dict[str, ty.Any] = dict(
        datatypes=[Json],
        source_roots=[dirs.inbox],
        recursive=True,  # the files are in a directory per session
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata=SESS_NAME,
        constant_labels={"project": "P"},
    )
    options.update(kwargs)
    return collate(
        list_input_files([dirs.inbox]),
        dirs.output,
        dirs.working,
        dirs.unprocessed,
        dirs.error,
        LABEL_FIELDS,
        **options,
    )


def _delivered(dirs: Dirs) -> list[str]:
    return sorted(
        p.name
        for p in dirs.output.iterdir()
        if p.name not in (BUILD_NAME_DEFAULT, "__processing__")
    )


def _only_run_dir(parent: Path) -> Path:
    (run_dir,) = parent.iterdir()
    return run_dir


def _reasons(run_dir: Path) -> dict[str, dict[str, ty.Any]]:
    entries = json.loads((run_dir / UNPROCESSED_MANIFEST).read_text())
    return {e["file"]: e for e in entries}


def _files_under(path: Path) -> list[Path]:
    return [p for p in path.rglob("*") if p.is_file()] if path.exists() else []


def test_delivers_and_leaves_the_rest(dirs: Dirs, tmp_path: Path) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/b.json": "{}", "s1/notes.txt": "x"})
    errors = _run(
        dirs,
        allow_unrecognised=[r".*\.txt"],
        metadata_tables=[_visit_table(tmp_path, "s1")],
    )
    assert errors == []
    (name,) = _delivered(dirs)
    assert name.startswith("P.s1.v1_")
    assert sorted(Accession.load(dirs.output / name).acquisitions) == ["a", "b"]
    run_dir = _only_run_dir(dirs.unprocessed)
    assert name.endswith(f"_{run_dir.name}")  # named with the run's UID
    reasons = _reasons(run_dir)
    assert list(reasons) == [f"{CLAIMED_FILES_DIRNAME}/s1/notes.txt"]
    assert reasons[f"{CLAIMED_FILES_DIRNAME}/s1/notes.txt"]["reason"] == "unrecognised"
    assert _files_under(dirs.inbox) == []
    assert _files_under(dirs.working) == []
    assert not (dirs.output / BUILD_NAME_DEFAULT / run_dir.name).exists()
    assert not dirs.error.exists()


def test_accession_that_cant_be_labelled(dirs: Dirs, tmp_path: Path) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s2/b.json": "{}"})
    errors = _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    (error,) = errors
    assert "'s2'" in error
    assert "['visit']" in error
    assert [n.split("_")[0] for n in _delivered(dirs)] == ["P.s1.v1"]
    reasons = _reasons(_only_run_dir(dirs.unprocessed))
    entry = reasons[f"{CLAIMED_FILES_DIRNAME}/s2/b.json"]
    assert entry["reason"] == "failed"
    assert entry["accession"] == "s2"
    assert entry["original"] == str(dirs.inbox / "s2" / "b.json")


def _missing_column_table(tmp_path: Path) -> MetadataTable:
    path = tmp_path / "tables" / "bad.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Other,visit\ns1,v1\n")
    return MetadataTable(str(path), "accession", "Session=sess")


@pytest.mark.parametrize(
    "case",
    ["contradicting datatypes", "generic directory", "table column", "constant label"],
)
def test_bad_configuration_fails_before_anything_is_created(
    dirs: Dirs, tmp_path: Path, case: str
) -> None:
    """Every step's configuration is checked before the run UID is reserved, so a bad
    one in any step leaves the input as it was and creates nothing"""
    _write(dirs.inbox, {"s1/a.json": "{}"})
    options: dict[str, ty.Any] = {
        "contradicting datatypes": {"ignore_datatypes": [Json]},  # BuildFilesets
        "generic directory": {"datatypes": [Directory]},  # BuildFilesets
        "table column": {"metadata_tables": [_missing_column_table(tmp_path)]},
        "constant label": {"constant_labels": {"site": "X"}},  # constant_label_fields
    }[case]
    with pytest.raises(ValueError):
        _run(dirs, **options)
    assert _files_under(dirs.inbox) == [dirs.inbox / "s1" / "a.json"]
    assert not dirs.output.exists()
    assert not dirs.error.exists()


def test_run_that_raises_is_moved_to_the_error_dir(dirs: Dirs, tmp_path: Path) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/notes.txt": "x"})
    with pytest.raises(FormatMismatchError) as excinfo:
        _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    assert str(dirs.inbox / "s1" / "notes.txt") in excinfo.value.__notes__[0]
    run_dir = _only_run_dir(dirs.error)
    record = json.loads((run_dir / ERROR_MANIFEST).read_text())
    assert record["type"] == "FormatMismatchError"
    assert sorted(
        p.relative_to(run_dir / CLAIMED_FILES_DIRNAME).as_posix()
        for p in _files_under(run_dir / CLAIMED_FILES_DIRNAME)
    ) == ["s1/a.json", "s1/notes.txt"]
    assert _delivered(dirs) == []
    assert not (dirs.output / BUILD_NAME_DEFAULT / run_dir.name).exists()
    assert not dirs.unprocessed.exists()


def test_raise_errors_abandons_the_run(dirs: Dirs, tmp_path: Path) -> None:
    _write(dirs.inbox, {"s2/b.json": "{}"})
    with pytest.raises(Exception, match="visit"):
        _run(dirs, metadata_tables=[_visit_table(tmp_path)], raise_errors=True)
    run_dir = _only_run_dir(dirs.error)
    assert (run_dir / CLAIMED_FILES_DIRNAME / "s2" / "b.json").exists()


def test_claim_that_raises_partway(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/b.json": "{}", "s1/c.json": "{}"})
    real_claim_one = claim_module._claim_one
    calls: list[Path] = []

    def fail_on_second(src: Path, dest: Path) -> bool:
        calls.append(src)
        if len(calls) == 2:
            raise OSError("disk unplugged")
        return real_claim_one(src, dest)

    monkeypatch.setattr(claim_module, "_claim_one", fail_on_second)
    with pytest.raises(OSError, match="disk unplugged"):
        _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    run_dir = _only_run_dir(dirs.error)
    assert (run_dir / CLAIMED_MANIFEST).exists()
    assert [
        p.relative_to(run_dir / CLAIMED_FILES_DIRNAME).as_posix()
        for p in _files_under(run_dir / CLAIMED_FILES_DIRNAME)
    ] == ["s1/a.json"]
    assert sorted(p.name for p in _files_under(dirs.inbox)) == ["b.json", "c.json"]


def test_constant_labels_are_saved_in_the_metadata(dirs: Dirs, tmp_path: Path) -> None:
    """A constant label is written to the metadata as a field named after its level,
    so the delivered accession's directory name matches its saved metadata"""
    _write(dirs.inbox, {"s1/a.json": "{}"})
    assert _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")]) == []
    (name,) = _delivered(dirs)
    assert name.startswith("P.s1.v1_")
    accession = Accession.load(dirs.output / name)
    assert accession.metadata["project"] == "P"
    assert accession.labels["project"] == "P"


def test_interrupt_leaves_the_claim_in_place(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupt, e.g. Ctrl-C, leaves the claim in the working directory to be
    retried, and the build directory is removed"""
    _write(dirs.inbox, {"s1/a.json": "{}"})

    def interrupt(self: BuildFilesets, *args: ty.Any, **kwargs: ty.Any) -> ty.Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(BuildFilesets, "act", interrupt)
    with pytest.raises(KeyboardInterrupt):
        _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    run_dir = _only_run_dir(dirs.working)
    assert (run_dir / CLAIMED_FILES_DIRNAME / "s1" / "a.json").exists()
    assert not (dirs.output / BUILD_NAME_DEFAULT / run_dir.name).exists()
    assert not dirs.error.exists()


def test_files_that_arrive_during_a_run_wait_for_the_next(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The race test: a file added to the input directory after the listing stays there
    and is collated by the next run"""
    _write(dirs.inbox, {"s1/a.json": "{}"})
    real_act = BuildFilesets.act

    def arrive_then_act(self: BuildFilesets, *args: ty.Any, **kwargs: ty.Any) -> ty.Any:
        _write(dirs.inbox, {"s2/late.json": "{}"})
        return real_act(self, *args, **kwargs)

    table = _visit_table(tmp_path, "s1", "s2")
    monkeypatch.setattr(BuildFilesets, "act", arrive_then_act)
    assert _run(dirs, metadata_tables=[table]) == []
    assert [p.relative_to(dirs.inbox).as_posix() for p in _files_under(dirs.inbox)] == [
        "s2/late.json"
    ]
    assert [n.split("_")[0] for n in _delivered(dirs)] == ["P.s1.v1"]

    monkeypatch.setattr(BuildFilesets, "act", real_act)
    assert _run(dirs, metadata_tables=[table]) == []
    assert sorted(n.split("_")[0] for n in _delivered(dirs)) == ["P.s1.v1", "P.s2.v1"]
    assert _files_under(dirs.inbox) == []


def test_run_uid_clash_makes_another(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}"})
    taken, free = "20261126010203_aaaaaa", "20261126010203_bbbbbb"
    (dirs.working / taken).mkdir(parents=True)  # taken by another run
    uids = iter([taken, free])
    monkeypatch.setattr(claim_module, "make_run_uid", lambda: next(uids))
    assert _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")]) == []
    assert _delivered(dirs) == [f"P.s1.v1_{free}"]


def test_every_run_uid_taken(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}"})
    taken = "20261126010203_aaaaaa"
    (dirs.working / taken).mkdir(parents=True)  # taken by another run
    monkeypatch.setattr(claim_module, "make_run_uid", lambda: taken)
    with pytest.raises(RuntimeError, match="unused run UID"):
        _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    assert (dirs.inbox / "s1" / "a.json").exists()
    assert [p.name for p in dirs.working.iterdir()] == [taken]
    assert not (dirs.output / BUILD_NAME_DEFAULT).exists()


def test_source_roots_keep_top_level_directories_whole(
    dirs: Dirs, tmp_path: Path
) -> None:
    """As collate() lists an input directory: without --recursive, each top-level
    directory is classified whole"""
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/b.json": "{}"})
    errors = _run(
        dirs,
        datatypes=[DirectoryOf[Json]],
        recursive=False,
        path_metadata=[PathMetadataPattern("{sess}", DirectoryOf[Json])],
        acquisition_id_field=[IDSpec("sess")],
        metadata_tables=[_visit_table(tmp_path, "s1")],
    )
    assert errors == []
    (name,) = _delivered(dirs)
    accession = Accession.load(dirs.output / name)
    assert list(accession.acquisitions) == ["s1"]


def test_recursive_ignored_directory_recorded_as_ignored(
    dirs: Dirs, tmp_path: Path
) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/lesion/data.csv": "a,b\n1,2\n"})
    errors = _run(
        dirs,
        ignore_datatypes=[DirectoryOf[Csv]],
        recursive=True,
        metadata_tables=[_visit_table(tmp_path, "s1")],
    )
    assert errors == []
    entry = _reasons(_only_run_dir(dirs.unprocessed))[
        f"{CLAIMED_FILES_DIRNAME}/s1/lesion/data.csv"
    ]
    assert entry["reason"] == "ignored"
    assert entry["datatype"]


def test_no_input_files(dirs: Dirs) -> None:
    dirs.inbox.mkdir()
    assert _run(dirs) == []
    assert _delivered(dirs) == []
    # The run's directory was reserved, then removed as nothing was claimed
    assert list(dirs.working.iterdir()) == []
    assert not dirs.unprocessed.exists()
    assert not dirs.error.exists()
    assert list((dirs.output / BUILD_NAME_DEFAULT).iterdir()) == []


def test_bad_path_metadata_pattern_changes_nothing(dirs: Dirs) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}"})
    with pytest.raises(ValueError, match="Unmatched brace"):
        _run(dirs, path_metadata=[PathMetadataPattern("{sess/{name}.json", Json)])
    assert (dirs.inbox / "s1" / "a.json").exists()
    assert not dirs.output.exists()


# Counterparts of the DICOM tests of the old collate(), in api/tests/test_collate.py
# (composites step C5) -------------------------------------------------------------

DICOM_LABEL_FIELDS = {
    "project": "StudyID",
    "subject": "PatientID",
    "session": "AccessionNumber",
}


@pytest.fixture(scope="module")
def dicom_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A PET series, copied into each test's inbox, as a run claims (moves) its input"""
    source = tmp_path_factory.mktemp("dicom")
    get_pet_image(out_dir=source)
    return source


def _run_dicom(dirs: Dirs, dicom_source: Path, **kwargs: ty.Any) -> list[str]:
    """Collates a copy of the PET series with the DICOM defaults"""
    shutil.copytree(dicom_source, dirs.inbox / "dicom")
    options: dict[str, ty.Any] = dict(
        datatypes=[DicomSeries],
        source_roots=[dirs.inbox],
        recursive=True,
        acquisition_field="SeriesDescription",
    )
    options.update(kwargs)
    return collate(
        list_input_files([dirs.inbox]),
        dirs.output,
        dirs.working,
        dirs.unprocessed,
        dirs.error,
        DICOM_LABEL_FIELDS,
        **options,
    )


def test_dicom_delivered_labelled(dirs: Dirs, dicom_source: Path) -> None:
    """Counterpart of test_collate_creates_pre_label_session_dir: delivered labelled,
    as <labels>_<run_uid>, not as a pre-label '_.<uid>' directory"""
    assert _run_dicom(dirs, dicom_source) == []
    (name,) = _delivered(dirs)
    assert not name.startswith(Accession.PRE_LABEL_PREFIX)
    assert name.startswith("PROJECT_ID.")
    assert RUN_UID_RE.search(name)
    acquisition_dirs = [d for d in (dirs.output / name).iterdir() if d.is_dir()]
    assert len(acquisition_dirs) == 1
    # The acquisition's description is assigned with its labels
    assert not acquisition_dirs[0].name.endswith(".")
    assert _files_under(dirs.inbox) == []
    assert not dirs.unprocessed.exists()
    assert not dirs.error.exists()


def test_dicom_delivered_reloads_with_labels(dirs: Dirs, dicom_source: Path) -> None:
    """Counterpart of test_collate_output_reloadable_with_no_labelled_ids"""
    assert _run_dicom(dirs, dicom_source) == []
    (name,) = _delivered(dirs)
    reloaded = Accession.load(dirs.output / name)
    assert reloaded.labels["project"] == "PROJECT_ID"
    assert reloaded.labels["session"] == "987654321"
    assert name.endswith(f"_{reloaded.run_uid}")
    acquisition = next(iter(reloaded.acquisitions.values()))
    assert acquisition.type == "PET SWB 8MIN"


def test_dicom_accession_metadata_from_table(
    dirs: Dirs, dicom_source: Path, tmp_path: Path
) -> None:
    """Counterpart of test_collate_injects_session_metadata_from_table"""
    table = tmp_path / "clinical.csv"
    table.write_text(
        "PatientID,StudyComment,Cohort\n"
        "Session Label,injected-via-table,control\n"
        "someone-else,should-not-be-used,case\n"
    )
    errors = _run_dicom(
        dirs,
        dicom_source,
        metadata_tables=[MetadataTable(str(table), "accession", "PatientID=PatientID")],
    )
    assert errors == []
    (name,) = _delivered(dirs)
    reloaded = Accession.load(dirs.output / name)
    assert reloaded.metadata["StudyComment"] == "injected-via-table"
    assert reloaded.metadata["Cohort"] == "control"


def test_dicom_directory_converted_to_zip(dirs: Dirs, dicom_source: Path) -> None:
    """Counterpart of test_collate_converts_directory_to_zip"""
    errors = _run_dicom(
        dirs,
        dicom_source,
        datatypes=[DicomDir],
        recursive=False,
        conversion_map={DicomDir: (Zip, {"compression": "ZIP_STORED"})},
    )
    assert errors == []
    (name,) = _delivered(dirs)
    acquisition_dir = next(d for d in (dirs.output / name).iterdir() if d.is_dir())
    resource_dir = next(d for d in acquisition_dir.iterdir() if d.is_dir())
    manifest = Json(resource_dir / Resource.MANIFEST_FNAME).load()
    assert manifest["datatype"] == Zip.mime_like
    assert (resource_dir / "dicom.zip").exists()


@pytest.mark.parametrize("same_mount", [True, False])
def test_dicom_warns_when_hardlinks_unavailable(
    dirs: Dirs,
    dicom_source: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    same_mount: bool,
) -> None:
    """Counterpart of test_collate_warns_when_hardlinks_unavailable"""
    from fileformats.core.fs_mount_identifier import FsMountIdentifier

    monkeypatch.setattr(
        FsMountIdentifier, "on_same_mount", classmethod(lambda cls, a, b: same_mount)
    )
    with caplog.at_level("WARNING"):
        errors = _run_dicom(
            dirs, dicom_source, copy_mode=FileSet.CopyMode.hardlink_or_copy
        )
    assert errors == []
    warnings = [
        r.getMessage() for r in caplog.records if "hard-linked" in r.getMessage()
    ]
    assert len(warnings) == (0 if same_mount else 1)
    # The warning names the output directory, not the run's build directory
    assert all(f"'{dirs.output}'" in w for w in warnings)


def test_dicom_hashes_each_resource_once(
    dirs: Dirs, dicom_source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counterpart of test_collate_hashes_each_resource_once: only the delivered copy
    is hashed, not the claimed files as well"""
    hashed: list[FileSet] = []
    hash_files = FileSet.hash_files

    def counting_hash_files(self: FileSet, *args: ty.Any, **kwargs: ty.Any) -> ty.Any:
        hashed.append(self)
        return hash_files(self, *args, **kwargs)

    monkeypatch.setattr(FileSet, "hash_files", counting_hash_files)
    errors = _run_dicom(dirs, dicom_source, copy_mode=FileSet.CopyMode.hardlink_or_copy)
    assert errors == []
    assert len(hashed) == 1
    assert not any(p.is_relative_to(dirs.working) for p in hashed[0].fspaths)
    assert not any(p.is_relative_to(dirs.inbox) for p in hashed[0].fspaths)
