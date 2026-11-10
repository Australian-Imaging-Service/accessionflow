"""Configuration that a store plugin provides to the store-neutral stages.

Each store plugin is a subpackage of the ``accessionflow.stores``
namespace package, e.g. ``accessionflow.stores.xnat``, which defines a
``STORE`` attribute holding a :class:`Store`. Its optional ``cli``
subpackage registers the plugin's subcommands, e.g. ``label xnat``, when it is
imported (see :func:`load_store_plugins`).
"""

import types
import typing as ty

import attrs

from accessionflow.helpers.plugins import get_plugin, load_cli_plugins, plugin_names

PLUGINS_PACKAGE = "accessionflow.stores"


@attrs.frozen
class LabelLevel:
    """A level of a store's hierarchy that a session is labelled with, or the
    store's name for an acquisition within the session.

    Parameters
    ----------
    name : str
        the store's name for the level, which names its command-line option
        (e.g. 'project' gives '--project') and environment variable
        (e.g. 'ACFLOW_PROJECT')
    default : str, optional
        the metadata field, or a format string over several fields, that the label is
        extracted from by default
    description : str
        what the label is in the store's terms, for the help text, e.g.
        'XNAT project ID'
    """

    name: str
    default: str | None = None
    description: str = ""

    @property
    def option_name(self) -> str:
        return "--" + self.name.replace("_", "-")

    def envvar(self, prefix: str) -> str:
        return prefix + self.name.upper().replace("-", "_")


def check_level_names(
    store_name: str, level_names: ty.Sequence[str], acquisition_name: str | None = None
) -> None:
    """Check a store's label level names, and its name for an acquisition, are usable

    Raises
    ------
    ValueError
        if there are no levels, or a name is repeated or isn't a valid identifier
    """
    if not level_names:
        raise ValueError(f"Store '{store_name}' needs at least one label level")
    names = list(level_names)
    if acquisition_name is not None:
        names.append(acquisition_name)
    if len(set(names)) != len(names):
        raise ValueError(f"Store '{store_name}' has repeated label names: {names}")
    if invalid := [n for n in names if not n.replace("-", "_").isidentifier()]:
        raise ValueError(
            f"Store '{store_name}' has label names that aren't valid identifiers: "
            f"{invalid}"
        )


def _check_labels(
    data_store: "Store", attribute: ty.Any, labels: tuple[LabelLevel, ...] | None
) -> None:
    if labels is not None:
        check_level_names(
            data_store.name,
            [level.name for level in labels],
            data_store.acquisition.name if data_store.acquisition else None,
        )


@attrs.frozen
class Store:
    """How sessions are labelled for, and named within, a store.

    Parameters
    ----------
    name : str
        the plugin name, used as the subcommand name, e.g. 'xnat' for 'label xnat'
    title : str
        the name of the store for help text, e.g. 'XNAT'
    labels : tuple[LabelLevel, ...] or None
        the levels of the store's hierarchy, from the top, e.g. XNAT's project,
        subject and session. A labelled session is saved in a folder named by its
        labels joined by '.', in this order, and 'deidentify' selects recipes by the
        first label. None if the store has no fixed hierarchy, in which case the levels
        are named when labelling (with 'label <store> --level NAME FIELD ...')
    acquisition : LabelLevel, optional
        the store's name for an acquisition, and the metadata field to describe
        each one by, e.g. XNAT's 'scan' described by 'SeriesDescription'. None if the
        store does not describe acquisitions
    multiple_resources : bool
        whether an acquisition can hold more than one resource (e.g. the DICOM files
        and a NIfTI conversion of them), as XNAT scans can. If False, each acquisition
        must hold exactly one, which 'label' checks
    envvar_prefix : str
        the prefix of the environment variables that the options can be set by
    """

    name: str
    title: str
    labels: tuple[LabelLevel, ...] | None = attrs.field(validator=_check_labels)
    acquisition: LabelLevel | None = None
    multiple_resources: bool = True
    envvar_prefix: str = "ACFLOW_"


def store_plugins() -> list[str]:
    """The names of the store plugins that are installed"""
    return plugin_names(PLUGINS_PACKAGE)


def get_store(name: str) -> Store:
    """The configuration of the named store plugin"""
    return ty.cast(Store, get_plugin(PLUGINS_PACKAGE, name, "store").STORE)


def load_store_plugins() -> dict[str, types.ModuleType | None]:
    """Import the 'cli' subpackage of each store plugin once, so that the
    plugins can register their subcommands (see
    :func:`accessionflow.helpers.plugins.load_cli_plugins`)"""
    return load_cli_plugins(PLUGINS_PACKAGE, "store")
