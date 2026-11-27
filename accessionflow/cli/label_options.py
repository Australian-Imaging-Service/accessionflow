"""Label options:

- the store-neutral set, '--project', '--subject', '--session', '--scan' and
  '--constant-project-id', which 'collate folder' labels the accessions it collates
  with (see ``prefect-migration-docs/ROADMAP.md``, Phase 1, Store-neutral labels, N1)
- the label options of a store, e.g. XNAT's '--project', '--subject', '--session' and
  '--scan', or the folder store's '--level', which the 'label <store>' commands take
  until they become store-neutral (N3 and N4)
"""

import typing as ty

import attrs
import click

from accessionflow.model.store import Store, check_level_names

__all__ = [
    "LabelOptions",
    "NEUTRAL_LABEL_DEFAULTS",
    "NEUTRAL_LEVELS",
    "StoreLabelOption",
    "neutral_label_options",
    "neutral_labels",
    "resolve_label_options",
    "store_label_options",
]

# What each label option sets
Role = ty.Literal["level", "acquisition", "constant_top", "levels", "constant_labels"]


@attrs.frozen
class StoreLabelOption:
    """A label option of a store, and what it sets

    Parameters
    ----------
    role : str
        'level' (the field of one of the store's fixed levels), 'acquisition' (the field
        of an acquisition's description), 'constant_top' (a constant label for the top
        fixed level), 'levels' (the levels of a store without fixed levels, as name and
        field pairs) or 'constant_labels' (constant labels, as name and value pairs)
    option : click.Option
        the option
    level : str, optional
        the name of the level, for the 'level' role
    """

    role: Role
    option: click.Option
    level: str | None = None

    @property
    def name(self) -> str:
        """The name of the option's Python parameter"""
        return ty.cast(str, self.option.name)


@attrs.frozen
class LabelOptions:
    """The arguments of `assign_labels` given by a store's label options"""

    label_fields: dict[str, str]
    acquisition_field: str | None
    constant_labels: dict[str, str]


_FIELD_HELP = (
    "The keyword of the metadata field to extract the {what} from, or a Python format "
    "string over several fields, e.g. '{{PatientID}}_{{StudyDate:%Y%m%d}}', to compose "
    "one"
)


# The levels every accession is labelled with, from the top, whatever store it is
# going to, and the metadata fields they are made from by default, as for XNAT
NEUTRAL_LEVELS = ("project", "subject", "session")
NEUTRAL_LABEL_DEFAULTS = {
    "project": "StudyComments",
    "subject": "PatientID",
    "session": "AccessionNumber",
}
# The field each acquisition's description is made from by default
NEUTRAL_ACQUISITION_DEFAULT = "SeriesDescription"

_NEUTRAL_ENVVAR_PREFIX = "ACFLOW_"


def neutral_label_options(
    command: ty.Callable[..., ty.Any],
) -> ty.Callable[..., ty.Any]:
    """Adds the store-neutral label options to a command, with the names, environment
    variables and defaults of 'label xnat': '--project', '--subject' and '--session'
    (the fields the accession's labels are made from), '--scan' (the field each
    acquisition's description is made from) and '--constant-project-id'. The command
    takes them as the parameters 'project', 'subject', 'session', 'scan' and
    'constant_project_id', and turns them into labels with `neutral_labels`"""
    options = [
        click.option(
            f"--{level}",
            level,
            type=str,
            default=NEUTRAL_LABEL_DEFAULTS[level],
            envvar=f"{_NEUTRAL_ENVVAR_PREFIX}{level.upper()}",
            help=(
                _FIELD_HELP.format(what=f"accession's {level} label")
                + f" ({_NEUTRAL_ENVVAR_PREFIX}{level.upper()} env. var)"
            ),
        )
        for level in NEUTRAL_LEVELS
    ]
    options.append(
        click.option(
            "--scan",
            "scan",
            type=str,
            default=NEUTRAL_ACQUISITION_DEFAULT,
            envvar=f"{_NEUTRAL_ENVVAR_PREFIX}SCAN",
            help=(
                "The keyword of the metadata field to extract the description of each "
                "acquisition from. Acquisitions for which the field can't be resolved "
                f"are left without one ({_NEUTRAL_ENVVAR_PREFIX}SCAN env. var)"
            ),
        )
    )
    options.append(
        click.option(
            "--constant-project-id",
            "constant_project_id",
            type=str,
            default=None,
            envvar=f"{_NEUTRAL_ENVVAR_PREFIX}CONSTANT_PROJECT_ID",
            help=(
                "Fix the project label as a constant for all data matched by this "
                "command. It is saved in the accession's metadata as its 'project' "
                f"field ({_NEUTRAL_ENVVAR_PREFIX}CONSTANT_PROJECT_ID env. var)"
            ),
        )
    )
    # Applied in reverse, so that the help lists them in the order above
    for option in reversed(options):
        command = option(command)
    return command


