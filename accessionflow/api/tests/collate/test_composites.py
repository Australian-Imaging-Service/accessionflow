import pickle
from pathlib import Path

import pytest
from fileformats.application import Json
from fileformats.core import FileSet
from fileformats.core.exceptions import FormatMismatchError
from fileformats.generic import DirectoryOf, File
from fileformats.text import Csv, Plain

from accessionflow.api.collate import (
    ClaimedFiles,
    CollectedAccessions,
    claim_input_files,
    collect_accessions,
    load_metadata_tables,
    plan_recursion,
)
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
    # The loose text file was classified and dropped. The CSV directory is skipped
    # whole by the walk (expand_claimed_paths), so it is never classified
    assert [type(f) for f in collected.ignored] == [Plain]


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
