import errno
import json
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
    ERROR_MANIFEST,
    PROCESSING_NAME_DEFAULT,
    UNPROCESSED_MANIFEST,
    ClaimedFiles,
    ClaimInputFiles,
    FinishClaim,
    ReserveRunUid,
    claim_run_dir,
    has_claim_plan,
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

    claimed = ClaimInputFiles(processing, tmp_path / "error").act(
        files, RUN_UID, source_roots=[inbox]
    )

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
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        files, RUN_UID, [inbox]
    )
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
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(files, RUN_UID)
    assert claimed.base == tmp_path / "in"
    assert claimed.roots == (tmp_path / "in" / "x", tmp_path / "in" / "y")
    assert claimed.claimed_roots == [claimed.files_dir / "x", claimed.files_dir / "y"]


def test_claim_two_source_roots(tmp_path: Path) -> None:
    first = _tree(tmp_path / "site1" / "inbox", "a.txt")
    second = _tree(tmp_path / "site2" / "inbox", "a.txt")
    roots = [tmp_path / "site1" / "inbox", tmp_path / "site2" / "inbox"]
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        first + second, RUN_UID, roots
    )
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
        ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
            inside + outside, RUN_UID, [tmp_path / "inbox"]
        )
    assert all(p.exists() for p in inside + outside)
    assert not (tmp_path / "proc").exists()


@pytest.mark.parametrize("run_uid", ["", "a/b", ".x", "__x"])
def test_claim_rejects_invalid_run_uid(tmp_path: Path, run_uid: str) -> None:
    files = _tree(tmp_path / "inbox", "a.txt")
    with pytest.raises(ValueError, match="Invalid run UID for a claim directory"):
        ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(files, run_uid)
    assert files[0].exists()
    assert not (tmp_path / "proc").exists()


def test_claim_no_files_creates_nothing(tmp_path: Path) -> None:
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act([], RUN_UID)
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
        claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
            files, RUN_UID, [inbox]
        )

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

    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        files, RUN_UID, [inbox]
    )

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
        claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
            files, RUN_UID, [inbox]
        )
    assert [p.name for p in claimed.files] == ["a.txt"]
    assert any("disappeared" in r.getMessage() for r in caplog.records)


def test_claim_leaves_files_that_arrive_after_listing(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    listed = _tree(inbox, "a.txt", "b.txt")
    (late,) = _tree(inbox, "late.txt")
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        listed, RUN_UID, [inbox]
    )
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
        ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
            files, RUN_UID, [inbox]
        )
    assert sum(p.exists() for p in files) == 2

    calls.clear()
    # The retry is given a different list, but follows the saved plan
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        files[:1], RUN_UID, [inbox]
    )
    assert len(calls) == 2  # only the files not claimed yet are moved
    assert sorted(p.name for p in claimed.files) == ["1.txt", "2.txt", "3.txt", "4.txt"]
    assert not any(p.exists() for p in files)

    monkeypatch.setattr(os, "rename", real_rename)
    clean = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        _tree(tmp_path / "inbox2", "1.txt", "2.txt", "3.txt", "4.txt"),
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
    claimed = ClaimInputFiles(processing, tmp_path / "error").act(
        [src], RUN_UID, [inbox]
    )
    (dest,) = claimed.files
    shutil.copy2(dest, src)  # as if the source had never been deleted
    if source_changed:
        src.write_text("a new file with the same name")

    retried = ClaimInputFiles(processing, tmp_path / "error").act(
        [src], RUN_UID, [inbox]
    )

    assert retried.files == claimed.files
    assert src.exists() is source_changed
    assert dest.read_text() == "a.txt"


def test_claimed_files_load_and_pickle(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/b.txt")
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        files, RUN_UID, [inbox]
    )
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
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        files, RUN_UID, [inbox]
    )
    assert len(claimed.files) == 2
    assert (claimed.files_dir / CLAIMED_MANIFEST).read_text() == CLAIMED_MANIFEST
    assert ClaimedFiles.load(claimed.run_dir) == claimed  # the plan is intact
    assert not any(p.exists() for p in files)


