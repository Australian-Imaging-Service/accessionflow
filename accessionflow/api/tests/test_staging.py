from pathlib import Path
from types import SimpleNamespace

import pytest

from accessionflow.api.staging import (
    BUILD_NAME_DEFAULT,
    for_each_accession,
    move_into_place,
    prepare_build_dir,
    remove_build_dir,
)


def test_prepare_build_dir_creates_it(tmp_path: Path) -> None:
    output_dir = tmp_path / "staged"
    build_dir = prepare_build_dir(output_dir, "run1")
    assert build_dir == output_dir / BUILD_NAME_DEFAULT / "run1"
    assert build_dir.is_dir()
    # Again, now that it exists
    assert prepare_build_dir(output_dir, "run1") == build_dir
    # Another run builds alongside it
    assert prepare_build_dir(output_dir, "run2").parent == build_dir.parent


@pytest.mark.parametrize("run_uid", ["", "a/b", ".x", "__x", ".."])
def test_prepare_build_dir_rejects_invalid_run_uid(
    tmp_path: Path, run_uid: str
) -> None:
    with pytest.raises(ValueError, match="Invalid run UID"):
        prepare_build_dir(tmp_path / "staged", run_uid)
    assert not (tmp_path / "staged").exists()


def test_remove_build_dir_removes_empty_run_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "staged"
    build_dir = prepare_build_dir(output_dir, "run1")
    assert remove_build_dir(build_dir) == []
    assert not build_dir.exists()
    assert (output_dir / BUILD_NAME_DEFAULT).is_dir()
    # Already gone
    assert remove_build_dir(build_dir) == []


def test_remove_build_dir_keeps_leftovers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_dir = prepare_build_dir(tmp_path / "staged", "run1")
    (build_dir / "partial").mkdir()
    with caplog.at_level("WARNING"):
        assert remove_build_dir(build_dir) == [build_dir / "partial"]
    assert build_dir.is_dir()
    assert any("Leaving build directory" in r.getMessage() for r in caplog.records)


def _built_accession(parent: Path, acquisitions: list[str]) -> Path:
    saved_dir = parent / "built"
    for acquisition in acquisitions:
        (saved_dir / acquisition).mkdir(parents=True)
        (saved_dir / acquisition / "file.txt").write_text(acquisition)
    return saved_dir


def test_move_into_place(tmp_path: Path) -> None:
    output_dir = tmp_path / "staged"
    output_dir.mkdir()
    saved_dir = _built_accession(prepare_build_dir(output_dir, "run1"), ["1.t1"])
    dest = move_into_place(saved_dir, output_dir, ["accession"])
    assert dest == output_dir / "accession"
    assert (dest / "1.t1" / "file.txt").read_text() == "1.t1"
    assert not saved_dir.exists()


def test_move_into_place_merges_with_existing(tmp_path: Path) -> None:
    output_dir = tmp_path / "staged"
    (output_dir / "accession" / "1.t1").mkdir(parents=True)
    saved_dir = _built_accession(prepare_build_dir(output_dir, "run1"), ["2.t2"])
    dest = move_into_place(saved_dir, output_dir, ["accession"])
    assert sorted(p.name for p in dest.iterdir()) == ["1.t1", "2.t2"]
    assert not saved_dir.exists()


def test_for_each_accession_collects_errors_and_continues() -> None:
    accessions = [
        SimpleNamespace(name="a", uid="1"),
        SimpleNamespace(name=None, uid="2"),
        SimpleNamespace(name="c", uid="3"),
    ]
    done = []

    def step(accession: SimpleNamespace) -> None:
        if accession.uid in ("1", "2"):
            raise ValueError(f"bad {accession.uid}")
        done.append(accession.uid)

    errors = for_each_accession(accessions, step, "Testing")
    assert done == ["3"]
    assert len(errors) == 2
    # Named by name, or by UID when it has no name
    assert errors[0].startswith("Skipping 'a' due to an error: \"bad 1\"")
    assert errors[1].startswith("Skipping '2' due to an error: \"bad 2\"")


def test_for_each_accession_name_of() -> None:
    def step(accession: str) -> None:
        raise ValueError("bad")

    errors = for_each_accession(["x"], step, "Testing", name_of=str.upper)
    assert errors[0].startswith("Skipping 'X'")


def test_for_each_accession_raises_errors() -> None:
    done = []

    def step(accession: int) -> None:
        if accession == 1:
            raise ValueError("bad")
        done.append(accession)

    with pytest.raises(ValueError, match="bad"):
        for_each_accession([0, 1, 2], step, "Testing", raise_errors=True)
    assert done == [0]


def test_for_each_accession_without_errors() -> None:
    assert for_each_accession([1, 2], lambda a: None, "Testing") == []
