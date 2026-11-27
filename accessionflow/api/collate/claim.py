"""Taking ownership of the files to collate (see ``prefect-migration-docs/ROADMAP.md``,
Phase 1)"""

import errno
import json
import os
import random
import secrets
import shutil
import traceback
import typing as ty
from datetime import UTC, datetime
from pathlib import Path

import attrs
from fileformats.core import FileSet, to_mime

from accessionflow.api.staging import (
    check_run_uid,
    prepare_build_dir,
    prune_empty_dirs,
)
from accessionflow.api.step import Step
from accessionflow.helpers.logging import logger
from accessionflow.model.accession import Accession

__all__ = [
    "CLAIMED_FILES_DIRNAME",
    "CLAIMED_MANIFEST",
    "ERROR_MANIFEST",
    "PROCESSING_NAME_DEFAULT",
    "UNPROCESSED_NAME_DEFAULT",
    "ERROR_NAME_DEFAULT",
    "UNPROCESSED_MANIFEST",
    "AbandonClaim",
    "ClaimInputFiles",
    "ClaimedFiles",
    "FinishClaim",
    "ReserveRunUid",
    "claim_run_dir",
    "has_claim_plan",
    "make_run_uid",
    "RUN_UID_ATTEMPTS",
    "write_error_record",
]

# The subdirectory of the output directory that the files of each run are claimed
# into, under a subdirectory named after the run's UID. Later stages don't see it,
# because list_session_dirs skips directories whose names start with '__'
PROCESSING_NAME_DEFAULT = "__processing__"

# The subdirectories of the output directory that the CLI moves a run directory to by
# default, when files are left (FinishClaim) or the run fails (AbandonClaim). The
# combiner moves the run accessions of a group that fails to the same error directory
UNPROCESSED_NAME_DEFAULT = "__unprocessed__"
ERROR_NAME_DEFAULT = "__error__"

# The plan of a claim, written to the run's directory before any file is moved
CLAIMED_MANIFEST = "claimed.json"

# The subdirectory of the run directory the files are claimed into, kept apart from
# the plan so that no input file can clash with it
CLAIMED_FILES_DIRNAME = "files"

# Written into a run directory that is moved to the unprocessed directory, giving why
# each file was left, and into one moved to the error directory, giving the error
UNPROCESSED_MANIFEST = "unprocessed.json"
ERROR_MANIFEST = "error.json"

# Appended to the hidden name a run directory is copied to across file systems, before
# it is renamed into place
_MOVING_SUFFIX = ".moving"

# Appended to the hidden name a file is copied to across file systems, before it is
# renamed into place
_COPY_SUFFIX = ".claiming"

# The tolerance when comparing modification times across file systems, some of which
# store them with as little as 2-second precision
_MTIME_TOLERANCE_NS = 2_000_000_000


