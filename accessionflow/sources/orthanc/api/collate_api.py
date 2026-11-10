"""Collates DICOM studies held by an Orthanc server into accessions"""

from pathlib import Path

from fileformats.core import FileSet

from accessionflow.helpers.logging import logger

from ..staging import stage_studies


def collate(
    url: str,
    store_dir: Path,
    output_dir: Path,
    user: str,
    password: str,
    to_process_label: str | None = None,
    processed_label: str | None = None,
    unlink_source: str | None = None,
    raise_errors: bool = False,
    copy_mode: FileSet.CopyMode = FileSet.CopyMode.hardlink_or_copy,
    conversion_map: (
        dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
    ) = None,
) -> list[str]:
    """Collates the DICOM studies held by an Orthanc server into accessions in the
    staging directory, hardlinking the files from Orthanc's storage directory.

    Parameters
    ----------
    url: str
        the base URL of the Orthanc REST API, e.g. 'http://orthanc:8042'
    store_dir: Path
        Orthanc's StorageDirectory as mounted, which must be on the same file system
        as output_dir for the files to be hardlinked
    output_dir: Path
        the staging directory the collated accessions are saved in
    user: str
        the Orthanc user to log in as
    password: str
        the password of the Orthanc user
    to_process_label: str | None
        the label applied to studies in Orthanc, by something else, to mark them for
        collation. If None, all studies are collated
    processed_label: str | None
        the label applied to studies in Orthanc once they have been collated, so that
        they aren't collated again
    unlink_source: str | None
        if "all" or "keep-metadata", the studies would be removed from Orthanc once
        they have been collated. Not yet implemented
    raise_errors: bool
        whether to raise errors instead of logging them. Not yet implemented
    copy_mode: FileSet.CopyMode
        how the files are copied. Only hardlinks are implemented
    conversion_map: dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
        the types series are converted to before the study is labelled as processed,
        with the options passed through to ``convert()``

    Returns
    -------
    list[str]
        the IDs of the studies that couldn't be collated
    """

    if (
        unlink_source is not None
        or copy_mode is not FileSet.CopyMode.hardlink_or_copy
        or raise_errors is True
    ):
        raise NotImplementedError(
            "'unlink_source', copy_mode' and 'raise_errors' are not yet implemented for Orthanc collation."
        )

    errors: list[str] = []

    stage_studies(
        url=url,
        output_dir=output_dir,
        store_dir=store_dir,
        user=user,
        password=password,
        to_process_label=to_process_label,
        processed_label=processed_label,
        conversion_map=conversion_map,
        errors=errors,
    )

    if errors:
        logger.error("Collating from Orthanc completed with %s errors", len(errors))
    else:
        logger.info("Collating from Orthanc completed successfully")
    return errors
