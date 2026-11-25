"""Recognising the run UID at the end of a staged accession's directory name

A labelled accession's directory is named ``<labels>_<run_uid>``, e.g.
``proj.subj.sess_20261125073856_a3f09c``. Labels can contain ``_`` and ``-``, and the
run UID contains ``_`` itself, so the run UID is found by matching its whole pattern at
the end of the name, never by splitting at the last separator.
"""

import re

__all__ = ["RUN_UID_RE", "RUN_UID_SEPARATOR", "split_run_uid"]

# A run UID made by make_run_uid (the UTC time, '_' and 6 random hex characters), or by
# Accession.from_paths until it is removed (6 hex characters of a hash, then the time)
RUN_UID_RE = re.compile(r"\d{14}_[0-9a-f]{6}|[0-9a-f]{6}\d{14}")

# Joins the labels and the run UID in a labelled accession's directory name
RUN_UID_SEPARATOR = "_"

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
