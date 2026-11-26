"""Tests of `collate_files`, the folder source's run on the collate steps (see
``prefect-migration-docs/ROADMAP.md``, Phase 1, Composites step C4)"""

import json
import typing as ty
from pathlib import Path

import pytest
from fileformats.application import Json
from fileformats.core.exceptions import FormatMismatchError
from fileformats.generic import DirectoryOf
from fileformats.text import Csv

from accessionflow.api.collate import (
    CLAIMED_FILES_DIRNAME,
    CLAIMED_MANIFEST,
    ERROR_MANIFEST,
    UNPROCESSED_MANIFEST,
    list_input_files,
)
from accessionflow.api.collate import claim as claim_module
from accessionflow.api.staging import BUILD_NAME_DEFAULT
from accessionflow.helpers.arg_types import IDSpec, MetadataTable, PathMetadataPattern
from accessionflow.model.accession import Accession
from accessionflow.sources.folder.api import collate_api
from accessionflow.sources.folder.api.collate_api import collate_files

LABEL_FIELDS = {"project": "project", "subject": "sess", "session": "visit"}
SESS_NAME = [PathMetadataPattern("{sess}/{name}.json", Json)]


class Dirs(ty.NamedTuple):
    inbox: Path
    output: Path
    working: Path
    unprocessed: Path
    error: Path


@pytest.fixture
def dirs(tmp_path: Path) -> Dirs:
    output = tmp_path / "out"
    return Dirs(
        inbox=tmp_path / "inbox",
        output=output,
        working=output / "__processing__",
        unprocessed=tmp_path / "unprocessed",
        error=tmp_path / "error",
    )


def _write(root: Path, files: dict[str, str]) -> None:
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _visit_table(tmp_path: Path, *sessions: str) -> MetadataTable:
    """An accession table that gives a visit to the given sessions only"""
    path = tmp_path / "tables" / "visits.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Session,visit\n" + "".join(f"{s},v1\n" for s in sessions))
    return MetadataTable(str(path), "accession", "Session=sess")


def _run(dirs: Dirs, **kwargs: ty.Any) -> list[str]:
    """Lists the inbox and collates its files, as the CLI will"""
    options: dict[str, ty.Any] = dict(
        datatypes=[Json],
        source_roots=[dirs.inbox],
        recursive=True,  # the files are in a directory per session
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata=SESS_NAME,
        constant_labels={"project": "P"},
    )
    options.update(kwargs)
    return collate_files(
        list_input_files([dirs.inbox]),
        dirs.output,
        dirs.working,
        dirs.unprocessed,
        dirs.error,
        LABEL_FIELDS,
        **options,
    )


def _delivered(dirs: Dirs) -> list[str]:
    return sorted(
        p.name
        for p in dirs.output.iterdir()
        if p.name not in (BUILD_NAME_DEFAULT, "__processing__")
    )


def _only_run_dir(parent: Path) -> Path:
    (run_dir,) = parent.iterdir()
    return run_dir


def _reasons(run_dir: Path) -> dict[str, dict[str, ty.Any]]:
    entries = json.loads((run_dir / UNPROCESSED_MANIFEST).read_text())
    return {e["file"]: e for e in entries}


def _files_under(path: Path) -> list[Path]:
    return [p for p in path.rglob("*") if p.is_file()] if path.exists() else []


def test_delivers_and_leaves_the_rest(dirs: Dirs, tmp_path: Path) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/b.json": "{}", "s1/notes.txt": "x"})
    errors = _run(
        dirs,
        allow_unrecognised=[r".*\.txt"],
        metadata_tables=[_visit_table(tmp_path, "s1")],
    )
    assert errors == []
    (name,) = _delivered(dirs)
    assert name.startswith("P.s1.v1_")
    assert sorted(Accession.load(dirs.output / name).acquisitions) == ["a", "b"]
    run_dir = _only_run_dir(dirs.unprocessed)
    assert name.endswith(f"_{run_dir.name}")  # named with the run's UID
    reasons = _reasons(run_dir)
    assert list(reasons) == [f"{CLAIMED_FILES_DIRNAME}/s1/notes.txt"]
    assert reasons[f"{CLAIMED_FILES_DIRNAME}/s1/notes.txt"]["reason"] == "unrecognised"
    assert _files_under(dirs.inbox) == []
    assert _files_under(dirs.working) == []
    assert not (dirs.output / BUILD_NAME_DEFAULT / run_dir.name).exists()
    assert not dirs.error.exists()


