from pathlib import Path

import pytest

from accessionflow.helpers.remotes import LocalSessionListing
from accessionflow.helpers.run_uid import split_run_uid

NEW_UID = "20261125073856_a3f09c"
OLD_UID = "abc12320261124010203"


@pytest.mark.parametrize(
    "name, expected",
    [
        (f"proj.subj.sess_{NEW_UID}", ("proj.subj.sess", NEW_UID)),
        (f"proj.subj.sess_{OLD_UID}", ("proj.subj.sess", OLD_UID)),
        # labels containing '_' and '-'
        (f"proj.subj-01.S1_scan_{NEW_UID}", ("proj.subj-01.S1_scan", NEW_UID)),
        # a single level, which has no '.'
        (f"subj_{NEW_UID}", ("subj", NEW_UID)),
        # no run UID
        ("proj.subj.sess", ("proj.subj.sess", None)),
        ("proj.subj.sess_v2", ("proj.subj.sess_v2", None)),
        ("proj.subj.sess_20261125073856", ("proj.subj.sess_20261125073856", None)),
        # the run UID joined by '.', as names written before were
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
