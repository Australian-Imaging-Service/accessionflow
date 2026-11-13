import hashlib
import os
import shutil
import time
import typing as ty
from pathlib import Path
from unittest.mock import patch

import fsspec
import pytest
from click.testing import CliRunner
from fileformats.generic import File

from accessionflow.api.push_api import (
    Compatibility,
    DestinationUnreachable,
    LockFailed,
    _fingerprint,
    check_push,
    push,
)
from accessionflow.cli import cli
from accessionflow.helpers.metadata import Metadata
from accessionflow.model.accession import Accession
from accessionflow.model.acquisition import Acquisition
from accessionflow.model.resource import Resource

NAME = "PROJECT.SUBJECT.SESSION"
CLEAN_ENV = {key: None for key in os.environ if key.startswith("ACFLOW_")}


def _stage(staged: Path, src: Path, contents: str = "image data") -> Path:
    """Stage an accession with an acquisition resource, an accession resource and
    fields, the files of the first being links to where they came from"""
    src.mkdir(parents=True, exist_ok=True)
    image = src / "image.dat"
    image.write_text(contents)
    report = src / "report.txt"
    report.write_text("a report")
    accession = Accession(
        uid="1.2.3",
        labels={"project": "PROJECT", "subject": "SUBJECT", "session": "SESSION"},
        acquisitions=[Acquisition(id="1", type="t1", resources={"RAW": File(image)})],
    )
    accession.add_session_resource("REPORT", File(report))
    accession.fields["site"] = "SYDNEY"
    accession.save(staged, copy_mode=File.CopyMode.symlink)
    return staged / NAME


def _relfiles(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.startswith(".")
    }


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    staged_dir = tmp_path / "staged"
    _stage(staged_dir, tmp_path / "src")
    return staged_dir


@pytest.fixture
def memory_dest() -> ty.Iterator[str]:
    fs = fsspec.filesystem("memory")
    fs.store.clear()
    fs.pseudo_dirs.clear()
    fs.pseudo_dirs.append("")
    yield "memory://dest"
    fs.store.clear()


