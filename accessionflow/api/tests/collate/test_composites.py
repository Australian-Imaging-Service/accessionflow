import json
import pickle
import typing as ty
from pathlib import Path

import pytest
from fileformats.application import Json
from fileformats.core import FileSet
from fileformats.core.exceptions import FormatMismatchError
from fileformats.generic import DirectoryOf, File
from fileformats.text import Csv, Plain

from accessionflow.api.collate import (
    CLAIMED_FILES_DIRNAME,
    UNPROCESSED_MANIFEST,
    ClaimedFiles,
    CollectedAccessions,
    claim_input_files,
    collect_accessions,
    deliver_accessions,
    finish_claim,
    load_metadata_tables,
    plan_recursion,
)
from accessionflow.api.collate import composites as composites_module
from accessionflow.api.collate import save as save_module
from accessionflow.api.staging import prepare_build_dir, remove_build_dir
from accessionflow.exceptions import LabelsNotAssignedError
from accessionflow.helpers.arg_types import IDSpec, MetadataTable, PathMetadataRegex
from accessionflow.model.accession import Accession

RUN_UID = "20261124010203_abc123"
TYPE_KEY = Accession.TYPE_METADATA_KEY

SESS_NAME_REGEX = [
    PathMetadataRegex(r".*/(?P<sess>[^/]+)/(?P<name>[^/]+)\.json$", Json)
]


def _claim(tmp_path: Path, files: dict[str, str]) -> ClaimedFiles:
    inbox = tmp_path / "inbox"
    paths = []
    for relpath, content in files.items():
        path = inbox / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        paths.append(path)
    return claim_input_files(paths, tmp_path / "proc", RUN_UID, [inbox])


def _collect(
    claimed: ClaimedFiles,
    datatypes: list[type[FileSet]],
    ignore_datatypes: list[type[FileSet]] = [],
    recursive: bool = True,
    **kwargs: object,
) -> CollectedAccessions:
    recursion = plan_recursion(datatypes, ignore_datatypes, recursive)
    return collect_accessions(
        claimed,
        datatypes,
        recursion,
        recursive=recursive,
        **kwargs,  # type: ignore[arg-type]
    )


# Moved from test_group.py and test_metadata.py -----------------------------------


def test_like_from_paths_datatype_field(tmp_path: Path) -> None:
    """Mirrors model/tests/test_accession.py::
    test_from_paths_injects_datatype_metadata_field"""
    claimed = _claim(tmp_path, {"src/a.txt": "x"})
    collected = _collect(
        claimed,
        [File],
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("sess")],
        resource_field=[IDSpec("res_{__datatype__}")],
        path_metadata_regex=[PathMetadataRegex(r".*/(?P<sess>[^/]+)\.txt", File)],
    )
    (accession,) = collected.accessions
    acquisition = next(iter(accession.acquisitions.values()))
    assert list(acquisition.resources) == ["res_File"]
    resource = next(iter(acquisition.resources.values()))
    assert resource.fileset.metadata["sess"] == "a"
    assert resource.fileset.metadata[TYPE_KEY] == "File"


def test_like_from_paths_recursive(tmp_path: Path) -> None:
    """Mirrors model/tests/test_accession.py::
    test_from_paths_recursive_pulls_nested_directory_datatype"""
    claimed = _claim(
        tmp_path,
        {
            "analysis/result.json": "{}",
            "analysis/notes.txt": "inside the wanted dir",
            "lesion/data.csv": "a,b\n1,2\n",
            "plain/deep/result.json": "{}",
            "scan.txt": "a loose file",
        },
    )
    collected = _collect(
        claimed,
        [DirectoryOf[Json]],
        [DirectoryOf[Csv], Plain],
        accession_uid_field=[IDSpec("__datatype__")],
        acquisition_id_field=[IDSpec("name")],
        resource_field=[IDSpec("name")],
        path_metadata_regex=[
            PathMetadataRegex(r".*/(?P<name>[^/]+)$", DirectoryOf[Json])
        ],
    )
    (accession,) = collected.accessions
    assert set(accession.acquisitions) == {"analysis", "deep"}
    # The CSV directory and the loose text file were classified and dropped
    assert [type(f) for f in collected.ignored] == [DirectoryOf[Csv], Plain]


# Ignored file-sets -----------------------------------------------------------------


def test_nothing_ignored(tmp_path: Path) -> None:
    claimed = _claim(tmp_path, {"s1/a.json": "{}", "s2/b.json": "{}"})
    collected = _collect(
        claimed,
        [Json],
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata_regex=SESS_NAME_REGEX,
        run_uid=RUN_UID,
    )
    assert [a.uid for a in collected.accessions] == ["s1", "s2"]
    assert collected.ignored == []


