import pickle
import re
from pathlib import Path

import pytest
from fileformats.application import Json
from fileformats.core import FileSet
from fileformats.generic import DirectoryOf, File, SetOf
from fileformats.text import Csv

from accessionflow.api.collate import (
    ClaimedFiles,
    apply_path_metadata,
    claim_input_files,
    classify_paths,
    disable_metadata_reading,
    expand_claimed_paths,
    inject_fileset_tables,
    load_metadata_tables,
    plan_recursion,
    tag_fileset_types,
)
from accessionflow.helpers.arg_types import (
    MetadataTable,
    PathMetadataPattern,
    PathMetadataRegex,
)
from accessionflow.model.accession import Accession
from accessionflow.sources.folder.api.collate_api import merge_path_metadata

RUN_UID = "abc12320261124010203"


def _claim(
    tmp_path: Path, relpaths: list[str], processing_dir: Path | None = None
) -> tuple[Path, ClaimedFiles]:
    inbox = tmp_path / "inbox"
    files = []
    for relpath in relpaths:
        path = inbox / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "a,b\n1,2\n")
        files.append(path)
    claimed = claim_input_files(
        files, processing_dir or tmp_path / "proc", RUN_UID, [inbox]
    )
    return inbox, claimed


def _filesets(
    claimed: ClaimedFiles, datatypes: list[type[FileSet]], recursive: bool = True
) -> list[FileSet]:
    plan = plan_recursion(datatypes, recursive=recursive)
    fspaths = expand_claimed_paths(claimed, datatypes, plan, recursive)
    return classify_paths(fspaths, datatypes, plan.ignore_datatypes)


def test_unanchored_regex_matches_original_path(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["cohort-A/a.json"])
    (fileset,) = apply_path_metadata(
        _filesets(claimed, [Json]),
        [PathMetadataRegex(r".*/(?P<cohort>[^/]+)/[^/]+$", Json)],
        claimed,
    )
    assert fileset.metadata["cohort"] == "cohort-A"


def test_anchored_regex_matches_only_the_original_path(tmp_path: Path) -> None:
    inbox, claimed = _claim(tmp_path, ["cohort-A/a.json"])
    regex = [PathMetadataRegex(rf"^{re.escape(str(inbox))}/(?P<cohort>[^/]+)/", Json)]
    (fileset,) = apply_path_metadata(_filesets(claimed, [Json]), regex, claimed)
    assert fileset.metadata["cohort"] == "cohort-A"
    # Without the claim, the path in the processing area doesn't match
    with pytest.raises(ValueError, match="Could not extract metadata"):
        apply_path_metadata(_filesets(claimed, [Json]), regex)


def test_anchored_glob_pattern_matches_original_path(tmp_path: Path) -> None:
    inbox, claimed = _claim(tmp_path, ["cohort-A/a.json"])
    regex = merge_path_metadata([PathMetadataPattern(f"{inbox}/{{cohort}}/*", Json)])
    (fileset,) = apply_path_metadata(_filesets(claimed, [Json]), regex, claimed)
    assert fileset.metadata["cohort"] == "cohort-A"


def test_pattern_applies_only_to_its_datatype(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["x/a.json", "y/b.csv"])
    filesets = apply_path_metadata(
        _filesets(claimed, [Json, Csv]),
        [PathMetadataRegex(r".*/(?P<dir>[^/]+)/[^/]+\.csv$", Csv)],
        claimed,
    )
    by_type = {type(f).__name__: f.metadata.get("dir") for f in filesets}
    assert by_type == {"Json": None, "Csv": "y"}


def test_later_pattern_wins(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["cohort-A/a.json"])
    (fileset,) = apply_path_metadata(
        _filesets(claimed, [Json]),
        [
            PathMetadataRegex(r".*/(?P<name>[^/]+)/[^/]+$", Json),
            PathMetadataRegex(r".*/(?P<name>[^/]+)\.json$", Json),
        ],
        claimed,
    )
    assert fileset.metadata["name"] == "a"


