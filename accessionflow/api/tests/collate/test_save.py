import typing as ty
from pathlib import Path

import pytest
from fileformats.application import Json
from fileformats.core import FileSet
from fileformats.core.fs_mount_identifier import FsMountIdentifier
from fileformats.generic import DirectoryOf

from accessionflow.api.collate import (
    ClaimedFiles,
    ClaimInputFiles,
    apply_path_metadata,
    assign_labels,
    classify_paths,
    expand_claimed_paths,
    group_into_accessions,
    move_to_target,
    plan_recursion,
    remove_claimed_files,
    save_to_build_dir,
    tag_fileset_types,
    warn_if_hardlinks_unavailable,
)
from accessionflow.api.collate import save as save_module
from accessionflow.api.staging import prepare_build_dir, remove_build_dir
from accessionflow.helpers.arg_types import IDSpec, PathMetadataRegex
from accessionflow.model.accession import Accession

RUN_UID = "20261124010203_abc123"


def _accessions(tmp_path: Path) -> list[Accession]:
    """One accession of three JSON resources, all in one claimed directory"""
    return _claim_and_group(tmp_path)[1]


def _claim_and_group(tmp_path: Path) -> tuple[ClaimedFiles, list[Accession]]:
    inbox = tmp_path / "inbox"
    files = []
    for name in ("a", "b", "c"):
        path = inbox / "s1" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{{"{name}": 1}}')
        files.append(path)
    claimed = ClaimInputFiles(tmp_path / "proc").act(files, RUN_UID, [inbox])
    plan = plan_recursion([Json], recursive=True)
    fspaths = expand_claimed_paths(claimed, [Json], plan, recursive=True)
    filesets = apply_path_metadata(
        classify_paths(fspaths, [Json], plan.ignore_datatypes),
        [PathMetadataRegex(r".*/(?P<sess>[^/]+)/(?P<name>[^/]+)\.json$", Json)],
        claimed,
    )
    return claimed, group_into_accessions(
        filesets, [IDSpec("sess")], [IDSpec("name")], run_uid=RUN_UID
    )


@pytest.fixture
def mounts(monkeypatch: pytest.MonkeyPatch) -> ty.Callable[[bool], list[tuple]]:
    """Patches the mount check to answer ``same`` and records its calls"""
    calls: list[tuple] = []

    def patch(same: bool) -> list[tuple]:
        def on_same_mount(cls: ty.Any, a: Path, b: Path) -> bool:
            calls.append((a, b))
            return same

        monkeypatch.setattr(
            FsMountIdentifier, "on_same_mount", classmethod(on_same_mount)
        )
        return calls

    return patch


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "hard-linked" in r.getMessage()]


def test_warns_once_naming_the_output_dir(
    tmp_path: Path, mounts: ty.Any, caplog: pytest.LogCaptureFixture
) -> None:
    calls = mounts(False)
    output_dir = tmp_path / "out"
    build_dir = prepare_build_dir(output_dir, RUN_UID)
    with caplog.at_level("WARNING"):
        unlinkable = warn_if_hardlinks_unavailable(
            _accessions(tmp_path), build_dir, FileSet.CopyMode.hardlink_or_copy
        )
    assert sorted(p.name for p in unlinkable) == ["a.json", "b.json", "c.json"]
    (warning,) = _warnings(caplog)
    assert warning.startswith("3 of 3 resources")
    assert f"'{output_dir}'" in warning
    assert len(calls) == 1  # one lookup for the one directory


def test_no_warning_on_the_same_mount(
    tmp_path: Path, mounts: ty.Any, caplog: pytest.LogCaptureFixture
) -> None:
    mounts(True)
    build_dir = prepare_build_dir(tmp_path / "out", RUN_UID)
    with caplog.at_level("WARNING"):
        assert (
            warn_if_hardlinks_unavailable(
                _accessions(tmp_path), build_dir, FileSet.CopyMode.hardlink_or_copy
            )
            == []
        )
    assert _warnings(caplog) == []


