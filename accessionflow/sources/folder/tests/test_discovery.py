from pathlib import Path

import pytest

from accessionflow.sources.folder.discovery import find_files, glob_to_regex


def _tree(root: Path) -> Path:
    (root / "sub" / "deeper").mkdir(parents=True)
    (root / "top.txt").write_text("top")
    (root / "sub" / "mid.txt").write_text("mid")
    (root / "sub" / "deeper" / "low.txt").write_text("low")
    return root


def _rel(files: list[Path], root: Path) -> set[str]:
    return {str(f.relative_to(root)) for f in files}


def test_find_files_directory_lists_only_its_files(tmp_path: Path) -> None:
    root = _tree(tmp_path / "root")
    assert _rel(find_files([str(root)]), root) == {"top.txt"}


def test_find_files_recursive_flattens_the_tree(tmp_path: Path) -> None:
    root = _tree(tmp_path / "root")
    assert _rel(find_files([root], recursive=True), root) == {
        "top.txt",
        "sub/mid.txt",
        "sub/deeper/low.txt",
    }


def test_find_files_glob_skips_directories(tmp_path: Path) -> None:
    root = _tree(tmp_path / "root")
    assert _rel(find_files([f"{root}/**/*"]), root) == {
        "top.txt",
        "sub/mid.txt",
        "sub/deeper/low.txt",
    }


def test_find_files_file_path_is_passed_through(tmp_path: Path) -> None:
    root = _tree(tmp_path / "root")
    assert _rel(find_files([root / "sub" / "mid.txt"]), root) == {"sub/mid.txt"}


def test_find_files_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        find_files([tmp_path / "missing"])


def test_find_files_exclude_path_matches_relative_depth(tmp_path: Path) -> None:
    """--exclude-path matches the path *relative to the input dir*, so it drops a
    3-deep .txt while sparing the same type 2 deep."""
    root = tmp_path / "root"
    (root / "subject").mkdir(parents=True)
    (root / "subject" / "shallow.txt").write_text("keep")  # relative depth 2
    (root / "uuid" / "stamp").mkdir(parents=True)
    (root / "uuid" / "stamp" / "deep.txt").write_text("drop")  # relative depth 3

    files = find_files([root], recursive=True, exclude_paths=["*/*/*.txt"])

    assert _rel(files, root) == {"subject/shallow.txt"}


@pytest.mark.parametrize(
    "pattern, path, matches",
    [
        ("*/*/*.png", "a/b/c.png", True),
        ("*/*/*.png", "a/c.png", False),
        ("*/*/*.png", "w/x/y/z.png", False),
        ("**/*.png", "a.png", True),
        ("**/*.png", "a/b/c.png", True),
        ("**/*.png", "a/b/c.txt", False),
        ("**/[XY]P.png", "u/2026/XP.png", True),
        ("**/[XY]P.png", "u/2026/ZP.png", False),
        ("*.txt", "a.txt", True),
        ("*.txt", "a/b.txt", False),
    ],
)
def test_glob_to_regex(pattern: str, path: str, matches: bool) -> None:
    assert bool(glob_to_regex(pattern).match(path)) is matches
