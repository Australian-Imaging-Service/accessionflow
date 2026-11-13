"""Support for keeping renamed options (and their environment variables) working as
hidden, deprecated aliases of their new names."""

import typing as ty

import click
from click.core import ParameterSource

T = ty.TypeVar("T")


def resolve_deprecated_alias(
    value: T,
    deprecated_value: T,
    *,
    param: str,
    deprecated_param: str,
) -> T:
    """Returns the value of an option that may have been given by its deprecated alias.

    The alias is a separate hidden option (with ``default=()`` or ``None``), so that its
    use can be detected and warned about. Giving both the option and its alias is an
    error, whether on the command line or in the environment.

    Parameters
    ----------
    value
        the value of the option under its new name
    deprecated_value
        the value of the deprecated alias
    param : str
        the name of the option's parameter, e.g. "accession_uid"
    deprecated_param : str
        the name of the alias's parameter, e.g. "accession_uid_deprecated"

    Returns
    -------
    the value to use
    """
    ctx = click.get_current_context()
    deprecated_source = ctx.get_parameter_source(deprecated_param)
    if deprecated_source in (None, ParameterSource.DEFAULT):
        return value
    new, old = (_param(ctx, n) for n in (param, deprecated_param))
    if deprecated_source is ParameterSource.ENVIRONMENT:
        used, instead = _envvar(old), _envvar(new)
    else:
        used, instead = _opt(old), _opt(new)
    if ctx.get_parameter_source(param) not in (None, ParameterSource.DEFAULT):
        raise click.UsageError(
            f"{used} is a deprecated alias of {_opt(new)} ({_envvar(new)}), so only "
            "one of them can be given",
            ctx=ctx,
        )
    click.echo(
        f"Warning: {used} is deprecated and will be removed in a future release, "
        f"use {instead} instead",
        err=True,
    )
    return deprecated_value


def _param(ctx: click.Context, name: str) -> click.Parameter:
    return next(p for p in ctx.command.params if p.name == name)


def _opt(param: click.Parameter) -> str:
    return max(param.opts, key=len)


def _envvar(param: click.Parameter) -> str:
    names = param.envvar
    if not names:
        return "no env. var"
    return f"{names if isinstance(names, str) else names[0]} env. var"