def test_claim_run_dir_is_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _tree(tmp_path / "inbox", "a.txt")
    claimed = ClaimInputFiles(Path("proc"), Path("error")).act(
        files, RUN_UID, [tmp_path / "inbox"]
    )
    assert claimed.run_dir == tmp_path / "proc" / RUN_UID
    assert claim_run_dir(Path("proc"), RUN_UID) == claimed.run_dir
    # A relative path to a claimed file is mapped too
    assert claimed.original_of(
        Path("proc") / RUN_UID / CLAIMED_FILES_DIRNAME / "a.txt"
    ) == (tmp_path / "inbox" / "a.txt")


def test_has_claim_plan(tmp_path: Path) -> None:
    run_dir = claim_run_dir(tmp_path / "proc", RUN_UID)
    assert not has_claim_plan(run_dir)
    files = _tree(tmp_path / "inbox", "a.txt")
    ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        files, RUN_UID, [tmp_path / "inbox"]
    )
    assert has_claim_plan(run_dir)


def test_find_claim_without_one(tmp_path: Path) -> None:
    assert ClaimedFiles.find(tmp_path / "proc", RUN_UID) is None
    # A claim of no files writes no plan, so there is none to find
    ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act([], RUN_UID)
    assert ClaimedFiles.find(tmp_path / "proc", RUN_UID) is None


def test_find_claim(tmp_path: Path) -> None:
    files = _tree(tmp_path / "inbox", "a.txt", "b/c.txt")
    claimed = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        files, RUN_UID, [tmp_path / "inbox"]
    )
    assert ClaimedFiles.find(tmp_path / "proc", RUN_UID) == claimed
    assert ClaimedFiles.load(claimed.run_dir) == claimed


def test_find_claim_that_stopped_partway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "1.txt", "2.txt", "3.txt")
    real_rename = os.rename
    calls = []

    def crashing_rename(src: ty.Any, dst: ty.Any) -> None:
        calls.append(src)
        if len(calls) == 2:
            raise RuntimeError("crash")
        real_rename(src, dst)

    monkeypatch.setattr(os, "rename", crashing_rename)
    with pytest.raises(RuntimeError, match="crash"):
        ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
            files, RUN_UID, [inbox]
        )

    found = ClaimedFiles.find(tmp_path / "proc", RUN_UID)
    assert found is not None
    # Only the file moved before the crash is in the record
    assert list(found.files.values()) == [files[0]]


# FinishClaim and clean_up ---------------------------------------------------------


def _claim(tmp_path: Path, *relpaths: str) -> tuple[Path, ClaimedFiles]:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, *relpaths)
    return inbox, ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act(
        files, RUN_UID, [inbox]
    )


def _reasons(moved_run_dir: Path) -> dict[str, dict[str, ty.Any]]:
    entries = json.loads((moved_run_dir / UNPROCESSED_MANIFEST).read_text())
    return {e["file"]: e for e in entries}


