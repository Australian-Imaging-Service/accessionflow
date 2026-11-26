"""Runs the collate steps the way ``Accession.from_paths`` is called, so that its tests
can check that both give the same accessions (see ``prefect-migration-docs/ROADMAP.md``,
Phase 1, Composites step C5). Deleted, with ``from_paths``, at the removals step,
when the tests call the steps directly."""

import typing as ty
from pathlib import Path

from fileformats.core import FileSet

from accessionflow.api.collate import (
    check_datatypes,
    claim_input_files,
    collect_accessions,
    list_input_files,
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


def collect_like_from_paths(
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
    """Lists, claims and collects the files as ``Accession.from_paths`` does, taking the
    same arguments, plus the ``working_dir`` the files are claimed into. The input
    files are moved there, as in a real run"""
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
    # as from_paths classifies them. A file found by a glob outside them is its own
    # top-level entry
    input_dirs = [
        Path(p).absolute()
        for p in files_path
        if (isinstance(p, Path) or "*" not in p) and Path(p).is_dir()
    ]
    roots = list(input_dirs)
    for fspath in files:
        if not any(fspath.absolute().is_relative_to(r) for r in roots):
            roots.append(fspath.absolute().parent)

    run_uid = make_run_uid()
    claimed = claim_input_files(files, working_dir, run_uid, roots)
    return collect_accessions(
        claimed,
        datatypes,
        recursion,
        accession_uid_field=accession_uid_field,
        recursive=recursive,
        allow_unrecognised=allow_unrecognised or (),
        dont_read_metadata=dont_read_metadata,
        path_metadata_regex=path_metadata_regex,
        metadata_tables=tables,
        acquisition_id_field=acquisition_id_field,
        resource_field=resource_field,
        on_resource_clash=on_resource_clash,
        run_uid=run_uid,
    ).accessions
