from pathlib import Path

import pytest
from fileformats.application import Json, Zip
from fileformats.core import FileSet
from fileformats.generic import Directory, DirectoryOf
from fileformats.medimage import DicomSeries
from fileformats.text import Csv

from accessionflow.api.collate import (
    ClaimedFiles,
    RecursionPlan,
    check_datatypes,
    claim_input_files,
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

RUN_UID = "abc12320261124010203"


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
            "lesion/data.csv",  # an ignored directory, skipped whole
            "plain/deep/result.json",  # found by descending 'plain'
            "scan.txt",  # a loose file
        ],
    )
    assert _expand(
        claimed, [DirectoryOf[Json]], [DirectoryOf[Csv]], recursive=True
    ) == ["analysis", "plain/deep", "scan.txt"]


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