def test_finish_claim_removes_run_dir_when_all_staged(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/b.txt", "sub/deeper/c.txt")
    processing = tmp_path / "out" / PROCESSING_NAME_DEFAULT
    claimed = ClaimInputFiles(processing, tmp_path / "error").act(
        files, RUN_UID, [inbox]
    )
    for path in claimed.files:
        path.unlink()  # as stage_accession does
    unprocessed = tmp_path / "unprocessed"
    assert FinishClaim(unprocessed).act(claimed) == []
    assert not claimed.run_dir.exists()
    assert processing.is_dir()
    assert not unprocessed.exists()


def test_finish_claim_moves_leftovers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    inbox, claimed = _claim(tmp_path, "a.txt", "sub/notes.txt", "other/deeper/c.txt")
    notes = claimed.files_dir / "sub" / "notes.txt"
    for path in claimed.files:
        if path != notes:
            path.unlink()
    unprocessed = tmp_path / "unprocessed"
    with caplog.at_level("WARNING"):
        moved = FinishClaim(unprocessed).act(claimed)
    moved_run_dir = unprocessed / RUN_UID
    assert moved == [moved_run_dir / CLAIMED_FILES_DIRNAME / "sub" / "notes.txt"]
    assert not claimed.run_dir.exists()
    assert not (moved_run_dir / CLAIMED_FILES_DIRNAME / "other").exists()  # pruned
    reloaded = ClaimedFiles.load(moved_run_dir)
    assert reloaded.original_of(moved[0]) == inbox / "sub" / "notes.txt"
    assert _reasons(moved_run_dir) == {
        "files/sub/notes.txt": {
            "file": "files/sub/notes.txt",
            "original": str(inbox / "sub" / "notes.txt"),
            "reason": "unrecognised",
        }
    }
    (warning,) = [
        r.getMessage() for r in caplog.records if "weren't staged" in r.getMessage()
    ]
    assert "1 unrecognised" in warning and str(moved_run_dir) in warning
    # Retried once the run directory has been moved
    assert FinishClaim(unprocessed).act(claimed) == moved


def test_finish_claim_records_why_files_were_left(tmp_path: Path) -> None:
    from fileformats.application import Json
    from fileformats.generic import DirectoryOf
    from fileformats.text import Csv

    from accessionflow.api.collate import classify_paths, group_into_accessions
    from accessionflow.helpers.arg_types import IDSpec

    _, claimed = _claim(
        tmp_path, "fail/x.json", "fail/y.json", "ignored.csv", "notes.txt"
    )
    files_dir = claimed.files_dir
    (files_dir / "fail" / "x.json").write_text("{}")
    (files_dir / "fail" / "y.json").write_text("{}")
    (directory,) = classify_paths([files_dir / "fail"], [DirectoryOf[Json]])
    directory.metadata["sess"] = "s1"
    (accession,) = group_into_accessions([directory], [IDSpec("sess")])
    (csv,) = classify_paths([files_dir / "ignored.csv"], [Csv])

    FinishClaim(tmp_path / "unprocessed").act(
        claimed,
        failed=[(accession, "save failed")],
        ignored=[csv],
    )

    reasons = _reasons(tmp_path / "unprocessed" / RUN_UID)
    for name in ("files/fail/x.json", "files/fail/y.json"):
        assert reasons[name]["reason"] == "failed"
        assert reasons[name]["accession"] == "s1"
        assert reasons[name]["error"] == "save failed"
    assert reasons["files/ignored.csv"]["reason"] == "ignored"
    assert reasons["files/ignored.csv"]["datatype"] == "text/csv"
    assert reasons["files/notes.txt"]["reason"] == "unrecognised"


def test_finish_claim_removes_partial_copies(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, "a.txt")
    (claimed.files_dir / "a.txt").unlink()
    (claimed.files_dir / ".b.txt.claiming").write_text("a copy stopped part way")
    assert FinishClaim(tmp_path / "unprocessed").act(claimed) == []
    assert not claimed.run_dir.exists()


def test_finish_claim_without_run_dir(tmp_path: Path) -> None:
    empty = ClaimInputFiles(tmp_path / "proc", tmp_path / "error").act([], RUN_UID)
    assert FinishClaim(tmp_path / "unprocessed").act(empty) == []
    _, claimed = _claim(tmp_path, "a.txt")
    for path in claimed.files:
        path.unlink()
    assert FinishClaim(tmp_path / "unprocessed").act(claimed) == []
    assert FinishClaim(tmp_path / "unprocessed").act(claimed) == []  # again


def test_finish_claim_moves_across_file_systems(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, claimed = _claim(tmp_path, "notes.txt")
    real_rename = os.rename

    def exdev_for_run_dir(src: ty.Any, dst: ty.Any) -> None:
        if Path(src) == claimed.run_dir:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        real_rename(src, dst)

    monkeypatch.setattr(os, "rename", exdev_for_run_dir)
    unprocessed = tmp_path / "unprocessed"
    (moved,) = FinishClaim(unprocessed).act(claimed)
    assert moved.read_text() == "notes.txt"
    assert not claimed.run_dir.exists()
    assert sorted(p.name for p in unprocessed.iterdir()) == [RUN_UID]  # no .moving


def test_finish_claim_retry_after_crash_before_delete(tmp_path: Path) -> None:
    """A copy across file systems got into place, but the original wasn't deleted"""
    _, claimed = _claim(tmp_path, "notes.txt")
    unprocessed = tmp_path / "unprocessed"
    shutil.copytree(claimed.run_dir, unprocessed / RUN_UID)
    (moved,) = FinishClaim(unprocessed).act(claimed)
    assert moved == unprocessed / RUN_UID / CLAIMED_FILES_DIRNAME / "notes.txt"
    assert not claimed.run_dir.exists()


def _error(message: str) -> ValueError:
    """An error that has been raised, so it has a traceback"""
    try:
        raise ValueError(message)
    except ValueError as e:
        return e


def test_clean_up_moves_the_claim_of_a_run_that_raised(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, "a.txt", "sub/b.txt")
    claim = ClaimInputFiles(tmp_path / "proc", tmp_path / "errors")
    claim.clean_up(RUN_UID, error=_error("no datatype recognised 'a.txt'"))
    moved = tmp_path / "errors" / RUN_UID
    assert not claimed.run_dir.exists()
    assert (moved / CLAIMED_FILES_DIRNAME / "sub" / "b.txt").read_text() == "sub/b.txt"
    record = json.loads((moved / ERROR_MANIFEST).read_text())
    assert record["type"] == "ValueError"
    assert record["message"] == "no datatype recognised 'a.txt'"
    assert "Traceback" in record["traceback"]
    # Again, now it has been moved
    claim.clean_up(RUN_UID, error=_error("again"))
    assert json.loads((moved / ERROR_MANIFEST).read_text()) == record


@pytest.mark.parametrize("error", [None, KeyboardInterrupt()])
def test_clean_up_leaves_the_claim_of_a_run_that_didnt_raise(
    tmp_path: Path, error: BaseException | None
) -> None:
    """Without an error, or after an interrupt, the claim stays in the working
    directory"""
    _, claimed = _claim(tmp_path, "a.txt")
    ClaimInputFiles(tmp_path / "proc", tmp_path / "errors").clean_up(
        RUN_UID, error=error
    )
    assert has_claim_plan(claimed.run_dir)
    assert not (tmp_path / "errors").exists()


def test_clean_up_with_nothing_claimed(tmp_path: Path) -> None:
    claim = ClaimInputFiles(tmp_path / "proc", tmp_path / "errors")
    claim.act([], RUN_UID)
    claim.clean_up(RUN_UID, error=_error("failed"))
    assert not (tmp_path / "proc").exists()
    assert not (tmp_path / "errors").exists()


def test_clean_up_after_finish_claim(tmp_path: Path) -> None:
    _, claimed = _claim(tmp_path, "a.txt")
    FinishClaim(tmp_path / "unprocessed").act(claimed)
    ClaimInputFiles(tmp_path / "proc", tmp_path / "errors").clean_up(
        RUN_UID, error=_error("failed")
    )
    assert (
        tmp_path / "unprocessed" / RUN_UID / CLAIMED_FILES_DIRNAME / "a.txt"
    ).exists()
    assert not (tmp_path / "errors").exists()


def test_clean_up_moves_a_claim_that_stopped_partway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "1.txt", "2.txt")
    real_rename = os.rename
    calls = []

    def crashing_rename(src: ty.Any, dst: ty.Any) -> None:
        calls.append(src)
        if len(calls) == 2:
            raise RuntimeError("crash")
        real_rename(src, dst)

    claim = ClaimInputFiles(tmp_path / "proc", tmp_path / "errors")
    monkeypatch.setattr(os, "rename", crashing_rename)
    with pytest.raises(RuntimeError, match="crash") as raised:
        claim.act(files, RUN_UID, [inbox])
    monkeypatch.undo()

    claim.clean_up(RUN_UID, error=raised.value)
    moved = tmp_path / "errors" / RUN_UID / CLAIMED_FILES_DIRNAME
    assert sorted(p.name for p in moved.iterdir()) == ["1.txt"]
    assert not files[0].exists() and files[1].exists()
    assert not claim_run_dir(tmp_path / "proc", RUN_UID).exists()


def test_reserve_run_uid_clean_up_removes_the_build_dir(tmp_path: Path) -> None:
    reserve = ReserveRunUid(tmp_path / "out")
    _, build_dir = reserve.act()
    (build_dir / "empty").mkdir()
    reserve.clean_up(build_dir, error=_error("failed"))
    assert not build_dir.exists()
    reserve.clean_up(build_dir)  # again, with nothing left
