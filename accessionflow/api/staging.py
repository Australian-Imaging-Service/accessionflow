"""Helpers shared by every stage for writing accessions into a staging directory.

Each stage builds an accession in a subdirectory of its output directory and moves it
into place once it is complete, so that a later stage never sees a partly written
accession. These helpers are step functions in the sense of the Prefect migration
roadmap (``prefect-migration-docs/ROADMAP.md``): small, with explicit inputs and
outputs, and no dependency on Prefect.
"""

import traceback
import typing as ty
from pathlib import Path

from tqdm import tqdm

from accessionflow.helpers.logging import logger
from accessionflow.model.accession import Accession

__all__ = [
    "BUILD_NAME_DEFAULT",
    "prepare_build_dir",
    "move_into_place",
    "for_each_accession",
]

# The subdirectory of a stage's output directory that accessions are built in before
# they are moved into place
BUILD_NAME_DEFAULT = "__build__"

T = ty.TypeVar("T")


def prepare_build_dir(output_dir: Path) -> Path:
    """Creates the build directory of a stage's output directory, if it doesn't
    exist yet.

    Parameters
    ----------
    output_dir : Path
        the stage's output (staging) directory

    Returns
    -------
    Path
        the build directory, ``output_dir / BUILD_NAME_DEFAULT``
    """
    build_dir = Path(output_dir) / BUILD_NAME_DEFAULT
    build_dir.mkdir(parents=True, exist_ok=True)
    return build_dir


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
) -> list[str]:
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
    list[str]
        the error messages, one per accession the step failed on
    """
    errors: list[str] = []
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
            errors.append(msg)
    return errors
