from pathlib import Path

import pytest
from fileformats.application import Json, Zip
from fileformats.core import FileSet
from fileformats.core.exceptions import FormatMismatchError
from fileformats.generic import Directory, DirectoryOf
from fileformats.medimage import DicomSeries
from fileformats.text import Csv, Plain

from accessionflow.api.collate import (
    ClaimedFiles,
    RecursionPlan,
    check_datatypes,
    claim_input_files,
    classify_paths,
    disable_metadata_reading,
    drop_ignored_filesets,
    expand_claimed_paths,
    plan_recursion,
)


def test_check_datatypes_distinct_passes() -> None:
    check_datatypes([DicomSeries], [Json, Zip])
    check_datatypes([DicomSeries, Json])


def test_check_datatypes_overlap_names_only_overlapping_sorted() -> None:
    with pytest.raises(ValueError, match="listed for both") as excinfo:
        check_datatypes([DicomSeries, Json], [Json, Zip, DicomSeries])
    message = str(excinfo.value)
    assert message.endswith("['application/json', 'medimage/dicom-series']")
    assert "zip" not in message


def test_check_datatypes_parametrised_types() -> None:
    check_datatypes([DirectoryOf[Json]], [DirectoryOf[Csv]])
    with pytest.raises(ValueError, match="listed for both"):
        check_datatypes([DirectoryOf[Json]], [DirectoryOf[Json]])


@pytest.mark.parametrize(
    "datatypes, ignore_datatypes, recursive, expected",
    [
        ([DicomSeries], [], False, (False, [])),
        # the generic types are only rejected with recursion
        ([Directory], [], False, (False, [])),
        # recursion over files only: bare directories are ignored
        ([DicomSeries], [Json], True, (False, [Json, Directory])),
        # a directory format, wanted or ignored, makes the walk prune on a match
        ([DirectoryOf[Json]], [], True, (True, [])),
        ([Json], [DirectoryOf[Csv]], True, (True, [DirectoryOf[Csv]])),
        ([DicomSeries], [Directory], True, (True, [Directory])),
    ],
)
def test_plan_recursion(
    datatypes: list[type[FileSet]],
    ignore_datatypes: list[type[FileSet]],
    recursive: bool,
    expected: tuple[bool, list[type[FileSet]]],
) -> None:
    assert plan_recursion(datatypes, ignore_datatypes, recursive) == expected


@pytest.mark.parametrize(
    "generic, name", [(Directory, "generic/directory"), (FileSet, "core/file-set")]
)
def test_plan_recursion_rejects_generic_types(
    generic: type[FileSet], name: str
) -> None:
    with pytest.raises(ValueError, match="generic/directory") as excinfo:
        plan_recursion([Json, generic], recursive=True)
    assert f"'{name}'" in str(excinfo.value)


def test_plan_recursion_doesnt_change_its_input() -> None:
    ignore_datatypes = [Json]
    plan = plan_recursion([DicomSeries], ignore_datatypes, recursive=True)
    assert ignore_datatypes == [Json]
    assert plan.ignore_datatypes is not ignore_datatypes


def test_recursion_plan_fields() -> None:
    plan = plan_recursion([DirectoryOf[Json]], recursive=True)
    assert isinstance(plan, RecursionPlan)
    recurse_into_dirs, ignore_datatypes = plan
    assert plan.recurse_into_dirs is recurse_into_dirs is True
    assert plan.ignore_datatypes == ignore_datatypes == []


# expand_claimed_paths -------------------------------------------------------------

RUN_UID = "20261124010203_abc123"


def _claim_tree(
    tmp_path: Path, relpaths: list[str], source_roots: list[str] | None = None
) -> ClaimedFiles:
    inbox = tmp_path / "inbox"
    files = []
    for relpath in relpaths:
        path = inbox / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "a,b\n1,2\n")
        files.append(path)
    roots = [inbox / r for r in source_roots] if source_roots is not None else [inbox]
    return claim_input_files(files, tmp_path / "proc", RUN_UID, roots)


def _expand(
    claimed: ClaimedFiles,
    datatypes: list[type[FileSet]],
    ignore_datatypes: list[type[FileSet]] = [],
    recursive: bool = False,
) -> list[str]:
    plan = plan_recursion(datatypes, ignore_datatypes, recursive)
    expanded = expand_claimed_paths(claimed, datatypes, plan, recursive)
    return [p.relative_to(claimed.files_dir).as_posix() for p in expanded]


