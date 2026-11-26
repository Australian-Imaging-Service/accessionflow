import time
import typing as ty
from datetime import timedelta
from pathlib import Path

import click
from fileformats.core import FileSet

from accessionflow.api.collate import (
    ERROR_NAME_DEFAULT,
    PROCESSING_NAME_DEFAULT,
    RUNS_NAME_DEFAULT,
    UNPROCESSED_NAME_DEFAULT,
    check_primary_label,
    combine_run_accessions,
    list_input_files,
    list_source_roots,
)
from accessionflow.cli.aliases import resolve_deprecated_alias
from accessionflow.cli.collate_cli import collate_group, collate_options
from accessionflow.cli.label_options import (
    StoreLabelOption,
    resolve_label_options,
    store_label_options,
)
from accessionflow.cli.runner import (
    check_loop_options,
    log_stage_summary,
    run_on_interval,
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
    PathMetadataPattern,
    PathMetadataRegex,
    collation_map_from,
    conversion_map_from,
)
from accessionflow.helpers.logging import logger, set_logger_handling
from accessionflow.model.store import get_store, store_plugins

from ..api.collate_api import (
    DEFAULT_ACCESSION_UID_FIELD,
    DEFAULT_ACQUISITION_ID_FIELD,
    DEFAULT_RESOURCE_FIELD,
    collate_files,
)

DEFAULT_STORE = "xnat"
DEFAULT_PRIMARY_LABEL = "combined"

WAIT_PERIOD_HELP = (
    "The number of seconds an accession must have had no new data for before its run "
    "accessions are combined and delivered to OUTPUT_DIR. The files are collated on "
    "every run, whether or not more are still arriving, into run accessions in the "
    "run-accessions directory (--runs-dir) (ACFLOW_WAIT_PERIOD env. var)"
)