def neutral_labels(
    project: str,
    subject: str,
    session: str,
    scan: str | None,
    constant_project_id: str | None = None,
) -> LabelOptions:
    """The labels the values of the store-neutral label options give
    (`neutral_label_options`)

    Parameters
    ----------
    project, subject, session : str
        the metadata field (or a format string over several fields) each label is made
        from
    scan : str, optional
        the metadata field each acquisition's description is made from
    constant_project_id : str, optional
        the project label, used as given

    Returns
    -------
    LabelOptions
        the label fields, the acquisition field and the constant labels
    """
    return LabelOptions(
        label_fields={"project": project, "subject": subject, "session": session},
        acquisition_field=scan,
        constant_labels=(
            {"project": constant_project_id} if constant_project_id is not None else {}
        ),
    )


def store_label_options(store: Store) -> list[StoreLabelOption]:
    """The label options of a store, which its 'label <store>' command takes

    If the store has fixed label levels, there is an option for each of them, e.g.
    '--project', '--subject' and '--session' for XNAT, and one for a constant label of
    the top level, e.g. '--constant-project-id'. Otherwise, the levels are named, in
    order from the top, with a repeatable '--level NAME FIELD' option, and constant
    labels with '--constant-label NAME VALUE'. If the store describes acquisitions,
    there is an option for the field of the description, e.g. '--scan'. Each option is
    settable by an environment variable named after it, e.g. 'ACFLOW_PROJECT'.

    Parameters
    ----------
    store : Store
        the configuration of the store

    Returns
    -------
    list[StoreLabelOption]
        the options, in the order they are listed in the help
    """
    prefix = store.envvar_prefix
    options: list[StoreLabelOption] = []

    def add(
        role: Role,
        option_name: str,
        envvar: str,
        param_name: str,
        help: str,
        default: str | None = None,
        level: str | None = None,
        **kwargs: ty.Any,
    ) -> None:
        # An explicit default of None would count as a value for 'required' in
        # click >= 8.3, so an option without a default is given none at all
        if default is not None:
            kwargs["default"] = default
        elif role == "constant_top":
            # As 'label <store>' has always declared it
            kwargs["default"] = None
        options.append(
            StoreLabelOption(
                role=role,
                level=level,
                option=click.Option(
                    [option_name, param_name],
                    envvar=envvar,
                    help=f"{help} ({envvar} env. var)",
                    **kwargs,
                ),
            )
        )

    fixed_levels = store.labels
    acquisition = store.acquisition
    if fixed_levels is not None:
        for i, level in enumerate(fixed_levels):
            add(
                "level",
                level.option_name,
                level.envvar(prefix),
                f"label_{i}",
                _FIELD_HELP.format(what=level.description or level.name),
                default=level.default,
                level=level.name,
                type=str,
                required=level.default is None,
            )
    else:
        envvar = f"{prefix}LEVELS"
        add(
            "levels",
            "--level",
            envvar,
            "levels",
            (
                "A level of the folder hierarchy the sessions are labelled with, "
                "and the keyword of the metadata field to extract its label from "
                "(or a Python format string over several fields, e.g. "
                "'{PatientID}_{StudyDate:%Y%m%d}'). Repeat for each level, in "
                "order from the top, e.g. '--level site SiteID --level subject "
                "PatientID'"
            ),
            type=(str, str),
            multiple=True,
            required=True,
            metavar="<name> <field>",
        )
        # The help of 'label folder' says how the pairs are given in the variable
        last = options[-1].option
        last.help = ty.cast(str, last.help).replace(
            " env. var)", " env. var, as space-separated pairs)"
        )
    if acquisition is not None:
        add(
            "acquisition",
            acquisition.option_name,
            acquisition.envvar(prefix),
            "acquisition_field",
            (
                "The keyword of the metadata field to extract the "
                f"{acquisition.description or 'description'} of each "
                f"{acquisition.name} from. {acquisition.name.capitalize()}s for "
                "which the field can't be resolved are left without one"
            ),
            default=acquisition.default,
            type=str,
        )
    if fixed_levels is not None:
        top = fixed_levels[0]
        add(
            "constant_top",
            f"--constant-{top.name}-id",
            f"{prefix}CONSTANT_{top.name.upper()}_ID",
            "constant_top_label",
            (
                f"Fix the {top.description or top.name} as a constant for all "
                "data matched by this command"
            ),
            type=str,
        )
    else:
        add(
            "constant_labels",
            "--constant-label",
            f"{prefix}CONSTANT_LABELS",
            "constant_label_pairs",
            (
                "Fix the label of a level given by --level as a constant for all "
                "data matched by this command, e.g. '--constant-label site "
                "SYDNEY'. May be repeated"
            ),
            type=(str, str),
            multiple=True,
            metavar="<name> <value>",
        )
    return options