def test_expand_without_recursion_gives_top_level_entries(tmp_path: Path) -> None:
    claimed = _claim_tree(
        tmp_path, ["a.txt", "series/1.dcm", "series/2.dcm", "x/y/z.txt"]
    )
    assert _expand(claimed, [DicomSeries]) == ["a.txt", "series", "x"]


def test_expand_flat_recursion_gives_every_file(tmp_path: Path) -> None:
    claimed = _claim_tree(tmp_path, ["a.json", "x/b.json", "x/y/c.json"])
    assert _expand(claimed, [Json], recursive=True) == [
        "a.json",
        "x/b.json",
        "x/y/c.json",
    ]


def test_expand_recursion_prunes_on_directory_datatypes(tmp_path: Path) -> None:
    """Ported from model/tests/test_accession.py::test_recursive_collect_prunes_on_match"""
    claimed = _claim_tree(
        tmp_path,
        [
            "analysis/result.json",  # the wanted directory, yielded whole
            "analysis/notes.txt",
            "lesion/data.csv",  # an ignored directory, yielded whole
            "plain/deep/result.json",  # found by descending 'plain'
            "scan.txt",  # a loose file
        ],
    )
    assert _expand(
        claimed, [DirectoryOf[Json]], [DirectoryOf[Csv]], recursive=True
    ) == ["analysis", "lesion", "plain/deep", "scan.txt"]


def test_expand_returns_only_claimed_entries(tmp_path: Path) -> None:
    claimed = _claim_tree(tmp_path, ["a.txt", "sub/b.txt"])
    (claimed.files_dir / ".c.txt.claiming").write_text("left by a crash")
    (claimed.files_dir / "sub" / "stray.txt").write_text("not claimed")
    (claimed.files_dir / "stray_dir").mkdir()
    assert _expand(claimed, [Json]) == ["a.txt", "sub"]
    assert _expand(claimed, [Json], recursive=True) == ["a.txt", "sub/b.txt"]


def test_expand_overlapping_roots_lists_once(tmp_path: Path) -> None:
    claimed = _claim_tree(tmp_path, ["a.txt", "sub/b.txt"], source_roots=["", "sub"])
    assert _expand(claimed, [Json]) == ["a.txt", "sub"]


def test_expand_two_source_roots(tmp_path: Path) -> None:
    claimed = _claim_tree(
        tmp_path, ["site1/a.txt", "site2/s.dcm/1"], source_roots=["site1", "site2"]
    )
    assert _expand(claimed, [Json]) == ["site1/a.txt", "site2/s.dcm"]


def test_expand_empty_claim(tmp_path: Path) -> None:
    claimed = claim_input_files([], tmp_path / "proc", RUN_UID)
    assert _expand(claimed, [Json]) == []


# classify_paths -------------------------------------------------------------------


def _classify(
    tmp_path: Path,
    relpaths: list[str],
    datatypes: list[type[FileSet]],
    ignore_datatypes: list[type[FileSet]] = [],
    allow_unrecognised: list[str] = [],
) -> list[FileSet]:
    claimed = _claim_tree(tmp_path, relpaths)
    plan = plan_recursion(datatypes, ignore_datatypes)
    fspaths = expand_claimed_paths(claimed, datatypes, plan)
    return classify_paths(fspaths, datatypes, plan.ignore_datatypes, allow_unrecognised)


def _names(filesets: list[FileSet]) -> list[tuple[str, str]]:
    return sorted((type(f).__name__, f.fspath.name) for f in filesets)


def test_classify_returns_wanted_and_ignored(tmp_path: Path) -> None:
    filesets = _classify(tmp_path, ["a.json", "b.csv"], [Json], [Csv])
    assert _names(filesets) == [("Csv", "b.csv"), ("Json", "a.json")]


def test_classify_wanted_datatype_wins(tmp_path: Path) -> None:
    (fileset,) = _classify(
        tmp_path, ["d/x.json", "d/y.json"], [DirectoryOf[Json]], [Directory]
    )
    assert isinstance(fileset, DirectoryOf[Json])


def test_classify_unrecognised_raises(tmp_path: Path) -> None:
    with pytest.raises(FormatMismatchError, match="notes.txt"):
        _classify(tmp_path, ["a.json", "notes.txt"], [Json])


