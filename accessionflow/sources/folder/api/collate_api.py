"""Collates files found in local or mounted folders into accessions"""

import typing as ty
from pathlib import Path

from fileformats.core import FileSet
from fileformats.medimage import DicomSeries

from accessionflow.api.collate import (
    ClaimedFiles,
    abandon_claim,
    check_datatypes,
    claim_input_files,
    collect_accessions,
    deliver_accessions,
    finish_claim,
    load_metadata_tables,
    make_run_uid,
    merge_path_metadata,
    plan_recursion,
)
from accessionflow.api.collate.claim import CLAIMED_MANIFEST
from accessionflow.api.collate_api import save_accessions_to_dir
from accessionflow.api.staging import prepare_build_dir, remove_build_dir
from accessionflow.helpers.arg_types import (
    ClashSpec,
    IDSpec,
    MetadataTable,
    OnResourceClash,
    PathMetadataPattern,
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

# How many run UIDs a new run tries before giving up, should each be taken already
_RUN_UID_ATTEMPTS = 5


def _start_run(output_dir: Path) -> tuple[str, Path]:
    """Makes the run's UID and creates its build directory exclusively, making another
    UID if another run has already taken it

    Raises
    ------
    RuntimeError
        if every one of ``_RUN_UID_ATTEMPTS`` UIDs is taken
    """
    for _ in range(_RUN_UID_ATTEMPTS):
        run_uid = make_run_uid()
        try:
            return run_uid, prepare_build_dir(output_dir, run_uid, exclusive=True)
        except FileExistsError:
            logger.debug("Run UID '%s' is taken, making another", run_uid)
    raise RuntimeError(f"Couldn't make an unused run UID in '{output_dir}'")


def collate_files(
    input_files: ty.Sequence[Path],
    output_dir: Path,
    working_dir: Path,
    unprocessed_dir: Path,
    error_dir: Path,
    label_fields: ty.Mapping[str, str],
    *,
    datatypes: ty.Sequence[type[FileSet]] = _DEFAULT_DATATYPES,
    ignore_datatypes: ty.Sequence[type[FileSet]] = (),
    source_roots: ty.Sequence[Path] | None = None,
    recursive: bool = False,
    allow_unrecognised: ty.Sequence[str] = (),
    dont_read_metadata: ty.Sequence[type[FileSet]] = (),
    accession_uid_field: ty.Sequence[IDSpec] = DEFAULT_ACCESSION_UID_FIELD,
    acquisition_id_field: ty.Sequence[IDSpec] = DEFAULT_ACQUISITION_ID_FIELD,
    resource_field: ty.Sequence[IDSpec] = DEFAULT_RESOURCE_FIELD,
    path_metadata: ty.Sequence[PathMetadataPattern] = (),
    path_metadata_regex: ty.Sequence[PathMetadataRegex] = (),
    metadata_tables: ty.Sequence[MetadataTable] | None = None,
    on_resource_clash: OnResourceClash | ty.Sequence[ClashSpec] = "error",
    acquisition_field: str | None = None,
    constant_labels: ty.Mapping[str, str] | None = None,
    store_type: str | None = None,
    copy_mode: FileSet.CopyMode = FileSet.CopyMode.hardlink_or_copy,
    collation_map: dict[type[FileSet], FileSet.CopyCollation] | None = None,
    conversion_map: (
        dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
    ) = None,
    raise_errors: bool = False,
) -> list[str]:
    """Collates the given files into labelled accessions and delivers them to the
    output directory, running the collate steps in order (see
    ``prefect-migration-docs/ROADMAP.md``, Phase 1, Composites)

    1. Checks the arguments before anything is changed: `check_datatypes`,
       `plan_recursion`, `load_metadata_tables` and `merge_path_metadata`.
    2. Makes the run's UID (`make_run_uid`) and its build directory
       (`prepare_build_dir`), with another UID if one is taken.
    3. Claims the files into ``<working_dir>/<run_uid>/`` (`claim_input_files`). A
       file that arrives after they were listed stays in the input, for the next run.
    4. Forms the accessions (`collect_accessions`).
    5. Labels and delivers each one to ``<output_dir>/<labels>_<run_uid>/``
       (`deliver_accessions`).
    6. Moves the files that weren't delivered (unrecognised, ignored, or of an
       accession that failed) to ``<unprocessed_dir>/<run_uid>/`` (`finish_claim`).

    If a step raises, the run's claimed files are moved to ``<error_dir>/<run_uid>/``
    (`abandon_claim`) and the error is raised. The build directory is removed either
    way. An interrupt (e.g. Ctrl-C) leaves the claim in the working directory.

    Errors are returned rather than logged: the caller summarises them (e.g. with
    ``accessionflow.cli.runner.log_stage_summary``).

    Parameters
    ----------
    input_files : Sequence[Path]
        the files to collate, e.g. from `list_input_files`
    output_dir : Path
        the target directory the labelled accessions are delivered to
    working_dir : Path
        the directory each run's claimed files are moved into, e.g.
        ``<output_dir>/__processing__``
    unprocessed_dir : Path
        the directory a run's files that weren't delivered are moved to
    error_dir : Path
        the directory the claimed files of a run that raised are moved to
    label_fields : Mapping[str, str]
        the metadata field each label is made from, keyed by level (see
        `assign_labels`)
    datatypes : Sequence[type[FileSet]], optional
        the datatypes to collate, by default ``(DicomSeries,)`` as in the CLI
    ignore_datatypes : Sequence[type[FileSet]], optional
        the datatypes expected but not wanted, whose files are left as ignored
    source_roots : Sequence[Path], optional
        the directories the files were listed from (`claim_input_files`). Pass the input
        directories so that their top-level entries are classified as they were in them
    recursive : bool, optional
        whether to classify the files in subdirectories one by one
    allow_unrecognised : Sequence[str], optional
        patterns of the base names that no datatype needs to recognise
    dont_read_metadata : Sequence[type[FileSet]], optional
        the datatypes whose files aren't read for metadata
    accession_uid_field : Sequence[IDSpec], optional
        how each file-set's accession is identified
    acquisition_id_field : Sequence[IDSpec], optional
        how each file-set's acquisition is identified
    resource_field : Sequence[IDSpec], optional
        how each file-set's resource is labelled
    path_metadata : Sequence[PathMetadataPattern], optional
        glob-like patterns that read metadata fields from the paths
    path_metadata_regex : Sequence[PathMetadataRegex], optional
        regexes that read metadata fields from the paths, applied after the patterns
    metadata_tables : Sequence[MetadataTable], optional
        tables whose rows are joined to the file-sets' or accessions' metadata. They are
        read before the claim, so a table delivered with the data can be claimed with it
    on_resource_clash : OnResourceClash | Sequence[ClashSpec], optional
        what to do when two file-sets have the same acquisition and resource
    acquisition_field : str, optional
        the metadata field each acquisition's description is made from
    constant_labels : Mapping[str, str], optional
        labels used as given, keyed by level
    store_type : str, optional
        the data store the labels are for, e.g. 'xnat'
    copy_mode : FileSet.CopyMode, optional
        how the files are saved, by default hard-linked if possible, otherwise copied
    collation_map : dict[type[FileSet], FileSet.CopyCollation], optional
        the collation used to save each datatype
    conversion_map : dict[type[FileSet], tuple[type[FileSet], dict[str, str]]], optional
        the datatypes converted as they are saved, to a datatype and its options
    raise_errors : bool, optional
        whether an accession that fails to be delivered raises, which abandons the run,
        instead of being skipped

    Returns
    -------
    list[str]
        the error message of each accession that wasn't delivered. Empty if all were

    Raises
    ------
    ValueError
        if an argument is invalid. Nothing has been changed
    RuntimeError
        if no unused run UID could be made. Nothing has been claimed
    """
    check_datatypes(datatypes, ignore_datatypes)
    recursion = plan_recursion(datatypes, ignore_datatypes, recursive)
    tables = load_metadata_tables(metadata_tables)
    regexes = merge_path_metadata(path_metadata, path_metadata_regex)

    run_uid, build_dir = _start_run(output_dir)
    claimed: ClaimedFiles | None = None
    try:
        claimed = claim_input_files(input_files, working_dir, run_uid, source_roots)
        collected = collect_accessions(
            claimed,
            datatypes,
            recursion,
            accession_uid_field=accession_uid_field,
            recursive=recursive,
            allow_unrecognised=allow_unrecognised,
            dont_read_metadata=dont_read_metadata,
            path_metadata_regex=regexes,
            metadata_tables=tables,
            acquisition_id_field=acquisition_id_field,
            resource_field=resource_field,
            on_resource_clash=on_resource_clash,
            run_uid=run_uid,
        )
        failed = deliver_accessions(
            collected.accessions,
            build_dir,
            output_dir,
            claimed,
            label_fields,
            acquisition_field=acquisition_field,
            constant_labels=constant_labels,
            store_type=store_type,
            copy_mode=copy_mode,
            collation_map=collation_map,
            conversion_map=conversion_map,
            raise_errors=raise_errors,
        )
        finish_claim(claimed, unprocessed_dir, failed, collected.ignored)
    except Exception as e:
        if claimed is None:
            # The claim raised partway: the files it moved are found from its plan
            run_dir = Path(working_dir).absolute() / run_uid
            if (run_dir / CLAIMED_MANIFEST).exists():
                claimed = ClaimedFiles.load(run_dir)
        if claimed is not None:
            abandon_claim(claimed, error_dir, e)
        raise
    finally:
        remove_build_dir(build_dir)
    return [message for _, message in failed]


def collate(
    input_paths: list[str],
    output_dir: Path,
    datatypes: ty.Sequence[type[FileSet]] = _DEFAULT_DATATYPES,
    accession_uid: ty.Sequence[IDSpec] = DEFAULT_ACCESSION_UID_FIELD,
    acquisition_id: ty.Sequence[IDSpec] = DEFAULT_ACQUISITION_ID_FIELD,
    resource: ty.Sequence[IDSpec] = DEFAULT_RESOURCE_FIELD,
    path_metadata_regex: ty.Sequence[PathMetadataRegex] = (),
    path_metadata: ty.Sequence[PathMetadataPattern] = (),
    unlink_source: str | None = None,
    raise_errors: bool = False,
    copy_mode: FileSet.CopyMode = FileSet.CopyMode.hardlink_or_copy,
    wait_period: int = 0,
    collation_map: dict[type[FileSet], FileSet.CopyCollation] | None = None,
    conversion_map: (
        dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
    ) = None,
    allow_unrecognised: ty.Sequence[str] = (),
    exclude_paths: ty.Sequence[str] = (),
    ignore_datatypes: ty.Sequence[type[FileSet]] = (),
    on_resource_clash: OnResourceClash | ty.Sequence[ClashSpec] = "error",
    metadata_tables: list[MetadataTable] | None = None,
    recursive: bool = False,
    dont_read_metadata: ty.Sequence[type[FileSet]] = (),
) -> list[str]:
    """Collates the input files into accessions/acquisitions/resources and stages them into the
    staging directory. Project/subject/visit IDs and scan descriptions are not
    labelled at this point, see the 'label' function for that.

    Parameters
    ----------
    input_paths: list[str]
        List of paths to search for input files: directories, or glob patterns that
        select the files directly. They must be local or on a mounted file system.
    output_dir: Path
        Path to the staging directory where the collated sessions will be saved. This should be a local path.
    datatypes: ty.Sequence[type[FileSet]]
        FileSet types to look for in the input files. Only files with these datatypes will be
        considered for staging. Defaults to ``(DicomSeries,)`` to mirror the CLI.
    accession_uid: ty.Sequence[IDSpec]
        Field specifications to extract the accession UIDs from the input files, to
        collate them into separate accessions. Defaults to ``DEFAULT_ACCESSION_UID_FIELD``
        (``StudyInstanceUID`` scoped to DICOM collections; the same object backs the
        CLI's ``--accession``); other fileset types need an explicit spec.
    acquisition_id: ty.Sequence[IDSpec]
        Field specifications to extract the acquisition IDs from the input files, to
        collate them into acquisitions. Defaults to ``DEFAULT_ACQUISITION_ID_FIELD``
        (``SeriesNumber`` scoped to DICOM collections; shared with the CLI's
        ``--acquisition``); for a fileset whose type is not matched by any spec here the
        acquisition is named after that fileset's resource.
    resource: ty.Sequence[IDSpec]
        List of field specifications to use for extracting the resource IDs from the input files to collate them into
        resources. If empty, each resource is labelled with the mime-like rendering
        of its fileset type name, e.g. 'vectra-export', 'sqlite3-db'
    path_metadata_regex: ty.Sequence[PathMetadataRegex]
        Regular expressions to extract "metadata" values from resource file paths as named groups. The named
        groups are used as metadata fields for the resource files, and the extracted values will be used to populate
        the corresponding metadata fields to complement the metadata read from the file headers.
    path_metadata: ty.Sequence[PathMetadataPattern]
        A simpler, glob-like alternative to ``path_metadata_regex``, where ``{name}`` placeholders
        mark the parts of the path to extract as metadata fields, e.g. ``'{subject}/{session}'``.
        Each pattern is translated into a regex (see ``accessionflow.helpers.path_pattern.path_metadata_pattern_to_regex``) and applied
        before the ``path_metadata_regex`` ones, so a regex wins where both set the same field.
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
        matches are skipped instead of raising ``FormatMismatchError``. ``[".*"]`` tolerates
        all unrecognised files. Does not affect recognised filesets.
    exclude_paths: ty.Sequence[str]
        Globs matched against each input path *relative to its input directory*, applied before
        classification so a match is dropped even if a datatype would claim it (e.g. a vendor
        thumbnail that is a valid ``image/png``). ``*`` does not cross ``/``, ``**`` does.
    ignore_datatypes: ty.Sequence[type[FileSet]]
        Datatypes expected in the input but not wanted: recognised filesets of these types are
        dropped rather than raising, and (with ``recursive``) matching directories are skipped
        without descending. A path matching neither ``datatypes`` nor ``ignore_datatypes`` (nor
        ``allow_unrecognised`` / ``exclude_paths``) still raises.
    dont_read_metadata: ty.Sequence[type[FileSet]]
        Datatypes whose files aren't read for metadata, so their only metadata fields are those
        from ``path_metadata``/``path_metadata_regex`` and ``metadata_tables``. Saves reading the
        header of every file when none of its fields are used.
    wait_period: int
        If provided, this is the number of seconds that must have passed since the last modification time of the session before
        it will be staged. This can be used to avoid staging sessions that are still being modified or created.
    on_resource_clash: OnResourceClash or Sequence[ClashSpec]
        Behaviour when two filesets resolve to the same scan/resource name. A bare policy
        string ("error"/"avoid"/"merge"/"overwrite") applies to any clash. A sequence of
        ``ClashSpec`` (policy + datatype scope) resolves each clash with the first spec whose
        scope covers *both* filesets - a clash no spec covers raises. "avoid" suffixes,
        "merge" folds into one ``SetOf``, "overwrite" replaces. Default "error".
    recursive: bool
        If True, the input paths will be searched recursively for files to stage. If False, only the files directly within the
        input paths will be considered for staging.
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

    check_datatypes(datatypes, ignore_datatypes)
    # Checks the options before anything is created. Until the expansion step uses
    # the plan, Accession.from_paths works it out again for itself
    plan_recursion(datatypes, ignore_datatypes, recursive)

    _, build_dir = _start_run(output_dir)
    try:
        sessions = Accession.from_paths(
            files_path=input_paths,
            datatypes=datatypes,
            accession_uid_field=accession_uid,
            acquisition_id_field=acquisition_id,
            resource_field=resource,
            recursive=recursive,
            on_resource_clash=on_resource_clash,
            allow_unrecognised=allow_unrecognised,
            exclude_paths=exclude_paths,
            ignore_datatypes=ignore_datatypes,
            path_metadata_regex=merge_path_metadata(path_metadata, path_metadata_regex),
            metadata_tables=metadata_tables,
            dont_read_metadata=dont_read_metadata,
        )

        errors = save_accessions_to_dir(
            sessions,
            f"Collating files found in '{input_paths}' to {output_dir!s}",
            wait_period=wait_period,
            build_dir=build_dir,
            copy_mode=copy_mode,
            output_dir=output_dir,
            unlink_source=unlink_source,
            raise_errors=raise_errors,
            collation_map=collation_map,
            conversion_map=conversion_map,
        )
    finally:
        # Stops an empty build directory being left by every run, even one that
        # raised
        remove_build_dir(build_dir)
    if errors:
        logger.error("Collating completed with %s errors", len(errors))
    else:
        logger.info("Collating completed successfully")
    return errors
