"""Turning the claimed files into file-sets (see ``prefect-migration-docs/ROADMAP.md``,
Phase 1)"""

import typing as ty
from pathlib import Path

from fileformats.core import FileSet, to_mime
from fileformats.generic import Directory

from .claim import ClaimedFiles

__all__ = [
    "RecursionPlan",
    "check_datatypes",
    "expand_claimed_paths",
    "plan_recursion",
]


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


def expand_claimed_paths(
    claimed: ClaimedFiles,
    datatypes: ty.Sequence[type[FileSet]],
    recursion: RecursionPlan,
    recursive: bool = False,
) -> list[Path]:
    """Expands the claimed source roots into the paths to classify, with the same rules
    as the input directories had before the claim, so ``--recursive`` and directory
    datatypes behave as they did

    - Without ``recursive``: each root's top-level entries, so a subdirectory (e.g. a
      DICOM directory) is classified whole.
    - With ``recursive`` and only file datatypes: every claimed file under each root.
    - With ``recursive`` and a directory format among the wanted or ignored datatypes
      (``recursion.recurse_into_dirs``): a walk that keeps a directory matching a
      wanted datatype whole, skips one matching an ignored directory format, and
      descends into any other.

    Only claimed files, and the directories that hold them, are ever returned. Roots
    inside another root are dropped, so nothing is listed twice. To get the same
    top-level entries as listing the input directories, claim the files with those
    directories as the ``source_roots``.

    Parameters
    ----------
    claimed : ClaimedFiles
        the run's claimed files, from `claim_input_files`
    datatypes : Sequence[type[FileSet]]
        the datatypes to collate
    recursion : RecursionPlan
        from `plan_recursion`, given the same ``datatypes`` and ``recursive``
    recursive : bool, optional
        whether directories are searched recursively

    Returns
    -------
    list[Path]
        the paths in the run directory to classify, sorted, without duplicates
    """
    keep = set(claimed.files)
    for fspath in claimed.files:
        keep.update(p for p in fspath.parents if p.is_relative_to(claimed.files_dir))
    roots = sorted(set(claimed.claimed_roots))
    outermost = [
        r for r in roots if not any(r != o and r.is_relative_to(o) for o in roots)
    ]
    expanded: set[Path] = set()
    for root in outermost:
        if root not in keep:
            continue  # nothing was claimed from this root
        if not recursive:
            expanded.update(p for p in root.iterdir() if p in keep)
        elif not recursion.recurse_into_dirs:
            expanded.update(p for p in claimed.files if p.is_relative_to(root))
        else:
            expanded.update(
                _walk_pruning(root, datatypes, recursion.ignore_datatypes, keep)
            )
    return sorted(expanded)


def _walk_pruning(
    root: Path,
    datatypes: ty.Sequence[type[FileSet]],
    ignore_datatypes: ty.Sequence[type[FileSet]],
    keep: ty.Collection[Path],
) -> ty.Iterator[Path]:
    """Walks ``root``, yielding the entries in ``keep`` to classify

    A directory that validates as one of ``datatypes`` is yielded whole and not
    descended into. A directory that validates only as an ``ignore_datatypes``
    directory format is skipped whole. Any other directory is descended into. Every
    file is yielded, so an unlisted file type still raises when it is classified.
    Copied from ``accessionflow.model.accession._recursive_collect``, which
    ``Accession.from_paths`` uses until it is removed, with the filter on ``keep``
    added.
    """
    want = tuple(d for d in datatypes if issubclass(d, Directory))
    skip = tuple(d for d in ignore_datatypes if issubclass(d, Directory))
    stack: list[Path] = [root]
    seen: set[Path] = set()
    while stack:
        current = stack.pop()
        resolved = current.resolve()
        if resolved in seen:  # guard against symlink loops
            continue
        seen.add(resolved)
        for child in sorted(current.iterdir()):
            if child not in keep:
                continue
            if not child.is_dir() or any(dt.matches(child) for dt in want):
                yield child
            elif any(dt.matches(child) for dt in skip):
                continue
            else:
                stack.append(child)
