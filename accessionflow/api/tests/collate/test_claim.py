import errno
import os
import pickle
import random
import re
import shutil
import typing as ty
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from accessionflow.api.collate import (
    CLAIMED_FILES_DIRNAME,
    CLAIMED_MANIFEST,
    PROCESSING_NAME_DEFAULT,
    ClaimedFiles,
    claim_input_files,
    finish_claim,
    make_run_uid,
)
from accessionflow.model.accession import Accession

NOW = datetime(2026, 11, 24, 1, 2, 3, tzinfo=UTC)


def test_make_run_uid_format() -> None:
    run_uid = make_run_uid()
    assert re.fullmatch(r"\d{14}_[0-9a-f]{6}", run_uid)
    assert "." not in run_uid and "-" not in run_uid


def test_make_run_uid_injected_clock_and_random_source() -> None:
    run_uid = make_run_uid(now=NOW, rng=random.Random(0))
    assert run_uid == make_run_uid(now=NOW, rng=random.Random(0))
    assert run_uid == f"20261124010203_{random.Random(0).getrandbits(24):06x}"


def test_make_run_uid_converts_to_utc() -> None:
    same_instant = datetime(
        2026, 11, 24, 11, 2, 3, tzinfo=timezone(timedelta(hours=10))
    )
    assert make_run_uid(now=same_instant, rng=random.Random(0)) == make_run_uid(
        now=NOW, rng=random.Random(0)
    )


def test_make_run_uid_default_clock() -> None:
    before = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    timestamp = make_run_uid()[:14]
    after = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    assert before <= timestamp <= after


def test_make_run_uids_sort_by_time() -> None:
    earlier = make_run_uid(now=NOW, rng=random.Random(1))
    later = make_run_uid(now=NOW + timedelta(seconds=1), rng=random.Random(0))
    assert earlier < later


def test_make_run_uid_differs_in_the_same_second() -> None:
    assert make_run_uid(now=NOW, rng=random.Random(0)) != make_run_uid(
        now=NOW, rng=random.Random(1)
    )


def test_make_run_uid_round_trips_through_staged_dirname() -> None:
    """The run UID follows the labels in a staged directory's name, separated by '.'"""
    run_uid = make_run_uid(now=NOW)
    labels, parsed = Accession._labels_from_dirname(f"proj.subj.sess.{run_uid}", {})
    assert parsed == run_uid
    assert labels == {"project": "proj", "subject": "subj", "session": "sess"}


# claim_input_files ----------------------------------------------------------------

RUN_UID = "20261124010203_abc123"


def _tree(root: Path, *relpaths: str) -> list[Path]:
    paths = []
    for relpath in relpaths:
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relpath)
        paths.append(path)
    return paths


def _exdev_rename(*args: ty.Any, **kwargs: ty.Any) -> ty.NoReturn:
    raise OSError(errno.EXDEV, "Invalid cross-device link")


