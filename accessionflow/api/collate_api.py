import traceback
import typing as ty
from pathlib import Path

from fileformats.core import FileSet

from accessionflow.helpers.logging import logger
from accessionflow.model.accession import Accession

# The subdirectory of a stage's output directory that accessions (or, for collate,
# individual resources) are built in before they are moved into place
BUILD_NAME_DEFAULT = "__build__"


def save_accessions_to_dir(
    accessions: list[Accession],
    copy_mode: FileSet.CopyMode,
    output_dir: Path,
    collation_map: dict[type[FileSet], FileSet.CopyCollation] | None = None,
    conversion_map: (
        dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
    ) = None,
    unlink_source: str | None = None,
    raise_errors: bool = False,
) -> list[str]:
    """Save collated accessions directly into the staging directory

    Parameters
    ----------
    accessions : list[Accession]
        the collated accessions, referencing their files at the source
    copy_mode : FileSet.CopyMode
        how the files are copied from the source
    output_dir : Path
        the staging directory the accessions are saved into
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
    try:
        for session in accessions:
            try:
                _, saved_dir = session.save(
                    output_dir,
                    copy_mode=copy_mode,
                    collation_map=collation_map,
                    conversion_map=conversion_map,
                )
                logger.info(
                    "Successfully collated session '%s' to '%s'",
                    session.uid,
                    str(saved_dir),
                )
                if unlink_source is not None:
                    # 'all' and 'keep-metadata' are equivalent here: this session's
                    # source files may live in a directory shared with other,
                    # not-yet-processed sessions, so only the individual files are ever
                    # removed — never the whole parent directory (unlike
                    # 'label'/'deidentify', which clean up a staged directory that
                    # accessionflow created and owns exclusively)
                    session.unlink()
            except Exception as e:
                if raise_errors:
                    raise
                error_msg = (
                    f"Skipping '{session.uid}' session due to error in collation: \"{e}\""
                    f"\n{traceback.format_exc()}\n\n"
                )
                logger.error(error_msg)
                errors.append(error_msg)
    finally:
        # Accession.save copies each resource into a temporary directory under
        # __build__ before moving it into place. rmdir, not rmtree: it only removes
        # the directory when it is empty, so a save still in progress elsewhere is
        # never taken out from under it
        try:
            (output_dir / BUILD_NAME_DEFAULT).rmdir()
        except OSError:
            pass

    return errors
