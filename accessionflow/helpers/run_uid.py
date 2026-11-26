"""Recognising the suffix at the end of a staged accession's directory name

A labelled accession's directory is named ``<labels>_<suffix>``. The suffix is a run
UID for an accession delivered by a collate run, e.g.
``proj.subj.sess_20261125073856_a3f09c``, or a primary label for one written by the
combiner, e.g. ``proj.subj.sess_combined``. Labels can contain ``_`` and ``-``, and the
run UID contains ``_`` itself, so a run UID is found by matching its whole pattern at
the end of the name, never by splitting at the last separator. A primary label can only
be told apart from the labels by knowing the labels, which every accession saves in its
metadata (see `split_name_suffix`).
"""

import re
import typing as ty
from datetime import UTC, datetime

__all__ = [
    "PRIMARY_LABEL_RE",
    "RUN_UID_RE",
    "RUN_UID_SEPARATOR",
    "run_uid_time",
    "split_name_suffix",
    "split_run_uid",
]

# A run UID made by make_run_uid (the UTC time, '_' and 6 random hex characters), or by
# Accession.from_paths until it is removed (6 hex characters of a hash, then the time)
RUN_UID_RE = re.compile(r"\d{14}_[0-9a-f]{6}|[0-9a-f]{6}\d{14}")

# Joins the labels and the suffix (a run UID or a primary label) in a labelled
# accession's directory name
RUN_UID_SEPARATOR = "_"

# A primary label, which names a combined accession in place of a run UID. It has no
# '.' (which joins the labels) and no '_' (which joins the suffix)
PRIMARY_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")

_NEW_RUN_UID = re.compile(r"(?P<time>\d{14})_[0-9a-f]{6}")
_OLD_RUN_UID = re.compile(r"[0-9a-f]{6}(?P<time>\d{14})")

_TRAILING_RUN_UID = re.compile(
    rf"(?P<base>.+){RUN_UID_SEPARATOR}(?P<run_uid>{RUN_UID_RE.pattern})\Z"
)


def split_run_uid(name: str) -> tuple[str, str | None]:
    """Splits a trailing ``_<run_uid>`` off a directory name

    Parameters
    ----------
    name : str
        the directory name, e.g. ``proj.subj.sess_20261125073856_a3f09c``

    Returns
    -------
    tuple[str, str | None]
        the name without the run UID, and the run UID, or the name unchanged and None
        if it doesn't end with one
    """
    if match := _TRAILING_RUN_UID.fullmatch(name):
        return match["base"], match["run_uid"]
    return name, None


def split_name_suffix(
    name: str, labels: ty.Sequence[str] | None = None
) -> tuple[str, str | None]:
    """Splits the suffix, a run UID or a primary label, off a labelled accession's
    directory name

    Parameters
    ----------
    name : str
        the directory name, e.g. ``proj.subj.sess_combined``
    labels : Sequence[str], optional
        the accession's labels in level order, as saved in its metadata. With them, the
        name is matched exactly, so a suffix of any kind is found, even when a label
        contains ``_``. Without them (an accession staged before the labels were saved),
        only a run UID can be recognised (`split_run_uid`)

    Returns
    -------
    tuple[str, str | None]
        the name without the suffix, and the suffix, or the name unchanged and None if
        it has none
    """
    if labels:
        base = ".".join(labels)
        if name == base:
            return name, None
        prefix = base + RUN_UID_SEPARATOR
        if name.startswith(prefix) and len(name) > len(prefix):
            return base, name[len(prefix) :]
    return split_run_uid(name)


def run_uid_time(run_uid: str) -> datetime:
    """The time a run UID was made, in UTC

    Parameters
    ----------
    run_uid : str
        a run UID, ``YYYYMMDDHHMMSS_<6 hex>`` (`make_run_uid`) or, from
        ``Accession.from_paths``, ``<6 hex>YYYYMMDDHHMMSS``

    Returns
    -------
    datetime
        the time, with the UTC time zone

    Raises
    ------
    ValueError
        if ``run_uid`` isn't a run UID
    """
    match = _NEW_RUN_UID.fullmatch(run_uid) or _OLD_RUN_UID.fullmatch(run_uid)
    if match is None:
        raise ValueError(f"'{run_uid}' isn't a run UID")
    return datetime.strptime(match["time"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
