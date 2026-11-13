import time
import typing as ty
from pathlib import Path

import click

from accessionflow.api.push_api import (
    Compatibility,
    DestinationUnreachable,
    check_push,
    push,
)
from accessionflow.helpers.arg_types import LoggerConfig
from accessionflow.helpers.logging import logger, set_logger_handling
from accessionflow.helpers.remote_fs import parse_storage_options

from .base import cli


def _destination_options(func: ty.Callable[..., None]) -> ty.Callable[..., None]:
    """The arguments and options shared by 'push' and 'check-push'"""
    decorators = [
        click.argument(
            "staged",
            type=click.Path(path_type=Path, exists=True, file_okay=False),
            envvar="ACFLOW_STAGED",
        ),
        click.argument("dest", type=str, envvar="ACFLOW_DEST"),
        click.option(
            "--storage-option",
            "storage_option_pairs",
            type=(str, str),
            multiple=True,
            metavar="<key> <value>",
            envvar="ACFLOW_STORAGE_OPTIONS",
            help=(
                "An option for the fsspec file system of the destination, e.g. "
                "'--storage-option anon true', '--storage-option key <access-key>' or "
                "'--storage-option endpoint_url https://s3.example.org'. Values that "
                "are JSON are decoded. May be repeated (ACFLOW_STORAGE_OPTIONS env. "
                "var, as space-separated pairs)"
            ),
        ),
        click.option(
            "--logger",
            "loggers",
            multiple=True,
            type=LoggerConfig.cli_type,
            envvar="ACFLOW_LOGGERS",
            nargs=3,
            default=[],
            metavar="<logtype> <loglevel> <location>",
            help=(
                "Setup handles to capture logs that are generated (ACFLOW_LOGGERS env. "
                "var)"
            ),
        ),
        click.option(
            "--additional-logger",
            "additional_loggers",
            type=str,
            multiple=True,
            default=[],
            envvar="ACFLOW_ADDITIONAL_LOGGERS",
            help=(
                "Additional loggers to capture the logs of, besides 'accessionflow' "
                "(e.g. 's3fs') (ACFLOW_ADDITIONAL_LOGGERS env. var)"
            ),
        ),
        click.option(
            "--raise-errors/--dont-raise-errors",
            default=False,
            type=bool,
            help=(
                "Whether to raise errors instead of logging them (typically for "
                "debugging)"
            ),
        ),
    ]
    for decorator in reversed(decorators):
        func = decorator(func)
    return func


