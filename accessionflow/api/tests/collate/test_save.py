import typing as ty
from pathlib import Path

import pytest
from fileformats.application import Json
from fileformats.core import FileSet
from fileformats.core.fs_mount_identifier import FsMountIdentifier

from accessionflow.api.collate import (
    apply_path_metadata,
    claim_input_files,
    classify_paths,
    expand_claimed_paths,
    group_into_accessions,
    plan_recursion,
    warn_if_hardlinks_unavailable,
)
from accessionflow.api.staging import prepare_build_dir
from accessionflow.helpers.arg_types import IDSpec, PathMetadataRegex
from accessionflow.model.accession import Accession

RUN_UID = "abc12320261124010203"


def _accessions(tmp_path: Path) -> list[Accession]:
    """One accession of three JSON resources, all in one claimed directory"""
    inbox = tmp_path / "inbox"
    files = []
    for name in ("a", "b", "c"):
        path = inbox / "s1" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{{"{name}": 1}}')
        files.append(path)
    claimed = claim_input_files(files, tmp_path / "proc", RUN_UID, [inbox])
    plan = plan_recursion([Json], recursive=True)
    fspaths = expand_claimed_paths(claimed, [Json], plan, recursive=True)
    filesets = apply_path_metadata(
        classify_paths(fspaths, [Json], plan.ignore_datatypes),
        [PathMetadataRegex(r".*/(?P<sess>[^/]+)/(?P<name>[^/]+)\.json$", Json)],
        claimed,
    )
    return group_into_accessions(filesets, [IDSpec("sess")], [IDSpec("name")])


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
