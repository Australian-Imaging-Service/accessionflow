"""Combining the run accessions of a session into one accession, once no new run
accession has arrived for it for a quiet period (see ``prefect-migration-docs/ROADMAP.md``,
Phase 1, Combine)

Each collate run delivers a run accession per project.subject.session it found files
for, named ``<labels>_<run_uid>``, into a run-accessions directory. The combiner groups
them by their labels, and once a group's newest run accession is older than the quiet
period, it combines the group into one accession, ``<labels>_<primary_label>``, in the
output directory, and removes the run accessions.
"""

import json
import shutil
import typing as ty
from datetime import UTC, datetime, timedelta
from pathlib import Path

import attrs
from fileformats.core import FileSet

from accessionflow.helpers.arg_types import ClashSpec, OnResourceClash
from accessionflow.helpers.logging import logger
from accessionflow.helpers.metadata import Metadata, _values_equal
from accessionflow.helpers.run_uid import (
    PRIMARY_LABEL_RE,
    RUN_UID_RE,
    run_uid_time,
    split_run_uid,
)
from accessionflow.model.accession import Accession

from .claim import write_error_record

__all__ = [
    "COMBINED_FROM_KEY",
    "RUNS_NAME_DEFAULT",
    "RunAccessionGroup",
    "abandon_group",
    "check_primary_label",
    "combine_accessions",
    "deliver_combined",
    "list_run_accessions",
    "remove_run_accessions",
    "select_quiet_groups",
]

# The metadata key a combined accession records the names of its run accessions under
COMBINED_FROM_KEY = "__combined_from__"

# The subdirectory of the output directory that the CLI delivers the run accessions to
# by default, for the combiner. Later stages don't see it, because list_session_dirs
# skips directories whose names start with '__'
RUNS_NAME_DEFAULT = "__runs__"


@attrs.frozen
class RunAccessionGroup:
    """The run accessions of one project.subject.session, as listed by
    `list_run_accessions`. The unit a flow maps the combine over

    Attributes
    ----------
    name : str
        the labels joined by '.', e.g. ``P.S.V1``
    run_dirs : tuple[Path, ...]
        the run accessions' directories, oldest first
    newest : datetime
        the time of the newest run accession's run UID, in UTC
    """

    name: str
    run_dirs: tuple[Path, ...] = attrs.field(converter=tuple)
    newest: datetime


def check_primary_label(primary_label: str) -> None:
    """Checks the primary label that names the combined accessions,
    ``<labels>_<primary_label>``

    Raises
    ------
    ValueError
        if it isn't letters, digits and '-' (starting with a letter or digit), so that
        it can't be confused with the labels, or if it is in the form of a run UID, so
        that a combined accession can't be taken for a run accession
    """
    if not PRIMARY_LABEL_RE.fullmatch(primary_label):
        raise ValueError(
            f"Primary label '{primary_label}' must be letters, digits and '-', "
            "starting with a letter or digit"
        )
    if RUN_UID_RE.fullmatch(primary_label):
        raise ValueError(
            f"Primary label '{primary_label}' can't be in the form of a run UID"
        )


def list_run_accessions(runs_dir: Path) -> list[RunAccessionGroup]:
    """Lists the run accessions in the run-accessions directory, grouped by their
    labels

    A run accession is a directory named ``<labels>_<run_uid>``. Hidden directories,
    directories whose names start with ``__`` (e.g. the build directories), and any
    other entries are skipped.

    Parameters
    ----------
    runs_dir : Path
        the run-accessions directory, which collate delivers to

    Returns
    -------
    list[RunAccessionGroup]
        a group per labels, sorted by name, each with its run accessions oldest first.
        Empty if the directory doesn't exist
    """
    runs_dir = Path(runs_dir)
    if not runs_dir.exists():
        return []
    by_name: dict[str, list[tuple[datetime, Path]]] = {}
    for entry in sorted(runs_dir.iterdir()):
        if entry.name.startswith((".", "__")) or not entry.is_dir():
            continue
        name, run_uid = split_run_uid(entry.name)
        if run_uid is None:
            logger.debug("Skipping '%s', which isn't a run accession", entry)
            continue
        by_name.setdefault(name, []).append((run_uid_time(run_uid), entry))
    groups = []
    for name, runs in sorted(by_name.items()):
        runs.sort()
        groups.append(
            RunAccessionGroup(
                name=name, run_dirs=[p for _, p in runs], newest=runs[-1][0]
            )
        )
    return groups