@pytest.mark.parametrize(
    "copy_mode",
    [FileSet.CopyMode.copy, FileSet.CopyMode.any, FileSet.CopyMode.hardlink],
)
def test_no_warning_without_a_copy_fallback(
    tmp_path: Path,
    mounts: ty.Any,
    caplog: pytest.LogCaptureFixture,
    copy_mode: FileSet.CopyMode,
) -> None:
    calls = mounts(False)
    build_dir = prepare_build_dir(tmp_path / "out", RUN_UID)
    with caplog.at_level("WARNING"):
        assert (
            warn_if_hardlinks_unavailable(_accessions(tmp_path), build_dir, copy_mode)
            == []
        )
    assert _warnings(caplog) == []
    assert calls == []


def test_converted_resources_are_skipped(tmp_path: Path, mounts: ty.Any) -> None:
    mounts(False)
    build_dir = prepare_build_dir(tmp_path / "out", RUN_UID)
    assert (
        warn_if_hardlinks_unavailable(
            _accessions(tmp_path),
            build_dir,
            FileSet.CopyMode.hardlink_or_copy,
            conversion_map={Json: None},
        )
        == []
    )


def test_build_dir_outside_the_build_area(
    tmp_path: Path, mounts: ty.Any, caplog: pytest.LogCaptureFixture
) -> None:
    mounts(False)
    build_dir = tmp_path / "elsewhere"
    build_dir.mkdir()
    with caplog.at_level("WARNING"):
        warn_if_hardlinks_unavailable(
            _accessions(tmp_path), build_dir, FileSet.CopyMode.hardlink_or_copy
        )
    (warning,) = _warnings(caplog)
    assert f"'{build_dir}'" in warning


# save_to_build_dir ----------------------------------------------------------------


def test_save_to_build_dir(tmp_path: Path) -> None:
    _, (accession,) = _claim_and_group(tmp_path)
    build_dir = prepare_build_dir(tmp_path / "out", RUN_UID)
    saved_dir = save_to_build_dir(accession, build_dir)
    assert saved_dir == build_dir / accession.staging_dirname()
    assert sorted(Accession.load(saved_dir).acquisitions) == ["a", "b", "c"]


def test_save_to_build_dir_clears_earlier_attempt(tmp_path: Path) -> None:
    _, (accession,) = _claim_and_group(tmp_path)
    build_dir = prepare_build_dir(tmp_path / "out", RUN_UID)
    scratch = build_dir / accession.staging_dirname()
    scratch.mkdir()
    (scratch / "junk.txt").write_text("left by a failed save")
    saved_dir = save_to_build_dir(accession, build_dir)
    assert not (saved_dir / "junk.txt").exists()
    assert sorted(Accession.load(saved_dir).acquisitions) == ["a", "b", "c"]


# remove_claimed_files -------------------------------------------------------------


def test_remove_claimed_files(tmp_path: Path) -> None:
    claimed, (accession,) = _claim_and_group(tmp_path)
    removed = remove_claimed_files(accession, claimed)
    assert sorted(p.name for p in removed) == ["a.json", "b.json", "c.json"]
    assert not any(p.exists() for p in removed)
    # Again, now they are gone
    assert remove_claimed_files(accession, claimed) == []