def test_accession_that_cant_be_labelled(dirs: Dirs, tmp_path: Path) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s2/b.json": "{}"})
    errors = _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    (error,) = errors
    assert "'s2'" in error
    assert "['visit']" in error
    assert [n.split("_")[0] for n in _delivered(dirs)] == ["P.s1.v1"]
    reasons = _reasons(_only_run_dir(dirs.unprocessed))
    entry = reasons[f"{CLAIMED_FILES_DIRNAME}/s2/b.json"]
    assert entry["reason"] == "failed"
    assert entry["accession"] == "s2"
    assert entry["original"] == str(dirs.inbox / "s2" / "b.json")


def test_run_that_raises_is_moved_to_the_error_dir(dirs: Dirs, tmp_path: Path) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/notes.txt": "x"})
    with pytest.raises(FormatMismatchError) as excinfo:
        _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    assert str(dirs.inbox / "s1" / "notes.txt") in excinfo.value.__notes__[0]
    run_dir = _only_run_dir(dirs.error)
    record = json.loads((run_dir / ERROR_MANIFEST).read_text())
    assert record["type"] == "FormatMismatchError"
    assert sorted(
        p.relative_to(run_dir / CLAIMED_FILES_DIRNAME).as_posix()
        for p in _files_under(run_dir / CLAIMED_FILES_DIRNAME)
    ) == ["s1/a.json", "s1/notes.txt"]
    assert _delivered(dirs) == []
    assert not (dirs.output / BUILD_NAME_DEFAULT / run_dir.name).exists()
    assert not dirs.unprocessed.exists()


def test_raise_errors_abandons_the_run(dirs: Dirs, tmp_path: Path) -> None:
    _write(dirs.inbox, {"s2/b.json": "{}"})
    with pytest.raises(Exception, match="visit"):
        _run(dirs, metadata_tables=[_visit_table(tmp_path)], raise_errors=True)
    run_dir = _only_run_dir(dirs.error)
    assert (run_dir / CLAIMED_FILES_DIRNAME / "s2" / "b.json").exists()