def test_ignored_filesets_returned(tmp_path: Path) -> None:
    claimed = _claim(
        tmp_path, {"s1/a.json": "{}", "s1/notes.txt": "x", "s1/sub/c.txt": "y"}
    )
    collected = _collect(
        claimed,
        [Json],
        [Plain],
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata_regex=SESS_NAME_REGEX,
    )
    (accession,) = collected.accessions
    assert list(accession.acquisitions) == ["a"]
    files_dir = claimed.files_dir
    assert sorted(
        p.relative_to(files_dir).as_posix()
        for f in collected.ignored
        for p in f.fspaths
    ) == ["s1/notes.txt", "s1/sub/c.txt"]


# Metadata --------------------------------------------------------------------------


def test_metadata_tables_reach_filesets_and_accessions(tmp_path: Path) -> None:
    claimed = _claim(tmp_path, {"s1/a.json": "{}", "s1/b.json": "{}"})
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    (tables_dir / "files.csv").write_text("Name,Note\na,first\n")
    (tables_dir / "acc.csv").write_text("Session,Cohort\ns1,case\n")
    tables = load_metadata_tables(
        [
            MetadataTable(
                str(tables_dir / "files.csv"),
                "fileset[application/json]",
                "Name=name",
            ),
            MetadataTable(str(tables_dir / "acc.csv"), "accession", "Session=sess"),
        ]
    )
    collected = _collect(
        claimed,
        [Json],
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata_regex=SESS_NAME_REGEX,
        metadata_tables=tables,
    )
    (accession,) = collected.accessions
    assert accession.metadata["Cohort"] == "case"
    notes = {
        name: next(iter(acq.resources.values())).fileset.metadata.get("Note")
        for name, acq in accession.acquisitions.items()
    }
    assert notes == {"a": "first", "b": None}


def test_dont_read_metadata(tmp_path: Path) -> None:
    claimed = _claim(tmp_path, {"s1/a.json": '{"inside": 1}'})
    kwargs: dict[str, object] = dict(
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata_regex=SESS_NAME_REGEX,
    )
    (accession,) = _collect(
        claimed, [Json], dont_read_metadata=[Json], **kwargs
    ).accessions
    fileset = next(iter(accession.acquisitions["a"].resources.values())).fileset
    assert fileset.metadata.read_disabled
    assert dict(fileset.metadata) == {"sess": "s1", "name": "a", TYPE_KEY: "Json"}


# Unrecognised files ----------------------------------------------------------------


def test_unrecognised_file_names_its_original_path(tmp_path: Path) -> None:
    claimed = _claim(tmp_path, {"s1/a.json": "{}", "s1/notes.txt": "x"})
    with pytest.raises(FormatMismatchError) as excinfo:
        _collect(claimed, [Json], accession_uid_field=[IDSpec("sess")])
    original = tmp_path / "inbox" / "s1" / "notes.txt"
    (note,) = excinfo.value.__notes__
    assert str(original) in note.splitlines()
    assert str(claimed.files_dir / "s1" / "notes.txt") not in note
    assert str(claimed.run_dir) in note


def test_allow_unrecognised(tmp_path: Path) -> None:
    claimed = _claim(tmp_path, {"s1/a.json": "{}", "s1/notes.txt": "x"})
    collected = _collect(
        claimed,
        [Json],
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata_regex=SESS_NAME_REGEX,
        allow_unrecognised=[r".*\.txt"],
    )
    (accession,) = collected.accessions
    assert list(accession.acquisitions) == ["a"]
    assert collected.ignored == []


# Pickling --------------------------------------------------------------------------


def test_collected_accessions_pickle(tmp_path: Path) -> None:
    claimed = _claim(tmp_path, {"s1/a.json": "{}", "s1/notes.txt": "x"})
    collected = _collect(
        claimed,
        [Json],
        [Plain],
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata_regex=SESS_NAME_REGEX,
        run_uid=RUN_UID,
    )
    restored = pickle.loads(pickle.dumps(collected))
    (accession,) = restored.accessions
    assert accession.uid == "s1"
    assert list(accession.acquisitions) == ["a"]
    assert list(accession.acquisitions["a"].resources) == list(
        collected.accessions[0].acquisitions["a"].resources
    )
    assert [list(f.fspaths) for f in restored.ignored] == [
        list(f.fspaths) for f in collected.ignored
    ]


# deliver_accessions ----------------------------------------------------------------

LABEL_FIELDS = {"project": "project", "subject": "sess", "session": "visit"}


def _collect_sessions(
    tmp_path: Path, *sessions: str, extra: dict[str, str] | None = None
) -> tuple[ClaimedFiles, list[Accession], Path, Path]:
    """Claims and collects one accession per session, each with a visit unless its
    name ends in '-novisit', and prepares the build directory"""
    files = {f"{s}/{s[:2]}a.json": f'{{"{s}": 1}}' for s in sessions}
    files.update(extra or {})
    claimed = _claim(tmp_path, files)
    collected = _collect(
        claimed,
        [Json],
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata_regex=SESS_NAME_REGEX,
        allow_unrecognised=[r".*\.txt"],
        run_uid=RUN_UID,
    )
    for accession in collected.accessions:
        if not accession.uid.endswith("-novisit"):
            accession.metadata["visit"] = "v1"
    output_dir = tmp_path / "out"
    return (
        claimed,
        collected.accessions,
        output_dir,
        prepare_build_dir(output_dir, RUN_UID),
    )


