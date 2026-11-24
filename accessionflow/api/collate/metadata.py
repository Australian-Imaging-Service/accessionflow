"""Adding metadata to the file-sets from their paths and from metadata tables (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

import re
import typing as ty
from pathlib import Path

from fileformats.core import FileSet

from accessionflow.helpers.arg_types import PathMetadataRegex
from accessionflow.model.accession import Accession

from .claim import ClaimedFiles

__all__ = ["apply_path_metadata", "tag_fileset_types"]


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
