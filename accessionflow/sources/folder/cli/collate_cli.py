import time
import typing as ty
from pathlib import Path

import click
from fileformats.core import FileSet

from accessionflow.cli.collate_cli import (
    check_loop_options,
    collate_group,
    collate_options,
)
from accessionflow.helpers.arg_types import (
    SEMICOLON_LIST,
    ClashSpec,
    CollationSpec,
    Convert,
    IDSpec,
    LoggerConfig,
    MetadataTable,
    MimeType,
    PathMetadataRegex,
)
from accessionflow.helpers.logging import logger, set_logger_handling

from ..api.collate_api import (
    DEFAULT_ACCESSION_UID_FIELD,
    DEFAULT_ACQUISITION_ID_FIELD,
    DEFAULT_RESOURCE_FIELD,
    collate,
)
from ..discovery import find_files


@collate_group.command(
    name="folder",
    help="""Collates the files found in folders, on a local path or a mounted file
system, into accessions, acquisitions and resources

INPUT_PATHS are paths to files, to directories containing the files to collate, or
glob patterns that select the files directly. Only files are collated, directories
are expanded into the files they contain (see --recursive)

OUTPUT_DIR is the staging directory the files of each accession are collated to,
ready to be labelled
""",
)
@click.argument("input_paths", type=str, nargs=-1, envvar="ACFLOW_INPUT_PATHS")
@click.argument(
    "output_dir", type=click.Path(path_type=Path), envvar="ACFLOW_OUTPUT_DIR"
)
@click.option(
    "--accession-uid",
    type=IDSpec.cli_type,
    nargs=2,
    multiple=True,
    default=DEFAULT_ACCESSION_UID_FIELD,
    metavar="<specifier> <datatype>",
    envvar="ACFLOW_ACCESSION_UID",
    help=(
        "The metadata field whose value identifies the accession each file is collated "
        "into, before it is labelled (ACFLOW_ACCESSION_UID env. var). Defaults to "
        "'StudyInstanceUID' for DICOM collections; other fileset types need an explicit "
        "spec. Can also be a "
        "Python format string over several fields, e.g. '{PatientID}_{StudyDate:%Y%m%d}', "
        "to compose one. Not to be confused with DICOM's AccessionNumber, which is just "
        "another field that can be used here or to label the accession."
    ),
)
@click.option(
    "--acquisition-id",
    type=IDSpec.cli_type,
    nargs=2,
    multiple=True,
    default=DEFAULT_ACQUISITION_ID_FIELD,
    metavar="<specifier> <datatype>",
    envvar="ACFLOW_ACQUISITION_ID",
    help=(
        "The keyword of the metadata field to extract the acquisition ID from, or a "
        "Python format string over several fields (see --accession-uid). Defaults to "
        "'SeriesNumber' for DICOM collections (one acquisition per series); for any "
        "fileset type not matched by an --acquisition-id spec the acquisition is named "
        "after the resource (ACFLOW_ACQUISITION_ID env. var)"
    ),
)
@click.option(
    "--resource",
    type=IDSpec.cli_type,
    nargs=2,
    multiple=True,
    default=DEFAULT_RESOURCE_FIELD,
    metavar="<specifier> <datatype>",
    envvar="ACFLOW_RESOURCE",
    help=(
        "The keywords of the metadata field to extract the resource ID from "
        "for different datatypes (use `generic/file-set` as a catch-all if required), or a "
        "Python format string over several fields (see --accession-uid). If not given, each "
        "resource is labelled with the mime-like rendering of its fileset type name, "
        "e.g. 'vectra-export', 'sqlite3-db' (ACFLOW_RESOURCE env. var)"
    ),
)
@click.option(
    "--datatype",
    type=MimeType.cli_type,
    metavar="<mime-type>",
    multiple=True,
    default=["medimage/dicom-series"],
    envvar="ACFLOW_DATATYPES",
    help=(
        'The MIME-type(s) (or "MIME-like" see FileFormats docs) of potential datatype(s) '
        "of the primary files to to upload, defaults to 'medimage/dicom-series'. "
        "Any formats implemented in the FileFormats Python package "
        "(https://github.com/ArcanaFramework/fileformats) that implement the 'read_metadata' "
        '"extra" are supported, see FF docs on how to add support for new formats. '
        "Directory datatypes are not supported."
    ),
)
@click.option(
    "--path-metadata-regex",
    type=PathMetadataRegex.cli_type,
    multiple=True,
    nargs=2,
    metavar="<regex> <datatype>",
    envvar="ACFLOW_PATH_METADATA_REGEX",
    default=(),
    help=(
        'Regular expressions to extract "metadata" values from resource file paths as named groups. '
        "using Python regular expression syntax. The named groups are used as metadata fields for "
        "the resource files, and the extracted values will be used to populate the corresponding "
        "metadata fields to complement the metadata read from the file headers."
    ),
)
@click.option(
    "--on-resource-clash",
    type=ClashSpec.cli_type,
    nargs=2,
    multiple=True,
    default=(),
    metavar="<policy> <scope>",
    envvar="ACFLOW_ON_RESOURCE_CLASH",
    help=(
        "How to handle two filesets resolving to the same acquisition/resource name: a <policy> "
        "('avoid' appends a _2/_3 suffix, 'merge' folds both into one SetOf, 'overwrite' "
        "replaces) plus the datatype <scope> it applies to (a mime-like, a '|'-union, or "
        "'all'). Repeatable. A clash is resolved by the first spec whose scope covers BOTH "
        "filesets; a clash no spec covers raises. (ACFLOW_ON_RESOURCE_CLASH env. var)"
    ),
)
@click.option(
    "--allow-unrecognised",
    "--allow-unrecognized",
    "allow_unrecognised",
    type=SEMICOLON_LIST,
    default=(),
    multiple=True,
    envvar="ACFLOW_ALLOW_UNRECOGNISED",
    help=(
        "Regular expressions matched against the basename of any input path that no --datatype "
        "recognised; matches are skipped instead of raising. Use '.*' to tolerate all "
        "unrecognised files. Does not affect recognised filesets. Repeatable; the "
        "ACFLOW_ALLOW_UNRECOGNISED env. var takes a ';'-separated list."
    ),
)
@click.option(
    "--exclude-path",
    "exclude_paths",
    type=SEMICOLON_LIST,
    default=(),
    multiple=True,
    envvar="ACFLOW_EXCLUDE_PATH",
    help=(
        "Glob patterns matched against each input path relative to <input-dir>, applied before "
        "classification so a match is dropped even if a --datatype would claim it (e.g. a vendor "
        "thumbnail that is a valid image/png). '*' does not cross '/', '**' does. Repeatable; the "
        "ACFLOW_EXCLUDE_PATH env. var takes a ';'-separated list."
    ),
)
@click.option(
    "--ignore-datatype",
    "ignore_datatypes",
    type=MimeType.cli_type,
    default=(),
    multiple=True,
    envvar="ACFLOW_IGNORE_DATATYPE",
    help=(
        "Datatypes expected in the input but not wanted: recognised files of these types are "
        "dropped instead of raising. A file matching neither --datatype nor --ignore-datatype "
        "nor --allow-unrecognised/--exclude-path still raises. (ACFLOW_IGNORE_DATATYPE env. var)"
    ),
)
@click.option(
    "--recursive/--not-recursive",
    type=bool,
    default=False,
    envvar="ACFLOW_RECURSIVE",
    help=("Whether to recursively search input directories for input files"),
)
@click.option(
    "--unlink-source",
    type=click.Choice(["all", "keep-metadata"]),
    default=None,
    envvar="ACFLOW_UNLINK_SOURCE",
    help=(
        "Whether to unlink the source files after they have been successfully "
        "collated. 'all' and 'keep-metadata' behave the same here (individual "
        "source files are removed one by one) since 'collate's source isn't a "
        "directory tree that accessionflow owns and can't have a metadata skeleton "
        "left behind in it (ACFLOW_UNLINK_SOURCE env. var)"
    ),
)
@click.option(
    "--collate-resources",
    type=CollationSpec.cli_type,
    metavar="<mime-type> <collation>",
    nargs=2,
    multiple=True,
    default=(),
    envvar="ACFLOW_COLLATE_RESOURCES",
    help=(
        "Flatten files of the given datatype into the resource directory during collation, "
        "regardless of source directory structure. "
        "Collation level is one of 'any', 'siblings', or 'adjacent' (default 'siblings'). "
    ),
)
@click.option(
    "--metadata-table",
    "metadata_tables",
    multiple=True,
    type=MetadataTable.cli_type,
    envvar="ACFLOW_METADATA_TABLES",
    nargs=3,
    default=(),
    metavar="<path> <row-frequency> <join-exprs>",
    help=(
        "Specify metadata tables to extract and join metadata from input files (ACFLOW_METADATA_TABLES env. var). "
        "The 'path' arg specifies the location of the metadata table file. Its format is auto-detected as CSV or "
        "TSV from the file extension; a different format can be forced by appending its mime-type in square "
        "brackets, e.g. 'path/to/table.dat[text/csv]'. "
        'The "row frequency" arg specifies what each row in the '
        "metadata table corresponds to in the data hierarchy, and can be one of 'accession', 'acquisition', 'resource', "
        "'fileset', 'fileset[<mime-type>]'. When one or more mime-types are given in square brackets after 'fileset' "
        "they restrict the join to input files of those types (multiple mime-types can be '|'-separated, e.g. "
        "'fileset[image/png|image/jpeg]'); a bare 'fileset' matches any input file. "
        "The 'join-exprs' arg is a comma-separated list of '<column-name>=<cell-value>' expressions; a row is a "
        "match when every expression holds. The '<cell-value>' is either the name of an existing metadata field or "
        "a Python format string over one or more metadata fields, e.g. '{PatientID}_{SessionID}'. All columns of "
        "the matched row are then merged into the target's metadata. "
        "The example below extracts the relative path of an image file with `--path-metadata-regex` and uses it to "
        "join a table whose 'ImagePath' column holds spreadsheet HYPERLINK() formulas.\n\n"
        "    accessionflow collate folder ...  \\\n"
        "        --path-metadata-regex '.*/(?P<relpath>[\\w-]+/[\\w-]+\\.(?:png|jpg))' image/png|image/jpeg \\\n"
        "        --metadata-table path/to/table.csv[text/csv] fileset[image/png|image/jpeg] "
        "'ImagePath=HYPERLINK(\"{relpath}\")'\n"
    ),
)
@collate_options
def collate_cmd(
    input_paths: list[str],
    output_dir: Path,
    accession_uid: ty.Sequence[IDSpec],
    acquisition_id: ty.Sequence[IDSpec],
    resource: ty.Sequence[IDSpec],
    datatype: list[MimeType] | None,
    path_metadata_regex: list[PathMetadataRegex],
    unlink_source: str | None,
    loggers: list[LoggerConfig],
    additional_loggers: list[str],
    raise_errors: bool,
    on_resource_clash: tuple[ClashSpec, ...],
    allow_unrecognised: tuple[str, ...],
    exclude_paths: tuple[str, ...],
    ignore_datatypes: tuple[MimeType, ...],
    loop: int,
    recursive: bool,
    copy_mode: FileSet.CopyMode,
    collate_resources: tuple[CollationSpec, ...],
    conversions: tuple[Convert, ...],
    metadata_tables: tuple[MetadataTable, ...],
) -> None:
    check_loop_options(raise_errors, loop)

    set_logger_handling(
        logger_configs=loggers,
        additional_loggers=additional_loggers,
    )

    # Run the collation in a loop if loop is set to a positive value, otherwise just
    # run it once
    while True:
        start_time = time.monotonic()
        errors = collate(
            input_file_paths=find_files(
                input_paths, recursive=recursive, exclude_paths=exclude_paths
            ),
            output_dir=output_dir,
            datatypes=[dt.datatype for dt in datatype or ()],
            accession_uid=accession_uid,
            acquisition_id=acquisition_id,
            resource=resource,
            unlink_source=unlink_source,
            raise_errors=raise_errors,
            copy_mode=copy_mode,
            allow_unrecognised=allow_unrecognised,
            ignore_datatypes=[dt.datatype for dt in ignore_datatypes],
            on_resource_clash=list(on_resource_clash),
            path_metadata_regex=path_metadata_regex,
            collation_map={cs.datatype: cs.collation_level for cs in collate_resources},
            conversion_map={c.source: (c.target, c.options) for c in conversions},
            metadata_tables=list(metadata_tables),
        )
        if errors:
            logger.error(
                "Staging completed with %s errors:\n\n%s",
                len(errors),
                "\n".join(errors),
            )
        else:
            logger.info("Staging completed successfully")
        if loop < 0:
            break
        elapsed_seconds = time.monotonic() - start_time
        sleep_time = max(loop - elapsed_seconds, 0)
        logger.info(
            "Collate took %s seconds, waiting another %s seconds before running "
            "again (loop every %s seconds)",
            elapsed_seconds,
            sleep_time,
            loop,
        )
        time.sleep(sleep_time)
