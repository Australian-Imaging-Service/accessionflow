"""Sequences of the collate steps, which the CLI runs and the flows repository mirrors
(see ``prefect-migration-docs/ROADMAP.md``, Phase 1, Composites)"""

import typing as ty
from pathlib import Path

import attrs
from fileformats.core import FileSet
from fileformats.core.exceptions import FormatMismatchError

from accessionflow.api.staging import for_each_accession
from accessionflow.helpers.arg_types import (
    ClashSpec,
    IDSpec,
    MetadataTable,
    OnResourceClash,
    PathMetadataRegex,
)
from accessionflow.model.accession import Accession

from .assign import assign_labels
from .claim import ClaimedFiles
from .classify import (
    RecursionPlan,
    classify_paths,
    disable_metadata_reading,
    drop_ignored_filesets,
    expand_claimed_paths,
)
from .group import group_into_accessions
from .metadata import (
    apply_path_metadata,
    inject_accession_tables,
    inject_fileset_tables,
    tag_fileset_types,
)
from .save import move_to_target, warn_if_hardlinks_unavailable

__all__ = [
    "ClassifiedFilesets",
    "apply_fileset_metadata",
    "build_accessions",
    "build_filesets",
    "move_accessions",
]


@attrs.frozen
class ClassifiedFilesets:
    """What `build_filesets` returns

    Attributes
    ----------
    filesets : list[FileSet]
        the file-sets of the wanted datatypes, for `apply_fileset_metadata`
    ignored : list[FileSet]
        the file-sets of ignored datatypes, which `drop_ignored_filesets` dropped. Pass
        them to `finish_claim`, which records their files as ignored
    """

    filesets: list[FileSet] = attrs.field(converter=list)
    ignored: list[FileSet] = attrs.field(converter=list)


def build_filesets(
    claimed: ClaimedFiles,
    datatypes: ty.Sequence[type[FileSet]],
    recursion: RecursionPlan,
    *,
    recursive: bool = False,
    allow_unrecognised: ty.Sequence[str] = (),
) -> ClassifiedFilesets:
    """Turns the claimed files into file-sets: steps 7 to 9

    Runs, in order, `expand_claimed_paths`, `classify_paths` and
    `drop_ignored_filesets`. No metadata is read or applied: that is
    `apply_fileset_metadata`.

    Parameters
    ----------
    claimed : ClaimedFiles
        the run's claim, from `claim_input_files`
    datatypes : Sequence[type[FileSet]]
        the datatypes to collate, checked by `check_datatypes`
    recursion : RecursionPlan
        from `plan_recursion`, whose ``ignore_datatypes`` are the datatypes dropped
    recursive : bool, optional
        whether to classify the files in the claimed directories one by one
    allow_unrecognised : Sequence[str], optional
        patterns of the base names that no datatype needs to recognise

    Returns
    -------
    ClassifiedFilesets
        the file-sets to collate, and the ignored file-sets for `finish_claim`

    Raises
    ------
    FormatMismatchError
        if a claimed file isn't recognised. A note lists the unrecognised files'
        original paths, and the run directory that holds them
    """
    fspaths = expand_claimed_paths(claimed, datatypes, recursion, recursive)
    try:
        classified = classify_paths(
            fspaths, datatypes, recursion.ignore_datatypes, allow_unrecognised
        )
    except FormatMismatchError as e:
        _note_original_paths(e, fspaths, claimed)
        raise
    filesets = drop_ignored_filesets(classified, datatypes, recursion.ignore_datatypes)
    kept_ids = {id(f) for f in filesets}
    ignored = [f for f in classified if id(f) not in kept_ids]
    return ClassifiedFilesets(filesets=filesets, ignored=ignored)


def apply_fileset_metadata(
    filesets: ty.Sequence[FileSet],
    claimed: ClaimedFiles,
    *,
    dont_read_metadata: ty.Sequence[type[FileSet]] = (),
    path_metadata_regex: ty.Sequence[PathMetadataRegex] = (),
    metadata_tables: ty.Sequence[MetadataTable] = (),
) -> list[FileSet]:
    """Adds the file-sets' metadata: steps 10 to 13

    Runs, in order, `disable_metadata_reading`, `apply_path_metadata`,
    `tag_fileset_types` and `inject_fileset_tables`. The file-sets are changed in
    place, and returned.

    Parameters
    ----------
    filesets : Sequence[FileSet]
        the file-sets, from `build_filesets`
    claimed : ClaimedFiles
        the run's claim, whose original paths the path metadata is read from
    dont_read_metadata : Sequence[type[FileSet]], optional
        the datatypes whose files aren't read for metadata
    path_metadata_regex : Sequence[PathMetadataRegex], optional
        the path-metadata regexes, already merged with the glob-like patterns
        (`merge_path_metadata`)
    metadata_tables : Sequence[MetadataTable], optional
        the metadata tables, already loaded (`load_metadata_tables`)

    Returns
    -------
    list[FileSet]
        the same file-sets, with their metadata, for `build_accessions`
    """
    filesets = disable_metadata_reading(filesets, dont_read_metadata)
    filesets = apply_path_metadata(filesets, path_metadata_regex, claimed)
    filesets = tag_fileset_types(filesets)
    return inject_fileset_tables(filesets, metadata_tables)