def test_directory_datatype_matches_its_original_directory(tmp_path: Path) -> None:
    inbox, claimed = _claim(tmp_path, ["export/analysis/result.json"])
    (fileset,) = apply_path_metadata(
        _filesets(claimed, [DirectoryOf[Json]]),
        [PathMetadataRegex(r"(?P<path>.*)", DirectoryOf[Json])],
        claimed,
    )
    assert fileset.metadata["path"] == str(inbox / "export" / "analysis")


def test_fileset_without_fspath_matches_its_parent(tmp_path: Path) -> None:
    inbox, claimed = _claim(tmp_path, ["series-7/1.json", "series-7/2.json"])
    fileset = SetOf[Json](*claimed.files)
    apply_path_metadata(
        [fileset],
        [PathMetadataRegex(r"(?P<path>.*)", SetOf[Json])],
        claimed,
    )
    assert fileset.metadata["path"] == str(inbox / "series-7")


def test_no_match_names_the_original_path(tmp_path: Path) -> None:
    inbox, claimed = _claim(tmp_path, ["a.json"])
    with pytest.raises(ValueError) as excinfo:
        apply_path_metadata(
            _filesets(claimed, [Json]),
            [PathMetadataRegex(r"^/nowhere/(?P<x>.*)", Json)],
            claimed,
        )
    assert str(inbox / "a.json") in str(excinfo.value)
    assert str(claimed.run_dir) not in str(excinfo.value)


def test_no_patterns(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["a.json"])
    filesets = _filesets(claimed, [Json])
    assert apply_path_metadata(filesets, [], claimed) == filesets
    assert "cohort" not in filesets[0].metadata


def test_relative_processing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _, claimed = _claim(
        tmp_path, ["cohort-A/a.json"], processing_dir=Path("out/__processing__")
    )
    assert claimed.run_dir.is_absolute()
    (fileset,) = apply_path_metadata(
        _filesets(claimed, [Json]),
        [PathMetadataRegex(r".*/(?P<cohort>[^/]+)/[^/]+$", Json)],
        claimed,
    )
    assert fileset.metadata["cohort"] == "cohort-A"


# tag_fileset_types ----------------------------------------------------------------

TYPE_KEY = Accession.TYPE_METADATA_KEY


def test_tag_fileset_types(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["a.json", "b.csv", "d/x.json"])
    filesets = _filesets(claimed, [Json, Csv, DirectoryOf[Json]], recursive=False)
    result = tag_fileset_types(filesets)
    assert result == filesets
    assert TYPE_KEY == "__datatype__"
    assert sorted(f.metadata[TYPE_KEY] for f in result) == [
        "Csv",
        "DirectoryOf[Json]",
        "Json",
    ]


def test_tag_fileset_types_keeps_value_from_path(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["custom.json"])
    filesets = apply_path_metadata(
        _filesets(claimed, [Json]),
        [PathMetadataRegex(r".*/(?P<__datatype__>[^/]+)\.json$", Json)],
        claimed,
    )
    (fileset,) = tag_fileset_types(filesets)
    assert fileset.metadata[TYPE_KEY] == "custom"


def test_tag_fileset_types_with_reading_disabled(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["a.json"])
    filesets = disable_metadata_reading(_filesets(claimed, [Json]), [Json])
    (fileset,) = tag_fileset_types(filesets)
    assert dict(fileset.metadata) == {TYPE_KEY: "Json"}


def test_steps_7_to_11_together(tmp_path: Path) -> None:
    """Mirrors model/tests/test_accession.py::
    test_from_paths_injects_datatype_metadata_field up to grouping"""
    _, claimed = _claim(tmp_path, ["src/a.txt"])
    (fileset,) = tag_fileset_types(
        apply_path_metadata(
            _filesets(claimed, [File]),
            [PathMetadataRegex(r".*/(?P<sess>[^/]+)\.txt", File)],
            claimed,
        )
    )
    assert fileset.metadata["sess"] == "a"
    assert fileset.metadata[TYPE_KEY] == "File"


# load_metadata_tables and inject_fileset_tables -----------------------------------

NAME_REGEX = [PathMetadataRegex(r".*/(?P<name>[^/]+)\.json$", Json)]


def _table(path: Path, content: str, row_frequency: str, join: str) -> MetadataTable:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return MetadataTable(str(path), row_frequency, join)