@cli.command(
    name="push",
    help="""Copies the accessions in a staging directory, as they are, to a staging
directory on another file system, e.g. an S3 bucket that a central node reads them
from with 'store xnat s3://...'.

STAGED is the staging directory, e.g. the output of 'label' or 'deidentify'.

DEST is the staging directory to copy them to, a path or an fsspec URL, e.g.
's3://bucket/staged' or 'sftp://host/staged'. Remote file systems need their fsspec
package installed, e.g. 'accessionflow[s3]' for S3 or 'accessionflow[ssh]' for SFTP.

Each accession is copied to DEST/<accession>/, metadata and manifests included. A
resource's manifest is written after its files, and the accession's metadata after
everything else. A resource whose manifest and file sizes at the destination match
the staged ones is skipped, so pushing again only copies what is missing, incomplete
or changed. Nothing is deleted: not the staged accessions, and nothing at the
destination except the files of a resource being replaced by a changed one.
""",
)
@_destination_options
@click.option(
    "--wait-period",
    type=click.IntRange(min=0),
    default=0,
    envvar="ACFLOW_WAIT_PERIOD",
    help=(
        "The number of seconds since anything in an accession was last modified before "
        "it is pushed (ACFLOW_WAIT_PERIOD env. var)"
    ),
)
@click.option(
    "--loop",
    type=int,
    default=-1,
    envvar="ACFLOW_LOOP",
    help="Run continuously, every LOOP seconds (ACFLOW_LOOP env. var)",
)
@click.option(
    "--probe-attempts",
    type=click.IntRange(min=1),
    default=12,
    envvar="ACFLOW_PROBE_ATTEMPTS",
    help=(
        "The number of times to try listing the destination, 5 seconds apart, before "
        "giving up when the command starts (ACFLOW_PROBE_ATTEMPTS env. var)"
    ),
)
@click.option(
    "--marker-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    envvar="ACFLOW_PUSH_MARKER_DIR",
    help=(
        "For compatibility with ais-edge's reclaimer: write a marker here for each "
        "accession once it has been pushed, holding a fingerprint of its staged files, "
        "and skip an accession whose marker matches it without checking the "
        "destination (ACFLOW_PUSH_MARKER_DIR env. var)"
    ),
)
@click.option(
    "--marker-root",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    envvar="ACFLOW_PUSH_MARKER_ROOT",
    help=(
        "The directory the stage directories are in, searched before a marker is "
        "removed: a marker is removed once no stage holds its accession. Defaults to "
        "the parent of STAGED (ACFLOW_PUSH_MARKER_ROOT env. var)"
    ),
)
@click.option(
    "--recopy-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    envvar="ACFLOW_PUSH_RECOPY_DIR",
    help=(
        "For compatibility with ais-edge's reclaimer: a directory where it asks for an "
        "accession to be copied again in full, with a file named after it "
        "(ACFLOW_PUSH_RECOPY_DIR env. var)"
    ),
)
@click.option(
    "--lock-file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    envvar="ACFLOW_PUSH_LOCK_FILE",
    help=(
        "For compatibility with ais-edge's reclaimer: a lock file to hold, with flock, "
        "while each accession is copied (ACFLOW_PUSH_LOCK_FILE env. var)"
    ),
)
@click.option(
    "--lock-wait",
    type=click.IntRange(min=0),
    default=600,
    envvar="ACFLOW_PUSH_LOCK_WAIT",
    help=(
        "The number of seconds to wait for --lock-file before skipping the accession "
        "until the next pass (ACFLOW_PUSH_LOCK_WAIT env. var)"
    ),
)
def push_cmd(
    staged: Path,
    dest: str,
    storage_option_pairs: ty.Sequence[tuple[str, str]],
    loggers: ty.List[LoggerConfig],
    additional_loggers: ty.List[str],
    raise_errors: bool,
    wait_period: int,
    loop: int,
    probe_attempts: int,
    marker_dir: Path | None,
    marker_root: Path | None,
    recopy_dir: Path | None,
    lock_file: Path | None,
    lock_wait: int,
) -> None:
    if raise_errors and loop >= 0:
        raise ValueError(
            "Cannot use --raise-errors and --loop together as the loop will "
            "continue to run even if an error occurs"
        )
    set_logger_handling(logger_configs=loggers, additional_loggers=additional_loggers)
    options = parse_storage_options(storage_option_pairs)
    compatibility = Compatibility(
        marker_dir=marker_dir,
        marker_root=marker_root,
        recopy_dir=recopy_dir,
        lock_file=lock_file,
        lock_wait=lock_wait,
    )
    first_pass = True
    while True:
        start_time = time.monotonic()
        attempts = probe_attempts if first_pass else 1
        for attempt in range(1, attempts + 1):
            try:
                push(
                    input_dir=staged,
                    dest=dest,
                    storage_options=options,
                    wait_period=wait_period,
                    raise_errors=raise_errors,
                    compatibility=compatibility,
                )
                break
            except DestinationUnreachable as e:
                if attempt < attempts:
                    logger.warning(
                        "%s, trying again in 5 seconds (%d/%d)", e, attempt, attempts
                    )
                    time.sleep(5)
                elif first_pass:
                    raise click.ClickException(
                        f"{e}, after {attempts} attempts — refusing to start pushing"
                    ) from e
                else:
                    logger.error("%s, trying again on the next pass", e)
        first_pass = False
        if loop < 0:
            break
        elapsed_seconds = time.monotonic() - start_time
        sleep_time = max(loop - elapsed_seconds, 0)
        logger.info(
            "Pushing took %s seconds, waiting another %s seconds before running "
            "again (loop every %s seconds)",
            elapsed_seconds,
            sleep_time,
            loop,
        )
        time.sleep(sleep_time)


@cli.command(
    name="check-push",
    help="""Checks the copies that 'push' made of the accessions in a staging directory,
and logs every resource that is missing, incomplete or different at the destination.
Exits with a non-zero status if there are any.

STAGED is the staging directory the accessions were pushed from.

DEST is the staging directory they were pushed to, a path or an fsspec URL.
""",
)
@_destination_options
@click.option(
    "--checksums/--sizes-only",
    default=True,
    envvar="ACFLOW_CHECK_CHECKSUMS",
    help=(
        "Whether to check the files' checksums, which reads every file back from the "
        "destination, or only compare their sizes, which is much cheaper "
        "(ACFLOW_CHECK_CHECKSUMS env. var)"
    ),
)
def check_push_cmd(
    staged: Path,
    dest: str,
    storage_option_pairs: ty.Sequence[tuple[str, str]],
    loggers: ty.List[LoggerConfig],
    additional_loggers: ty.List[str],
    raise_errors: bool,
    checksums: bool,
) -> None:
    set_logger_handling(logger_configs=loggers, additional_loggers=additional_loggers)
    problems = check_push(
        input_dir=staged,
        dest=dest,
        storage_options=parse_storage_options(storage_option_pairs),
        checksums=checksums,
        raise_errors=raise_errors,
    )
    if problems:
        raise click.ClickException(
            f"{len(problems)} problem(s) found with what was pushed to '{dest}'"
        )
