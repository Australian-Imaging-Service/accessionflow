import os
import sys
from pathlib import Path

import pytest

from accessionflow.api.collate import list_input_files


def _touch(root: Path, *relpaths: str) -> None:
    for relpath in relpaths:
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relpath)


def _rel(fspaths: list[Path], root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in fspaths]


def test_directory_lists_all_files_sorted(tmp_path: Path) -> None:
    _touch(tmp_path, "b.txt", "a.txt", "series/2.dcm", "series/1.dcm", "x/y/z.txt")
    assert _rel(list_input_files([tmp_path]), tmp_path) == [
        "a.txt",
        "b.txt",
        "series/1.dcm",
        "series/2.dcm",
        "x/y/z.txt",
    ]


def test_directory_given_as_str(tmp_path: Path) -> None:
    _touch(tmp_path, "a.txt")
    assert _rel(list_input_files([str(tmp_path)]), tmp_path) == ["a.txt"]


def test_hidden_files_and_dirs_skipped(tmp_path: Path) -> None:
    _touch(
        tmp_path,
        "a.txt",
        ".a.txt.Xy12",  # an rsync upload in progress
        "sub/.DS_Store",
        "sub/b.txt",
        ".hidden/c.txt",
        "sub/.partial/d.txt",
    )
    assert _rel(list_input_files([tmp_path]), tmp_path) == ["a.txt", "sub/b.txt"]


def test_hidden_file_named_explicitly_is_listed(tmp_path: Path) -> None:
    _touch(tmp_path, ".named.txt")
    assert list_input_files([tmp_path / ".named.txt"]) == [tmp_path / ".named.txt"]


def test_glob_lists_files_and_walks_dirs(tmp_path: Path) -> None:
    _touch(tmp_path, "a.dcm", "b.txt", "s1.dcm/1", "s1.dcm/2", "sub/c.dcm")
    assert _rel(list_input_files([f"{tmp_path}/*.dcm"]), tmp_path) == [
        "a.dcm",
        "s1.dcm/1",
        "s1.dcm/2",
    ]
    assert _rel(list_input_files([f"{tmp_path}/**/*.dcm"]), tmp_path) == [
        "a.dcm",
        "s1.dcm/1",
        "s1.dcm/2",
        "sub/c.dcm",
    ]


def test_glob_without_matches_lists_nothing(tmp_path: Path) -> None:
    assert list_input_files([f"{tmp_path}/*.nothing"]) == []


@pytest.mark.parametrize("as_str", [True, False])
def test_missing_path_raises(tmp_path: Path, as_str: bool) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="does not exist"):
        list_input_files([str(missing) if as_str else missing])


def test_exclude_by_relative_depth(tmp_path: Path) -> None:
    """Ported from test_from_paths_exclude_path_drops_recognised_by_relative_depth"""
    root = tmp_path / "root"
    _touch(root, "subject/shallow.txt", "uuid/stamp/deep.txt")
    assert _rel(list_input_files([root], exclude_paths=["*/*/*.txt"]), root) == [
        "subject/shallow.txt"
    ]


def test_exclude_directory_drops_its_contents(tmp_path: Path) -> None:
    _touch(tmp_path, "a.png", "thumbs/b.png", "thumbs/deep/c.png", "keep/thumbs.png")
    assert _rel(list_input_files([tmp_path], exclude_paths=["thumbs"]), tmp_path) == [
        "a.png",
        "keep/thumbs.png",
    ]


def test_exclude_double_star(tmp_path: Path) -> None:
    _touch(tmp_path, "a.png", "x/b.png", "x/c.txt")
    assert _rel(list_input_files([tmp_path], exclude_paths=["**/*.png"]), tmp_path) == [
        "x/c.txt"
    ]


def test_exclude_doesnt_apply_outside_input_dirs(tmp_path: Path) -> None:
    _touch(tmp_path, "a.png", "b.png")
    assert _rel(
        list_input_files([tmp_path / "a.png", f"{tmp_path}/b*"], exclude_paths=["*"]),
        tmp_path,
    ) == ["a.png", "b.png"]


def test_overlapping_inputs_listed_once(tmp_path: Path) -> None:
    _touch(tmp_path, "a.txt", "sub/b.txt")
    listed = list_input_files(
        [tmp_path, f"{tmp_path}/sub/*", tmp_path / "a.txt", tmp_path]
    )
    assert _rel(listed, tmp_path) == ["a.txt", "sub/b.txt"]


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX symlinks")
def test_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _touch(root, "sub/a.txt")
    _touch(tmp_path, "target.txt")
    (root / "sub" / "loop").symlink_to(root, target_is_directory=True)
    (root / "link.txt").symlink_to(tmp_path / "target.txt")
    assert _rel(list_input_files([root]), root) == ["link.txt", "sub/a.txt"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs os.mkfifo")
def test_fifo_skipped(tmp_path: Path) -> None:
    _touch(tmp_path, "a.txt")
    os.mkfifo(tmp_path / "pipe")
    assert _rel(list_input_files([tmp_path]), tmp_path) == ["a.txt"]


# metadata_table_paths -------------------------------------------------------------

TABLE = "Dermoscopy/LesionData.csv"


def test_metadata_table_in_input_dir_left_out(tmp_path: Path) -> None:
    _touch(tmp_path, "s1/a.png", TABLE)
    listed = list_input_files([tmp_path], metadata_table_paths=[tmp_path / TABLE])
    assert _rel(listed, tmp_path) == ["s1/a.png"]


def test_metadata_table_outside_inputs_changes_nothing(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    _touch(inbox, "s1/a.png")
    _touch(tmp_path, "tables/LesionData.csv")
    listed = list_input_files(
        [inbox], metadata_table_paths=[tmp_path / "tables" / "LesionData.csv"]
    )
    assert _rel(listed, inbox) == ["s1/a.png"]


def test_metadata_table_matched_however_spelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _touch(tmp_path, "s1/a.png", TABLE)
    monkeypatch.chdir(tmp_path)
    for spelling in (Path(TABLE), tmp_path / "s1" / ".." / TABLE):
        listed = list_input_files([tmp_path], metadata_table_paths=[spelling])
        assert _rel(listed, tmp_path) == ["s1/a.png"]


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX symlinks")
def test_metadata_table_named_through_a_symlink(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    _touch(inbox, "s1/a.png", TABLE)
    link = tmp_path / "current-table.csv"
    link.symlink_to(inbox / TABLE)
    listed = list_input_files([inbox], metadata_table_paths=[link])
    assert _rel(listed, inbox) == ["s1/a.png"]


def test_same_name_in_another_directory_is_listed(tmp_path: Path) -> None:
    _touch(tmp_path, TABLE, "other/LesionData.csv")
    listed = list_input_files([tmp_path], metadata_table_paths=[tmp_path / TABLE])
    assert _rel(listed, tmp_path) == ["other/LesionData.csv"]


def test_metadata_table_from_glob_or_named_input_left_out(tmp_path: Path) -> None:
    _touch(tmp_path, "s1/a.csv", TABLE)
    table = tmp_path / TABLE
    by_glob = list_input_files([f"{tmp_path}/**/*.csv"], metadata_table_paths=[table])
    assert _rel(by_glob, tmp_path) == ["s1/a.csv"]
    assert list_input_files([table], metadata_table_paths=[table]) == []


def test_missing_metadata_table_ignored(tmp_path: Path) -> None:
    _touch(tmp_path, "a.png")
    listed = list_input_files(
        [tmp_path], metadata_table_paths=[tmp_path / "missing.csv"]
    )
    assert _rel(listed, tmp_path) == ["a.png"]
