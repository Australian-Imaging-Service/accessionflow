import time
import traceback
import typing as ty
from pathlib import Path

from fileformats.core import FileSet
from tqdm import tqdm

from accessionflow.helpers.logging import logger
from accessionflow.model.accession import Accession

# The subdirectory of a stage's output directory that accessions are built in before
# they are moved into place
BUILD_NAME_DEFAULT = "__build__"


def save_accessions_to_dir(
    accessions: list[Accession],
    msg: str,
    build_dir: Path,
    copy_mode: FileSet.CopyMode,
    output_dir: Path,
    wait_period: int = 0,
    collation_map: dict[type[FileSet], FileSet.CopyCollation] | None = None,
    conversion_map: (
        dict[type[FileSet], tuple[ty.Type[FileSet], dict[str, str]]] | None
    ) = None,
    unlink_source: str | None = None,
    raise_errors: bool = False,
) -> list[str]:
    """Save collated accessions into a build directory, then move each one into the
    staging directory once it is complete, so that a later stage never sees a
    partly saved accession.

    Parameters
    ----------
    accessions : list[Accession]
        the collated accessions, referencing their files at the source
    msg : str
        the description of the progress bar
    build_dir : Path
        the directory the accessions are saved into before they are moved
    copy_mode : FileSet.CopyMode
        how the files are copied from the source
    output_dir : Path
        the staging directory the accessions are moved into
    wait_period : int
        the number of seconds since an accession's files were last modified before
        it is saved, so that accessions still being transferred are skipped
    collation_map : dict[type[FileSet], FileSet.CopyCollation], optional
        how files of each type are laid out in their resource directories
    conversion_map : dict[type[FileSet], tuple[type[FileSet], dict[str, str]]], optional
        the types resources are converted to as they are saved, with the options
        passed to ``convert()``
    unlink_source : str, optional
        if "all" or "keep-metadata", each accession's source files are removed once
        it is saved
    raise_errors : bool
        whether to raise errors instead of logging them and moving on to the next
        accession

    Returns
    -------
    list[str]
        the errors, one per accession that couldn't be saved
    """
    errors = []
    for session in tqdm(accessions, msg):
        if wait_period:
            last_mod = session.last_modified()
            if (time.time_ns() - last_mod) < wait_period * 1e9:
                logger.info(
                    "Skipping collation of session '%s' as it was last modified "
                    "at %s which is less than %s seconds ago to ensure transfer is complete. ",
                    session.uid,
                    last_mod,
                    wait_period,
                )
                continue

        try:
            # We save the session into a temporary "pre-stage" directory first before
            # moving them into the final "staged" directory. This is to prevent the
            # files being transferred/deleted until the saved session is in a final state.
            _, saved_dir = session.save(
                build_dir,
                copy_mode=copy_mode,
                collation_map=collation_map,
                conversion_map=conversion_map,
            )
            logger.info(
                "Successfully collated session '%s' to '%s'",
                session.uid,
                str(saved_dir),
            )
            session_output_dir = output_dir.joinpath(*session.staging_relpath)
            Accession.move_dir(saved_dir, session_output_dir)
            if unlink_source is not None:
                # 'all' and 'keep-metadata' are equivalent here: this session's source
                # files may live in a directory shared with other, not-yet-processed
                # sessions, so only the individual files are ever removed — never the
                # whole parent directory (unlike 'label'/'deidentify', which clean up
                # a staged directory that accessionflow created and owns exclusively)
                session.unlink()
        except Exception as e:
            if not raise_errors:
                msg = (
                    f"Skipping '{session.uid}' session due to error in collation: \"{e}\""
                    f"\n{traceback.format_exc()}\n\n"
                )
                logger.error(msg)
                errors.append(msg)
                continue
            else:
                raise

    return errors
