"""Taking ownership of the files to collate (see ``prefect-migration-docs/ROADMAP.md``,
Phase 1)"""

import hashlib
import typing as ty
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["make_run_uid"]


def make_run_uid(
    input_files: ty.Sequence[Path],
    now: datetime | None = None,
) -> str:
    """Makes the UID of a collation run, which names its build directory, its claim
    directory and the staged directory of each accession it collates

    The UID is the first 6 hex characters of a SHA-256 hash of the files' absolute
    paths, followed by the time in UTC as ``YYYYMMDDHHMMSS``. It holds only hex
    characters and digits, never a ``.``, which separates it from the labels in a
    staged directory's name.

    Make it once per run. A retry of the run passes the same value on, rather than
    making a new one, so that it finds the directories the first attempt made.

    Parameters
    ----------
    input_files : Sequence[Path]
        the files the run collates. Their order doesn't matter
    now : datetime, optional
        the time of the run, by default the current time. A time with a time zone is
        converted to UTC, and a naive time is taken as local time

    Returns
    -------
    str
        the run UID
    """
    crypto = hashlib.sha256()
    for fspath in sorted(str(p.absolute()) for p in input_files):
        crypto.update(fspath.encode())
    when = datetime.now(UTC) if now is None else now.astimezone(UTC)
    return crypto.hexdigest()[:6] + when.strftime("%Y%m%d%H%M%S")
