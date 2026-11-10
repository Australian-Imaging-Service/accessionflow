"""Configuration that a source plugin provides to the 'collate' stage.

Each source plugin is a subpackage of the ``accessionflow.sources`` namespace
package, e.g. ``accessionflow.sources.orthanc``, which defines a ``SOURCE``
attribute holding a :class:`Source`. Its optional ``cli`` subpackage registers the
plugin's ``collate <source>`` subcommand when it is imported (see
:func:`load_source_plugins`).
"""

import types
import typing as ty

import attrs

from accessionflow.helpers.plugins import get_plugin, load_cli_plugins, plugin_names

PLUGINS_PACKAGE = "accessionflow.sources"


@attrs.frozen
class Source:
    """Where the files that are collated into accessions come from.

    Parameters
    ----------
    name : str
        the plugin name, used as the subcommand name, e.g. 'orthanc' for
        'collate orthanc'
    title : str
        the name of the source for help text, e.g. 'Orthanc'
    """

    name: str
    title: str


def source_plugins() -> list[str]:
    """The names of the source plugins that are installed"""
    return plugin_names(PLUGINS_PACKAGE)


def get_source(name: str) -> Source:
    """The configuration of the named source plugin"""
    return ty.cast(Source, get_plugin(PLUGINS_PACKAGE, name, "source").SOURCE)


def load_source_plugins() -> dict[str, types.ModuleType | None]:
    """Import the 'cli' subpackage of each source plugin once, so that the
    plugins can register their subcommands (see
    :func:`accessionflow.helpers.plugins.load_cli_plugins`)"""
    return load_cli_plugins(PLUGINS_PACKAGE, "source")
