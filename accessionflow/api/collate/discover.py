"""Choosing the files to collate, before collation starts

Not part of the collate API itself: the API is given the files to collate as a list of
paths. The CLI chooses them with `list_input_files`, and so can the flows repository
(see ``prefect-migration-docs/ROADMAP.md``, Phase 1).
"""

import os
import typing as ty
from glob import glob
from pathlib import Path

from accessionflow.helpers.glob2re import glob_to_regex
from accessionflow.helpers.logging import logger
from accessionflow.model.accession import fix_long_path

__all__ = ["list_input_files"]


def list_input_files(
    input_paths: ty.Sequence[str | Path],
    exclude_paths: ty.Sequence[str] = (),
    metadata_table_paths: ty.Sequence[Path] = (),
) -> list[Path]:
    """Lists the files to collate, from the CLI's ``INPUT_PATHS`` and
    ``--exclude-path``

    Only files are listed. Collation moves the files it is given into a processing
    area, so a file that isn't listed is never moved.

    - A `Path`, or a string without ``*``, is a path, which must exist. A file is
      listed as given. A directory is walked: every file in it and in its
      subdirectories is listed, so a directory datatype in it (e.g. a DICOM directory)
      is kept whole. The listing is the same with or without ``--recursive``, which
      only changes how the files are classified.
    - A string with ``*`` is a glob pattern (``**`` crosses directories). A matching
      file is listed, and a matching directory is walked.
    - Hidden files and directories, whose names start with ``.``, are skipped at every
      depth, because they are often uploads still in progress (e.g. rsync writes to
      ``.<name>.<random>`` and then renames). A hidden file given as an input path is
      still listed.
    - Only regular files are listed (a symlink to a file counts). Symlinked
      directories aren't followed.
    - The metadata tables (``--metadata-table``) are left out, wherever they are
      listed from, so a table kept in an input directory stays where it is, for this
      run (`load_metadata_tables`) and later ones.

    Parameters
    ----------
    input_paths : Sequence[str | Path]
        directories, files and glob patterns to list the files from
    exclude_paths : Sequence[str], optional
        glob patterns matched against each file's path relative to the input directory
        it was found in. ``*`` doesn't cross ``/``, and ``**`` does. A file is excluded
        if its relative path, or that of any directory it is in, matches, so a pattern
        that matches a directory excludes everything in it. Files found by a glob
        pattern outside every input directory aren't matched
    metadata_table_paths : Sequence[Path], optional
        the files of the metadata tables, which are left out. A table is recognised
        however its path is written (relative, with '..' or through a symlink). A path
        that doesn't exist is ignored

    Returns
    -------
    list[Path]
        the files to collate, without duplicates, sorted

    Raises
    ------
    ValueError
        if an input path that isn't a glob pattern doesn't exist
    """
    fspaths: list[Path] = []
    input_dirs: list[Path] = []
    for input_path in input_paths:
        if isinstance(input_path, Path) or "*" not in input_path:
            path = Path(input_path)
            if not path.exists():
                raise ValueError(f"Provided file-system path '{path}' does not exist")
            if path.is_dir():
                input_dirs.append(path)
                fspaths.extend(_walk_files(path))
            else:
                fspaths.append(path)
        else:
            logger.debug("Searching for file-system paths using glob '%s'", input_path)
            for match in sorted(glob(input_path, recursive=True)):
                matched = Path(match)
                if matched.is_dir():
                    fspaths.extend(_walk_files(matched))
                elif matched.is_file():
                    fspaths.append(matched)

    fspaths = [fix_long_path(p) for p in fspaths]
    if exclude_paths:
        fspaths = _drop_excluded(fspaths, input_dirs, exclude_paths)
    if metadata_table_paths:
        fspaths = _drop_metadata_tables(fspaths, metadata_table_paths)

    unique: dict[Path, Path] = {}
    for fspath in fspaths:
        unique.setdefault(fspath.absolute(), fspath)
    return sorted(unique.values())


def _walk_files(root: Path) -> ty.Iterator[Path]:
    """Yields the regular files under ``root``, skipping hidden files and directories
    and not following symlinked directories"""
    logger.debug("Listing the files in '%s'", str(root))
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if filename.startswith("."):
                continue
            fspath = Path(dirpath) / filename
            if fspath.is_file():
                yield fspath


def _drop_excluded(
    fspaths: ty.Sequence[Path],
    input_dirs: ty.Sequence[Path],
    exclude_globs: ty.Sequence[str],
) -> list[Path]:
    """Drops every file whose path relative to one of ``input_dirs``, or the relative
    path of a directory it is in, matches one of ``exclude_globs``"""
    matchers = [glob_to_regex(g) for g in exclude_globs]
    bases = [fix_long_path(d) for d in input_dirs]
    kept: list[Path] = []
    for fspath in fspaths:
        candidates: list[str] = []
        for base in bases:
            try:
                parts = fspath.relative_to(base).parts
            except ValueError:
                continue
            candidates.extend("/".join(parts[: i + 1]) for i in range(len(parts)))
        if any(m.match(c) for m in matchers for c in candidates):
            logger.debug("Excluding '%s' (matched --exclude-path)", fspath)
            continue
        kept.append(fspath)
    return kept


def _drop_metadata_tables(
    fspaths: ty.Sequence[Path], metadata_table_paths: ty.Sequence[Path]
) -> list[Path]:
    """Drops the files that are metadata tables. Only the files with the base name of a
    table are compared with it, so a large listing isn't stat'ed in full"""
    tables = [Path(t) for t in metadata_table_paths if Path(t).exists()]
    # A table named through a symlink may have a different name from its file
    names = {t.name for t in tables} | {t.resolve().name for t in tables}
    kept: list[Path] = []
    for fspath in fspaths:
        if fspath.name in names and any(os.path.samefile(fspath, t) for t in tables):
            logger.debug("Leaving out metadata table '%s'", fspath)
            continue
        kept.append(fspath)
    return kept
