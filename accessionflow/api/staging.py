"""Helpers shared by every stage for writing accessions into a staging directory.

Each stage builds an accession in a subdirectory of its output directory and moves it
into place once it is complete, so that a later stage never sees a partly written
accession. These helpers are step functions in the sense of the Prefect migration
roadmap (``prefect-migration-docs/ROADMAP.md``): small, with explicit inputs and
outputs, and no dependency on Prefect.
"""

import os
import traceback
import typing as ty
from pathlib import Path

from tqdm import tqdm

from accessionflow.helpers.logging import logger
from accessionflow.model.accession import Accession

__all__ = [
    "BUILD_NAME_DEFAULT",
    "check_run_uid",
    "prepare_build_dir",
    "prune_empty_dirs",
    "remove_build_dir",
    "move_into_place",
    "for_each_accession",
]

# The subdirectory of a stage's output directory that accessions are built in before
# they are moved into place
BUILD_NAME_DEFAULT = "__build__"

T = ty.TypeVar("T")


def check_run_uid(run_uid: str, purpose: str) -> None:
    """Checks that a run UID can name a run's directory: a single path component that
    isn't hidden and doesn't start with ``__``, so that it can't escape its parent or be
    mistaken for a hidden or internal entry

    Parameters
    ----------
    run_uid : str
        the run UID to check
    purpose : str
        what the run UID names, e.g. 'build directory', for the error message

    Raises
    ------
    ValueError
        if ``run_uid`` isn't a valid directory name
    """
    if not run_uid or Path(run_uid).name != run_uid or run_uid.startswith((".", "__")):
        raise ValueError(f"Invalid run UID for a {purpose}: {run_uid!r}")


def prepare_build_dir(output_dir: Path, run_uid: str, exclusive: bool = False) -> Path:
    """Creates the build directory of one run of a stage. Each run builds in its own
    subdirectory of ``BUILD_NAME_DEFAULT``, so that runs writing to the same output
    directory at the same time don't collide.

    A new run creates it exclusively, so that a UID another run has already taken is
    caught: the run then makes another UID. A retry of a run reuses the directory its
    first attempt created.

    Parameters
    ----------
    output_dir : Path
        the stage's output (staging) directory
    run_uid : str
        the UID of the run, which names its build directory. It must be a single,
        non-hidden path component that doesn't start with ``__``
    exclusive : bool, optional
        raise ``FileExistsError`` if the run's build directory already exists, for a
        new run. By default, an existing directory is reused, for a retry

    Returns
    -------
    Path
        the run's build directory, ``output_dir / BUILD_NAME_DEFAULT / run_uid``

    Raises
    ------
    ValueError
        if ``run_uid`` isn't a valid directory name
    FileExistsError
        if ``exclusive`` and the run's build directory already exists
    """
    check_run_uid(run_uid, "build directory")
    build_dir = Path(output_dir) / BUILD_NAME_DEFAULT / run_uid
    if exclusive:
        build_dir.parent.mkdir(parents=True, exist_ok=True)
        build_dir.mkdir()
    else:
        build_dir.mkdir(parents=True, exist_ok=True)
    return build_dir


def prune_empty_dirs(root: Path) -> None:
    """Removes every empty directory under ``root``, deepest first, so that a directory
    left empty by removing its empty subdirectories goes too. ``root`` itself is kept.

    Parameters
    ----------
    root : Path
        the directory to prune
    """
    for dirpath, _, _ in sorted(os.walk(root), key=lambda w: -len(w[0])):
        if Path(dirpath) != Path(root) and not any(Path(dirpath).iterdir()):
            Path(dirpath).rmdir()


def remove_build_dir(build_dir: Path) -> list[Path]:
    """Removes a run's build directory once the run has finished, if it holds no files.
    Empty subdirectories are removed with it. ``BUILD_NAME_DEFAULT`` itself is left,
    since other runs share it.

    Parameters
    ----------
    build_dir : Path
        the run's build directory, as returned by `prepare_build_dir`

    Returns
    -------
    list[Path]
        what was left in the build directory, e.g. by a save that failed part way, in
        which case the directory is kept and a warning logged. Empty if it was removed
    """
    if not build_dir.exists():
        return []
    # Empty subdirectories, e.g. the one Accession.save makes for its resources'
    # temporary files, are removed first
    prune_empty_dirs(build_dir)
    leftovers = sorted(build_dir.iterdir())
    if leftovers:
        logger.warning(
            "Leaving build directory '%s' in place, as it still holds %s entries "
            "(e.g. '%s')",
            build_dir,
            len(leftovers),
            leftovers[0].name,
        )
        return leftovers
    build_dir.rmdir()
    return []


def move_into_place(
    saved_dir: Path, output_dir: Path, relpath: ty.Sequence[str]
) -> Path:
    """Moves an accession that has been built in full into its place in the output
    directory. If an accession is already there, the two are merged (see
    :meth:`Accession.move_dir`).

    Parameters
    ----------
    saved_dir : Path
        the directory the accession was built in
    output_dir : Path
        the stage's output (staging) directory
    relpath : Sequence[str]
        the path of the accession's directory relative to ``output_dir``, e.g.
        :attr:`Accession.staging_relpath`

    Returns
    -------
    Path
        the accession's directory in the output directory
    """
    dest = Path(output_dir).joinpath(*relpath)
    Accession.move_dir(Path(saved_dir), dest)
    return dest


def _default_name(item: ty.Any) -> str:
    """The name of an accession, or of a listing of one, for error messages"""
    for attr in ("name", "uid"):
        value = getattr(item, attr, None)
        if value:
            return str(value)
    return str(item)


def for_each_accession(
    accessions: ty.Iterable[T],
    step: ty.Callable[[T], object],
    desc: str,
    raise_errors: bool = False,
    name_of: ty.Callable[[T], str] = _default_name,
) -> list[tuple[T, str]]:
    """Runs a per-accession step on each accession in turn. A failure of one accession
    is either raised, or logged so that the remaining accessions are still processed.

    Parameters
    ----------
    accessions : Iterable
        the accessions, or listings of them, to run the step on
    step : Callable
        the step, called with each accession in turn. Its return value is ignored
    desc : str
        the description of the progress bar
    raise_errors : bool
        whether to raise the first error instead of logging it and moving on to the
        next accession
    name_of : Callable, optional
        gives the name of an accession for the error messages. By default its
        ``name`` or, if it has none, its ``uid``

    Returns
    -------
    list[tuple[T, str]]
        each accession the step failed on, with its error message (which gives the
        traceback too), in order. Pass the messages to `log_stage_summary`, and the
        failed accessions and their messages to `finish_claim`
    """
    failures: list[tuple[T, str]] = []
    for accession in tqdm(accessions, desc):
        try:
            step(accession)
        except Exception as e:
            if raise_errors:
                raise
            msg = (
                f"Skipping '{name_of(accession)}' due to an error: \"{e}\"\n"
                f"{traceback.format_exc()}\n"
            )
            logger.error(msg)
            failures.append((accession, msg))
    return failures