@pytest.mark.parametrize(
    "allow_unrecognised, raises",
    [
        ([r".*\.txt"], False),
        ([r".*\.md"], True),
        ([r".*\.md", r".*\.txt"], False),
        (["notes"], False),  # matched from the start of the base name
        (["otes"], True),
    ],
)
def test_classify_allow_unrecognised(
    tmp_path: Path, allow_unrecognised: list[str], raises: bool
) -> None:
    if raises:
        with pytest.raises(FormatMismatchError):
            _classify(tmp_path, ["a.json", "notes.txt"], [Json], [], allow_unrecognised)
    else:
        filesets = _classify(
            tmp_path, ["a.json", "notes.txt"], [Json], [], allow_unrecognised
        )
        assert _names(filesets) == [("Json", "a.json")]


def test_classify_no_paths() -> None:
    assert classify_paths([], [Json]) == []


def test_classify_after_recursive_expansion(tmp_path: Path) -> None:
    """Mirrors model/tests/test_accession.py::
    test_from_paths_recursive_pulls_nested_directory_datatype up to classification"""
    claimed = _claim_tree(
        tmp_path,
        [
            "analysis/result.json",
            "analysis/notes.txt",
            "lesion/data.csv",
            "plain/deep/result.json",
            "scan.txt",
        ],
    )
    datatypes: list[type[FileSet]] = [DirectoryOf[Json]]
    plan = plan_recursion(datatypes, [DirectoryOf[Csv], Plain], recursive=True)
    fspaths = expand_claimed_paths(claimed, datatypes, plan, recursive=True)
    filesets = classify_paths(fspaths, datatypes, plan.ignore_datatypes)
    assert sorted(
        (type(f).__name__, f.fspath.relative_to(claimed.files_dir).as_posix())
        for f in filesets
    ) == [
        ("DirectoryOf[Csv]", "lesion"),
        ("DirectoryOf[Json]", "analysis"),
        ("DirectoryOf[Json]", "plain/deep"),
        ("Plain", "scan.txt"),
    ]
    # Dropping the ignored leaves the acquisitions that are collated
    kept = drop_ignored_filesets(filesets, datatypes, plan.ignore_datatypes)
    assert sorted(f.fspath.name for f in kept) == ["analysis", "deep"]


def test_check_datatypes_rejects_none() -> None:
    with pytest.raises(ValueError, match="At least one datatype"):
        check_datatypes([])


# disable_metadata_reading ---------------------------------------------------------


def test_disable_metadata_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesets = _classify(
        tmp_path, ["a.json", "b.csv", "d/x.json"], [Json, Csv, DirectoryOf[Json]]
    )
    # Stands in for reading a header, which plain JSON and CSV files don't have
    monkeypatch.setattr(
        FileSet, "_loaded_metadata", property(lambda self: {"from_header": 1})
    )
    for fileset in filesets:
        fileset.metadata["from_path"] = "p"

    # Directory matches DirectoryOf[Json] by isinstance
    result = disable_metadata_reading(filesets, [Json, Directory])

    assert result == filesets
    by_type = {type(f).__name__: dict(f.metadata) for f in result}
    assert by_type == {
        "Json": {"from_path": "p"},
        "DirectoryOf[Json]": {"from_path": "p"},
        "Csv": {"from_path": "p", "from_header": 1},
    }


def test_disable_metadata_reading_with_no_datatypes(tmp_path: Path) -> None:
    filesets = _classify(tmp_path, ["a.json"], [Json])
    assert disable_metadata_reading(filesets) == filesets
    assert not filesets[0].metadata.read_disabled


# drop_ignored_filesets ------------------------------------------------------------


def test_drop_ignored_filesets(tmp_path: Path) -> None:
    filesets = _classify(tmp_path, ["a.json", "b.csv"], [Json], [Csv])
    kept = drop_ignored_filesets(filesets, [Json], [Csv])
    assert _names(kept) == [("Json", "a.json")]
    assert len(filesets) == 2  # the input isn't changed


def test_drop_ignored_filesets_keeps_wanted_subclass(tmp_path: Path) -> None:
    filesets = _classify(tmp_path, ["d/x.json"], [DirectoryOf[Json]], [Directory])
    assert isinstance(filesets[0], Directory)
    assert drop_ignored_filesets(filesets, [DirectoryOf[Json]], [Directory]) == filesets


def test_drop_ignored_filesets_with_none_ignored(tmp_path: Path) -> None:
    filesets = _classify(tmp_path, ["a.json"], [Json])
    kept = drop_ignored_filesets(filesets, [Json])
    assert kept == filesets
    assert kept is not filesets


def test_classify_returns_filesets_sorted_by_path(tmp_path: Path) -> None:
    relpaths = ["c.json", "a.json", "d.json", "b.json"]
    filesets = _classify(tmp_path, relpaths, [Json])
    paths = [str(f.fspath) for f in filesets]
    assert paths == sorted(paths)
