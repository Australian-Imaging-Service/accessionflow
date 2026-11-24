"""Turning the claimed files into file-sets (see ``prefect-migration-docs/ROADMAP.md``,
Phase 1)"""

import typing as ty

from fileformats.core import FileSet, to_mime
from fileformats.generic import Directory

__all__ = ["RecursionPlan", "check_datatypes", "plan_recursion"]


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


class RecursionPlan(ty.NamedTuple):
    """How ``--recursive`` expands the claimed files, as worked out by
    `plan_recursion`"""

    recurse_into_dirs: bool
    """whether the walk stops at a directory that matches a directory datatype (and
    keeps it whole) instead of flattening every directory into its files"""
    ignore_datatypes: list[type[FileSet]]
    """the datatypes to ignore, with ``Directory`` added for recursion over files
    only, so that the bare directories it finds are dropped"""


def plan_recursion(
    datatypes: ty.Sequence[type[FileSet]],
    ignore_datatypes: ty.Sequence[type[FileSet]] = (),
    recursive: bool = False,
) -> RecursionPlan:
    """Checks the datatypes can be used with ``recursive``, and works out how the
    claimed files are expanded. It only checks and computes, so it runs before any step
    that changes the file system

    With ``recursive``, if any wanted or ignored datatype is a directory format, the
    walk stops at a directory that matches one of them. Otherwise every directory is
    flattened into its files, and ``Directory`` is added to the ignored datatypes so
    the bare directories are dropped instead of raising.

    Parameters
    ----------
    datatypes : Sequence[type[FileSet]]
        the datatypes to collate
    ignore_datatypes : Sequence[type[FileSet]], optional
        the datatypes that are expected in the input but not wanted. Not changed
    recursive : bool, optional
        whether directories are searched recursively

    Returns
    -------
    RecursionPlan
        ``(recurse_into_dirs, ignore_datatypes)``, with a new ``ignore_datatypes`` list

    Raises
    ------
    ValueError
        if ``recursive`` is given with ``generic/directory`` or ``generic/file-set`` as
        a datatype, since they match every directory at every depth
    """
    ignore = list(ignore_datatypes)
    if not recursive:
        return RecursionPlan(False, ignore)
    if Directory in datatypes or FileSet in datatypes:
        names = [to_mime(d, official=False) for d in datatypes]
        raise ValueError(
            "Cannot use `generic/directory` or `generic/file-set` as a `--datatype` "
            "with `--recursive` (they match every directory / path at every depth). "
            f"Use a specific directory datatype instead (datatypes={names})"
        )
    recurse_into_dirs = any(
        isinstance(d, type) and issubclass(d, Directory) for d in (*datatypes, *ignore)
    )
    if not recurse_into_dirs:
        # No directory format is wanted or ignored, so Directory isn't in the list yet
        ignore.append(Directory)
    return RecursionPlan(recurse_into_dirs, ignore)