def test_claim_that_raises_partway(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/b.json": "{}", "s1/c.json": "{}"})
    real_claim_one = claim_module._claim_one
    calls: list[Path] = []

    def fail_on_second(src: Path, dest: Path) -> bool:
        calls.append(src)
        if len(calls) == 2:
            raise OSError("disk unplugged")
        return real_claim_one(src, dest)

    monkeypatch.setattr(claim_module, "_claim_one", fail_on_second)
    with pytest.raises(OSError, match="disk unplugged"):
        _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    run_dir = _only_run_dir(dirs.error)
    assert (run_dir / CLAIMED_MANIFEST).exists()
    assert [
        p.relative_to(run_dir / CLAIMED_FILES_DIRNAME).as_posix()
        for p in _files_under(run_dir / CLAIMED_FILES_DIRNAME)
    ] == ["s1/a.json"]
    assert sorted(p.name for p in _files_under(dirs.inbox)) == ["b.json", "c.json"]


def test_files_that_arrive_during_a_run_wait_for_the_next(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The race test: a file added to the input directory after the listing stays there
    and is collated by the next run"""
    _write(dirs.inbox, {"s1/a.json": "{}"})
    real_collect = collate_api.collect_accessions

    def arrive_then_collect(*args: ty.Any, **kwargs: ty.Any) -> ty.Any:
        _write(dirs.inbox, {"s2/late.json": "{}"})
        return real_collect(*args, **kwargs)

    table = _visit_table(tmp_path, "s1", "s2")
    monkeypatch.setattr(collate_api, "collect_accessions", arrive_then_collect)
    assert _run(dirs, metadata_tables=[table]) == []
    assert [p.relative_to(dirs.inbox).as_posix() for p in _files_under(dirs.inbox)] == [
        "s2/late.json"
    ]
    assert [n.split("_")[0] for n in _delivered(dirs)] == ["P.s1.v1"]

    monkeypatch.setattr(collate_api, "collect_accessions", real_collect)
    assert _run(dirs, metadata_tables=[table]) == []
    assert sorted(n.split("_")[0] for n in _delivered(dirs)) == ["P.s1.v1", "P.s2.v1"]
    assert _files_under(dirs.inbox) == []


def test_run_uid_clash_makes_another(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}"})
    taken, free = "20261126010203_aaaaaa", "20261126010203_bbbbbb"
    (dirs.output / BUILD_NAME_DEFAULT / taken).mkdir(parents=True)
    uids = iter([taken, free])
    monkeypatch.setattr(collate_api, "make_run_uid", lambda: next(uids))
    assert _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")]) == []
    assert _delivered(dirs) == [f"P.s1.v1_{free}"]


def test_every_run_uid_taken(
    dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}"})
    taken = "20261126010203_aaaaaa"
    (dirs.output / BUILD_NAME_DEFAULT / taken).mkdir(parents=True)
    monkeypatch.setattr(collate_api, "make_run_uid", lambda: taken)
    with pytest.raises(RuntimeError, match="unused run UID"):
        _run(dirs, metadata_tables=[_visit_table(tmp_path, "s1")])
    assert (dirs.inbox / "s1" / "a.json").exists()
    assert not dirs.working.exists()


def test_source_roots_keep_top_level_directories_whole(
    dirs: Dirs, tmp_path: Path
) -> None:
    """As collate() lists an input directory: without --recursive, each top-level
    directory is classified whole"""
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/b.json": "{}"})
    errors = _run(
        dirs,
        datatypes=[DirectoryOf[Json]],
        recursive=False,
        path_metadata=[PathMetadataPattern("{sess}", DirectoryOf[Json])],
        acquisition_id_field=[IDSpec("sess")],
        metadata_tables=[_visit_table(tmp_path, "s1")],
    )
    assert errors == []
    (name,) = _delivered(dirs)
    accession = Accession.load(dirs.output / name)
    assert list(accession.acquisitions) == ["s1"]


def test_recursive_ignored_directory_recorded_as_ignored(
    dirs: Dirs, tmp_path: Path
) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}", "s1/lesion/data.csv": "a,b\n1,2\n"})
    errors = _run(
        dirs,
        ignore_datatypes=[DirectoryOf[Csv]],
        recursive=True,
        metadata_tables=[_visit_table(tmp_path, "s1")],
    )
    assert errors == []
    entry = _reasons(_only_run_dir(dirs.unprocessed))[
        f"{CLAIMED_FILES_DIRNAME}/s1/lesion/data.csv"
    ]
    assert entry["reason"] == "ignored"
    assert entry["datatype"]


def test_no_input_files(dirs: Dirs) -> None:
    dirs.inbox.mkdir()
    assert _run(dirs) == []
    assert _delivered(dirs) == []
    assert not dirs.working.exists()
    assert not dirs.unprocessed.exists()
    assert not dirs.error.exists()
    assert not (dirs.output / BUILD_NAME_DEFAULT).exists() or not any(
        (dirs.output / BUILD_NAME_DEFAULT).iterdir()
    )


def test_bad_path_metadata_pattern_changes_nothing(dirs: Dirs) -> None:
    _write(dirs.inbox, {"s1/a.json": "{}"})
    with pytest.raises(ValueError, match="Unmatched brace"):
        _run(dirs, path_metadata=[PathMetadataPattern("{sess/{name}.json", Json)])
    assert (dirs.inbox / "s1" / "a.json").exists()
    assert not dirs.output.exists()