def make_run_uid(
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> str:
    """Makes the UID of a collation run, which names its build directory, its claim
    directory and the staged directory of each accession it collates

    The UID is the time in UTC as ``YYYYMMDDHHMMSS``, an underscore, and 6 random hex
    characters, e.g. ``20261125073856_a3f09c``. UIDs therefore sort by time, and two
    runs started in the same second still get different ones. It never holds a ``.``
    or a ``-``, which separate it from the labels in a staged directory's name.

    Make it once per run. A new run creates its build directory exclusively
    (``prepare_build_dir(..., exclusive=True)``) and makes another UID if that one is
    taken, so a clash is caught. A retry of the run passes the same UID on, rather than
    making a new one, so that it finds the directories the first attempt made.

    Parameters
    ----------
    now : datetime, optional
        the time of the run, by default the current time. A time with a time zone is
        converted to UTC, and a naive time is taken as local time
    rng : random.Random, optional
        the source of the random characters, for tests. By default, ``secrets``

    Returns
    -------
    str
        the run UID
    """
    when = datetime.now(UTC) if now is None else now.astimezone(UTC)
    suffix = secrets.token_hex(3) if rng is None else f"{rng.getrandbits(24):06x}"
    return f"{when.strftime('%Y%m%d%H%M%S')}_{suffix}"


def claim_run_dir(working_dir: Path, run_uid: str) -> Path:
    """The directory of a run's claim in the processing area, ``working_dir / run_uid``,
    which holds its plan and, under ``files/``, the files it claimed

    Parameters
    ----------
    working_dir : Path
        the processing area, e.g. ``<output_dir>/__processing__``
    run_uid : str
        the run's UID

    Returns
    -------
    Path
        the run's directory, absolute even if ``working_dir`` is relative
    """
    return Path(working_dir).absolute() / run_uid


def has_claim_plan(run_dir: Path) -> bool:
    """Whether a claim's plan (`CLAIMED_MANIFEST`) has been written to its run
    directory. The plan is written before any file is moved, so a run directory without
    one holds no claimed files

    Parameters
    ----------
    run_dir : Path
        the run's directory in the processing area (`claim_run_dir`)
    """
    return (Path(run_dir) / CLAIMED_MANIFEST).exists()


@attrs.frozen(hash=False)
class ClaimedFiles:
    """The files a run has claimed, as returned by `ClaimInputFiles`

    Attributes
    ----------
    run_dir : Path
        the run's directory in the processing area, which holds the claimed files
    base : Path
        the directory the claimed files' layout is relative to: the common directory of
        the source roots
    roots : tuple[Path, ...]
        the directories the files were listed from (their original paths)
    files : dict[Path, Path]
        each claimed file's path in ``run_dir``, mapped to its original path
    """

    run_dir: Path
    base: Path
    roots: tuple[Path, ...] = attrs.field(converter=tuple)
    files: dict[Path, Path] = attrs.field(factory=dict)

    @property
    def files_dir(self) -> Path:
        """The directory in the run directory that holds the claimed files, laid out
        as they were relative to ``base``"""
        return self.run_dir / CLAIMED_FILES_DIRNAME

    @property
    def claimed_roots(self) -> list[Path]:
        """The source roots' equivalents in the run directory"""
        return [self.files_dir / root.relative_to(self.base) for root in self.roots]

    def original_of(self, claimed_path: Path) -> Path:
        """The original path of a claimed file, or of a directory that holds claimed
        files (e.g. a directory datatype)

        Raises
        ------
        ValueError
            if ``claimed_path`` isn't in ``files_dir``
        """
        return self.base / Path(claimed_path).absolute().relative_to(self.files_dir)

    @classmethod
    def load(cls, run_dir: Path) -> "ClaimedFiles":
        """Rebuilds the record of a claim from the plan in its run directory, with the
        files from the plan that are in the run directory now

        Parameters
        ----------
        run_dir : Path
            the run's directory in the processing area

        Raises
        ------
        FileNotFoundError
            if the run directory holds no plan
        """
        return cls._from_plan(Path(run_dir), _read_plan(Path(run_dir)))

    @classmethod
    def find(cls, working_dir: Path, run_uid: str) -> "ClaimedFiles | None":
        """Finds the claim of a run in the processing area, e.g. after the claim raised
        partway and returned nothing, so that the files it moved can be dealt with

        Parameters
        ----------
        working_dir : Path
            the processing area the run claimed its files into
        run_uid : str
            the run's UID

        Returns
        -------
        ClaimedFiles or None
            the record of the claim, with the files from its plan that are in its run
            directory now (`load`), or None if no plan was written, i.e. no file was
            moved
        """
        run_dir = claim_run_dir(working_dir, run_uid)
        return cls.load(run_dir) if has_claim_plan(run_dir) else None

    @classmethod
    def _from_plan(cls, run_dir: Path, plan: dict[str, ty.Any]) -> "ClaimedFiles":
        files_dir = run_dir / CLAIMED_FILES_DIRNAME
        files = {
            files_dir / entry["claimed"]: Path(entry["original"])
            for entry in plan["files"]
            if (files_dir / entry["claimed"]).exists()
        }
        return cls(
            run_dir=run_dir,
            base=Path(plan["base"]),
            roots=tuple(Path(r) for r in plan["roots"]),
            files=files,
        )


# How many run UIDs a new run tries before giving up, should each be taken already
RUN_UID_ATTEMPTS = 5


@attrs.define
class ReserveRunUid(Step):
    """Reserves an unused UID for a run, which names everything the run creates, by
    creating the run's build directory, ``<output_dir>/__build__/<run_uid>/``,
    exclusively (`prepare_build_dir`). If another run has already taken the UID, it
    makes another (`make_run_uid`). Used by the collate and combine composites. Its
    configuration needs no checks

    Parameters
    ----------
    output_dir : Path
        the directory the run delivers to, which holds the build directories
    """

    output_dir: Path = attrs.field(converter=Path)

    def act(self) -> tuple[str, Path]:
        """Makes the run's UID and creates its build directory

        Returns
        -------
        tuple[str, Path]
            the run's UID, and its build directory

        Raises
        ------
        RuntimeError
            if every one of `RUN_UID_ATTEMPTS` UIDs is taken
        """
        for _ in range(RUN_UID_ATTEMPTS):
            run_uid = make_run_uid()
            try:
                return run_uid, prepare_build_dir(
                    self.output_dir, run_uid, exclusive=True
                )
            except FileExistsError:
                logger.debug("Run UID '%s' is taken, making another", run_uid)
        raise RuntimeError(f"Couldn't make an unused run UID in '{self.output_dir}'")


def write_error_record(directory: Path, error: BaseException | str) -> Path:
    """Writes the record of why a run failed (`ERROR_MANIFEST`) into the directory
    that is moved to the error directory, with the error's type and traceback if it is
    an exception

    Returns
    -------
    Path
        the record
    """
    record: dict[str, ty.Any] = {"message": str(error)}
    if isinstance(error, BaseException):
        record["type"] = type(error).__name__
        record["traceback"] = "".join(traceback.format_exception(error))
    path = Path(directory) / ERROR_MANIFEST
    path.write_text(json.dumps(record, indent=2))
    return path


@attrs.define
class ClaimInputFiles(Step):
    """Moves the files to collate into the run's own directory in the processing area,
    ``working_dir / run_uid / files``, so that the rest of the run works on a fixed set of
    files while the input directory keeps changing. A file that arrives after the files
    were listed stays where it is, for the next run.

    Each file keeps its path relative to the common directory of the source roots, so
    directory datatypes and file names that repeat across directories survive. On one
    file system each file is moved with an atomic rename. Across file systems it is
    copied to a hidden temporary name, checked to be unchanged (size and modification
    time), renamed into place, and then deleted from the input. A file that changes
    while it is copied is left for the next run, and a file that has disappeared since
    it was listed is skipped. Both are logged, and so, once, are any copies across file
    systems.

    The plan of the claim (``claimed.json``) is written to the run directory before any
    file is moved. If the run is retried with the same ``run_uid``, the saved plan is
    used and the files that are already claimed are skipped, so no file is claimed
    twice.

    Limits: on one file system, a file that is still being written is moved, and the
    writer goes on writing to it in the processing area (`list_input_files` skips
    hidden files, which are often uploads in progress). Across file systems, two runs
    claiming the same file at the same time can both copy it, so runs that may overlap
    need the input on the same file system as the processing area.

    Its configuration needs no checks: whether the files are in the source roots depends
    on the files, so `act` checks it.

    Parameters
    ----------
    working_dir : Path
        the directory each run's own directory is made in, ``working_dir / run_uid``,
        e.g. ``<output_dir>/__processing__`` (`PROCESSING_NAME_DEFAULT`)
    """

    working_dir: Path = attrs.field(converter=Path)

    def act(
        self,
        input_files: ty.Sequence[Path],
        run_uid: str,
        source_roots: ty.Sequence[Path] | None = None,
    ) -> ClaimedFiles:
        """Claims the files into ``working_dir / run_uid / files``

        Parameters
        ----------
        input_files : Sequence[Path]
            the files to claim, e.g. from `list_input_files`. Ignored on a retry, which
            uses the saved plan
        run_uid : str
            the run's UID, from `ReserveRunUid`, which names its directory
        source_roots : Sequence[Path], optional
            the directories the files were listed from. Every file must be in one of
            them. By default, the directory of each file

        Returns
        -------
        ClaimedFiles
            the files now in the run directory, with their original paths. With no
            files to claim, an empty record, and nothing is created

        Raises
        ------
        ValueError
            if ``run_uid`` isn't a valid directory name, a file isn't in any of the
            source roots, or the roots have no common directory. Nothing is moved
        """
        check_run_uid(run_uid, "claim directory")
        run_dir = claim_run_dir(self.working_dir, run_uid)
        if has_claim_plan(run_dir):
            plan = _read_plan(run_dir)
            planned = {entry["original"] for entry in plan["files"]}
            if planned != {str(Path(p).absolute()) for p in input_files}:
                logger.debug(
                    "Retrying the claim of run '%s' with its saved plan, which differs "
                    "from the files given",
                    run_uid,
                )
        else:
            plan = _make_plan(input_files, source_roots)
            if not plan["files"]:
                return ClaimedFiles._from_plan(run_dir, plan)
            _write_plan(run_dir, plan)

        n_copied = 0
        for entry in plan["files"]:
            n_copied += _claim_one(
                Path(entry["original"]),
                run_dir / CLAIMED_FILES_DIRNAME / entry["claimed"],
            )
        claimed = ClaimedFiles._from_plan(run_dir, plan)
        if n_copied:
            logger.warning(
                "%s of %s files were copied into '%s' from a different file system, "
                "which is slower than moving them and not atomic. To move them, put the "
                "input on the same file system as the processing area (by default the "
                "output directory).",
                n_copied,
                len(plan["files"]),
                run_dir,
            )
        logger.info(
            "Claimed %s of %s files into '%s'",
            len(claimed.files),
            len(plan["files"]),
            run_dir,
        )
        return claimed


@attrs.define
class FinishClaim(Step):
    """Finishes a run's claim once its accessions have been staged. If no claimed files
    are left, the run directory is removed. Otherwise the whole run directory, with its
    plan, is moved to ``unprocessed_dir / run_uid``, after recording why each file was
    left in its ``unprocessed.json`` (`UNPROCESSED_MANIFEST`):

    - ``failed``: it belongs to an accession that failed to stage, given with the
      accession's UID and the error
    - ``ignored``: it belongs to a file-set of an ``--ignore-datatype``, given with its
      MIME-like datatype
    - ``unrecognised``: no datatype recognised it, and ``--allow-unrecognised`` let it
      through

    Empty directories are removed first, and so is a hidden temporary file left by a
    copy across file systems that was stopped part way, whose source is still in the
    input. It can be retried: once the run directory has been moved, a second call
    returns the files it moved.

    Its configuration needs no checks.

    Parameters
    ----------
    unprocessed_dir : Path
        where a run directory with files left in it is moved to
    """

    unprocessed_dir: Path = attrs.field(converter=Path)

    def act(
        self,
        claimed: ClaimedFiles,
        failed: ty.Sequence[tuple[Accession, str]] = (),
        ignored: ty.Sequence[FileSet] = (),
    ) -> list[Path]:
        """Removes the run directory, or moves it to the unprocessed directory

        Parameters
        ----------
        claimed : ClaimedFiles
            the run's claimed files, from `ClaimInputFiles`
        failed : Sequence[tuple[Accession, str]], optional
            the accessions that failed to stage, each with its error message
        ignored : Sequence[FileSet], optional
            the file-sets of ignored datatypes, dropped by `drop_ignored_filesets`

        Returns
        -------
        list[Path]
            the files left, at their paths in the unprocessed directory, sorted. Empty
            if none were left
        """
        run_dir = claimed.run_dir
        dest = self.unprocessed_dir / run_dir.name
        if not run_dir.exists():
            return _files_in(dest / CLAIMED_FILES_DIRNAME)
        leftovers = _tidy_run_dir(claimed)
        if not leftovers:
            shutil.rmtree(run_dir)
            return []
        reasons = _leftover_reasons(claimed, leftovers, failed, ignored)
        (run_dir / UNPROCESSED_MANIFEST).write_text(json.dumps(reasons, indent=2))
        moved_dir = _move_run_dir(run_dir, self.unprocessed_dir)
        counts: dict[str, int] = {}
        for entry in reasons:
            counts[entry["reason"]] = counts.get(entry["reason"], 0) + 1
        logger.warning(
            "Moved %s files that weren't staged (%s) to '%s'",
            len(leftovers),
            ", ".join(f"{n} {reason}" for reason, n in sorted(counts.items())),
            moved_dir,
        )
        return _files_in(moved_dir / CLAIMED_FILES_DIRNAME)


@attrs.define
class AbandonClaim(Step):
    """Moves the claim of a run that failed after the claim, e.g. on a file no datatype
    recognised, to ``error_dir / run_uid``, with the error recorded in its
    ``error.json`` (`ERROR_MANIFEST`), so its files can be dealt with and the
    processing area doesn't keep them. Act when the run raises, then re-raise.

    Its configuration needs no checks.

    Parameters
    ----------
    error_dir : Path
        where the run directory is moved to
    """

    error_dir: Path = attrs.field(converter=Path)

    def act(self, claimed: ClaimedFiles, error: BaseException | str) -> Path:
        """Moves the run directory to the error directory, with the error recorded

        Parameters
        ----------
        claimed : ClaimedFiles
            the run's claimed files, from `ClaimInputFiles`
        error : BaseException or str
            the error the run failed with

        Returns
        -------
        Path
            the run directory's new path, or where it would have been if the run
            claimed nothing
        """
        run_dir = claimed.run_dir
        dest = self.error_dir / run_dir.name
        if not run_dir.exists():
            return dest
        _tidy_run_dir(claimed)
        write_error_record(run_dir, error)
        moved_dir = _move_run_dir(run_dir, self.error_dir)
        logger.error(
            "Moved the claim of failed run '%s' to '%s'", run_dir.name, moved_dir
        )
        return moved_dir


def _tidy_run_dir(claimed: ClaimedFiles) -> list[Path]:
    """Deletes partial copies and empty directories, and returns the files left"""
    files_dir = claimed.files_dir
    if not files_dir.exists():
        return []
    for tmp in files_dir.rglob(f".*{_COPY_SUFFIX}"):
        tmp.unlink()
    prune_empty_dirs(files_dir)
    return _files_in(files_dir)


def _files_in(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if not p.is_dir())


def _leftover_reasons(
    claimed: ClaimedFiles,
    leftovers: ty.Sequence[Path],
    failed: ty.Sequence[tuple[Accession, str]],
    ignored: ty.Sequence[FileSet],
) -> list[dict[str, ty.Any]]:
    """Why each file was left: failed, ignored or unrecognised"""
    failed_paths = [
        (Path(p).absolute(), accession.uid, error)
        for accession, error in failed
        for resource in accession.resources
        for p in resource.fileset.fspaths
    ]
    ignored_paths = [
        (Path(p).absolute(), to_mime(type(fileset), official=False))
        for fileset in ignored
        for p in fileset.fspaths
    ]
    reasons = []
    for fspath in leftovers:
        entry: dict[str, ty.Any] = {
            "file": fspath.relative_to(claimed.run_dir).as_posix(),
            "original": str(claimed.original_of(fspath)),
        }
        failure = next(
            ((uid, err) for p, uid, err in failed_paths if fspath.is_relative_to(p)),
            None,
        )
        datatype = next(
            (dt for p, dt in ignored_paths if fspath.is_relative_to(p)), None
        )
        if failure is not None:
            entry.update(reason="failed", accession=failure[0], error=failure[1])
        elif datatype is not None:
            entry.update(reason="ignored", datatype=datatype)
        else:
            entry["reason"] = "unrecognised"
        reasons.append(entry)
    return reasons


def _move_run_dir(run_dir: Path, dest_parent: Path) -> Path:
    """Moves a run directory into ``dest_parent``: with a rename on one file system,
    or across file systems by copying it to a hidden name, renaming that into place
    and deleting the original. Safe to retry after a failure part way"""
    dest = dest_parent / run_dir.name
    dest_parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        # An earlier attempt got it into place but stopped before deleting the original
        if run_dir.exists():
            shutil.rmtree(run_dir)
        return dest
    try:
        os.rename(run_dir, dest)
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
        tmp = dest_parent / f".{run_dir.name}{_MOVING_SUFFIX}"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(run_dir, tmp, symlinks=True)
        os.replace(tmp, dest)
        shutil.rmtree(run_dir)
    return dest


def _make_plan(
    input_files: ty.Sequence[Path], source_roots: ty.Sequence[Path] | None
) -> dict[str, ty.Any]:
    """Works out where each file goes, relative to the common directory of the roots"""
    originals = sorted({Path(p).absolute() for p in input_files})
    if source_roots is None:
        roots = sorted({p.parent for p in originals})
    else:
        roots = sorted({Path(r).absolute() for r in source_roots})
    if not roots:
        return {"base": "", "roots": [], "files": []}
    try:
        base = Path(os.path.commonpath(roots))
    except ValueError as e:
        raise ValueError(
            f"The source roots have no common directory to claim from: {roots}"
        ) from e
    if outside := [p for p in originals if not any(p.is_relative_to(r) for r in roots)]:
        raise ValueError(
            f"{len(outside)} files aren't in any of the source roots {roots}, "
            f"e.g. '{outside[0]}'"
        )
    return {
        "base": str(base),
        "roots": [str(r) for r in roots],
        "files": [
            {"original": str(p), "claimed": p.relative_to(base).as_posix()}
            for p in originals
        ],
    }


def _write_plan(run_dir: Path, plan: dict[str, ty.Any]) -> None:
    """Writes the plan to the run directory atomically"""
    run_dir.mkdir(parents=True, exist_ok=True)
    tmp = run_dir / f".{CLAIMED_MANIFEST}.tmp"
    tmp.write_text(json.dumps(plan, indent=2))
    os.replace(tmp, run_dir / CLAIMED_MANIFEST)


def _read_plan(run_dir: Path) -> dict[str, ty.Any]:
    plan: dict[str, ty.Any] = json.loads((run_dir / CLAIMED_MANIFEST).read_text())
    return plan


def _claim_one(src: Path, dest: Path) -> bool:
    """Moves one file into the run directory, or works out that it was claimed by an
    earlier attempt. Returns whether it was copied across file systems"""
    if dest.exists():
        if not src.exists():
            return False  # claimed by an earlier attempt
        # An earlier attempt copied the file across file systems but stopped before it
        # deleted the source, or a new file with the same name has arrived since
        if _same_contents_stat(src.stat(), dest.stat()):
            src.unlink(missing_ok=True)
        else:
            logger.info(
                "Leaving '%s' for the next run, as it differs from the file claimed "
                "from the same path",
                src,
            )
        return False
    if not src.exists():
        logger.warning("Skipping '%s', which has disappeared since it was listed", src)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dest)
    except FileNotFoundError:
        logger.warning("Skipping '%s', which has disappeared since it was listed", src)
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
        return _copy_across_file_systems(src, dest)
    return False


def _copy_across_file_systems(src: Path, dest: Path) -> bool:
    """Copies a file to a hidden temporary name next to ``dest``, renames it into place
    if the source didn't change while it was copied, and then deletes the source.
    Returns whether the file was claimed"""
    tmp = dest.with_name(f".{dest.name}{_COPY_SUFFIX}")
    try:
        before = src.stat()
        shutil.copy2(src, tmp)
        after = src.stat()
    except FileNotFoundError:
        tmp.unlink(missing_ok=True)
        logger.warning("Skipping '%s', which has disappeared since it was listed", src)
        return False
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        tmp.unlink(missing_ok=True)
        logger.info(
            "Leaving '%s' for the next run, as it changed while it was copied", src
        )
        return False
    os.replace(tmp, dest)
    src.unlink(missing_ok=True)
    return True


def _same_contents_stat(a: os.stat_result, b: os.stat_result) -> bool:
    """Whether two files, possibly on different file systems, have the same size and
    modification time"""
    return (
        a.st_size == b.st_size
        and abs(a.st_mtime_ns - b.st_mtime_ns) <= _MTIME_TOLERANCE_NS
    )
