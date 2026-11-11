"""Collates files found in local or mounted folders into accessions"""

import typing as ty
from pathlib import Path

from fileformats.core import FileSet
from fileformats.medimage import DicomSeries

from accessionflow.api.collate_api import save_accessions_to_dir
from accessionflow.helpers.arg_types import (
    ClashSpec,
    IDSpec,
    MetadataTable,
    OnResourceClash,
    PathMetadataRegex,
)
from accessionflow.helpers.logging import logger
from accessionflow.model.accession import Accession

# Default ID specs, shared verbatim with the 'collate folder' CLI options so the API
# and CLI can never drift apart
DEFAULT_ACCESSION_UID_FIELD: tuple[IDSpec, ...] = (
    IDSpec("StudyInstanceUID", "medimage/dicom-collection"),
)
DEFAULT_ACQUISITION_ID_FIELD: tuple[IDSpec, ...] = (
    IDSpec("SeriesNumber", "medimage/dicom-collection"),
)
DEFAULT_RESOURCE_FIELD: tuple[IDSpec, ...] = ()
_DEFAULT_DATATYPES: tuple[type[FileSet], ...] = (DicomSeries,)


def collate(
    # required
    input_file_paths: list[Path],
    output_dir: Path,

    # optional
    datatypes: ty.Sequence[type[FileSet]] = _DEFAULT_DATATYPES,
    accession_uid: ty.Sequence[IDSpec] = DEFAULT_ACCESSION_UID_FIELD,
    acquisition_id: ty.Sequence[IDSpec] = DEFAULT_ACQUISITION_ID_FIELD,
    resource: ty.Sequence[IDSpec] = DEFAULT_RESOURCE_FIELD,
    path_metadata_regex: ty.Sequence[PathMetadataRegex] = (),
    collation_map: dict[type[FileSet], FileSet.CopyCollation] | None = None,
    conversion_map: (
        dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
    ) = None,
    allow_unrecognised: ty.Sequence[str] = (),
    ignore_datatypes: ty.Sequence[type[FileSet]] = (),
    on_resource_clash: OnResourceClash | ty.Sequence[ClashSpec] = "error",
    metadata_tables: list[MetadataTable] | None = None,
    unlink_source: str | None = None,
    raise_errors: bool = False,
    copy_mode: FileSet.CopyMode = FileSet.CopyMode.hardlink_or_copy,
) -> list[str]:
    """Collates the input files into accessions/acquisitions/resources and saves them
    directly into the staging directory. Project/subject/visit IDs and scan descriptions are not
    labelled at this point, see the 'label' function for that.

    Parameters
    ----------
    input_file_paths: list[Path]
        The files to collate. Each path must be an existing file, local or on a mounted
        file system; directories are not walked (see
        ``accessionflow.sources.folder.discovery.find_files``).
    output_dir: Path
        Path to the staging directory where the collated sessions will be saved. This should be a local path.
    datatypes: ty.Sequence[type[FileSet]]
        FileSet types to look for in the input files. Only files with these datatypes will be
        considered for staging. Directory datatypes are not supported. Defaults to
        ``(DicomSeries,)`` to mirror the CLI.
    accession_uid: ty.Sequence[IDSpec]
        Field specifications to extract the accession UIDs from the input files, to
        collate them into separate accessions. Defaults to ``DEFAULT_ACCESSION_UID_FIELD``
        (``StudyInstanceUID`` scoped to DICOM collections; the same object backs the
        CLI's ``--accession-uid``); other fileset types need an explicit spec.
    acquisition_id: ty.Sequence[IDSpec]
        Field specifications to extract the acquisition IDs from the input files, to
        collate them into acquisitions. Defaults to ``DEFAULT_ACQUISITION_ID_FIELD``
        (``SeriesNumber`` scoped to DICOM collections; shared with the CLI's
        ``--acquisition-id``); for a fileset whose type is not matched by any spec here the
        acquisition is named after that fileset's resource.
    resource: ty.Sequence[IDSpec]
        List of field specifications to use for extracting the resource IDs from the input files to collate them into
        resources. If empty, each resource is labelled with the mime-like rendering
        of its fileset type name, e.g. 'vectra-export', 'sqlite3-db'
    path_metadata_regex: ty.Sequence[PathMetadataRegex]
        Regular expressions to extract "metadata" values from resource file paths as named groups. The named
        groups are used as metadata fields for the resource files, and the extracted values will be used to populate
        the corresponding metadata fields to complement the metadata read from the file headers.
    unlink_source: str | None
        If "all" or "keep-metadata", the input files will be unlinked one by one after staging (both behave the same
        here, since the source isn't a directory tree that accessionflow owns). If None, the input files will be left
        in place.
    raise_errors: bool
        If True, any errors encountered during staging will raise an exception. If False, errors will be logged and the
        staging process will continue for the remaining sessions.
    copy_mode: FileSet.CopyMode
        The copy mode to use when saving the sessions. This determines whether files are copied, moved or symlinked when
        saving the sessions to the staging directory.
    collation_map: dict[ty.Type[FileSet], FileSet.CopyCollation] | None
        A mapping of FileSet types to CopyCollation objects that specify how to collate files of that type when saving the
        sessions. If None, the default collation behavior for each FileSet type will be used.
    conversion_map: dict[ty.Type[FileSet], tuple[ty.Type[FileSet], dict[str, str]]] | None
        A mapping of source FileSet types to (target FileSet types, conversion options).
        When a resource matches a source type, it will be converted to the target type during save,
        with the options passed through to ``convert()``.
    allow_unrecognised: ty.Sequence[str]
        Regexes matched against the *basename* of any input path that no datatype recognised;
        matches are skipped instead of raising ``FormatRecognitionError``. ``[".*"]`` tolerates
        all unrecognised files. Does not affect recognised filesets.
    ignore_datatypes: ty.Sequence[type[FileSet]]
        Datatypes expected in the input but not wanted: recognised filesets of these types are
        dropped rather than raising. A file matching neither ``datatypes`` nor
        ``ignore_datatypes`` (nor ``allow_unrecognised``) still raises.
    on_resource_clash: OnResourceClash or Sequence[ClashSpec]
        Behaviour when two filesets resolve to the same scan/resource name. A bare policy
        string ("error"/"avoid"/"merge"/"overwrite") applies to any clash. A sequence of
        ``ClashSpec`` (policy + datatype scope) resolves each clash with the first spec whose
        scope covers *both* filesets - a clash no spec covers raises. "avoid" suffixes,
        "merge" folds into one ``SetOf``, "overwrite" replaces. Default "error".
    metadata_tables: list[MetadataTable] | None
        Specify metadata tables to extract and join metadata from input files (ACFLOW_METADATA_TABLES env. var).
        The 'path' arg specifies the location of the metadata table file. Its format is auto-detected as CSV or
        TSV from the file extension; a different format can be forced by appending its mime-type in square
        brackets, e.g. 'path/to/table.dat[text/csv]'.
        The "row frequency" arg specifies what each row in the
        metadata table corresponds to in the data hierarchy, and can be one of 'accession', 'acquisition', 'resource',
        'fileset', 'fileset[<mime-type>]'. When one or more mime-types are given in square brackets after
        'fileset' they restrict the join to input files of those types (multiple mime-types can be '|'-separated,
        e.g. 'fileset[image/png|image/jpeg]'); a bare 'fileset' matches any input file.
        The 'join-exprs' arg is a comma-separated list of '<column-name>=<cell-value>' expressions; a row is a
        match when every expression holds. The '<cell-value>' is either the name of an existing metadata field
        or a Python format string over one or more metadata fields, e.g. '{PatientID}_{SessionID}'. All columns
        of the matched row are then merged into the target's metadata.
        The example below extracts the relative path of an image file with `path_metadata_regex` and uses it to
        join a table whose 'ImagePath' column holds spreadsheet HYPERLINK() formulas::

            collate(
                ...,
                path_metadata_regex=[
                    PathMetadataRegex(
                        regex=r".*/(?P<relpath>[\\w-]+/[\\w-]+\\.(?:png|jpg))",
                        datatype="image/png|image/jpeg",
                    )
                ],
                metadata_tables=[
                    MetadataTable(
                        table_file="path/to/table.csv[text/csv]",
                        row_frequency="fileset[image/png|image/jpeg]",
                        join_exprs='ImagePath=HYPERLINK("{relpath}")',
                    )
                ],
            )
    """

    sessions = Accession.from_paths(
        files=input_file_paths,
        datatypes=datatypes,
        accession_uid_field=accession_uid,
        acquisition_id_field=acquisition_id,
        resource_field=resource,
        on_resource_clash=on_resource_clash,
        allow_unrecognised=allow_unrecognised,
        ignore_datatypes=ignore_datatypes,
        path_metadata_regex=path_metadata_regex,
        metadata_tables=metadata_tables,
    )

    errors = save_accessions_to_dir(
        sessions,
        copy_mode=copy_mode,
        output_dir=output_dir,
        unlink_source=unlink_source,
        raise_errors=raise_errors,
        collation_map=collation_map,
        conversion_map=conversion_map,
    )
    if errors:
        logger.error("Collating completed with %s errors", len(errors))
    else:
        logger.info("Collating completed successfully")
    return errors
