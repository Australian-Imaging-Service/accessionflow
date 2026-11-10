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
from accessionflow.helpers.arg_types import Convert, LoggerConfig
from accessionflow.helpers.logging import logger, set_logger_handling

from ..api.collate_api import collate


@collate_group.command(
    name="orthanc",
    help="""Collates the DICOM studies held by an Orthanc server into accessions in a
staging directory, ready to be labelled. The files are hardlinked from Orthanc's
storage directory, so it must be on the same file system as the staging directory.

URL of the Orthanc instance to connect to (ACFLOW_ORTHANC_URL env. var)

STORE_DIR is the path to Orthanc's StorageDirectory as mounted
(ACFLOW_ORTHANC_STORE_DIR env. var)

OUTPUT_DIR is the staging directory the files of each accession are collated to

USER is the Orthanc user (ACFLOW_ORTHANC_USER env. var)

PASSWORD is the password of the Orthanc user (ACFLOW_ORTHANC_PASSWORD env. var)
""",
)
@click.argument("url", type=str, envvar="ACFLOW_ORTHANC_URL")
@click.argument(
    "store_dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    envvar="ACFLOW_ORTHANC_STORE_DIR",
)
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.argument("user", type=str, envvar="ACFLOW_ORTHANC_USER")
@click.argument("password", type=str, envvar="ACFLOW_ORTHANC_PASSWORD")
@click.option(
    "--to-process-label",
    type=str,
    default=None,
    envvar="ACFLOW_ORTHANC_TO_PROCESS",
    help=(
        "Label applied to Orthanc studies after staging to prevent re-processing. "
        "Can be removed via the Orthanc UI "
        "(ACFLOW_ORTHANC_TO_PROCESS env. var)"
    ),
)
@click.option(
    "--processed-label",
    type=str,
    default=None,
    envvar="ACFLOW_ORTHANC_PROCESSED",
    help=(
        "Label applied to Orthanc studies after staging to prevent re-processing. "
        "Can be removed via the Orthanc UI "
        "(ACFLOW_ORTHANC_PROCESSED env. var)"
    ),
)
@click.option(
    "--unlink-source",
    type=click.Choice(["all", "keep-metadata"]),
    default=None,
    envvar="ACFLOW_UNLINK_SOURCE",
    help=(
        "Whether to unlink the source studies in Orthanc after they have been "
        "successfully collated. Not yet implemented (ACFLOW_UNLINK_SOURCE env. var)"
    ),
)
@collate_options
def collate_cmd(
    url: str,
    store_dir: Path,
    output_dir: Path,
    user: str,
    password: str,
    processed_label: str | None,
    to_process_label: str | None,
    unlink_source: str | None,
    raise_errors: bool,
    loop: int,
    wait_period: int,
    copy_mode: FileSet.CopyMode,
    conversions: tuple[Convert, ...],
    loggers: ty.List[LoggerConfig],
    additional_loggers: ty.List[str],
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
        collate(
            url=url,
            store_dir=store_dir,
            output_dir=output_dir,
            user=user,
            password=password,
            processed_label=processed_label,
            to_process_label=to_process_label,
            unlink_source=unlink_source,
            raise_errors=raise_errors,
            copy_mode=copy_mode,
            wait_period=wait_period,
            conversion_map={c.source: (c.target, c.options) for c in conversions},
        )
        if loop < 0:
            break
        elapsed_seconds = time.monotonic() - start_time
        sleep_time = max(loop - elapsed_seconds, 0)
        logger.info(
            "Collating from Orthanc took %s seconds, waiting another %s seconds before "
            "running again (loop every %s seconds)",
            elapsed_seconds,
            sleep_time,
            loop,
        )
        time.sleep(sleep_time)