def resolve_label_options(
    store: Store,
    options: ty.Sequence[StoreLabelOption],
    values: ty.Mapping[str, ty.Any],
) -> LabelOptions:
    """The labels the values of a store's label options give, with the store's
    defaults for the options that weren't given

    Parameters
    ----------
    store : Store
        the configuration of the store
    options : Sequence[StoreLabelOption]
        the store's label options, from `store_label_options`
    values : Mapping[str, Any]
        the values of the command's parameters, by name

    Returns
    -------
    LabelOptions
        the label fields, the acquisition field and the constant labels

    Raises
    ------
    click.UsageError
        if a level without a default isn't given a field, no levels are given to a store
        without fixed levels, or a constant label names a level that isn't given
    ValueError
        if the level names given by '--level' aren't usable (`check_level_names`)
    """
    label_fields: dict[str, str] = {}
    acquisition_field: str | None = None
    constant_labels: dict[str, str] = {}
    fixed_levels = {level.name: level for level in store.labels or ()}
    for opt in options:
        value = values.get(opt.name)
        if opt.role == "level":
            assert opt.level is not None
            field = value if value is not None else fixed_levels[opt.level].default
            if field is None:
                raise click.UsageError(
                    f"{opt.option.opts[0]} is needed to label for {store.title}"
                )
            label_fields[opt.level] = field
        elif opt.role == "acquisition":
            assert store.acquisition is not None
            acquisition_field = (
                value if value is not None else store.acquisition.default
            )
        elif opt.role == "constant_top":
            if value is not None:
                constant_labels[next(iter(fixed_levels))] = value
        elif opt.role == "levels":
            if not value:
                raise click.UsageError(
                    f"{opt.option.opts[0]} is needed to label for {store.title}"
                )
            names = [name for name, _ in value]
            check_level_names(
                store.name, names, store.acquisition.name if store.acquisition else None
            )
            label_fields = dict(value)
        elif opt.role == "constant_labels":
            constant_labels = dict(value or ())
    if store.labels is None and (unknown := set(constant_labels) - set(label_fields)):
        raise click.UsageError(
            f"--constant-label names {sorted(unknown)} that aren't levels "
            f"given by --level ({list(label_fields)})"
        )
    return LabelOptions(
        label_fields=label_fields,
        acquisition_field=acquisition_field,
        constant_labels=constant_labels,
    )