def test_claim_moves_files_keeping_layout(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/b.txt", "sub/deeper/c.txt")
    processing = tmp_path / "out" / PROCESSING_NAME_DEFAULT
    caplog.set_level("WARNING")

    claimed = claim_input_files(files, processing, RUN_UID, source_roots=[inbox])

    run_dir = processing / RUN_UID
    assert claimed.run_dir == run_dir
    assert claimed.base == inbox
    files_dir = run_dir / CLAIMED_FILES_DIRNAME
    assert claimed.files_dir == files_dir
    assert claimed.claimed_roots == [files_dir]
    assert claimed.files == {files_dir / p.relative_to(inbox): p for p in files}
    assert all(p.read_text() == str(p.relative_to(files_dir)) for p in claimed.files)
    assert not any(p.exists() for p in files)
    assert (inbox / "sub" / "deeper").is_dir()  # emptied source dirs are left
    assert (run_dir / CLAIMED_MANIFEST).exists()
    # Moved, not copied, so no warning
    assert not any("different file system" in r.getMessage() for r in caplog.records)


def test_claim_keeps_repeated_names_and_directories_apart(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a/1.dcm", "b/1.dcm", "series.dcm/1", "series.dcm/2")
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    files_dir = claimed.files_dir
    assert sorted(p.relative_to(files_dir).as_posix() for p in claimed.files) == [
        "a/1.dcm",
        "b/1.dcm",
        "series.dcm/1",
        "series.dcm/2",
    ]
    assert (files_dir / "a" / "1.dcm").read_text() == "a/1.dcm"


def test_claim_roots_default_to_file_directories(tmp_path: Path) -> None:
    files = _tree(tmp_path / "in", "x/a.txt", "y/b.txt")
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID)
    assert claimed.base == tmp_path / "in"
    assert claimed.roots == (tmp_path / "in" / "x", tmp_path / "in" / "y")
    assert claimed.claimed_roots == [claimed.files_dir / "x", claimed.files_dir / "y"]


def test_claim_two_source_roots(tmp_path: Path) -> None:
    first = _tree(tmp_path / "site1" / "inbox", "a.txt")
    second = _tree(tmp_path / "site2" / "inbox", "a.txt")
    roots = [tmp_path / "site1" / "inbox", tmp_path / "site2" / "inbox"]
    claimed = claim_input_files(first + second, tmp_path / "proc", RUN_UID, roots)
    assert claimed.base == tmp_path
    assert claimed.claimed_roots == [
        claimed.files_dir / "site1" / "inbox",
        claimed.files_dir / "site2" / "inbox",
    ]
    assert len(claimed.files) == 2


def test_claim_file_outside_roots_raises_before_moving(tmp_path: Path) -> None:
    inside = _tree(tmp_path / "inbox", "a.txt")
    outside = _tree(tmp_path / "elsewhere", "b.txt")
    with pytest.raises(ValueError, match="aren't in any of the source roots"):
        claim_input_files(
            inside + outside, tmp_path / "proc", RUN_UID, [tmp_path / "inbox"]
        )
    assert all(p.exists() for p in inside + outside)
    assert not (tmp_path / "proc").exists()


@pytest.mark.parametrize("run_uid", ["", "a/b", ".x", "__x"])
def test_claim_rejects_invalid_run_uid(tmp_path: Path, run_uid: str) -> None:
    files = _tree(tmp_path / "inbox", "a.txt")
    with pytest.raises(ValueError, match="Invalid run UID for a claim directory"):
        claim_input_files(files, tmp_path / "proc", run_uid)
    assert files[0].exists()
    assert not (tmp_path / "proc").exists()


def test_claim_no_files_creates_nothing(tmp_path: Path) -> None:
    claimed = claim_input_files([], tmp_path / "proc", RUN_UID)
    assert claimed.files == {}
    assert not (tmp_path / "proc").exists()


def test_claim_across_file_systems(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/b.txt")
    mtimes = {p.name: p.stat().st_mtime_ns for p in files}
    monkeypatch.setattr(os, "rename", _exdev_rename)

    with caplog.at_level("WARNING"):
        claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])

    copy_warnings = [
        r.getMessage()
        for r in caplog.records
        if "different file system" in r.getMessage()
    ]
    assert len(copy_warnings) == 1
    assert copy_warnings[0].startswith("2 of 2 files were copied")

    assert len(claimed.files) == 2
    assert not any(p.exists() for p in files)
    assert {p.name: p.stat().st_mtime_ns for p in claimed.files} == mtimes
    assert not list(claimed.run_dir.rglob("*.claiming"))


def test_claim_leaves_file_that_changes_while_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "growing.txt")
    real_copy2 = shutil.copy2

    def copy_then_append(src: ty.Any, dst: ty.Any) -> ty.Any:
        result = real_copy2(src, dst)
        if Path(src).name == "growing.txt":
            with open(src, "a") as f:
                f.write(" more")
        return result

    monkeypatch.setattr(os, "rename", _exdev_rename)
    monkeypatch.setattr(shutil, "copy2", copy_then_append)

    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])

    assert [p.name for p in claimed.files] == ["a.txt"]
    assert (inbox / "growing.txt").read_text() == "growing.txt more"
    assert not list(claimed.run_dir.rglob("*.claiming"))


def test_claim_skips_file_that_disappeared(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "gone.txt")
    files[1].unlink()
    with caplog.at_level("WARNING"):
        claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    assert [p.name for p in claimed.files] == ["a.txt"]
    assert any("disappeared" in r.getMessage() for r in caplog.records)


