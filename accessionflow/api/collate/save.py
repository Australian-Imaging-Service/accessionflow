"""Saving the accessions into the staging directory (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

import shutil
import typing as ty
from pathlib import Path

from fileformats.core import FileSet
from fileformats.core.fs_mount_identifier import FsMountIdentifier

from accessionflow.api.staging import BUILD_NAME_DEFAULT, move_into_place
from accessionflow.helpers.logging import logger
from accessionflow.model.accession import Accession

from .claim import ClaimedFiles

__all__ = [
    "STAGED_MARKER_SUFFIX",
    "remove_claimed_files",
    "save_to_build_dir",
    "move_to_target",
    "warn_if_hardlinks_unavailable",
]

# Appended to an accession's directory name for the marker that `move_to_target` writes
# in the run's build directory once the accession has been moved into place
STAGED_MARKER_SUFFIX = ".staged"


def warn_if_hardlinks_unavailable(
    accessions: ty.Iterable[Accession],
    build_dir: Path,
    copy_mode: FileSet.CopyMode,
    conversion_map: ty.Container[type[FileSet]] | None = None,
) -> list[Path]:
    """Logs a single warning if ``copy_mode`` would hard-link the accessions' files but
    some of them are on a different file system from ``build_dir``, so they will be
    copied in full instead, which can be much slower for large files.

    Only the case where a full copy is the fallback is warned about, i.e. where the
    copy mode allows hard-linking and copying but not symlinking (which is preferred
    over hard-linking). Resources that are converted as they are saved are skipped,
    as they are written anew rather than linked.

    Once collate claims its input, the accessions' files are in the processing area,
    which by default is on the same file system as the output directory, so this only
    warns if the processing area has been put elsewhere. Input on another file system
    is copied by the claim instead, which `ClaimInputFiles` warns about.

    Parameters
    ----------
    accessions : Iterable[Accession]
        the accessions to be saved
    build_dir : Path
        the run's build directory, from `prepare_build_dir`
    copy_mode : FileSet.CopyMode
        how the files will be saved
    conversion_map : Container[type[FileSet]], optional
        the datatypes that are converted as they are saved

    Returns
    -------
    list[Path]
        one file of each resource that can't be hard-linked, or an empty list if all of
        them can, or the copy mode wouldn't fall back to a full copy
    """
    if not (
        copy_mode & FileSet.CopyMode.hardlink
        and copy_mode & FileSet.CopyMode.copy
        and not copy_mode & FileSet.CopyMode.symlink
    ):
        return []
    conversion_map = conversion_map or ()
    # Mounts are looked up once per directory rather than once per file
    same_mount: dict[Path, bool] = {}
    n_resources = 0
    unlinkable: list[Path] = []
    for accession in accessions:
        for resource in accession.resources:
            if type(resource.fileset) in conversion_map:
                continue
            n_resources += 1
            for fspath in resource.fileset.fspaths:
                parent = fspath.parent
                if parent not in same_mount:
                    same_mount[parent] = FsMountIdentifier.on_same_mount(
                        parent, build_dir
                    )
                if not same_mount[parent]:
                    unlinkable.append(fspath)
                    break
    if unlinkable:
        # A build directory from prepare_build_dir is <output_dir>/__build__/<run_uid>
        output_dir = (
            build_dir.parent.parent
            if build_dir.parent.name == BUILD_NAME_DEFAULT
            else build_dir
        )
        logger.warning(
            "%s of %s resources (e.g. '%s') are on a different file system from the "
            "output directory '%s', so they can't be hard-linked and will be copied in "
            "full instead, which can be slow for large files. To hard-link them, put "
            "the output directory on the same file system as the input.",
            len(unlinkable),
            n_resources,
            unlinkable[0],
            output_dir,
        )
    return unlinkable


def save_to_build_dir(
    accession: Accession,
    build_dir: Path,
    copy_mode: FileSet.CopyMode = FileSet.CopyMode.hardlink_or_copy,
    collation_map: dict[type[FileSet], FileSet.CopyCollation] | None = None,
    conversion_map: (
        dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
    ) = None,
) -> Path:
    """Saves an accession into the run's build directory, in a subdirectory named after
    it (`Accession.staging_dirname`). A subdirectory left by an earlier attempt that
    failed part way is removed first, so the save can be retried (principle 9).

    Parameters
    ----------
    accession : Accession
        the accession to save
    build_dir : Path
        the run's build directory, from `prepare_build_dir`
    copy_mode : FileSet.CopyMode, optional
        how the files are saved, by default hard-linked if possible, otherwise copied
    collation_map : dict[type[FileSet], FileSet.CopyCollation], optional
        the collation used to save each datatype
    conversion_map : dict[type[FileSet], tuple[type[FileSet], dict[str, str]]], optional
        the datatypes converted as they are saved, to a datatype and its options

    Returns
    -------
    Path
        the saved accession's directory
    """
    scratch = build_dir / accession.staging_dirname()
    if scratch.exists():
        shutil.rmtree(scratch)
    _, saved_dir = accession.save(
        build_dir,
        copy_mode=copy_mode,
        collation_map=collation_map,
        conversion_map=conversion_map,
    )
    return saved_dir


def remove_claimed_files(accession: Accession, claimed: ClaimedFiles) -> list[Path]:
    """Deletes an accession's files from the run's processing area, once it has been
    staged. A file is deleted, and so is the directory of a directory datatype. Paths
    that are already gone are skipped, so it can be retried. Directories left empty are
    for `FinishClaim` to remove.

    Parameters
    ----------
    accession : Accession
        the staged accession
    claimed : ClaimedFiles
        the run's claimed files. Only paths in ``claimed.files_dir`` are ever deleted

    Returns
    -------
    list[Path]
        the paths that were deleted

    Raises
    ------
    ValueError
        if any of the accession's files isn't in the processing area, in which case
        nothing is deleted
    """
    fspaths = [p for r in accession.resources for p in r.fileset.fspaths]
    files_dir = claimed.files_dir
    if outside := [p for p in fspaths if not p.absolute().is_relative_to(files_dir)]:
        raise ValueError(
            f"Not deleting the files of '{accession.uid}', as {len(outside)} of them "
            f"aren't in the processing area '{files_dir}', e.g. '{outside[0]}'"
        )
    removed = []
    for fspath in fspaths:
        if fspath.is_dir():
            shutil.rmtree(fspath)
        elif fspath.exists():
            fspath.unlink()
        else:
            continue
        removed.append(fspath)
    return removed


def move_to_target(
    accession: Accession,
    build_dir: Path,
    output_dir: Path,
    claimed: ClaimedFiles,
    copy_mode: FileSet.CopyMode = FileSet.CopyMode.hardlink_or_copy,
    collation_map: dict[type[FileSet], FileSet.CopyCollation] | None = None,
    conversion_map: (
        dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
    ) = None,
) -> Path:
    """Delivers one labelled accession to the target directory, as
    ``<labels>_<run_uid>`` (`Accession.staging_dirname`): saves it into the build
    directory (`save_to_build_dir`), moves it into place (`move_into_place`), and
    deletes its claimed files (`remove_claimed_files`). With `assign_labels`, the unit
    of work a flow maps over the accessions.

    It raises if any part fails. A failure before the move leaves the target directory
    untouched and the accession's files in the processing area. Once the move has
    succeeded, a marker (``<accession dir>.staged``) is written in the build directory,
    so that a retry after a failure in the delete skips the save and the move and only
    deletes the files. A crash in the instant between the move and writing the marker
    makes a retry fail on the move instead, as the accession's acquisitions are
    already in place; no data is lost.

    Parameters
    ----------
    accession : Accession
        the accession to deliver, labelled by `assign_labels`
    build_dir : Path
        the run's build directory, from `prepare_build_dir`
    output_dir : Path
        the target directory the accession is moved into
    claimed : ClaimedFiles
        the run's claimed files, from `ClaimInputFiles`
    copy_mode : FileSet.CopyMode, optional
        how the files are saved, by default hard-linked if possible, otherwise copied
    collation_map : dict[type[FileSet], FileSet.CopyCollation], optional
        the collation used to save each datatype
    conversion_map : dict[type[FileSet], tuple[type[FileSet], dict[str, str]]], optional
        the datatypes converted as they are saved, to a datatype and its options

    Returns
    -------
    Path
        the accession's directory in the target directory

    Raises
    ------
    ValueError
        if the accession hasn't been labelled
    """
    if accession.name is None:
        raise ValueError(
            f"Accession '{accession.uid}' must be labelled (assign_labels) before it "
            "is moved to the target directory"
        )
    dirname = accession.staging_dirname()
    marker = build_dir / f"{dirname}{STAGED_MARKER_SUFFIX}"
    if not marker.exists():
        saved_dir = save_to_build_dir(
            accession, build_dir, copy_mode, collation_map, conversion_map
        )
        move_into_place(saved_dir, output_dir, [dirname])
        marker.touch()
    remove_claimed_files(accession, claimed)
    marker.unlink(missing_ok=True)
    return output_dir / dirname
