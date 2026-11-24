"""Saving the accessions into the staging directory (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

import typing as ty
from pathlib import Path

from fileformats.core import FileSet
from fileformats.core.fs_mount_identifier import FsMountIdentifier

from accessionflow.api.staging import BUILD_NAME_DEFAULT
from accessionflow.helpers.logging import logger
from accessionflow.model.accession import Accession

__all__ = ["warn_if_hardlinks_unavailable"]


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
    is copied by the claim instead, which `claim_input_files` warns about.

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
