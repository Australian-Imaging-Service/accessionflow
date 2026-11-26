"""Collates files found in local or mounted folders into accessions"""

import typing as ty
from pathlib import Path

from fileformats.core import FileSet
from fileformats.medimage import DicomSeries

from accessionflow.api.collate import (
    ClaimedFiles,
    abandon_claim,
    apply_fileset_metadata,
    build_accessions,
    build_filesets,
    check_datatypes,
    claim_input_files,
    create_run_directory,
    finish_claim,
    load_metadata_tables,
    merge_path_metadata,
    move_accessions,
    plan_recursion,
)
from accessionflow.api.collate.claim import CLAIMED_MANIFEST
from accessionflow.api.staging import remove_build_dir
from accessionflow.helpers.arg_types import (
    ClashSpec,
    IDSpec,
    MetadataTable,
    OnResourceClash,
    PathMetadataPattern,
    PathMetadataRegex,
)

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
    2. Makes the run's UID and its build directory (`create_run_directory`), with
       another UID if one is taken.
    3. Claims the files into ``<working_dir>/<run_uid>/`` (`claim_input_files`). A
       file that arrives after they were listed stays in the input, for the next run.
    4. Turns the claimed files into file-sets (`build_filesets`), adds their
       metadata (`apply_fileset_metadata`) and groups them into accessions
       (`build_accessions`).
    5. Labels and moves each accession to ``<output_dir>/<labels>_<run_uid>/``
       (`move_accessions`).
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
        read before the claim, so a table delivered with the data can be claimed with
        it. For example, to read the relative path of each image with
        ``path_metadata_regex``, and join the rows of a table whose 'ImagePath' column
        holds spreadsheet HYPERLINK() formulas to them::

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

    run_uid, build_dir = create_run_directory(output_dir)
    claimed: ClaimedFiles | None = None
    try:
        claimed = claim_input_files(input_files, working_dir, run_uid, source_roots)
        classified = build_filesets(
            claimed,
            datatypes,
            recursion,
            recursive=recursive,
            allow_unrecognised=allow_unrecognised,
        )
        filesets = apply_fileset_metadata(
            classified.filesets,
            claimed,
            dont_read_metadata=dont_read_metadata,
            path_metadata_regex=regexes,
            metadata_tables=tables,
        )
        accessions = build_accessions(
            filesets,
            accession_uid_field=accession_uid_field,
            acquisition_id_field=acquisition_id_field,
            resource_field=resource_field,
            on_resource_clash=on_resource_clash,
            run_uid=run_uid,
            metadata_tables=tables,
        )
        failed = move_accessions(
            accessions,
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
        finish_claim(claimed, unprocessed_dir, failed, classified.ignored)
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
