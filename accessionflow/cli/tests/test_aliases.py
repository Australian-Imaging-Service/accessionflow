import click
import pytest
from click.testing import CliRunner

from accessionflow.cli.aliases import resolve_deprecated_alias


@click.command()
@click.option(
    "--new", "value", multiple=True, default=("default",), envvar="ACFLOW_NEW"
)
@click.option(
    "--old",
    "value_deprecated",
    multiple=True,
    default=(),
    envvar="ACFLOW_OLD",
    hidden=True,
)
def cmd(value: tuple[str, ...], value_deprecated: tuple[str, ...]) -> None:
    value = resolve_deprecated_alias(
        value, value_deprecated, param="value", deprecated_param="value_deprecated"
    )
    click.echo(",".join(value))


@pytest.mark.parametrize(
    "args, env, expected, warning",
    [
        ([], {}, "default", None),
        (["--new", "a"], {}, "a", None),
        ([], {"ACFLOW_NEW": "a"}, "a", None),
        (["--old", "a"], {}, "a", "--old is deprecated"),
        ([], {"ACFLOW_OLD": "a"}, "a", "ACFLOW_OLD env. var is deprecated"),
    ],
)
def test_deprecated_alias(args, env, expected, warning):
    result = CliRunner().invoke(cmd, args, env=env)
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == expected
    if warning:
        assert warning in result.stderr
        assert "use --new instead" in result.stderr or "use ACFLOW_NEW" in result.stderr
    else:
        assert "deprecated" not in result.stderr


@pytest.mark.parametrize(
    "args, env",
    [
        (["--new", "a", "--old", "b"], {}),
        ([], {"ACFLOW_NEW": "a", "ACFLOW_OLD": "b"}),
        (["--new", "a"], {"ACFLOW_OLD": "b"}),
    ],
)
def test_deprecated_alias_with_new_is_error(args, env):
    result = CliRunner().invoke(cmd, args, env=env)
    assert result.exit_code == 2
    assert "deprecated alias of --new" in result.output


def test_deprecated_aliases_hidden_from_help():
    from accessionflow.sources.folder.cli.collate_cli import collate_cmd

    help_text = CliRunner().invoke(collate_cmd, ["--help"]).output
    assert "--accession " in help_text and "--acquisition " in help_text
    assert "--accession-uid" not in help_text and "--acquisition-id" not in help_text
