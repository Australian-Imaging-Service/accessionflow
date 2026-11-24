from pathlib import Path
from types import SimpleNamespace

import pytest

from accessionflow.api.staging import (
    BUILD_NAME_DEFAULT,
    for_each_accession,
    move_into_place,
    prepare_build_dir,
)


def test_prepare_build_dir_creates_it(tmp_path: Path) -> None:
    output_dir = tmp_path / "staged"
    build_dir = prepare_build_dir(output_dir)
    assert build_dir == output_dir / BUILD_NAME_DEFAULT
    assert build_dir.is_dir()
    # Again, now that it exists
    assert prepare_build_dir(output_dir) == build_dir


def _built_accession(parent: Path, acquisitions: list[str]) -> Path:
    saved_dir = parent / "built"
    for acquisition in acquisitions:
        (saved_dir / acquisition).mkdir(parents=True)
        (saved_dir / acquisition / "file.txt").write_text(acquisition)
    return saved_dir


def test_move_into_place(tmp_path: Path) -> None:
    output_dir = tmp_path / "staged"
    output_dir.mkdir()
    saved_dir = _built_accession(prepare_build_dir(output_dir), ["1.t1"])
    dest = move_into_place(saved_dir, output_dir, ["accession"])
    assert dest == output_dir / "accession"
    assert (dest / "1.t1" / "file.txt").read_text() == "1.t1"
    assert not saved_dir.exists()


def test_move_into_place_merges_with_existing(tmp_path: Path) -> None:
    output_dir = tmp_path / "staged"
    (output_dir / "accession" / "1.t1").mkdir(parents=True)
    saved_dir = _built_accession(prepare_build_dir(output_dir), ["2.t2"])
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