def test_claim_leaves_files_that_arrive_after_listing(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    listed = _tree(inbox, "a.txt", "b.txt")
    (late,) = _tree(inbox, "late.txt")
    claimed = claim_input_files(listed, tmp_path / "proc", RUN_UID, [inbox])
    assert sorted(p.name for p in claimed.files) == ["a.txt", "b.txt"]
    assert late.read_text() == "late.txt"


def test_claim_retry_after_crash_part_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "1.txt", "2.txt", "3.txt", "4.txt")
    real_rename = os.rename
    calls = []

    def crashing_rename(src: ty.Any, dst: ty.Any) -> None:
        calls.append(src)
        if len(calls) == 3:
            raise RuntimeError("crash")
        real_rename(src, dst)

    monkeypatch.setattr(os, "rename", crashing_rename)
    with pytest.raises(RuntimeError, match="crash"):
        claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    assert sum(p.exists() for p in files) == 2

    calls.clear()
    # The retry is given a different list, but follows the saved plan
    claimed = claim_input_files(files[:1], tmp_path / "proc", RUN_UID, [inbox])
    assert len(calls) == 2  # only the files not claimed yet are moved
    assert sorted(p.name for p in claimed.files) == ["1.txt", "2.txt", "3.txt", "4.txt"]
    assert not any(p.exists() for p in files)

    monkeypatch.setattr(os, "rename", real_rename)
    clean = claim_input_files(
        _tree(tmp_path / "inbox2", "1.txt", "2.txt", "3.txt", "4.txt"),
        tmp_path / "proc",
        "20261124010203_def456",
        [tmp_path / "inbox2"],
    )
    assert sorted(p.relative_to(clean.run_dir) for p in clean.files) == sorted(
        p.relative_to(claimed.run_dir) for p in claimed.files
    )


@pytest.mark.parametrize("source_changed", [False, True])
def test_claim_retry_after_crash_before_source_deleted(
    tmp_path: Path, source_changed: bool
) -> None:
    """A copy across file systems was renamed into place, but the source wasn't
    deleted before the crash"""
    inbox = tmp_path / "inbox"
    (src,) = _tree(inbox, "a.txt")
    processing = tmp_path / "proc"
    claimed = claim_input_files([src], processing, RUN_UID, [inbox])
    (dest,) = claimed.files
    shutil.copy2(dest, src)  # as if the source had never been deleted
    if source_changed:
        src.write_text("a new file with the same name")

    retried = claim_input_files([src], processing, RUN_UID, [inbox])

    assert retried.files == claimed.files
    assert src.exists() is source_changed
    assert dest.read_text() == "a.txt"


