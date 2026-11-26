"""Tests of the accession combiner (see ``prefect-migration-docs/ROADMAP.md``, Phase 1,
Combine)"""

import json
import pickle
import typing as ty
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fileformats.application import Json

from accessionflow.api.collate import (
    COMBINED_FROM_KEY,
    ERROR_MANIFEST,
    RunAccessionGroup,
    abandon_group,
    check_primary_label,
    combine_accessions,
    combine_run_accessions,
    deliver_combined,
    list_run_accessions,
    remove_run_accessions,
    select_quiet_groups,
)
from accessionflow.api.collate import claim as claim_module
from accessionflow.api.staging import BUILD_NAME_DEFAULT, prepare_build_dir
from accessionflow.helpers.arg_types import IDSpec, MetadataTable, PathMetadataPattern
from accessionflow.helpers.remotes import LocalSessionListing
from accessionflow.model.accession import Accession
from accessionflow.sources.folder.api.collate_api import collate

LABEL_FIELDS = {"project": "project", "subject": "sess", "session": "visit"}
CONSTANT_LABELS = {"project": "P", "session": "V1"}
UID_1 = "20261126010000_aaaaaa"
UID_2 = "20261126013000_bbbbbb"
UID_3 = "20261126015500_cccccc"
NOW = datetime(2026, 11, 26, 2, 0, tzinfo=UTC)  # 5 minutes after UID_3


class Dirs(ty.NamedTuple):
    runs: Path
    output: Path
    errors: Path


@pytest.fixture
def dirs(tmp_path: Path) -> Dirs:
    return Dirs(tmp_path / "runs", tmp_path / "out", tmp_path / "combine-errors")


def _collate(
    tmp_path: Path,
    dirs: Dirs,
    monkeypatch: pytest.MonkeyPatch,
    run_uid: str,
    files: dict[str, str],
    table: str | None = None,
) -> None:
    """Delivers one collate run's run accessions, with the given run UID. ``table`` is
    the CSV of an accession table joined on 'Session'"""
    inbox = tmp_path / f"inbox-{run_uid}"
    paths = []
    for relpath, content in files.items():
        path = inbox / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        paths.append(path)
    tables = []
    if table is not None:
        table_path = tmp_path / f"table-{run_uid}.csv"
        table_path.write_text(table)
        tables = [MetadataTable(str(table_path), "accession", "Session=sess")]
    monkeypatch.setattr(claim_module, "make_run_uid", lambda: run_uid)
    errors = collate(
        paths,
        dirs.runs,
        tmp_path / "work",
        tmp_path / "unprocessed",
        tmp_path / "collate-errors",
        LABEL_FIELDS,
        datatypes=[Json],
        source_roots=[inbox],
        recursive=True,
        accession_uid_field=[IDSpec("sess")],
        acquisition_id_field=[IDSpec("name")],
        path_metadata=[PathMetadataPattern("{sess}/{name}.json", Json)],
        metadata_tables=tables,
        constant_labels=CONSTANT_LABELS,
    )
    assert errors == []
    monkeypatch.undo()


def _group(dirs: Dirs, name: str = "P.s1.V1") -> RunAccessionGroup:
    (group,) = [g for g in list_run_accessions(dirs.runs) if g.name == name]
    return group


