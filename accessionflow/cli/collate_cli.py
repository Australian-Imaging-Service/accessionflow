"""The 'collate' stage, whose subcommands are provided by the source plugins, e.g.
'collate folder' and 'collate orthanc', and the options they all share"""

import functools
import typing as ty

import click
from fileformats.core import FileSet

from accessionflow.helpers.arg_types import Convert, CopyModeParamType, LoggerConfig

from .base import source_group

collate_group = source_group(
    name="collate",
    help=(
        "Collates files from a source into accessions, acquisitions and resources in a "
        "staging directory. 'collate folder' also labels them with a project, subject "
        "and session; the accessions of other sources are labelled by the 'label' stage"
    ),
)


WAIT_PERIOD_HELP = (
    "The number of seconds since an accession was last modified at the "
    "source before it is collated, so that accessions that are still being "
    "transferred aren't collated partially (ACFLOW_WAIT_PERIOD env. var)"
)


def collate_options(
    func: ty.Callable[..., None] | None = None,
    *,
    wait_period_help: str = WAIT_PERIOD_HELP,
) -> ty.Any:
    """The options shared by the 'collate <source>' subcommands

    Used as ``@collate_options``, or as ``@collate_options(wait_period_help=...)`` by a
    source whose '--wait-period' means something else, e.g. the combiner's quiet period
    in 'collate folder'
    """
    if func is None:
        return functools.partial(collate_options, wait_period_help=wait_period_help)
    decorators = [
        click.option(
            "--loop",
            type=int,
            default=-1,
            envvar="ACFLOW_LOOP",
            help=(
                "Run the collation continuously every LOOP seconds (ACFLOW_LOOP env. var)"
            ),
        ),
        click.option(
            "--wait-period",
            type=click.IntRange(min=0),
            default=0,
            envvar="ACFLOW_WAIT_PERIOD",
            help=wait_period_help,
        ),
        click.option(
            "--copy-mode",
            type=CopyModeParamType(),
            default=FileSet.CopyMode.hardlink_or_copy,
            envvar="ACFLOW_COPY_MODE",
            help="The method to use for copying files (ACFLOW_COPY_MODE env. var)",
        ),
        click.option(
            "--convert",
            "conversions",
            type=Convert.cli_type,
            metavar="<src-mime-like> <tgt-spec>",
            nargs=2,
            multiple=True,
            default=(),
            envvar="ACFLOW_CONVERT",
            help=(
                "Convert resources of <src-mime-like> to <tgt-spec> during collation. "
                "<tgt-spec> may be either '<tgt-mime-like>' or "
                "'<tgt-mime-like>:key=value[,key=value...]', e.g. "
                "'application/zip:compression=ZIP_STORED' (ACFLOW_CONVERT env. var)"
            ),
        ),
        click.option(
            "--logger",
            "loggers",
            multiple=True,
            type=LoggerConfig.cli_type,
            envvar="ACFLOW_LOGGERS",
            nargs=3,
            default=(),
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
            default=(),
            envvar="ACFLOW_ADDITIONAL_LOGGERS",
            help=(
                "Additional loggers to capture the logs of, besides 'accessionflow' "
                "(e.g. 'xnat') (ACFLOW_ADDITIONAL_LOGGERS env. var)"
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