def test_push_copies_the_staging_layout(staged: Path, tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    assert push(staged, str(dest)) == []
    # Everything staged is copied, as it is, with the links followed
    assert _relfiles(dest / NAME) == _relfiles(staged / NAME)
    assert not any(p.is_symlink() for p in (dest / NAME).rglob("*"))
    pushed = Accession.load(dest / NAME)
    assert pushed.labels == {
        "project": "PROJECT",
        "subject": "SUBJECT",
        "session": "SESSION",
    }
    assert dict(pushed.fields) == {"site": "SYDNEY"}
    assert set(pushed.acquisitions["1"].resources) == {"RAW"}
    assert set(pushed.session_resources) == {"REPORT"}


def test_push_writes_manifests_after_files_and_metadata_last(
    staged: Path, memory_dest: str
) -> None:
    fs = fsspec.filesystem("memory")
    written: list[str] = []
    put_file, pipe_file = fs.put_file, fs.pipe_file

    def record_put(lpath: str, rpath: str, **kwargs: ty.Any) -> None:
        written.append(rpath)
        put_file(lpath, rpath, **kwargs)

    def record_pipe(path: str, value: bytes, **kwargs: ty.Any) -> None:
        written.append(path)
        pipe_file(path, value, **kwargs)

    with (
        patch.object(fs, "put_file", record_put),
        patch.object(fs, "pipe_file", record_pipe),
    ):
        assert push(staged, memory_dest) == []
    names = [path.rsplit("/", 1)[-1] for path in written]
    assert names[-1] == "__METADATA__.json" and written[-1].endswith(
        f"{NAME}/__METADATA__.json"
    )
    for resource in ("1.t1/RAW", "REPORT"):
        indices = [i for i, path in enumerate(written) if f"/{resource}/" in path]
        manifest = written.index(f"/dest/{NAME}/{resource}/{Resource.MANIFEST_FNAME}")
        assert manifest == max(indices), "the manifest is written after the files"


def test_push_again_copies_nothing(staged: Path, memory_dest: str) -> None:
    assert push(staged, memory_dest) == []
    fs = fsspec.filesystem("memory")
    with (
        patch.object(fs, "put_file") as put_file,
        patch.object(fs, "pipe_file") as pipe_file,
    ):
        assert push(staged, memory_dest) == []
    put_file.assert_not_called()
    pipe_file.assert_not_called()


def test_push_copies_a_missing_file_again(staged: Path, tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    push(staged, str(dest))
    (dest / NAME / "1.t1" / "RAW" / "image.dat").unlink()
    assert check_push(staged, str(dest), checksums=False)
    push(staged, str(dest))
    assert (dest / NAME / "1.t1" / "RAW" / "image.dat").read_text() == "image data"
    assert check_push(staged, str(dest)) == []


def test_push_copies_a_resource_left_without_a_manifest(
    staged: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "dest"
    push(staged, str(dest))
    (dest / NAME / "REPORT" / Resource.MANIFEST_FNAME).unlink()
    (dest / NAME / "REPORT" / "report.txt").write_text("partial")
    push(staged, str(dest))
    assert (dest / NAME / "REPORT" / "report.txt").read_text() == "a report"
    assert check_push(staged, str(dest)) == []


def test_push_replaces_a_changed_resource(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    dest = tmp_path / "dest"
    _stage(staged, tmp_path / "src")
    push(staged, str(dest))
    (dest / NAME / "1.t1" / "RAW" / "stale.dat").write_text("from an earlier copy")
    (dest / NAME / "unrelated.txt").write_text("not the push's")
    # The resource is staged again with different files
    (tmp_path / "src" / "image.dat").unlink()
    _stage(staged, tmp_path / "src", contents="corrected image data")
    push(staged, str(dest))
    raw = dest / NAME / "1.t1" / "RAW"
    assert (raw / "image.dat").read_text() == "corrected image data"
    # The changed resource's old files go, but nothing else is deleted
    assert not (raw / "stale.dat").exists()
    assert (dest / NAME / "unrelated.txt").exists()
    assert check_push(staged, str(dest)) == []


def test_push_refuses_an_accession_with_dangling_links(
    staged: Path, tmp_path: Path
) -> None:
    (tmp_path / "src" / "report.txt").unlink()
    errors = push(staged, str(tmp_path / "dest"))
    assert len(errors) == 1 and "targets have gone" in errors[0]
    assert not (tmp_path / "dest" / NAME).exists()


def test_push_waits_for_an_accession_to_settle(staged: Path, tmp_path: Path) -> None:
    assert push(staged, str(tmp_path / "dest"), wait_period=3600) == []
    assert not (tmp_path / "dest" / NAME).exists()
    past = time.time() - 7200
    for path in [staged / NAME, *(staged / NAME).rglob("*")]:
        os.utime(path, (past, past), follow_symlinks=False)
    assert push(staged, str(tmp_path / "dest"), wait_period=3600) == []
    assert (tmp_path / "dest" / NAME / Metadata.FNAME).exists()


def test_push_reports_an_unreachable_destination(staged: Path) -> None:
    fs = fsspec.filesystem("memory")
    with patch.object(fs, "find", side_effect=PermissionError("Access Denied")):
        with pytest.raises(DestinationUnreachable, match="Access Denied"):
            push(staged, "memory://dest")


def test_check_push_finds_what_is_wrong(staged: Path, tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    assert check_push(staged, str(dest), checksums=False)  # nothing pushed yet
    push(staged, str(dest))
    assert check_push(staged, str(dest)) == []
    image = dest / NAME / "1.t1" / "RAW" / "image.dat"
    image.write_text("IMAGE DATA")  # corrupted, with the same size
    assert check_push(staged, str(dest), checksums=False) == []
    (problem,) = check_push(staged, str(dest))
    assert "corrupted" in problem
    image.write_text("short")
    (problem,) = check_push(staged, str(dest), checksums=False)
    assert "wrong size" in problem
    (dest / NAME / "__METADATA__.json").unlink()
    image.write_text("image data")
    (problem,) = check_push(staged, str(dest))
    assert "no metadata" in problem


def test_fingerprint_matches_the_uploader_script(tmp_path: Path) -> None:
    """The fingerprint is what `cd DIR && find -L . -type f -exec stat -c '%n %s %Y'
    {} + | sort | md5sum` gives"""
    root = tmp_path / "accession"
    (root / "b").mkdir(parents=True)
    (root / "a.json").write_text("{}")
    (root / "b" / "c.dcm").write_text("12345")
    target = tmp_path / "target.dcm"
    target.write_text("linked")
    (root / "b" / "d.dcm").symlink_to(target)
    for path, mtime in [
        (root / "a.json", 1_700_000_000),
        (root / "b" / "c.dcm", 1_700_000_001),
        (target, 1_700_000_002),
    ]:
        os.utime(path, (mtime, mtime))
    expected = "./a.json 2 1700000000\n./b/c.dcm 5 1700000001\n./b/d.dcm 6 1700000002\n"
    assert _fingerprint(root) == hashlib.md5(expected.encode()).hexdigest()
    assert _fingerprint(tmp_path / "empty-or-missing") == hashlib.md5(b"").hexdigest()


def test_markers_skip_and_are_swept(staged: Path, tmp_path: Path) -> None:
    markers = tmp_path / "state"
    compat = Compatibility(marker_dir=markers, marker_root=tmp_path)
    dest = tmp_path / "dest"
    push(staged, str(dest), compatibility=compat)
    marker = markers / NAME
    assert marker.read_text().strip() == _fingerprint(staged / NAME)
    # A matching marker skips the accession without checking the destination
    (dest / NAME / "REPORT" / "report.txt").unlink()
    push(staged, str(dest), compatibility=compat)
    assert not (dest / NAME / "REPORT" / "report.txt").exists()
    # Without markers, the destination decides
    push(staged, str(dest))
    assert (dest / NAME / "REPORT" / "report.txt").exists()
    # The marker goes once no stage holds the accession
    shutil.rmtree(staged / NAME)
    shutil.rmtree(dest / NAME)
    push(staged, str(dest), compatibility=compat)
    assert not marker.exists()


def test_recopy_requests_copy_everything_again(staged: Path, tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    requests = tmp_path / "recopy"
    requests.mkdir()
    compat = Compatibility(recopy_dir=requests)
    push(staged, str(dest), compatibility=compat)
    image = dest / NAME / "1.t1" / "RAW" / "image.dat"
    image.write_text("IMAGE DATA")  # corrupted, which sizes don't show
    (requests / NAME).write_text("checksum mismatch for image.dat")
    push(staged, str(dest), compatibility=compat)
    assert image.read_text() == "image data"
    assert not list(requests.iterdir())


def test_a_failed_recopy_is_requested_again(staged: Path, tmp_path: Path) -> None:
    requests = tmp_path / "recopy"
    requests.mkdir()
    (requests / NAME).write_text("missing")
    (requests / f"{NAME}-other.claimed").write_text("claimed by a run that died")
    compat = Compatibility(recopy_dir=requests)
    with patch(
        "accessionflow.api.push_api.push_accession", side_effect=OSError("bucket gone")
    ):
        errors = push(staged, str(tmp_path / "dest"), compatibility=compat)
    assert len(errors) == 1
    assert sorted(p.name for p in requests.iterdir()) == [NAME, f"{NAME}-other"]


def test_lock_timeout_skips_and_other_lock_failures_stop(
    staged: Path, tmp_path: Path
) -> None:
    fcntl = pytest.importorskip("fcntl")
    lock_file = tmp_path / "writer.lock"
    requests = tmp_path / "recopy"
    requests.mkdir()
    (requests / NAME).write_text("missing")
    compat = Compatibility(lock_file=lock_file, lock_wait=0, recopy_dir=requests)
    with open(lock_file, "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert push(staged, str(tmp_path / "dest"), compatibility=compat) == []
        fcntl.flock(held, fcntl.LOCK_UN)
    assert not (tmp_path / "dest" / NAME).exists()
    assert (requests / NAME).exists(), "the request is kept for the next pass"
    push(staged, str(tmp_path / "dest"), compatibility=compat)
    assert (tmp_path / "dest" / NAME).exists()
    unopenable = Compatibility(lock_file=tmp_path / "missing-dir" / "writer.lock")
    with pytest.raises(LockFailed):
        push(staged, str(tmp_path / "dest2"), compatibility=unopenable)


def test_push_and_check_push_commands(staged: Path, tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    runner = CliRunner()
    result = runner.invoke(cli, ["push", str(staged), str(dest)], env=CLEAN_ENV)
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ["check-push", str(staged), str(dest)], env=CLEAN_ENV)
    assert result.exit_code == 0, result.output
    (dest / NAME / "REPORT" / "report.txt").unlink()
    result = runner.invoke(
        cli, ["check-push", str(staged), str(dest), "--sizes-only"], env=CLEAN_ENV
    )
    assert result.exit_code != 0
    assert "problem(s) found" in result.output


def test_push_command_refuses_to_start_without_a_destination(
    staged: Path,
) -> None:
    fs = fsspec.filesystem("memory")
    with patch.object(fs, "find", side_effect=PermissionError("Access Denied")):
        result = CliRunner().invoke(
            cli,
            ["push", str(staged), "memory://dest", "--probe-attempts", "1"],
            env=CLEAN_ENV,
        )
    assert result.exit_code != 0
    assert "refusing to start pushing" in result.output
