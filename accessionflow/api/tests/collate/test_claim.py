import errno
import hashlib
import os
import pickle
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
    make_run_uid,
)
from accessionflow.model.accession import Accession

NOW = datetime(2026, 11, 24, 1, 2, 3, tzinfo=UTC)
FILES = [Path("/in/b.dcm"), Path("/in/a.dcm"), Path("/in/sub/c.dcm")]


def test_make_run_uid_format() -> None:
    run_uid = make_run_uid(FILES, now=NOW)
    assert re.fullmatch(r"[0-9a-f]{6}\d{14}", run_uid)
    assert run_uid.endswith("20261124010203")


def test_make_run_uid_converts_to_utc() -> None:
    same_instant = datetime(
        2026, 11, 24, 11, 2, 3, tzinfo=timezone(timedelta(hours=10))
    )
    assert make_run_uid(FILES, now=same_instant) == make_run_uid(FILES, now=NOW)


def test_make_run_uid_default_clock() -> None:
    before = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    suffix = make_run_uid(FILES)[6:]
    after = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    assert before <= suffix <= after


def test_make_run_uid_ignores_order() -> None:
    assert make_run_uid(FILES, now=NOW) == make_run_uid(FILES[::-1], now=NOW)


def test_make_run_uid_relative_and_absolute_paths_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert make_run_uid([Path("a.dcm")], now=NOW) == make_run_uid(
        [tmp_path / "a.dcm"], now=NOW
    )


def test_make_run_uid_differs_for_different_files() -> None:
    assert make_run_uid(FILES, now=NOW)[:6] != make_run_uid(FILES[:2], now=NOW)[:6]


def test_make_run_uid_hash() -> None:
    """Pins the algorithm: SHA-256 over the sorted absolute paths"""
    crypto = hashlib.sha256()
    for path in sorted(str(p.absolute()) for p in FILES):
        crypto.update(path.encode())
    assert make_run_uid(FILES, now=NOW)[:6] == crypto.hexdigest()[:6]


def test_make_run_uid_no_files() -> None:
    assert make_run_uid([], now=NOW) == (
        hashlib.sha256().hexdigest()[:6] + "20261124010203"
    )


def test_make_run_uid_round_trips_through_staged_dirname() -> None:
    """The run UID follows the labels in a staged directory's name, separated by '.'"""
    run_uid = make_run_uid(FILES, now=NOW)
    labels, parsed = Accession._labels_from_dirname(f"proj.subj.sess.{run_uid}", {})
    assert parsed == run_uid
    assert labels == {"project": "proj", "subject": "subj", "session": "sess"}


# claim_input_files ----------------------------------------------------------------

RUN_UID = "abc12320261124010203"


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


def test_claim_moves_files_keeping_layout(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/b.txt", "sub/deeper/c.txt")
    processing = tmp_path / "out" / PROCESSING_NAME_DEFAULT

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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    files = _tree(inbox, "a.txt", "sub/b.txt")
    mtimes = {p.name: p.stat().st_mtime_ns for p in files}
    monkeypatch.setattr(os, "rename", _exdev_rename)

    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])

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
        "def45620261124010203",
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
