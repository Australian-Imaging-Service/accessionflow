"""Turning the claimed files into file-sets (see ``prefect-migration-docs/ROADMAP.md``,
Phase 1)"""

import typing as ty

from fileformats.core import FileSet, to_mime

__all__ = ["check_datatypes"]


def check_datatypes(
    datatypes: ty.Sequence[type[FileSet]],
    ignore_datatypes: ty.Sequence[type[FileSet]] = (),
) -> None:
    """Checks that no datatype is both wanted and ignored. The first step of the
    collate API: it only checks its arguments, so it runs before any step that changes
    the file system

    Parameters
    ----------
    datatypes : Sequence[type[FileSet]]
        the datatypes to collate
    ignore_datatypes : Sequence[type[FileSet]], optional
        the datatypes that are expected in the input but not wanted

    Raises
    ------
    ValueError
        if a datatype is in both ``datatypes`` and ``ignore_datatypes``. The message
        names each such datatype by its MIME-like name
    """
    if contradicting := set(datatypes) & set(ignore_datatypes):
        names = sorted(to_mime(d, official=False) for d in contradicting)
        raise ValueError(
            "The following datatypes were listed for both inclusion (`datatypes`) and "
            f"exclusion (`ignore_datatypes`): {names}"
        )
