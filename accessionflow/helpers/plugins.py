"""Discovery of the plugins in a namespace package, shared by the source plugins
(``accessionflow.sources``) and the store plugins (``accessionflow.stores``).

Each plugin is a subpackage of the namespace package. Its optional ``cli``
subpackage registers the plugin's subcommands when it is imported (see
:func:`load_cli_plugins`).
"""

import importlib
import pkgutil
import types
import warnings

_loaded: dict[str, dict[str, types.ModuleType | None]] = {}


def plugin_names(package: str) -> list[str]:
    """The names of the plugins installed in the given namespace package"""
    module = importlib.import_module(package)
    return sorted(
        info.name for info in pkgutil.iter_modules(module.__path__) if info.ispkg
    )


def get_plugin(package: str, name: str, kind: str) -> types.ModuleType:
    """Import the named plugin of the given namespace package

    Raises
    ------
    ValueError
        if no plugin of that name is installed
    """
    try:
        return importlib.import_module(f"{package}.{name}")
    except ModuleNotFoundError as e:
        if e.name != f"{package}.{name}":
            raise
        raise ValueError(
            f"No {kind} plugin named '{name}' is installed (installed: "
            f"{', '.join(plugin_names(package)) or 'none'})"
        ) from None


def load_cli_plugins(package: str, kind: str) -> dict[str, types.ModuleType | None]:
    """Import the 'cli' subpackage of each plugin in the namespace package once, so
    that the plugins can register their subcommands.

    A plugin that fails to import is skipped with a warning, so that one broken
    plugin does not stop the commands of the others from running.

    Parameters
    ----------
    package : str
        the namespace package the plugins are subpackages of
    kind : str
        what the plugins are, e.g. 'store', for the warnings

    Returns
    -------
    dict[str, types.ModuleType | None]
        the imported 'cli' subpackages by plugin name, None for plugins without one
    """
    if package not in _loaded:
        loaded: dict[str, types.ModuleType | None] = {}
        for name in plugin_names(package):
            module_name = f"{package}.{name}.cli"
            try:
                loaded[name] = importlib.import_module(module_name)
            except ModuleNotFoundError as e:
                if e.name != module_name:
                    warnings.warn(
                        f"Could not load the '{name}' {kind} plugin: {e}",
                        stacklevel=2,
                    )
                else:
                    loaded[name] = None
            except Exception as e:  # noqa: BLE001 - see docstring
                warnings.warn(
                    f"Could not load the '{name}' {kind} plugin: {e}",
                    stacklevel=2,
                )
        _loaded[package] = loaded
    return _loaded[package]
