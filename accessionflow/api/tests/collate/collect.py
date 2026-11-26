"""Test helpers that run the collate steps up to the accessions, without labelling or
delivering them: `collect_files`, for the tests of what the steps collect, and
`stage_unlabelled`, for the tests of the later stages that need accessions saved before
they are labelled"""

import typing as ty
from pathlib import Path

from fileformats.core import FileSet

from accessionflow.api.collate import (
    apply_fileset_metadata,
    build_accessions,
    build_filesets,
    check_datatypes,
    claim_input_files,
    list_input_files,
    list_source_roots,
    load_metadata_tables,
    make_run_uid,
    plan_recursion,
)
from accessionflow.helpers.arg_types import (
    ClashSpec,
    IDSpec,
    MetadataTable,
    OnResourceClash,
    PathMetadataRegex,
)
from accessionflow.model.accession import Accession


def collect_files(
    files_path: str | Path | ty.Sequence[str | Path],
    datatypes: type[FileSet] | ty.Sequence[type[FileSet]],
    accession_uid_field: ty.Sequence[IDSpec],
    acquisition_id_field: ty.Sequence[IDSpec] = (),
    resource_field: ty.Sequence[IDSpec] = (),
    *,
    working_dir: Path,
    recursive: bool = False,
    on_resource_clash: OnResourceClash | ty.Sequence[ClashSpec] = "error",
    allow_unrecognised: ty.Sequence[str] | None = None,
    exclude_paths: ty.Sequence[str] | None = None,
    ignore_datatypes: ty.Sequence[type[FileSet]] | None = None,
    path_metadata_regex: ty.Sequence[PathMetadataRegex] = (),
    metadata_tables: list[MetadataTable] | None = None,
    dont_read_metadata: ty.Sequence[type[FileSet]] = (),
) -> list[Accession]:
    """Lists, claims and collects the files into accessions, which aren't labelled. The
    input files are moved into ``working_dir``, as in a real run"""
    if isinstance(files_path, (str, Path)):
        files_path = [files_path]
    if isinstance(datatypes, type):
        datatypes = [datatypes]
    ignore_datatypes = ignore_datatypes or ()

    files = list_input_files(list(files_path), exclude_paths or ())
    check_datatypes(datatypes, ignore_datatypes)
    recursion = plan_recursion(datatypes, ignore_datatypes, recursive)
    tables = load_metadata_tables(metadata_tables)

    # The input directories are the roots, so their top-level entries are classified
    # as they were in them
    roots = list_source_roots(list(files_path), files)

    run_uid = make_run_uid()
    claimed = claim_input_files(files, working_dir, run_uid, roots)
    classified = build_filesets(
        claimed,
        datatypes,
        recursion,
        recursive=recursive,
        allow_unrecognised=allow_unrecognised or (),
    )
    filesets = apply_fileset_metadata(
        classified.filesets,
        claimed,
        dont_read_metadata=dont_read_metadata,
        path_metadata_regex=path_metadata_regex,
        metadata_tables=tables,
    )
    return build_accessions(
        filesets,
        accession_uid_field=accession_uid_field,
        acquisition_id_field=acquisition_id_field,
        resource_field=resource_field,
        on_resource_clash=on_resource_clash,
        run_uid=run_uid,
        metadata_tables=tables,
    )


def stage_unlabelled(
    files_path: str | Path | ty.Sequence[str | Path],
    output_dir: Path,
    datatypes: type[FileSet] | ty.Sequence[type[FileSet]],
    accession_uid_field: ty.Sequence[IDSpec],
    acquisition_id_field: ty.Sequence[IDSpec] = (),
    resource_field: ty.Sequence[IDSpec] = (),
    *,
    working_dir: Path,
    **kwargs: ty.Any,
) -> list[Path]:
    """Collects the files with `collect_files` and saves each accession, unlabelled, to
    ``output_dir/_.<uid>``, as the folder source staged them for the 'label' stage
    before collate labelled them (the Orthanc source still does)

    Returns
    -------
    list[Path]
        the saved accessions' directories
    """
    accessions = collect_files(
        files_path,
        datatypes,
        accession_uid_field,
        acquisition_id_field,
        resource_field,
        working_dir=working_dir,
        **kwargs,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    return [accession.save(output_dir)[1] for accession in accessions]