def test_load_metadata_tables_caches_the_rows(tmp_path: Path) -> None:
    table_path = tmp_path / "t.csv"
    table = _table(
        table_path, "Name,Note\na,first\n", "fileset[application/json]", "Name=name"
    )
    assert load_metadata_tables([table]) == [table]
    table_path.unlink()  # e.g. claimed away with the data
    _, claimed = _claim(tmp_path, ["a.json"])
    filesets = apply_path_metadata(_filesets(claimed, [Json]), NAME_REGEX, claimed)
    (fileset,) = inject_fileset_tables(filesets, [table])
    assert fileset.metadata["Note"] == "first"


def test_load_metadata_tables_checks_join_columns(tmp_path: Path) -> None:
    table = _table(tmp_path / "t.csv", "Name,Note\na,b\n", "fileset", "Missing=name")
    with pytest.raises(ValueError, match="Join column 'Missing' not found"):
        load_metadata_tables([table])


def test_load_metadata_tables_none() -> None:
    assert load_metadata_tables(None) == []
    assert load_metadata_tables([]) == []


def test_loaded_metadata_table_pickles(tmp_path: Path) -> None:
    table_path = tmp_path / "t.csv"
    table = _table(table_path, "Name,Note\na,b\n", "fileset", "Name=name")
    load_metadata_tables([table])
    table_path.unlink()
    assert pickle.loads(pickle.dumps(table)).table == {"Name": ["a"], "Note": ["b"]}


def test_inject_fileset_tables(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["a.json", "b.json", "c.json"])
    filesets = apply_path_metadata(_filesets(claimed, [Json]), NAME_REGEX, claimed)
    tables = load_metadata_tables(
        [
            _table(
                tmp_path / "files.csv",
                "Name,Note\na,first\nb,second\n",
                "fileset[application/json]",
                "Name={name}",
            ),
            # An accession table doesn't apply to file-sets
            _table(
                tmp_path / "acc.csv", "Name,Cohort\na,x\n", "accession", "Name=name"
            ),
        ]
    )
    result = inject_fileset_tables(filesets, tables)
    assert result == filesets
    notes = {f.metadata["name"]: f.metadata.get("Note") for f in result}
    assert notes == {"a": "first", "b": "second", "c": None}
    assert not any("Cohort" in f.metadata for f in result)


def test_inject_fileset_tables_several_rows_raise(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["a.json"])
    filesets = apply_path_metadata(_filesets(claimed, [Json]), NAME_REGEX, claimed)
    table = _table(tmp_path / "t.csv", "Name,Note\na,1\na,2\n", "fileset", "Name=name")
    with pytest.raises(ValueError, match="Multiple rows"):
        inject_fileset_tables(filesets, load_metadata_tables([table]))


def test_inject_fileset_tables_none(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, ["a.json"])
    filesets = _filesets(claimed, [Json])
    assert inject_fileset_tables(filesets) == filesets
    assert inject_fileset_tables(filesets, []) == filesets


def test_table_delivered_with_the_data(tmp_path: Path) -> None:
    """As in the Canfield export: the table is in the input directory, is loaded
    before the claim, and is claimed with the images"""
    inbox = tmp_path / "inbox"
    table = _table(
        inbox / "Dermoscopy" / "LesionData_20260805.csv",
        "ImagePath,LesionID\nsubj/a.json,L1\n",
        "fileset[application/json]",
        "ImagePath={relpath}",
    )
    (inbox / "subj").mkdir()
    (inbox / "subj" / "a.json").write_text("{}")
    load_metadata_tables([table])

    files = sorted(p for p in inbox.rglob("*") if p.is_file())
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    assert not table.table_file.fspath.exists()  # the table was claimed too

    plan = plan_recursion([Json], recursive=True)
    fspaths = expand_claimed_paths(claimed, [Json], plan, recursive=True)
    filesets = classify_paths(fspaths, [Json], plan.ignore_datatypes, [r".*\.csv"])
    filesets = apply_path_metadata(
        filesets,
        [PathMetadataRegex(r".*/(?P<relpath>[^/]+/[^/]+\.json)$", Json)],
        claimed,
    )
    (fileset,) = inject_fileset_tables(filesets, [table])
    assert fileset.metadata["LesionID"] == "L1"