def select_quiet_groups(
    groups: ty.Sequence[RunAccessionGroup],
    quiet_period: timedelta,
    now: datetime | None = None,
) -> list[RunAccessionGroup]:
    """Selects the groups that have had no new run accession for the quiet period

    The time of a run accession is the time in its run UID, when its collate run
    started, not a file's modification time, so it doesn't depend on the file system,
    and a retried delivery doesn't reset it.

    Parameters
    ----------
    groups : Sequence[RunAccessionGroup]
        the groups, from `list_run_accessions`
    quiet_period : timedelta
        how long a group must have had no new run accession
    now : datetime, optional
        the current time, by default now. A naive time is taken as local time

    Returns
    -------
    list[RunAccessionGroup]
        the quiet groups, in the same order
    """
    now = datetime.now(UTC) if now is None else now.astimezone(UTC)
    cutoff = now - quiet_period
    return [g for g in groups if g.newest <= cutoff]


def combine_accessions(
    group: RunAccessionGroup,
    on_resource_clash: OnResourceClash | ty.Sequence[ClashSpec] = "error",
) -> Accession:
    """Combines a group's run accessions into one accession, in memory

    The combined accession starts from the oldest run accession's labels, UID and
    fields, and has no run UID. The resources of every run accession are added
    to it in turn, oldest first (`Accession.add_resource`), so a resource that is
    identical to one already added (the same checksums) is skipped, and any other clash
    is resolved by ``on_resource_clash``. The names of the run accessions are recorded
    in its metadata, under `COMBINED_FROM_KEY`.

    The metadata each level holds of its own (e.g. from a metadata table), rather than
    collated from the level below it, is carried over. A key that two run accessions
    give different values is an error, as are different fields.

    Parameters
    ----------
    group : RunAccessionGroup
        the group to combine, from `select_quiet_groups`
    on_resource_clash : OnResourceClash | Sequence[ClashSpec], optional
        what to do when two run accessions have a different resource in the same
        acquisition under the same name, by default "error"

    Returns
    -------
    Accession
        the combined accession, whose resources are still in the run accessions

    Raises
    ------
    ValueError
        if the run accessions' own metadata or fields conflict, or a
        resource clash is an error under ``on_resource_clash``
    """
    run_accessions = [Accession.load(d) for d in group.run_dirs]
    for accession in run_accessions:
        _use_saved_metadata(accession)
    oldest = run_accessions[0]
    combined = oldest.new_empty()
    combined.run_uid = None
    # The metadata is gathered in plain dicts and set at the end: reading the combined
    # accession's metadata before its acquisitions are added would stop it collating
    # theirs (Metadata reads its collated values once)
    accession_metadata: dict[str, ty.Any] = {}
    acquisition_metadata: dict[str, dict[str, ty.Any]] = {}
    for run_dir, accession in zip(group.run_dirs, run_accessions):
        _merge_into(combined.fields, dict(accession.fields), "field", run_dir)
        _merge_into(
            accession_metadata,
            _own_metadata(accession.metadata, accession.acquisitions.values()),
            "metadata",
            run_dir,
        )
        for acquisition in accession.acquisitions.values():
            own = _own_metadata(acquisition.metadata, acquisition.resources.values())
            _merge_into(
                acquisition_metadata.setdefault(acquisition.id, {}),
                own,
                f"metadata of acquisition '{acquisition.id}'",
                run_dir,
            )
            for resource in acquisition.resources.values():
                combined.add_resource(
                    acquisition.id,
                    acquisition.type,
                    resource.name,
                    resource.fileset,
                    attached=acquisition.attached,
                    on_clash=on_resource_clash,
                    metadata=dict(resource.metadata),
                )
        for name, resource in accession.session_resources.items():
            existing = combined.session_resources.get(name)
            if existing is None:
                combined.session_resources[name] = resource
            elif existing.checksums != resource.checksums:
                raise ValueError(
                    f"Run accession '{run_dir.name}' has a different session resource "
                    f"'{name}' from an earlier run accession"
                )
    for acquisition_id, own in acquisition_metadata.items():
        combined.acquisitions[acquisition_id].metadata.update(own)
    combined.metadata.update(accession_metadata)
    combined.metadata.update({COMBINED_FROM_KEY: [d.name for d in group.run_dirs]})
    return combined


def _use_saved_metadata(accession: Accession) -> None:
    """Stops the files of a loaded run accession being read for metadata, so that its
    resources' metadata is what collate saved. That already holds what was read from
    the files (``Metadata.save`` reads them first), unless their datatype was in
    ``dont_read_metadata``: reading them again would add the fields that it left out,
    and could replace saved values, e.g. from the paths, with the files' own"""
    resources = [
        resource
        for acquisition in accession.acquisitions.values()
        for resource in acquisition.resources.values()
    ] + list(accession.session_resources.values())
    for resource in resources:
        resource.fileset.metadata.read_disabled = True


