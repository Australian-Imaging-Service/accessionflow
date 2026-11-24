"""Taking ownership of the files to collate (see ``prefect-migration-docs/ROADMAP.md``,
Phase 1)"""

import errno
import hashlib
import json
import os
import shutil
import typing as ty
from datetime import UTC, datetime
from pathlib import Path

import attrs

from accessionflow.api.staging import check_run_uid
from accessionflow.helpers.logging import logger

__all__ = [
    "CLAIMED_FILES_DIRNAME",
    "CLAIMED_MANIFEST",
    "PROCESSING_NAME_DEFAULT",
    "ClaimedFiles",
    "claim_input_files",
    "make_run_uid",
]

# The subdirectory of the output directory that the files of each run are claimed
# into, under a subdirectory named after the run's UID. Later stages don't see it,
# because list_session_dirs skips directories whose names start with '__'
PROCESSING_NAME_DEFAULT = "__processing__"

# The plan of a claim, written to the run's directory before any file is moved
CLAIMED_MANIFEST = "claimed.json"

# The subdirectory of the run directory the files are claimed into, kept apart from
# the plan so that no input file can clash with it
CLAIMED_FILES_DIRNAME = "files"

# Appended to the hidden name a file is copied to across file systems, before it is
# renamed into place
_COPY_SUFFIX = ".claiming"

# The tolerance when comparing modification times across file systems, some of which
# store them with as little as 2-second precision
_MTIME_TOLERANCE_NS = 2_000_000_000


def make_run_uid(
    input_files: ty.Sequence[Path],
    now: datetime | None = None,
) -> str:
    """Makes the UID of a collation run, which names its build directory, its claim
    directory and the staged directory of each accession it collates

    The UID is the first 6 hex characters of a SHA-256 hash of the files' absolute
    paths, followed by the time in UTC as ``YYYYMMDDHHMMSS``. It holds only hex
    characters and digits, never a ``.``, which separates it from the labels in a
    staged directory's name.

    Make it once per run. A retry of the run passes the same value on, rather than
    making a new one, so that it finds the directories the first attempt made.

    Parameters
    ----------
    input_files : Sequence[Path]
        the files the run collates. Their order doesn't matter
    now : datetime, optional
        the time of the run, by default the current time. A time with a time zone is
        converted to UTC, and a naive time is taken as local time

    Returns
    -------
    str
        the run UID
    """
    crypto = hashlib.sha256()
    for fspath in sorted(str(p.absolute()) for p in input_files):
        crypto.update(fspath.encode())
    when = datetime.now(UTC) if now is None else now.astimezone(UTC)
    return crypto.hexdigest()[:6] + when.strftime("%Y%m%d%H%M%S")


@attrs.frozen(hash=False)
class ClaimedFiles:
    """The files a run has claimed, as returned by `claim_input_files`

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


def claim_input_files(
    input_files: ty.Sequence[Path],
    processing_dir: Path,
    run_uid: str,
    source_roots: ty.Sequence[Path] | None = None,
) -> ClaimedFiles:
    """Moves the files to collate into the run's own directory in the processing area,
    ``processing_dir / run_uid / files``, so that the rest of the run works on a fixed set of
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

    Parameters
    ----------
    input_files : Sequence[Path]
        the files to claim, e.g. from `list_input_files`. Ignored on a retry, which uses
        the saved plan
    processing_dir : Path
        the processing area, by default ``<output_dir>/__processing__``
        (`PROCESSING_NAME_DEFAULT`)
    run_uid : str
        the run's UID, from `make_run_uid`, which names its directory
    source_roots : Sequence[Path], optional
        the directories the files were listed from. Every file must be in one of them.
        By default, the directory of each file

    Returns
    -------
    ClaimedFiles
        the files now in the run directory, with their original paths. With no files to
        claim, an empty record, and nothing is created

    Raises
    ------
    ValueError
        if ``run_uid`` isn't a valid directory name, a file isn't in any of the source
        roots, or the roots have no common directory. Nothing is moved
    """
    check_run_uid(run_uid, "claim directory")
    run_dir = Path(processing_dir).absolute() / run_uid
    if (run_dir / CLAIMED_MANIFEST).exists():
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
            Path(entry["original"]), run_dir / CLAIMED_FILES_DIRNAME / entry["claimed"]
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
