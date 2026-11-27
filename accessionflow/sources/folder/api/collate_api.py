"""Collates files found in local or mounted folders into accessions"""

import typing as ty
from contextlib import ExitStack
from pathlib import Path

from fileformats.core import FileSet
from fileformats.medimage import DicomSeries

from accessionflow.api.collate import (
    ApplyFilesetMetadata,
    BuildAccessions,
    BuildFilesets,
    ClaimInputFiles,
    FinishClaim,
    MoveAccessions,
    ReserveRunUid,
    constant_label_fields,
)
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

    1. Makes each step with its configuration, and checks every step's configuration
       (`Step.check_configuration`) before anything is changed.
    2. Reserves the run's UID by creating its directory, ``<working_dir>/<run_uid>/``
       (`ReserveRunUid`), with another UID if one is taken.
    3. Claims the files into the run's directory (`ClaimInputFiles`). A file that
       arrives after they were listed stays in the input, for the next run.
    4. Turns the claimed files into file-sets (`BuildFilesets`), adds their
       metadata (`ApplyFilesetMetadata`) and groups them into accessions
       (`BuildAccessions`).
    5. Labels each accession, builds it in ``<output_dir>/__build__/<run_uid>/`` and
       moves it to ``<output_dir>/<labels>_<run_uid>/`` (`MoveAccessions`).
    6. Moves the files that weren't delivered (unrecognised, ignored, or of an
       accession that failed) to ``<unprocessed_dir>/<run_uid>/`` (`FinishClaim`).

    Each step's clean-up (`Step.clean_up`) is registered as the step acts, and runs
    when the run ends, in reverse order. If a step raises, including the claim part
    way, the run's claimed files are moved to ``<error_dir>/<run_uid>/``
    (`ClaimInputFiles.clean_up`) and the error is raised. Either way, the build
    directory is removed (`MoveAccessions.clean_up`), and so is the run's directory if
    nothing is left in it (`ReserveRunUid.clean_up`). An interrupt (e.g. Ctrl-C) leaves
    the claim in the working directory.

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
        the directories the files were listed from (`ClaimInputFiles`). Pass the input
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
        labels used as given, keyed by level. Each is written to the accessions'
        metadata as a field named after its level, e.g. ``project``, which the level is
        labelled from (`constant_label_fields`)
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
        if a step's configuration is invalid. Nothing has been changed
    RuntimeError
        if no unused run UID could be made. Nothing has been claimed
    """
    # The constant labels are written to the metadata, so the labels are made from it
    label_fields, constant_fields = constant_label_fields(
        label_fields, constant_labels or {}
    )
    reserve = ReserveRunUid(working_dir)
    claim = ClaimInputFiles(working_dir, error_dir)
    build_filesets = BuildFilesets(
        datatypes,
        ignore_datatypes,
        recursive=recursive,
        allow_unrecognised=allow_unrecognised,
    )
    apply_metadata = ApplyFilesetMetadata(
        dont_read_metadata,
        path_metadata=path_metadata,
        path_metadata_regex=path_metadata_regex,
        metadata_tables=list(metadata_tables or ()),
        constant_fields=constant_fields,
    )
    build_accessions = BuildAccessions(
        accession_uid_field,
        acquisition_id_field,
        resource_field,
        on_resource_clash,
        # The same table objects, so that each table is read once
        metadata_tables=apply_metadata.metadata_tables,
    )
    move = MoveAccessions(
        output_dir,
        label_fields,
        acquisition_field=acquisition_field,
        copy_mode=copy_mode,
        collation_map=collation_map,
        conversion_map=conversion_map,
        raise_errors=raise_errors,
    )
    finish = FinishClaim(unprocessed_dir)
    # Every step's configuration is checked before anything is changed
    for step in (
        reserve,
        claim,
        build_filesets,
        apply_metadata,
        build_accessions,
        move,
        finish,
    ):
        step.check_configuration()

    with ExitStack() as stack:
        run_uid = reserve.act()
        reserve.register_clean_up(stack, run_uid)
        # Before the claim acts, so that a claim that raises part way is moved too
        claim.register_clean_up(stack, run_uid)
        claimed = claim.act(input_files, run_uid, source_roots)
        build_filesets.register_clean_up(stack)
        classified = build_filesets.act(claimed)
        apply_metadata.register_clean_up(stack)
        filesets = apply_metadata.act(classified.filesets, claimed)
        build_accessions.register_clean_up(stack)
        accessions = build_accessions.act(filesets, run_uid)
        # Before the move acts, so that a build directory left part way is removed too
        move.register_clean_up(stack, run_uid)
        failed = move.act(accessions, run_uid, claimed)
        finish.register_clean_up(stack)
        finish.act(claimed, failed, classified.ignored)
    return [message for _, message in failed]