def test_deliver_one_of_each_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Moved from test_claim.py::test_steps_end_to_end_with_a_leftover: one accession
    is delivered, one fails to save, one can't be labelled, and a file no datatype
    took is left"""
    claimed, accessions, output_dir, build_dir = _collect_sessions(
        tmp_path, "s1", "s2", "s3-novisit", extra={"s1/notes.txt": "x"}
    )
    s1, s2, s3 = accessions
    real_save = save_module.save_to_build_dir

    def save_fails_for_s2(accession: Accession, *args: ty.Any, **kw: ty.Any) -> Path:
        if accession is s2:
            raise RuntimeError("disk full")
        return real_save(accession, *args, **kw)

    monkeypatch.setattr(save_module, "save_to_build_dir", save_fails_for_s2)
    failed = deliver_accessions(
        accessions,
        build_dir,
        output_dir,
        claimed,
        LABEL_FIELDS,
        constant_labels={"project": "P"},
    )

    assert len(failed) == 2
    assert all(a is b for (a, _), b in zip(failed, [s2, s3], strict=True))
    assert "disk full" in failed[0][1]
    assert "LabelsNotAssignedError" in failed[1][1]
    assert "['visit']" in failed[1][1]
    delivered = output_dir / f"P.s1.v1_{RUN_UID}"
    assert sorted(Accession.load(delivered).acquisitions) == ["s1a"]
    assert not (claimed.files_dir / "s1" / "s1a.json").exists()

    unprocessed = tmp_path / "unprocessed"
    moved = finish_claim(claimed, unprocessed, failed=failed)
    files_dir = unprocessed / RUN_UID / CLAIMED_FILES_DIRNAME
    assert moved == [
        files_dir / "s1" / "notes.txt",
        files_dir / "s2" / "s2a.json",
        files_dir / "s3-novisit" / "s3a.json",
    ]
    reasons = _reasons(unprocessed / RUN_UID)
    assert reasons["files/s1/notes.txt"]["reason"] == "unrecognised"
    assert reasons["files/s2/s2a.json"]["reason"] == "failed"
    assert "disk full" in reasons["files/s2/s2a.json"]["error"]
    assert reasons["files/s3-novisit/s3a.json"]["accession"] == "s3-novisit"
    assert "['visit']" in reasons["files/s3-novisit/s3a.json"]["error"]
    assert remove_build_dir(build_dir) == []
    assert not any((tmp_path / "inbox").rglob("*.*"))  # all were claimed


def _reasons(moved_run_dir: Path) -> dict[str, dict[str, ty.Any]]:
    entries = json.loads((moved_run_dir / UNPROCESSED_MANIFEST).read_text())
    return {e["file"]: e for e in entries}


def test_deliver_all(tmp_path: Path) -> None:
    claimed, accessions, output_dir, build_dir = _collect_sessions(tmp_path, "s1", "s2")
    failed = deliver_accessions(
        accessions,
        build_dir,
        output_dir,
        claimed,
        LABEL_FIELDS,
        constant_labels={"project": "P"},
    )
    assert failed == []
    assert sorted(p.name for p in output_dir.iterdir() if p != build_dir.parent) == [
        f"P.s1.v1_{RUN_UID}",
        f"P.s2.v1_{RUN_UID}",
    ]
    assert remove_build_dir(build_dir) == []
    assert not claimed.files_dir.exists() or not any(
        p.is_file() for p in claimed.files_dir.rglob("*")
    )


def test_deliver_raise_errors(tmp_path: Path) -> None:
    claimed, accessions, output_dir, build_dir = _collect_sessions(
        tmp_path, "s1", "s3-novisit"
    )
    with pytest.raises(LabelsNotAssignedError, match="visit"):
        deliver_accessions(
            accessions,
            build_dir,
            output_dir,
            claimed,
            LABEL_FIELDS,
            constant_labels={"project": "P"},
            raise_errors=True,
        )
    assert (output_dir / f"P.s1.v1_{RUN_UID}").is_dir()
    assert (claimed.files_dir / "s3-novisit" / "s3a.json").exists()


def test_deliver_warns_once_before_delivering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claimed, accessions, output_dir, build_dir = _collect_sessions(tmp_path, "s1", "s2")
    calls: list[tuple[ty.Any, ...]] = []

    def record(*args: ty.Any) -> list[Path]:
        calls.append(args)
        assert not (output_dir / f"P.s1.v1_{RUN_UID}").exists()
        return []

    monkeypatch.setattr(composites_module, "warn_if_hardlinks_unavailable", record)
    copy_mode = FileSet.CopyMode.copy
    deliver_accessions(
        accessions,
        build_dir,
        output_dir,
        claimed,
        LABEL_FIELDS,
        constant_labels={"project": "P"},
        copy_mode=copy_mode,
    )
    assert len(calls) == 1
    assert list(calls[0][0]) == accessions
    assert calls[0][1:3] == (build_dir, copy_mode)
