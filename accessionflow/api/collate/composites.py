"""Sequences of the collate steps, which the CLI runs and the flows repository mirrors
(see ``prefect-migration-docs/ROADMAP.md``, Phase 1, Composites)"""

import typing as ty

import attrs
from fileformats.core import FileSet
from fileformats.core.exceptions import FormatMismatchError

from accessionflow.helpers.arg_types import (
    ClashSpec,
    IDSpec,
    MetadataTable,
    OnResourceClash,
    PathMetadataRegex,
)
from accessionflow.model.accession import Accession

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

__all__ = ["CollectedAccessions", "collect_accessions"]


@attrs.frozen
class CollectedAccessions:
    """What `collect_accessions` returns

    Attributes
    ----------
    accessions : list[Accession]
        the accessions formed from the claimed files, with their metadata
    ignored : list[FileSet]
        the file-sets of ignored datatypes, which `drop_ignored_filesets` dropped. Pass
        them to `finish_claim`, which records their files as ignored
    """

    accessions: list[Accession] = attrs.field(converter=list)
    ignored: list[FileSet] = attrs.field(converter=list)


def collect_accessions(
    claimed: ClaimedFiles,
    datatypes: ty.Sequence[type[FileSet]],
    recursion: RecursionPlan,
    *,
    accession_uid_field: ty.Sequence[IDSpec],
    recursive: bool = False,
    allow_unrecognised: ty.Sequence[str] = (),
    dont_read_metadata: ty.Sequence[type[FileSet]] = (),
    path_metadata_regex: ty.Sequence[PathMetadataRegex] = (),
    metadata_tables: ty.Sequence[MetadataTable] = (),
    acquisition_id_field: ty.Sequence[IDSpec] = (),
    resource_field: ty.Sequence[IDSpec] = (),
    on_resource_clash: OnResourceClash | ty.Sequence[ClashSpec] = "error",
    run_uid: str | None = None,
) -> CollectedAccessions:
    """Forms the accessions from the claimed files: steps 7 to 15

    Runs, in order, `expand_claimed_paths`, `classify_paths`,
    `disable_metadata_reading`, `drop_ignored_filesets`, `apply_path_metadata`,
    `tag_fileset_types`, `inject_fileset_tables`, `group_into_accessions` and
    `inject_accession_tables`. See each step for its arguments.

    Parameters
    ----------
    claimed : ClaimedFiles
        the run's claim, from `claim_input_files`
    datatypes : Sequence[type[FileSet]]
        the datatypes to collate, checked by `check_datatypes`
    recursion : RecursionPlan
        from `plan_recursion`, whose ``ignore_datatypes`` are the datatypes dropped
    accession_uid_field : Sequence[IDSpec]
        how each file-set's accession is identified
    recursive : bool, optional
        whether to classify the files in the claimed directories one by one
    allow_unrecognised : Sequence[str], optional
        patterns of the base names that no datatype needs to recognise
    dont_read_metadata : Sequence[type[FileSet]], optional
        the datatypes whose files aren't read for metadata
    path_metadata_regex : Sequence[PathMetadataRegex], optional
        the path-metadata regexes, already merged with the glob-like patterns
        (`merge_path_metadata`)
    metadata_tables : Sequence[MetadataTable], optional
        the metadata tables, already loaded (`load_metadata_tables`), because a table
        delivered with the data may have been claimed
    acquisition_id_field : Sequence[IDSpec], optional
        how each file-set's acquisition is identified
    resource_field : Sequence[IDSpec], optional
        how each file-set's resource is labelled
    on_resource_clash : OnResourceClash | Sequence[ClashSpec], optional
        what to do when two file-sets have the same acquisition and resource
    run_uid : str, optional
        the run's UID, given to the accessions

    Returns
    -------
    CollectedAccessions
        the accessions, and the ignored file-sets for `finish_claim`

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
    classified = disable_metadata_reading(classified, dont_read_metadata)
    filesets = drop_ignored_filesets(classified, datatypes, recursion.ignore_datatypes)
    kept_ids = {id(f) for f in filesets}
    ignored = [f for f in classified if id(f) not in kept_ids]
    filesets = apply_path_metadata(filesets, path_metadata_regex, claimed)
    filesets = tag_fileset_types(filesets)
    filesets = inject_fileset_tables(filesets, metadata_tables)
    accessions = group_into_accessions(
        filesets,
        accession_uid_field,
        acquisition_id_field,
        resource_field,
        on_resource_clash,
        run_uid,
    )
    accessions = inject_accession_tables(accessions, metadata_tables)
    return CollectedAccessions(accessions=accessions, ignored=ignored)


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