def test_claimed_files_load_and_pickle(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/b.txt")
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    assert ClaimedFiles.load(claimed.run_dir) == claimed
    assert pickle.loads(pickle.dumps(claimed)) == claimed
    claimed_path = claimed.files_dir / "sub" / "b.txt"
    assert claimed.original_of(claimed_path) == inbox / "sub" / "b.txt"
    # A directory that holds claimed files, e.g. a directory datatype
    assert claimed.original_of(claimed.files_dir / "sub") == inbox / "sub"
    with pytest.raises(ValueError):
        claimed.original_of(inbox / "sub" / "b.txt")


def test_claim_input_file_named_like_the_manifest(tmp_path: Path) -> None:
    """A file named claimed.json goes with the other files, not over the plan"""
    inbox = tmp_path / "inbox"
    files = _tree(inbox, CLAIMED_MANIFEST, "a.txt")
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    assert len(claimed.files) == 2
    assert (claimed.files_dir / CLAIMED_MANIFEST).read_text() == CLAIMED_MANIFEST
    assert ClaimedFiles.load(claimed.run_dir) == claimed  # the plan is intact
    assert not any(p.exists() for p in files)


def test_claim_run_dir_is_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _tree(tmp_path / "inbox", "a.txt")
    claimed = claim_input_files(files, Path("proc"), RUN_UID, [tmp_path / "inbox"])
    assert claimed.run_dir == tmp_path / "proc" / RUN_UID
    # A relative path to a claimed file is mapped too
    assert claimed.original_of(
        Path("proc") / RUN_UID / CLAIMED_FILES_DIRNAME / "a.txt"
    ) == (tmp_path / "inbox" / "a.txt")


# finish_claim ---------------------------------------------------------------------


def test_finish_claim_removes_run_dir_when_all_staged(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/b.txt", "sub/deeper/c.txt")
    processing = tmp_path / "out" / PROCESSING_NAME_DEFAULT
    claimed = claim_input_files(files, processing, RUN_UID, [inbox])
    for path in claimed.files:
        path.unlink()  # as stage_accession does
    assert finish_claim(claimed) == []
    assert not claimed.run_dir.exists()
    assert processing.is_dir()


def test_finish_claim_keeps_and_reports_leftovers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/notes.txt", "other/deeper/c.txt")
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    notes = claimed.files_dir / "sub" / "notes.txt"
    for path in claimed.files:
        if path != notes:
            path.unlink()
    with caplog.at_level("WARNING"):
        assert finish_claim(claimed) == [notes]
    assert (claimed.run_dir / CLAIMED_MANIFEST).exists()
    assert ClaimedFiles.load(claimed.run_dir).files == {
        notes: inbox / "sub" / "notes.txt"
    }
    assert not (claimed.files_dir / "other").exists()  # empty directories pruned
    (warning,) = [
        r.getMessage() for r in caplog.records if "weren't staged" in r.getMessage()
    ]
    assert warning.startswith("Leaving 1 files")
    assert str(claimed.run_dir) in warning


def test_finish_claim_removes_partial_copies(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt")
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    (claimed.files_dir / "a.txt").unlink()
    (claimed.files_dir / ".b.txt.claiming").write_text("a copy stopped part way")
    assert finish_claim(claimed) == []
    assert not claimed.run_dir.exists()


def test_finish_claim_without_run_dir(tmp_path: Path) -> None:
    empty = claim_input_files([], tmp_path / "proc", RUN_UID)
    assert finish_claim(empty) == []
    files = _tree(tmp_path / "inbox", "a.txt")
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [tmp_path / "inbox"])
    for path in claimed.files:
        path.unlink()
    assert finish_claim(claimed) == []
    assert finish_claim(claimed) == []  # again


def test_steps_end_to_end_with_a_leftover(tmp_path: Path) -> None:
    """Claims, collects and stages one accession, leaving the file no datatype took"""
    from fileformats.application import Json

    from accessionflow.api.collate import (
        apply_path_metadata,
        classify_paths,
        expand_claimed_paths,
        group_into_accessions,
        plan_recursion,
        stage_accession,
    )
    from accessionflow.api.staging import prepare_build_dir, remove_build_dir
    from accessionflow.helpers.arg_types import IDSpec, PathMetadataRegex
    from accessionflow.model.accession import Accession

    inbox = tmp_path / "inbox"
    files = _tree(inbox, "s1/a.json", "s1/b.json", "s1/notes.txt")
    for path in files[:2]:
        path.write_text(f'{{"{path.stem}": 1}}')
    output_dir = tmp_path / "out"
    build_dir = prepare_build_dir(output_dir, RUN_UID)
    claimed = claim_input_files(
        files, output_dir / PROCESSING_NAME_DEFAULT, RUN_UID, [inbox]
    )
    plan = plan_recursion([Json], recursive=True)
    filesets = classify_paths(
        expand_claimed_paths(claimed, [Json], plan, recursive=True),
        [Json],
        plan.ignore_datatypes,
        allow_unrecognised=[r".*\.txt"],
    )
    filesets = apply_path_metadata(
        filesets,
        [PathMetadataRegex(r".*/(?P<sess>[^/]+)/(?P<name>[^/]+)\.json$", Json)],
        claimed,
    )
    (accession,) = group_into_accessions(filesets, [IDSpec("sess")], [IDSpec("name")])
    staged_dir = stage_accession(accession, build_dir, output_dir, claimed)

    assert finish_claim(claimed) == [claimed.files_dir / "s1" / "notes.txt"]
    assert remove_build_dir(build_dir) == []
    assert sorted(Accession.load(staged_dir).acquisitions) == ["a", "b"]
    assert not any(p.exists() for p in files)  # all three were claimed