def deliver_combined(
    accession: Accession,
    group: RunAccessionGroup,
    build_dir: Path,
    output_dir: Path,
    primary_label: str,
    copy_mode: FileSet.CopyMode = FileSet.CopyMode.hardlink_or_copy,
) -> Path:
    """Saves a combined accession into the build directory and moves it into the output
    directory, as ``<labels>_<primary_label>``

    An accession that is already in the output directory under that name is never
    changed: it raises, so that the group is moved to the error directory, unless it is
    this group's combined accession, delivered by an earlier attempt that failed before
    `remove_run_accessions`. Then it is returned as it is, so a retry only removes the
    run accessions.

    Parameters
    ----------
    accession : Accession
        the combined accession, from `combine_accessions`
    group : RunAccessionGroup
        the group it was combined from
    build_dir : Path
        the combine run's build directory
    output_dir : Path
        the directory the combined accessions are delivered to
    primary_label : str
        the suffix of the combined accession's name (`check_primary_label`)
    copy_mode : FileSet.CopyMode, optional
        how the files are saved, by default hard-linked if possible, otherwise copied

    Returns
    -------
    Path
        the combined accession's directory in the output directory

    Raises
    ------
    FileExistsError
        if another accession is already in the output directory under the name
    """
    accession.run_uid = primary_label
    dest = Path(output_dir) / accession.staging_dirname()
    if dest.exists():
        if _combined_from(dest) == [d.name for d in group.run_dirs]:
            logger.info(
                "'%s' was combined by an earlier attempt, keeping it", dest.name
            )
            return dest
        raise FileExistsError(
            f"'{dest}' is already in the output directory, so the run accessions of "
            f"'{group.name}' weren't combined"
        )
    _, saved_dir = accession.save(Path(build_dir), copy_mode=copy_mode)
    # A rename never replaces a directory with contents, so an accession delivered at
    # the same moment by another combiner isn't overwritten
    saved_dir.rename(dest)
    logger.info("Combined %s run accessions into '%s'", len(group.run_dirs), dest)
    return dest


def remove_run_accessions(group: RunAccessionGroup) -> None:
    """Deletes a group's run accessions, once their combined accession is delivered

    Parameters
    ----------
    group : RunAccessionGroup
        the group, from `select_quiet_groups`
    """
    for run_dir in group.run_dirs:
        if run_dir.exists():
            shutil.rmtree(run_dir)


def abandon_group(
    group: RunAccessionGroup,
    error_dir: Path,
    error: BaseException | str,
    run_uid: str,
) -> Path:
    """Moves the run accessions of a group that couldn't be combined to
    ``<error_dir>/<name>_<run_uid>/``, with the error recorded in its ``error.json``

    Parameters
    ----------
    group : RunAccessionGroup
        the group that failed
    error_dir : Path
        the directory the failed groups are moved to
    error : BaseException | str
        why it failed
    run_uid : str
        the combine run's UID, which makes the directory's name unique

    Returns
    -------
    Path
        the group's directory in the error directory
    """
    dest = Path(error_dir) / f"{group.name}_{run_uid}"
    dest.mkdir(parents=True)
    for run_dir in group.run_dirs:
        if run_dir.exists():
            shutil.move(run_dir, dest / run_dir.name)
    write_error_record(dest, error)
    logger.error("Moved the run accessions of '%s' to '%s'", group.name, dest)
    return dest


def _own_metadata(
    metadata: Metadata, children: ty.Iterable[ty.Any]
) -> dict[str, ty.Any]:
    """The metadata a level holds of its own, e.g. from a metadata table: the keys that
    aren't collated from the level below it, other than the bookkeeping keys"""
    collated = set().union(*(child.metadata.keys() for child in children))
    return {
        key: value
        for key, value in dict(metadata).items()
        if key not in collated
        and key not in Metadata.RESERVED_KEYS
        and key != COMBINED_FROM_KEY
    }


def _merge_into(
    target: ty.MutableMapping[str, ty.Any],
    values: ty.Mapping[str, ty.Any],
    what: str,
    run_dir: Path,
) -> None:
    """Merges ``values`` into ``target``, raising on a key whose value differs"""
    for key, value in values.items():
        if key in target and not _values_equal(target[key], value):
            raise ValueError(
                f"Run accession '{run_dir.name}' has a different value for the {what} "
                f"'{key}' ({value!r}) from an earlier run accession "
                f"({target[key]!r})"
            )
        target[key] = value


def _combined_from(accession_dir: Path) -> list[str] | None:
    """The run accessions a delivered combined accession was combined from"""
    try:
        metadata = json.loads((accession_dir / Metadata.FNAME).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    combined_from = metadata.get(COMBINED_FROM_KEY)
    return list(combined_from) if combined_from else None
