"""Adding metadata to the file-sets from their paths and from metadata tables (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

import re
import typing as ty
from pathlib import Path

from fileformats.core import FileSet

from accessionflow.helpers.arg_types import MetadataTable, PathMetadataRegex
from accessionflow.model.accession import Accession

from .claim import ClaimedFiles

__all__ = [
    "apply_path_metadata",
    "inject_fileset_tables",
    "load_metadata_tables",
    "tag_fileset_types",
]


def load_metadata_tables(
    metadata_tables: ty.Sequence[MetadataTable] | None = None,
) -> list[MetadataTable]:
    """Reads every metadata table into memory, and checks that the columns its join
    expressions name are in it. It only reads, so it runs before the claim, and a
    missing, unreadable or mismatched table fails before anything is created or moved.

    A table is read once and kept in the ``MetadataTable`` object, which pickles with
    it. That matters when the table is delivered with the data: a table file inside
    the input directory is claimed with the files around it, so it is no longer at its
    original path by the time the tables are injected.

    Parameters
    ----------
    metadata_tables : Sequence[MetadataTable], optional
        the tables, from ``--metadata-table``

    Returns
    -------
    list[MetadataTable]
        the same tables, now loaded

    Raises
    ------
    ValueError
        if a join expression names a column that isn't in its table
    """
    tables = list(metadata_tables or [])
    for table in tables:
        columns = table.table
        for expr in table.join_exprs:
            if expr.column_name not in columns:
                raise ValueError(
                    f"Join column '{expr.column_name}' not found in metadata table "
                    f"{table.table_file} (available columns: {list(columns)})"
                )
    return tables


def apply_path_metadata(
    filesets: ty.Sequence[FileSet],
    path_metadata_regex: ty.Sequence[PathMetadataRegex] = (),
    claimed: ClaimedFiles | None = None,
) -> list[FileSet]:
    """Adds the metadata fields that the regular expressions extract from the paths
    of the file-sets, as named groups

    Each regular expression is applied, in order, to the file-sets that are instances
    of its datatype, so where two set the same field the later one wins. It is matched
    from the start of the file-set's path: ``fspath``, or ``parent`` for a file-set of
    several files that has none (e.g. a DICOM series). If ``claimed`` is given, the
    file-set's **original** path is matched, from before it was claimed, so patterns
    written for the input directory still match.

    The file-sets' metadata is changed in place, and the same file-sets are returned.

    Parameters
    ----------
    filesets : Sequence[FileSet]
        the file-sets, from `drop_ignored_filesets`
    path_metadata_regex : Sequence[PathMetadataRegex], optional
        the regular expressions and the datatypes they apply to. Glob-like
        ``--path-metadata`` patterns are translated to regular expressions first,
        e.g. with ``accessionflow.sources.folder.api.merge_path_metadata``
    claimed : ClaimedFiles, optional
        the run's claimed files, to map each file-set's path back to its original
        path. If not given, the file-sets' own paths are matched

    Returns
    -------
    list[FileSet]
        the same file-sets

    Raises
    ------
    ValueError
        if a regular expression doesn't match the path of a file-set of its datatype.
        The message names the original path
    """
    for fileset in filesets:
        for path_mdata in path_metadata_regex:
            if not isinstance(fileset, path_mdata.datatype):
                continue
            fspath = Path(getattr(fileset, "fspath", fileset.parent))
            if claimed is not None:
                fspath = claimed.original_of(fspath)
            match = re.match(path_mdata.regex, str(fspath))
            if match is None:
                raise ValueError(
                    f"Could not extract metadata from path '{fspath}' using pattern "
                    f"'{path_mdata.regex}'"
                )
            fileset.metadata.update(match.groupdict())
    return list(filesets)


def tag_fileset_types(filesets: ty.Sequence[FileSet]) -> list[FileSet]:
    """Sets each file-set's ``__datatype__`` metadata field
    (``Accession.TYPE_METADATA_KEY``) to the name of its type, e.g. ``DicomSeries`` or
    ``DirectoryOf[Json]``, so that ``--accession``, ``--acquisition`` and ``--resource``
    specs can use it (e.g. ``'res_{__datatype__}'``)

    A value that is already set is kept, e.g. from a path-metadata group of the same
    name (`apply_path_metadata`), which is why this step runs after that one. The
    check includes the metadata read from the files, so a header field of that name
    is kept too. The metadata tables are injected after this step, so a table column
    of that name overrides it.

    The file-sets' metadata is changed in place, and the same file-sets are returned.

    Parameters
    ----------
    filesets : Sequence[FileSet]
        the file-sets, after `apply_path_metadata`

    Returns
    -------
    list[FileSet]
        the same file-sets
    """
    for fileset in filesets:
        fileset.metadata.setdefault(Accession.TYPE_METADATA_KEY, fileset.type_name)
    return list(filesets)


def inject_fileset_tables(
    filesets: ty.Sequence[FileSet],
    metadata_tables: ty.Sequence[MetadataTable] | None = None,
) -> list[FileSet]:
    """Merges into each file-set the row of each ``fileset`` metadata table that its
    metadata joins to. Tables with another row frequency (accession, acquisition or
    resource) are left for `inject_accession_tables`, after the file-sets are grouped.

    Load the tables with `load_metadata_tables` before the claim: a table that isn't
    loaded yet is read here, from a path the claim may have moved it from.

    The file-sets' metadata is changed in place, and the same file-sets are returned.

    Parameters
    ----------
    filesets : Sequence[FileSet]
        the file-sets, after `tag_fileset_types`
    metadata_tables : Sequence[MetadataTable], optional
        the tables, from `load_metadata_tables`

    Returns
    -------
    list[FileSet]
        the same file-sets

    Raises
    ------
    ValueError
        if more than one row of a table joins to a file-set
    """
    MetadataTable.inject_list(list(metadata_tables or []), list(filesets))
    return list(filesets)
