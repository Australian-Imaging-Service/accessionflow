import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from accessionflow.helpers.metadata import Metadata
from accessionflow.helpers.remotes import LocalSessionListing
from accessionflow.helpers.run_uid import (
    PRIMARY_LABEL_RE,
    run_uid_time,
    split_name_suffix,
    split_run_uid,
)

NEW_UID = "20261125073856_a3f09c"
# The run UID Accession.from_paths made (a hash, then the time), no longer recognised
OLD_UID = "abc12320261124010203"


@pytest.mark.parametrize(
    "name, expected",
    [
        (f"proj.subj.sess_{NEW_UID}", ("proj.subj.sess", NEW_UID)),
        # labels containing '_' and '-'
        (f"proj.subj-01.S1_scan_{NEW_UID}", ("proj.subj-01.S1_scan", NEW_UID)),
        # a single level, which has no '.'
        (f"subj_{NEW_UID}", ("subj", NEW_UID)),
        # no run UID
        ("proj.subj.sess", ("proj.subj.sess", None)),
        ("proj.subj.sess_v2", ("proj.subj.sess_v2", None)),
        ("proj.subj.sess_20261125073856", ("proj.subj.sess_20261125073856", None)),
        # from_paths' run UID, joined by '_' or by '.', as names written before were
        (f"proj.subj.sess_{OLD_UID}", (f"proj.subj.sess_{OLD_UID}", None)),
        (f"proj.subj.sess.{OLD_UID}", (f"proj.subj.sess.{OLD_UID}", None)),
    ],
)
def test_split_run_uid(name: str, expected: tuple[str, str | None]) -> None:
    assert split_run_uid(name) == expected


@pytest.mark.parametrize(
    "dirname, ids",
    [
        (f"proj.subj.sess_{NEW_UID}", ["proj", "subj", "sess"]),
        ("proj.subj.sess", ["proj", "subj", "sess"]),
        (f"proj.subj.sess.{OLD_UID}", ["proj", "subj", "sess", OLD_UID]),  # as before
        ("proj-subj-sess", ["proj", "subj", "sess"]),  # legacy delimiter
    ],
)
def test_session_listing_ids(tmp_path: Path, dirname: str, ids: list[str]) -> None:
    assert LocalSessionListing(tmp_path / dirname).ids == ids


LABELS = ["proj", "subj", "S1_scan"]


@pytest.mark.parametrize(
    "name, labels, expected",
    [
        # with the saved labels, a suffix of any kind is split off exactly
        ("proj.subj.S1_scan_combined", LABELS, ("proj.subj.S1_scan", "combined")),
        (f"proj.subj.S1_scan_{NEW_UID}", LABELS, ("proj.subj.S1_scan", NEW_UID)),
        ("proj.subj.S1_scan", LABELS, ("proj.subj.S1_scan", None)),
        # without them, only a run UID is recognised
        ("proj.subj.S1_scan_combined", None, ("proj.subj.S1_scan_combined", None)),
        (f"proj.subj.S1_scan_{NEW_UID}", None, ("proj.subj.S1_scan", NEW_UID)),
        # a name that doesn't start with the saved labels falls back to the run UID
        (f"other.subj.sess_{NEW_UID}", LABELS, ("other.subj.sess", NEW_UID)),
    ],
)
def test_split_name_suffix(
    name: str, labels: list[str] | None, expected: tuple[str, str | None]
) -> None:
    assert split_name_suffix(name, labels) == expected


def test_run_uid_time() -> None:
    expected = datetime(2026, 11, 25, 7, 38, 56, tzinfo=UTC)
    assert run_uid_time(NEW_UID) == expected
    for not_a_run_uid in ("combined", OLD_UID):
        with pytest.raises(ValueError, match="isn't a run UID"):
            run_uid_time(not_a_run_uid)


@pytest.mark.parametrize("label", ["combined", "v2", "Combined-1", "abc123"])
def test_primary_label_re_accepts(label: str) -> None:
    assert PRIMARY_LABEL_RE.fullmatch(label)


@pytest.mark.parametrize("label", ["", "a.b", "a_b", "-a", "a/b", "a b"])
def test_primary_label_re_refuses(label: str) -> None:
    assert not PRIMARY_LABEL_RE.fullmatch(label)


def test_session_listing_ids_from_saved_labels(tmp_path: Path) -> None:
    """A combined accession's name is read with the labels saved in its metadata, as
    the name alone can't tell the primary label from a label with '_' in it"""
    session_dir = tmp_path / "proj.subj.S1_scan_combined"
    session_dir.mkdir()
    (session_dir / Metadata.FNAME).write_text(
        json.dumps(
            {"__labels__": {"project": "proj", "subject": "subj", "session": "S1_scan"}}
        )
    )
    assert LocalSessionListing(session_dir).ids == ["proj", "subj", "S1_scan"]
