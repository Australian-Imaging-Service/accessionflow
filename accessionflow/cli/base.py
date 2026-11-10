import typing as ty

import click

from accessionflow.helpers import __version__
from accessionflow.model.source import load_source_plugins, source_plugins
from accessionflow.model.store import load_store_plugins, store_plugins


@click.group(
    help="Collates, labels, deidentifies and uploads data exported from instruments "
    "to data stores"
)
@click.version_option(version=__version__)
def cli() -> None:
    pass


class PluginGroup(click.Group):
    """A stage with one subcommand per plugin, e.g. 'collate orthanc' for a source
    plugin or 'label xnat' for a store plugin.

    The subcommands are registered by the plugins, which are loaded the first time
    the group is asked for its subcommands.

    Parameters
    ----------
    kind : str
        what the plugins are, e.g. 'store', for the error messages
    package : str
        the namespace package the plugins are subpackages of
    load_plugins : callable
        imports the plugins' 'cli' subpackages so that they register their subcommands
    plugin_names : callable
        the names of the installed plugins
    """

    def __init__(
        self,
        *args: ty.Any,
        kind: str,
        package: str,
        load_plugins: ty.Callable[[], object],
        plugin_names: ty.Callable[[], list[str]],
        **kwargs: ty.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.kind = kind
        self.package = package
        self.load_plugins = load_plugins
        self.plugin_names = plugin_names

    def list_commands(self, ctx: click.Context) -> list[str]:
        self.load_plugins()
        return super().list_commands(ctx)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        self.load_plugins()
        return super().get_command(ctx, cmd_name)

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        if args and not args[0].startswith("-") and not ctx.resilient_parsing:
            if self.get_command(ctx, args[0]) is None:
                if args[0] in self.plugin_names():
                    hint = (
                        f"the '{args[0]}' {self.kind} plugin does not provide a "
                        f"'{self.name}' command"
                    )
                else:
                    hint = (
                        f"no {self.kind} plugin named '{args[0]}' is installed. "
                        f"{self.kind.capitalize()} plugins are subpackages of "
                        f"'{self.package}', e.g. '{self.package}.{args[0]}'"
                    )
                available = ", ".join(self.list_commands(ctx)) or "none"
                ctx.fail(
                    f"Cannot run '{self.name} {args[0]}': {hint} ({self.kind}s "
                    f"available for '{self.name}': {available})"
                )
        return super().resolve_command(ctx, args)


def data_store_group(name: str, help: str) -> PluginGroup:
    """Add a stage to the CLI whose subcommands are provided by store plugins"""
    group = PluginGroup(
        name=name,
        help=f"{help}\n\nRun 'accessionflow {name} <data-store> --help' for the "
        "options for each data store.",
        kind="store",
        package="accessionflow.stores",
        load_plugins=load_store_plugins,
        plugin_names=store_plugins,
    )
    cli.add_command(group)
    return group


def source_group(name: str, help: str) -> PluginGroup:
    """Add a stage to the CLI whose subcommands are provided by source plugins"""
    group = PluginGroup(
        name=name,
        help=f"{help}\n\nRun 'accessionflow {name} <source> --help' for the "
        "options for each source.",
        kind="source",
        package="accessionflow.sources",
        load_plugins=load_source_plugins,
        plugin_names=source_plugins,
    )
    cli.add_command(group)
    return group
