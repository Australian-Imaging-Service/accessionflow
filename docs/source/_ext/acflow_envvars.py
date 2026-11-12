"""A Sphinx directive that lists the environment variables every AccessionFlow
command reads, generated from the click commands so that it can't drift from them.

Usage::

    .. acflow-envvars::
"""

import typing as ty

import click
from docutils import nodes
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective


def _commands(
    group: click.Group, ctx: click.Context, prefix: str
) -> ty.Iterator[tuple[str, click.Command]]:
    for name in group.list_commands(ctx):
        command = group.get_command(ctx, name)
        if command is None or command.hidden:
            continue
        path = f"{prefix} {name}"
        if isinstance(command, click.Group):
            yield from _commands(command, click.Context(command, parent=ctx), path)
        else:
            yield path, command


def collect() -> dict[str, dict[str, list[str]]]:
    """The environment variables read by the CLI, with the commands that read each
    one, by the option or argument it sets in them"""
    from accessionflow.cli import cli

    ctx = click.Context(cli)
    envvars: dict[str, dict[str, list[str]]] = {}
    for path, command in _commands(cli, ctx, "accessionflow"):
        for param in command.params:
            if getattr(param, "hidden", False):  # e.g. deprecated aliases
                continue
            names = param.envvar
            if not names:
                continue
            if isinstance(names, str):
                names = [names]
            if isinstance(param, click.Argument):
                option = (param.human_readable_name or param.name or "").upper()
            else:
                option = max(param.opts, key=len)
            for name in names:
                commands = envvars.setdefault(name, {}).setdefault(option, [])
                commands.append(path.removeprefix("accessionflow "))
    return dict(sorted(envvars.items()))


def _cell(*children: nodes.Node) -> nodes.entry:
    entry = nodes.entry()
    paragraph = nodes.paragraph()
    for child in children:
        paragraph += child
    entry += paragraph
    return entry


class EnvVarsDirective(SphinxDirective):
    has_content = False

    def run(self) -> list[nodes.Node]:
        table = nodes.table(classes=["acflow-envvars"])
        tgroup = nodes.tgroup(cols=2)
        table += tgroup
        tgroup += nodes.colspec(colwidth=35)
        tgroup += nodes.colspec(colwidth=65)
        thead = nodes.thead()
        row = nodes.row()
        for header in ("Variable", "Sets"):
            entry = nodes.entry()
            entry += nodes.paragraph(text=header)
            row += entry
        thead += row
        tgroup += thead
        tbody = nodes.tbody()
        for name, options in collect().items():
            row = nodes.row()
            entry = nodes.entry()
            entry += nodes.paragraph("", "", nodes.literal(text=name))
            row += entry
            entry = nodes.entry()
            for option, commands in options.items():
                paragraph = nodes.paragraph()
                paragraph += nodes.literal(text=option)
                paragraph += nodes.Text(" of ")
                for i, command in enumerate(sorted(set(commands))):
                    if i:
                        paragraph += nodes.Text(", ")
                    paragraph += nodes.literal(text=command)
                entry += paragraph
            row += entry
            tbody += row
        tgroup += tbody
        return [table]


def setup(app: Sphinx) -> dict[str, ty.Any]:
    app.add_directive("acflow-envvars", EnvVarsDirective)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