def _two_runs_of_s1(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> RunAccessionGroup:
    _collate(tmp_path, dirs, monkeypatch, UID_1, {"s1/a.json": '{"a": 1}'})
    _collate(tmp_path, dirs, monkeypatch, UID_2, {"s1/b.json": '{"b": 2}'})
    return _group(dirs)


# check_primary_label -------------------------------------------------------------


@pytest.mark.parametrize("label", ["combined", "v2", "Final-1"])
def test_check_primary_label_accepts(label: str) -> None:
    check_primary_label(label)


@pytest.mark.parametrize(
    "label", ["", "a.b", "a_b", "-a", "a b", "20261124010203_abc123"]
)
def test_check_primary_label_refuses(label: str) -> None:
    with pytest.raises(ValueError):
        check_primary_label(label)


# list_run_accessions and select_quiet_groups --------------------------------------


def test_list_run_accessions_groups_by_labels(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _collate(tmp_path, dirs, monkeypatch, UID_2, {"s1/b.json": "{}"})
    _collate(tmp_path, dirs, monkeypatch, UID_1, {"s1/a.json": "{}", "s2/c.json": "{}"})
    (dirs.runs / ".hidden_20261126010000_dddddd").mkdir()
    (dirs.runs / "not-a-run-accession").mkdir()
    (dirs.runs / "P.s3.V1_20261126010000_eeeeee.txt").write_text("a file")
    s1, s2 = list_run_accessions(dirs.runs)
    assert s1.name == "P.s1.V1"
    assert [d.name for d in s1.run_dirs] == [f"P.s1.V1_{UID_1}", f"P.s1.V1_{UID_2}"]
    assert s1.newest == datetime(2026, 11, 26, 1, 30, tzinfo=UTC)
    assert (s2.name, len(s2.run_dirs)) == ("P.s2.V1", 1)
    assert pickle.loads(pickle.dumps(s1)) == s1


def test_list_run_accessions_missing_dir(tmp_path: Path) -> None:
    assert list_run_accessions(tmp_path / "missing") == []


def test_select_quiet_groups() -> None:
    def group(name: str, newest: datetime) -> RunAccessionGroup:
        return RunAccessionGroup(name, (), newest)

    old = group("old", NOW - timedelta(minutes=20))
    edge = group("edge", NOW - timedelta(minutes=10))
    recent = group("recent", NOW - timedelta(minutes=9))
    assert select_quiet_groups([old, edge, recent], timedelta(minutes=10), NOW) == [
        old,
        edge,
    ]
    assert select_quiet_groups([old, edge, recent], timedelta(0), NOW) == [
        old,
        edge,
        recent,
    ]


# combine_accessions ----------------------------------------------------------------


def test_combine_two_runs(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = _two_runs_of_s1(tmp_path, dirs, monkeypatch)
    combined = combine_accessions(group)
    assert combined.labels == {"project": "P", "subject": "s1", "session": "V1"}
    assert combined.run_uid is None
    assert sorted(combined.acquisitions) == ["a", "b"]
    assert combined.metadata[COMBINED_FROM_KEY] == [
        f"P.s1.V1_{UID_1}",
        f"P.s1.V1_{UID_2}",
    ]
    # Path metadata saved with the run accessions' resources is carried over
    resource = next(iter(combined.acquisitions["b"].resources.values()))
    assert resource.metadata["name"] == "b"


def test_combine_identical_resource_kept_once(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _collate(tmp_path, dirs, monkeypatch, UID_1, {"s1/a.json": '{"a": 1}'})
    _collate(tmp_path, dirs, monkeypatch, UID_2, {"s1/a.json": '{"a": 1}'})
    combined = combine_accessions(_group(dirs))
    assert list(combined.acquisitions) == ["a"]
    assert len(combined.acquisitions["a"].resources) == 1


def test_combine_resource_clash(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _collate(tmp_path, dirs, monkeypatch, UID_1, {"s1/a.json": '{"a": 1}'})
    _collate(tmp_path, dirs, monkeypatch, UID_2, {"s1/a.json": '{"a": 2}'})
    group = _group(dirs)
    with pytest.raises(Exception, match="(?i)clash|already"):
        combine_accessions(group, on_resource_clash="error")
    avoided = combine_accessions(group, on_resource_clash="avoid")
    assert len(avoided.acquisitions["a"].resources) == 2
    merged = combine_accessions(group, on_resource_clash="merge")
    (resource,) = merged.acquisitions["a"].resources.values()
    assert len(resource.fileset.fspaths) == 2
    overwritten = combine_accessions(group, on_resource_clash="overwrite")
    (resource,) = overwritten.acquisitions["a"].resources.values()
    assert json.loads(Path(resource.fileset.fspath).read_text()) == {"a": 2}


def test_combine_accession_table_metadata(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = "Session,Cohort\ns1,case\n"
    _collate(tmp_path, dirs, monkeypatch, UID_1, {"s1/a.json": "{}"}, table)
    _collate(tmp_path, dirs, monkeypatch, UID_2, {"s1/b.json": "{}"}, table)
    combined = combine_accessions(_group(dirs))
    assert combined.metadata["Cohort"] == "case"


def test_combine_conflicting_metadata_raises(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _collate(
        tmp_path,
        dirs,
        monkeypatch,
        UID_1,
        {"s1/a.json": "{}"},
        "Session,Cohort\ns1,case\n",
    )
    _collate(
        tmp_path,
        dirs,
        monkeypatch,
        UID_2,
        {"s1/b.json": "{}"},
        "Session,Cohort\ns1,control\n",
    )
    with pytest.raises(ValueError, match="Cohort"):
        combine_accessions(_group(dirs))


# deliver_combined, remove_run_accessions and abandon_group -------------------------


def test_deliver_combined(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = _two_runs_of_s1(tmp_path, dirs, monkeypatch)
    build_dir = prepare_build_dir(dirs.output, UID_3)
    delivered = deliver_combined(
        combine_accessions(group), group, build_dir, dirs.output, "combined"
    )
    assert delivered == dirs.output / "P.s1.V1_combined"
    reloaded = Accession.load(delivered)
    assert reloaded.labels == {"project": "P", "subject": "s1", "session": "V1"}
    assert reloaded.run_uid == "combined"
    assert sorted(reloaded.acquisitions) == ["a", "b"]
    assert LocalSessionListing(delivered).ids == ["P", "s1", "V1"]
    # The run accessions are untouched until they are removed
    assert all(d.exists() for d in group.run_dirs)
    remove_run_accessions(group)
    assert not any(d.exists() for d in group.run_dirs)
    assert Accession.load(delivered).acquisitions["a"].resources  # files kept


def test_deliver_combined_existing_target_raises(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = _two_runs_of_s1(tmp_path, dirs, monkeypatch)
    (dirs.output / "P.s1.V1_combined").mkdir(parents=True)
    build_dir = prepare_build_dir(dirs.output, UID_3)
    with pytest.raises(FileExistsError, match="already in the output directory"):
        deliver_combined(
            combine_accessions(group), group, build_dir, dirs.output, "combined"
        )


def test_deliver_combined_retry_after_crash(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An attempt that delivered the combined accession but crashed before removing the
    run accessions is recognised, so a retry only removes them"""
    group = _two_runs_of_s1(tmp_path, dirs, monkeypatch)
    build_dir = prepare_build_dir(dirs.output, UID_3)
    first = deliver_combined(
        combine_accessions(group), group, build_dir, dirs.output, "combined"
    )
    again = deliver_combined(
        combine_accessions(group), group, build_dir, dirs.output, "combined"
    )
    assert again == first


def test_abandon_group(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = _two_runs_of_s1(tmp_path, dirs, monkeypatch)
    moved = abandon_group(group, dirs.errors, ValueError("clash"), UID_3)
    assert moved == dirs.errors / f"P.s1.V1_{UID_3}"
    assert sorted(p.name for p in moved.iterdir()) == sorted(
        [ERROR_MANIFEST] + [d.name for d in group.run_dirs]
    )
    record = json.loads((moved / ERROR_MANIFEST).read_text())
    assert (record["type"], record["message"]) == ("ValueError", "clash")
    assert not any(d.exists() for d in group.run_dirs)


# combine_run_accessions ------------------------------------------------------------


def _combine(dirs: Dirs, **kwargs: ty.Any) -> list[str]:
    options: dict[str, ty.Any] = dict(now=NOW)
    options.update(kwargs)
    return combine_run_accessions(
        dirs.runs,
        dirs.output,
        dirs.errors,
        timedelta(minutes=10),
        "combined",
        **options,
    )


def _delivered(dirs: Dirs) -> list[str]:
    if not dirs.output.exists():
        return []
    return sorted(p.name for p in dirs.output.iterdir() if p.name != BUILD_NAME_DEFAULT)


def test_combine_run_accessions_quiet_and_recent(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_runs_of_s1(tmp_path, dirs, monkeypatch)  # quiet since 01:30
    _collate(tmp_path, dirs, monkeypatch, UID_3, {"s2/c.json": "{}"})  # 01:55, recent
    assert _combine(dirs) == []
    assert _delivered(dirs) == ["P.s1.V1_combined"]
    assert [g.name for g in list_run_accessions(dirs.runs)] == ["P.s2.V1"]
    assert not any((dirs.output / BUILD_NAME_DEFAULT).iterdir())
    # Later, s2 is quiet too
    assert _combine(dirs, now=NOW + timedelta(minutes=10)) == []
    assert _delivered(dirs) == ["P.s1.V1_combined", "P.s2.V1_combined"]
    assert list_run_accessions(dirs.runs) == []


def test_combine_run_accessions_failed_group_moved_to_errors(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _collate(tmp_path, dirs, monkeypatch, UID_1, {"s1/a.json": '{"a": 1}'})
    _collate(tmp_path, dirs, monkeypatch, UID_2, {"s1/a.json": '{"a": 2}'})
    _collate(tmp_path, dirs, monkeypatch, UID_1.replace("a", "f"), {"s2/c.json": "{}"})
    (error,) = _combine(dirs)
    assert "P.s1.V1" in error
    assert _delivered(dirs) == ["P.s2.V1_combined"]
    (moved,) = dirs.errors.iterdir()
    assert moved.name.startswith("P.s1.V1_")
    assert (moved / ERROR_MANIFEST).exists()
    assert list_run_accessions(dirs.runs) == []


def test_combine_run_accessions_raise_errors(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _collate(tmp_path, dirs, monkeypatch, UID_1, {"s1/a.json": '{"a": 1}'})
    _collate(tmp_path, dirs, monkeypatch, UID_2, {"s1/a.json": '{"a": 2}'})
    with pytest.raises(Exception):
        _combine(dirs, raise_errors=True)
    assert len(list(dirs.errors.iterdir())) == 1
    assert not any((dirs.output / BUILD_NAME_DEFAULT).iterdir())


def test_combine_run_accessions_nothing_quiet_creates_nothing(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _collate(tmp_path, dirs, monkeypatch, UID_3, {"s1/a.json": "{}"})
    assert _combine(dirs) == []
    assert not dirs.output.exists()
    assert not dirs.errors.exists()


def test_combine_run_accessions_arrival_during_combine_waits(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run accession delivered after the listing is left for the next combine"""
    from accessionflow.api.collate import composites

    _two_runs_of_s1(tmp_path, dirs, monkeypatch)
    real_list = composites.list_run_accessions
    late = "20261126015900_dddddd"

    def list_then_deliver(runs_dir: Path) -> list[RunAccessionGroup]:
        groups = real_list(runs_dir)
        _collate(tmp_path, dirs, monkeypatch, late, {"s1/z.json": "{}"})
        monkeypatch.setattr(composites, "list_run_accessions", list_then_deliver)
        return groups

    monkeypatch.setattr(composites, "list_run_accessions", list_then_deliver)
    assert _combine(dirs) == []
    assert _delivered(dirs) == ["P.s1.V1_combined"]
    (left,) = list_run_accessions(dirs.runs)
    assert [d.name for d in left.run_dirs] == [f"P.s1.V1_{late}"]


def test_combine_run_accessions_bad_arguments_change_nothing(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = _two_runs_of_s1(tmp_path, dirs, monkeypatch)
    with pytest.raises(ValueError, match="Primary label"):
        combine_run_accessions(
            dirs.runs, dirs.output, dirs.errors, timedelta(0), "a_b", now=NOW
        )
    with pytest.raises(ValueError, match="negative"):
        combine_run_accessions(
            dirs.runs, dirs.output, dirs.errors, timedelta(-1), "combined", now=NOW
        )
    assert all(d.exists() for d in group.run_dirs)
    assert not dirs.output.exists()


def test_combine_accessions_keeps_the_metadata_collate_saved(
    tmp_path: Path, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = _two_runs_of_s1(tmp_path, dirs, monkeypatch)
    # Fields in the files that collate didn't save, as with dont_read_metadata, one
    # of them clashing with a field from the path
    monkeypatch.setattr(
        Json,
        "read_metadata",
        lambda self, **kwargs: {"header": "x", "name": "from-header"},
        raising=False,
    )
    combined = combine_accessions(group)
    resources = [
        resource
        for acquisition in combined.acquisitions.values()
        for resource in acquisition.resources.values()
    ]
    assert len(resources) == 2
    for resource in resources:
        assert "header" not in resource.metadata
        assert resource.metadata["name"] in ("a", "b")
