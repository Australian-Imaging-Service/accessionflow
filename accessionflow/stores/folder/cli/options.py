"""Options shared by 'store folder' and 'check-store folder'"""

import typing as ty
from pathlib import Path

import click

from accessionflow.helpers.arg_types import LoggerConfig, StoreCredentials
from accessionflow.helpers.remote_fs import parse_storage_options

# The name the folder store's commands use
storage_options = parse_storage_options


def common_options(func: ty.Callable[..., None]) -> ty.Callable[..., None]:
    decorators = [
        click.argument("staged", type=str, envvar="ACFLOW_STAGED"),
        click.argument("dest", type=str, envvar="ACFLOW_DEST"),
        click.option(
            "--storage-option",
            "storage_option_pairs",
            type=(str, str),
            multiple=True,
            metavar="<key> <value>",
            envvar="ACFLOW_STORAGE_OPTIONS",
            help=(
                "An option for the fsspec file system of the store, e.g. "
                "'--storage-option anon true' or '--storage-option key <access-key>'. "
                "Values that are JSON are decoded. May be repeated "
                "(ACFLOW_STORAGE_OPTIONS env. var, as space-separated pairs)"
            ),
        ),
        click.option(
            "--require-manifest/--dont-require-manifest",
            default=True,
            envvar="ACFLOW_REQUIRE_MANIFEST",
            help=(
                "Whether the staged resources must have manifests. If not, the "
                "checksums of resources without one are worked out from their files "
                "(ACFLOW_REQUIRE_MANIFEST env. var)"
            ),
        ),
        click.option(
            "--store-credentials",
            type=StoreCredentials.cli_type,
            metavar="<access-key> <secret-key>",
            envvar="ACFLOW_STORE_CREDENTIALS",
            default=None,
            nargs=2,
            help=(
                "Credentials of the S3 bucket the accessions are staged in, if STAGED "
                "is one (ACFLOW_STORE_CREDENTIALS env. var)"
            ),
        ),
        click.option(
            "--temp-dir",
            type=Path,
            default=None,
            envvar="ACFLOW_TEMPDIR",
            help="The directory to download accessions staged in S3 to",
        ),
        click.option(
            "--s3-max-workers",
            type=click.IntRange(min=1),
            default=None,
            envvar="ACFLOW_S3_MAX_WORKERS",
            help=(
                "The number of files to download from an S3 staging bucket at once "
                "(ACFLOW_S3_MAX_WORKERS env. var)"
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
            help="Setup handles to capture logs that are generated (ACFLOW_LOGGERS env. var)",
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
            help="Whether to raise errors instead of logging them (typically for debugging)",
        ),
    ]
    for decorator in reversed(decorators):
        func = decorator(func)
    return func
