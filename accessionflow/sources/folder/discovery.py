"""Finds the files to collate in local or mounted folders, expanding directories and
glob patterns into a list of individual files for :func:`collate`"""

import re
import typing as ty
from glob import glob
from pathlib import Path

from accessionflow.helpers.logging import logger
from accessionflow.model.accession import fix_long_path


def find_files(
    input_paths: ty.Sequence[str | Path],
    recursive: bool = False,
    exclude_paths: ty.Sequence[str] = (),
) -> list[Path]:
    """Expands the input paths into the individual files they select

    Parameters
    ----------
    input_paths : Sequence[str | Path]
        paths to files, to directories whose files are collated, or glob patterns that
        select the paths directly
    recursive : bool
        whether to include the files in the subdirectories of input directories, by
        default only the files directly within them are included
    exclude_paths : Sequence[str]
        glob patterns matched against each path *relative to its input directory*.
        Matching files are dropped. ``*`` does not cross ``/``, ``**`` does.

    Returns
    -------
    list[Path]
        the files that were found. Directories are never returned, only the files
        within them

    Raises
    ------
    ValueError
        if an input path that isn't a glob pattern doesn't exist
    """
    if isinstance(input_paths, (str, Path)):
        input_paths = [input_paths]
    fspaths: list[Path] = []
    input_dirs: list[Path] = []
    for input_path in input_paths:
        logger.debug("Searching for files in '%s'", str(input_path))
        if isinstance(input_path, Path) or "*" not in input_path:
            input_path = Path(input_path)
            if not input_path.exists():
                raise ValueError(
                    f"Provided file-system path '{input_path}' does not exist"
                )
            if input_path.is_dir():
                input_dirs.append(input_path)
                if recursive:
                    fspaths.extend(
                        Path(p)
                        for p in glob(str(input_path) + "/**/*", recursive=True)
                    )
                else:
                    fspaths.extend(input_path.iterdir())
            else:
                fspaths.append(input_path)
        else:
            fspaths.extend(Path(p) for p in glob(input_path, recursive=True))

    files: list[Path] = []
    for fspath in fspaths:
        if fspath.is_dir():
            logger.debug("Skipping directory '%s', only files are collated", fspath)
        else:
            files.append(fix_long_path(fspath))

    return drop_excluded_paths(files, input_dirs, exclude_paths)


def drop_excluded_paths(
    fspaths: ty.Sequence[Path],
    input_dirs: ty.Sequence[Path],
    exclude_globs: ty.Sequence[str],
) -> list[Path]:
    """Drop every ``fspath`` whose path *relative to one of ``input_dirs``* matches
    one of ``exclude_globs``. Unlike ``allow_unrecognised`` this fires before
    classification, so it removes a path even if a ``--datatype`` would claim it
    (e.g. a vendor thumbnail that is a valid ``image/png``). Globs use the standard
    ``glob`` syntax - ``*`` does not cross ``/``, ``**`` does - and match the whole
    relative path.
    """
    if not exclude_globs:
        return list(fspaths)
    matchers = [glob_to_regex(g) for g in exclude_globs]
    kept: list[Path] = []
    for p in fspaths:
        rels: list[str] = []
        for base in input_dirs:
            try:
                rels.append(str(p.relative_to(base)))
            except ValueError:
                continue
        if any(m.match(rel) for m in matchers for rel in rels):
            logger.debug("Excluding '%s' (matched --exclude-path)", p)
            continue
        kept.append(p)
    return kept


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    r"""Anchored regex for a ``/``-aware glob: ``*`` / ``?`` / ``[...]`` do not cross
    ``/``, ``**`` (optionally followed by ``/``) matches across directory levels.
    Equivalent to ``glob.translate(pattern, recursive=True)`` (py3.13+), spelled out
    so 3.11/3.12 work too.
    """
    i, n = 0, len(pattern)
    out = ["(?s:"]
    while i < n:
        c = pattern[i]
        i += 1
        if c == "*":
            if i < n and pattern[i] == "*":
                i += 1
                if i < n and pattern[i] == "/":
                    i += 1
                    out.append("(?:[^/]*/)*")  # '**/' -> zero or more segments
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = i + 1 if i < n and pattern[i] in "!^" else i
            j = j + 1 if j < n and pattern[j] == "]" else j
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:
                out.append(r"\[")
            else:
                inner = pattern[i:j]
                i = j + 1
                if inner[:1] in ("!", "^"):
                    inner = "^" + inner[1:]
                out.append("[" + inner + "]")
        else:
            out.append(re.escape(c))
    out.append(r")\Z")
    return re.compile("".join(out))
