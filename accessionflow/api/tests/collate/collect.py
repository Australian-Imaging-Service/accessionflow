"""Test helpers that run the collate steps up to the accessions, without labelling or
delivering them: `collect_files`, for the tests of what the steps collect, and
`stage_unlabelled`, for the tests of the later stages that need accessions saved before
they are labelled"""

import typing as ty
from pathlib import Path

from fileformats.core import FileSet

from accessionflow.api.collate import (
    ApplyFilesetMetadata,
    BuildAccessions,
    BuildFilesets,
    ClaimInputFiles,
    list_input_files,
    list_source_roots,
    make_run_uid,
)
from accessionflow.api.step import Step
from accessionflow.helpers.arg_types import (
    ClashSpec,
    IDSpec,
    MetadataTable,
    OnResourceClash,
    PathMetadataRegex,
)
from accessionflow.model.accession import Accession

StepT = ty.TypeVar("StepT", bound=Step)


def checked(step: StepT) -> StepT:
    """Checks a step's configuration, and returns the step, ready to act"""
    step.check_configuration()
    return step


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
    # Every step is checked before any acts, as in a run
    build_filesets = checked(
        BuildFilesets(
            datatypes,
            ignore_datatypes,
            recursive=recursive,
            allow_unrecognised=allow_unrecognised or (),
        )
    )
    apply_metadata = checked(
        ApplyFilesetMetadata(
            dont_read_metadata,
            path_metadata_regex=path_metadata_regex,
            metadata_tables=list(metadata_tables or ()),
        )
    )
    build_accessions = checked(
        BuildAccessions(
            accession_uid_field,
            acquisition_id_field,
            resource_field,
            on_resource_clash,
            metadata_tables=apply_metadata.metadata_tables,
        )
    )

    # The input directories are the roots, so their top-level entries are classified
    # as they were in them
    roots = list_source_roots(list(files_path), files)

    run_uid = make_run_uid()
    # It is not cleaned up, so no claim is moved to the error directory
    claimed = ClaimInputFiles(working_dir, working_dir.parent / "error").act(
        files, run_uid, roots
    )
    classified = build_filesets.act(claimed)
    filesets = apply_metadata.act(classified.filesets, claimed)
    return build_accessions.act(filesets, run_uid)


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
