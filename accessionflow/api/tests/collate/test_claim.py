import hashlib
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from accessionflow.api.collate import make_run_uid
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