def build_accessions(
    filesets: ty.Sequence[FileSet],
    *,
    accession_uid_field: ty.Sequence[IDSpec],
    acquisition_id_field: ty.Sequence[IDSpec] = (),
    resource_field: ty.Sequence[IDSpec] = (),
    on_resource_clash: OnResourceClash | ty.Sequence[ClashSpec] = "error",
    run_uid: str | None = None,
    metadata_tables: ty.Sequence[MetadataTable] = (),
) -> list[Accession]:
    """Groups the file-sets into accessions: steps 14 and 15

    Runs `group_into_accessions`, then `inject_accession_tables`.

    Parameters
    ----------
    filesets : Sequence[FileSet]
        the file-sets with their metadata, from `apply_fileset_metadata`
    accession_uid_field : Sequence[IDSpec]
        how each file-set's accession is identified
    acquisition_id_field : Sequence[IDSpec], optional
        how each file-set's acquisition is identified
    resource_field : Sequence[IDSpec], optional
        how each file-set's resource is labelled
    on_resource_clash : OnResourceClash | Sequence[ClashSpec], optional
        what to do when two file-sets have the same acquisition and resource
    run_uid : str, optional
        the run's UID, given to the accessions
    metadata_tables : Sequence[MetadataTable], optional
        the metadata tables, already loaded (`load_metadata_tables`), whose accession,
        acquisition and resource rows are joined

    Returns
    -------
    list[Accession]
        the accessions, for `move_accessions`
    """
    accessions = group_into_accessions(
        filesets,
        accession_uid_field,
        acquisition_id_field,
        resource_field,
        on_resource_clash,
        run_uid,
    )
    return inject_accession_tables(accessions, metadata_tables)


def move_accessions(
    accessions: ty.Sequence[Accession],
    build_dir: Path,
    output_dir: Path,
    claimed: ClaimedFiles,
    label_fields: ty.Mapping[str, str],
    *,
    acquisition_field: str | None = None,
    constant_labels: ty.Mapping[str, str] | None = None,
    store_type: str | None = None,
    copy_mode: FileSet.CopyMode = FileSet.CopyMode.hardlink_or_copy,
    collation_map: dict[type[FileSet], FileSet.CopyCollation] | None = None,
    conversion_map: (
        dict[type[FileSet], tuple[type[FileSet], dict[str, str]]] | None
    ) = None,
    raise_errors: bool = False,
) -> list[tuple[Accession, str]]:
    """Labels the accessions and moves them to the target directory: steps 16 to 18

    Runs `warn_if_hardlinks_unavailable` once, then, for each accession in turn,
    `assign_labels` followed by `move_to_target` (with `for_each_accession`). An
    accession that fails, e.g. with `LabelsNotAssignedError` or an error saving it, is
    skipped and its files stay in the run directory. Pass the failures to
    `finish_claim` as ``failed``, so that their files are recorded as failed in the
    unprocessed directory.

    Parameters
    ----------
    accessions : Sequence[Accession]
        the accessions to deliver, from `build_accessions`
    build_dir : Path
        the run's build directory, from `prepare_build_dir`
    output_dir : Path
        the target directory the accessions are moved into
    claimed : ClaimedFiles
        the run's claim, from `claim_input_files`
    label_fields : Mapping[str, str]
        the metadata field each label is made from, keyed by level (see
        `assign_labels`)
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
        whether to raise the first failure instead of skipping the accession. The
        accessions before it have already been delivered

    Returns
    -------
    list[tuple[Accession, str]]
        each accession that failed, with its error message (traceback included), in
        order. Empty if all were delivered
    """
    warn_if_hardlinks_unavailable(accessions, build_dir, copy_mode, conversion_map)

    def deliver(accession: Accession) -> Path:
        assign_labels(
            accession,
            label_fields,
            acquisition_field=acquisition_field,
            constant_labels=constant_labels,
            store_type=store_type,
        )
        return move_to_target(
            accession,
            build_dir,
            output_dir,
            claimed,
            copy_mode=copy_mode,
            collation_map=collation_map,
            conversion_map=conversion_map,
        )

    return for_each_accession(
        accessions, deliver, "Delivering accessions", raise_errors=raise_errors
    )


def _note_original_paths(
    error: FormatMismatchError, fspaths: ty.Sequence[ty.Any], claimed: ClaimedFiles
) -> None:
    """Adds a note naming the original paths of the claimed paths the error lists, one
    per line of its message"""
    lines = set(str(error).splitlines())
    unrecognised = [p for p in fspaths if str(p) in lines]
    if not unrecognised:
        return
    originals = "\n".join(str(claimed.original_of(p)) for p in unrecognised)
    error.add_note(
        f"The unrecognised files were claimed from:\n{originals}\n"
        f"The run's files are in '{claimed.run_dir}'"
    )