@collate_group.command(
    name="folder",
    help="""Collates the files found in folders, on a local path or a mounted file
system, into accessions, acquisitions and resources, labelled for the data store given
by --store

INPUT_PATHS are either paths to directories containing the files to collate, or
glob patterns that select the paths directly. The files collated are moved out of them

OUTPUT_DIR is the staging directory the accessions are delivered to, each in a directory
named '<labels>_<primary-label>', e.g. '<project>.<subject>.<session>_combined' for
XNAT. Each run delivers the accessions it collated to the run-accessions directory
(--runs-dir), and an accession's run accessions are combined into one in OUTPUT_DIR once
it has had no new data for --wait-period
""",
)
@click.argument("input_paths", type=str, nargs=-1, envvar="ACFLOW_INPUT_PATHS")
@click.argument(
    "output_dir", type=click.Path(path_type=Path), envvar="ACFLOW_OUTPUT_DIR"
)
@click.option(
    "--accession",
    "accession_uid",
    type=IDSpec.cli_type,
    nargs=2,
    multiple=True,
    default=DEFAULT_ACCESSION_UID_FIELD,
    metavar="<specifier> <datatype>",
    envvar="ACFLOW_ACCESSION",
    help=(
        "The metadata field whose value identifies the accession each file is collated "
        "into, before it is labelled, so it must be unique across all accessions "
        "(ACFLOW_ACCESSION env. var). Defaults to "
        "'StudyInstanceUID' for DICOM collections; other fileset types need an explicit "
        "spec. Can also be a "
        "Python format string over several fields, e.g. '{PatientID}_{StudyDate:%Y%m%d}', "
        "to compose one. Not to be confused with DICOM's AccessionNumber, which is just "
        "another field that can be used here or to label the accession."
    ),
)
@click.option(
    "--accession-uid",
    "accession_uid_deprecated",
    type=IDSpec.cli_type,
    nargs=2,
    multiple=True,
    default=(),
    envvar="ACFLOW_ACCESSION_UID",
    hidden=True,
    help="Deprecated alias of --accession (ACFLOW_ACCESSION_UID env. var)",
)
@click.option(
    "--acquisition",
    "acquisition_id",
    type=IDSpec.cli_type,
    nargs=2,
    multiple=True,
    default=DEFAULT_ACQUISITION_ID_FIELD,
    metavar="<specifier> <datatype>",
    envvar="ACFLOW_ACQUISITION",
    help=(
        "The keyword of the metadata field to extract the acquisition ID from, which must "
        "be unique within its accession, or a "
        "Python format string over several fields (see --accession). Defaults to "
        "'SeriesNumber' for DICOM collections (one acquisition per series); for any "
        "fileset type not matched by an --acquisition spec the acquisition is named "
        "after the resource (ACFLOW_ACQUISITION env. var)"
    ),
)
@click.option(
    "--acquisition-id",
    "acquisition_id_deprecated",
    type=IDSpec.cli_type,
    nargs=2,
    multiple=True,
    default=(),
    envvar="ACFLOW_ACQUISITION_ID",
    hidden=True,
    help="Deprecated alias of --acquisition (ACFLOW_ACQUISITION_ID env. var)",
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
        "Python format string over several fields (see --accession). If not given, each "
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
        '"extra" are supported, see FF docs on how to add support for new formats.'
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
    "--path-metadata",
    type=PathMetadataPattern.cli_type,
    multiple=True,
    nargs=2,
    metavar="<pattern> <datatype>",
    envvar="ACFLOW_PATH_METADATA",
    default=(),
    help=(
        "A simpler, glob-like alternative to --path-metadata-regex. '{name}' placeholders mark "
        "the parts of the resource's path to extract into the metadata field 'name', e.g. "
        "'{subject}/{session}'. '*' matches within a path segment, '**' across segments "
        "and '?' a single character; '{{' and '}}' match literal braces. Unless the pattern "
        "starts with '/', it only needs to match the trailing segments of the path. Applied "
        "before any --path-metadata-regex (ACFLOW_PATH_METADATA env. var)"
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
        "dropped instead of raising, and with --recursive a matching directory is skipped "
        "without descending into it. A path matching neither --datatype nor --ignore-datatype "
        "nor --allow-unrecognised/--exclude-path still raises. (ACFLOW_IGNORE_DATATYPE env. var)"
    ),
)
@click.option(
    "--dont-read-metadata",
    "dont_read_metadata",
    type=MimeType.cli_type,
    default=(),
    multiple=True,
    metavar="<datatype>",
    envvar="ACFLOW_DONT_READ_METADATA",
    help=(
        "Datatypes whose files aren't read for metadata, so their only metadata fields are "
        "those from --path-metadata/--path-metadata-regex and --metadata-table. Saves reading "
        "the header of every file when none of its fields are used, e.g. when the IDs all come "
        "from the path. Matched with isinstance, so 'medimage/nifti' also covers "
        "'medimage/nifti-gz'. Repeatable. (ACFLOW_DONT_READ_METADATA env. var)"
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
        "Deprecated, and has no effect: the files collated are always moved out of the "
        "input directories (ACFLOW_UNLINK_SOURCE env. var)"
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
@click.option(
    "--store",
    "store_name",
    type=click.Choice(store_plugins()),
    default=DEFAULT_STORE,
    envvar="ACFLOW_STORE",
    help=(
        "The data store the accessions are labelled for, which gives the label "
        "options used, e.g. --project, --subject, --session and --scan for 'xnat', or "
        "--level and --constant-label for 'folder' (ACFLOW_STORE env. var)"
    ),
)
@click.option(
    "--primary-label",
    type=str,
    default=DEFAULT_PRIMARY_LABEL,
    envvar="ACFLOW_PRIMARY_LABEL",
    help=(
        "The suffix of the names of the accessions delivered to OUTPUT_DIR, "
        "'<labels>_<primary-label>': letters, digits and '-' "
        "(ACFLOW_PRIMARY_LABEL env. var)"
    ),
)
@click.option(
    "--runs-dir",
    type=click.Path(path_type=Path),
    default=None,
    envvar="ACFLOW_RUNS_DIR",
    help=(
        "The directory each run delivers its run accessions to, "
        f"'<labels>_<run-uid>', by default OUTPUT_DIR/{RUNS_NAME_DEFAULT} "
        "(ACFLOW_RUNS_DIR env. var)"
    ),
)
@click.option(
    "--working-dir",
    type=click.Path(path_type=Path),
    default=None,
    envvar="ACFLOW_WORKING_DIR",
    help=(
        "The directory the files of each run are moved into while they are collated, "
        f"by default OUTPUT_DIR/{PROCESSING_NAME_DEFAULT} (ACFLOW_WORKING_DIR env. var)"
    ),
)
@click.option(
    "--unprocessed-dir",
    type=click.Path(path_type=Path),
    default=None,
    envvar="ACFLOW_UNPROCESSED_DIR",
    help=(
        "The directory the files of a run that weren't delivered (unrecognised, "
        "ignored, or of an accession that failed) are moved to, by default "
        f"OUTPUT_DIR/{UNPROCESSED_NAME_DEFAULT} (ACFLOW_UNPROCESSED_DIR env. var)"
    ),
)
@click.option(
    "--error-dir",
    type=click.Path(path_type=Path),
    default=None,
    envvar="ACFLOW_ERROR_DIR",
    help=(
        "The directory the files of a run that failed, and the run accessions of an "
        "accession that couldn't be combined, are moved to, by default "
        f"OUTPUT_DIR/{ERROR_NAME_DEFAULT} (ACFLOW_ERROR_DIR env. var)"
    ),
)
@collate_options(wait_period_help=WAIT_PERIOD_HELP)
def collate_cmd(
    input_paths: list[str],
    output_dir: Path,
    accession_uid: ty.Sequence[IDSpec],
    accession_uid_deprecated: ty.Sequence[IDSpec],
    acquisition_id: ty.Sequence[IDSpec],
    acquisition_id_deprecated: ty.Sequence[IDSpec],
    resource: ty.Sequence[IDSpec],
    datatype: list[MimeType] | None,
    path_metadata_regex: list[PathMetadataRegex],
    path_metadata: list[PathMetadataPattern],
    unlink_source: str | None,
    loggers: list[LoggerConfig],
    additional_loggers: list[str],
    raise_errors: bool,
    on_resource_clash: tuple[ClashSpec, ...],
    allow_unrecognised: tuple[str, ...],
    exclude_paths: tuple[str, ...],
    ignore_datatypes: tuple[MimeType, ...],
    dont_read_metadata: tuple[MimeType, ...],
    loop: int,
    wait_period: int,
    recursive: bool,
    copy_mode: FileSet.CopyMode,
    collate_resources: tuple[CollationSpec, ...],
    conversions: tuple[Convert, ...],
    metadata_tables: tuple[MetadataTable, ...],
    store_name: str,
    primary_label: str,
    runs_dir: Path | None,
    working_dir: Path | None,
    unprocessed_dir: Path | None,
    error_dir: Path | None,
    **label_values: ty.Any,
) -> None:
    accession_uid = resolve_deprecated_alias(
        accession_uid,
        accession_uid_deprecated,
        param="accession_uid",
        deprecated_param="accession_uid_deprecated",
    )
    acquisition_id = resolve_deprecated_alias(
        acquisition_id,
        acquisition_id_deprecated,
        param="acquisition_id",
        deprecated_param="acquisition_id_deprecated",
    )
    check_loop_options(raise_errors, loop)

    set_logger_handling(
        logger_configs=loggers,
        additional_loggers=additional_loggers,
    )

    # Everything is checked before anything is changed
    store = get_store(store_name)
    _refuse_other_stores_options(store_name)
    labels = resolve_label_options(store, STORE_LABEL_OPTIONS[store_name], label_values)
    check_primary_label(primary_label)
    if unlink_source is not None:
        logger.warning(
            "--unlink-source (ACFLOW_UNLINK_SOURCE) is deprecated and has no effect: "
            "the files collated are always moved out of the input directories"
        )
    output_dir = Path(output_dir)
    runs_dir = runs_dir or output_dir / RUNS_NAME_DEFAULT
    working_dir = working_dir or output_dir / PROCESSING_NAME_DEFAULT
    unprocessed_dir = unprocessed_dir or output_dir / UNPROCESSED_NAME_DEFAULT
    error_dir = error_dir or output_dir / ERROR_NAME_DEFAULT

    def run_once() -> None:
        # Listed again on every run, which picks up the files that arrived since the
        # last one
        input_files = list_input_files(
            input_paths,
            exclude_paths,
            metadata_table_paths=[t.table_file.fspath for t in metadata_tables],
        )
        errors = collate_files(
            input_files,
            runs_dir,
            working_dir,
            unprocessed_dir,
            error_dir,
            labels.label_fields,
            datatypes=[dt.datatype for dt in datatype or ()],
            ignore_datatypes=[dt.datatype for dt in ignore_datatypes],
            source_roots=list_source_roots(input_paths, input_files),
            recursive=recursive,
            allow_unrecognised=allow_unrecognised,
            dont_read_metadata=[dt.datatype for dt in dont_read_metadata],
            accession_uid_field=accession_uid,
            acquisition_id_field=acquisition_id,
            resource_field=resource,
            path_metadata=path_metadata,
            path_metadata_regex=path_metadata_regex,
            metadata_tables=list(metadata_tables),
            on_resource_clash=list(on_resource_clash),
            acquisition_field=labels.acquisition_field,
            constant_labels=labels.constant_labels,
            store_type=store.name,
            copy_mode=copy_mode,
            collation_map=collation_map_from(collate_resources),
            conversion_map=conversion_map_from(conversions),
            raise_errors=raise_errors,
        )
        errors += combine_run_accessions(
            runs_dir,
            output_dir,
            error_dir,
            timedelta(seconds=wait_period),
            primary_label,
            on_resource_clash=list(on_resource_clash),
            copy_mode=copy_mode,
            raise_errors=raise_errors,
        )
        log_stage_summary(errors, "Staging")

    # The clock and sleep are looked up here, so that they can be patched in this
    # module
    run_on_interval(
        run_once, loop, "Collate", monotonic=time.monotonic, sleep=time.sleep
    )


def _store_label_options() -> dict[str, list[StoreLabelOption]]:
    """The label options of each installed store, by store name, as 'collate folder'
    takes them. An option whose name or environment variable is one of the command's
    own is named after its store, e.g. the folder store's '--acquisition' (the field of
    an acquisition's description) is '--folder-acquisition', since '--acquisition' is
    the acquisition ID"""
    taken_opts: set[str] = set()
    taken_envvars: set[str] = set()
    for param in collate_cmd.params:
        taken_opts.update(param.opts + param.secondary_opts)
        if isinstance(param.envvar, str):
            taken_envvars.add(param.envvar)
    by_store: dict[str, list[StoreLabelOption]] = {}
    for name in store_plugins():
        store = get_store(name)
        rename = {
            opt.option.opts[0]: f"--{name}-{opt.option.opts[0][2:]}"
            for opt in store_label_options(store, collate=True)
            if opt.option.opts[0] in taken_opts or opt.option.envvar in taken_envvars
        }
        by_store[name] = store_label_options(store, collate=True, rename=rename)
    return by_store


def _add_store_label_options() -> None:
    """Adds the label options of every installed store to the command, each once,
    before the options that all sources share"""
    added: dict[str, click.Option] = {}
    for name, options in STORE_LABEL_OPTIONS.items():
        for opt in options:
            if opt.name in added:
                # Another store's option of the same name
                added[
                    opt.name
                ].help = f"{added[opt.name].help}. Also used with --store {name}"
            else:
                added[opt.name] = opt.option
    first_shared = next(
        i for i, param in enumerate(collate_cmd.params) if param.name == "loop"
    )
    collate_cmd.params[first_shared:first_shared] = list(added.values())


def _refuse_other_stores_options(store_name: str) -> None:
    """Refuses a label option of another store given on the command line. From the
    environment, it is ignored, since the environment is shared with other stages,
    e.g. 'label folder'

    Raises
    ------
    click.UsageError
        if an option of another store is given on the command line
    """
    ctx = click.get_current_context()
    own = {opt.name for opt in STORE_LABEL_OPTIONS[store_name]}
    for name, options in STORE_LABEL_OPTIONS.items():
        for opt in options:
            if (
                opt.name not in own
                and ctx.get_parameter_source(opt.name)
                == click.core.ParameterSource.COMMANDLINE
            ):
                raise click.UsageError(
                    f"{opt.option.opts[0]} is a label option of --store {name}, not "
                    f"of --store {store_name}"
                )


STORE_LABEL_OPTIONS = _store_label_options()
_add_store_label_options()