def test_remove_claimed_files_removes_directory_datatypes(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    files = []
    for name in ("x", "y"):
        path = inbox / "s1" / "dir" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        files.append(path)
    claimed = ClaimInputFiles(tmp_path / "proc").act(files, RUN_UID, [inbox / "s1"])
    datatypes: list[type[FileSet]] = [DirectoryOf[Json]]
    plan = plan_recursion(datatypes)
    filesets = classify_paths(
        expand_claimed_paths(claimed, datatypes, plan), datatypes, plan.ignore_datatypes
    )
    (accession,) = group_into_accessions(
        tag_fileset_types(filesets), [IDSpec("__datatype__")]
    )
    (removed,) = remove_claimed_files(accession, claimed)
    assert removed == claimed.files_dir / "dir"
    assert not removed.exists()


def test_remove_claimed_files_refuses_unclaimed_files(tmp_path: Path) -> None:
    claimed, _ = _claim_and_group(tmp_path)
    live = tmp_path / "live"
    live.mkdir()
    (live / "a.json").write_text("{}")
    (fileset,) = classify_paths([live / "a.json"], [Json])
    fileset.metadata["sess"] = "s9"
    (accession,) = group_into_accessions([fileset], [IDSpec("sess")])
    with pytest.raises(ValueError, match="aren't in the processing area"):
        remove_claimed_files(accession, claimed)
    assert (live / "a.json").exists()


# move_to_target -------------------------------------------------------------------

LABEL_FIELDS = {"project": "project", "subject": "sess", "session": "sess"}
TARGET_NAME = f"PROJ.s1.s1_{RUN_UID}"


def _labelled(tmp_path: Path) -> tuple[ClaimedFiles, Accession]:
    claimed, (accession,) = _claim_and_group(tmp_path)
    assign_labels(accession, LABEL_FIELDS, constant_labels={"project": "PROJ"})
    return claimed, accession


def test_move_to_target(tmp_path: Path) -> None:
    claimed, accession = _labelled(tmp_path)
    output_dir = tmp_path / "out"
    build_dir = prepare_build_dir(output_dir, RUN_UID)
    target_dir = move_to_target(accession, build_dir, output_dir, claimed)
    assert target_dir == output_dir / TARGET_NAME
    delivered = Accession.load(target_dir)
    assert delivered.labels == {"project": "PROJ", "subject": "s1", "session": "s1"}
    assert delivered.run_uid == RUN_UID
    assert sorted(delivered.acquisitions) == ["a", "b", "c"]
    assert not any(p.exists() for p in claimed.files)
    assert not list(build_dir.glob(f"*{save_module.STAGED_MARKER_SUFFIX}"))
    assert remove_build_dir(build_dir) == []
    assert not build_dir.exists()


def test_move_to_target_needs_labels(tmp_path: Path) -> None:
    claimed, (accession,) = _claim_and_group(tmp_path)
    output_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="must be labelled"):
        move_to_target(
            accession, prepare_build_dir(output_dir, RUN_UID), output_dir, claimed
        )
    assert all(p.exists() for p in claimed.files)


def test_move_to_target_retry_after_failed_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claimed, accession = _labelled(tmp_path)
    output_dir = tmp_path / "out"
    build_dir = prepare_build_dir(output_dir, RUN_UID)
    real_remove = save_module.remove_claimed_files
    calls = []

    def fail_once(*args: ty.Any) -> list[Path]:
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("crash while deleting")
        return real_remove(*args)

    monkeypatch.setattr(save_module, "remove_claimed_files", fail_once)
    with pytest.raises(RuntimeError, match="crash while deleting"):
        move_to_target(accession, build_dir, output_dir, claimed)
    target_dir = output_dir / TARGET_NAME
    assert target_dir.is_dir()
    marker = build_dir / f"{TARGET_NAME}{save_module.STAGED_MARKER_SUFFIX}"
    assert marker.exists()

    # The retry skips the save and the move, which would clash with the moved scans
    assert move_to_target(accession, build_dir, output_dir, claimed) == target_dir
    assert not any(p.exists() for p in claimed.files)
    assert not marker.exists()
    assert sorted(Accession.load(target_dir).acquisitions) == ["a", "b", "c"]


def test_move_to_target_failed_move_keeps_claimed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claimed, accession = _labelled(tmp_path)
    output_dir = tmp_path / "out"
    build_dir = prepare_build_dir(output_dir, RUN_UID)

    def failing_move(*args: ty.Any) -> ty.NoReturn:
        raise RuntimeError("move failed")

    monkeypatch.setattr(save_module, "move_into_place", failing_move)
    with pytest.raises(RuntimeError, match="move failed"):
        move_to_target(accession, build_dir, output_dir, claimed)
    assert all(p.exists() for p in claimed.files)
    assert not list(build_dir.glob(f"*{save_module.STAGED_MARKER_SUFFIX}"))
