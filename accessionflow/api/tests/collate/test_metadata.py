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
    plan_recursion,
    tag_fileset_types,
)
from accessionflow.helpers.arg_types import PathMetadataPattern, PathMetadataRegex
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
