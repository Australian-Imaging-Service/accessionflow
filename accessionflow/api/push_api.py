"""Copying staged accessions, as they are, to a staging directory on another file
system, e.g. an S3 bucket that a central node reads from with ``store xnat``.

The destination is the record of what has been pushed: a resource is complete there
once its manifest has been written, since it is always written after the resource's
files, and a resource whose manifest and file sizes there match the staged ones isn't
copied again. So nothing needs to be kept locally to know what has been pushed, and a
resource that goes missing at the destination is copied again on the next pass.

``push`` never deletes the staged accessions, and never deletes anything at the
destination except the files of a resource that it is replacing with a changed one.
"""

import contextlib
import hashlib
import json
import os
import time
import traceback
import typing as ty
from pathlib import Path

import attrs
import fsspec

from accessionflow.helpers.logging import logger
from accessionflow.helpers.metadata import Metadata
from accessionflow.helpers.remote_fs import (
    is_side_car,
    open_fs,
    read_remote_manifest,
    remote_md5,
    write_atomically,
)
from accessionflow.helpers.remotes import list_session_dirs
from accessionflow.model.resource import Resource

FIELDS_FNAME = "__FIELDS__.json"


class DestinationUnreachable(ConnectionError):
    """The destination couldn't be listed, e.g. its endpoint is down or the
    credentials can't see it"""


class LockTimeout(TimeoutError):
    """The lock file wasn't free within the time allowed"""


class LockFailed(OSError):
    """The lock file couldn't be opened or locked, for a reason other than a timeout"""


@attrs.define
class Compatibility:
    """Optional behaviour that keeps an external reclaimer of the staged copies working
    as it did with ais-edge's s3-uploader script, until it checks the destination
    itself (e.g. with ``check-push``).

    Parameters
    ----------
    marker_dir : Path, optional
        if given, a marker is written here for each accession once it has been pushed,
        named after it and holding a fingerprint of its staged files (the MD5 of their
        sorted relative paths, sizes and modification times), and an accession whose
        marker matches its current fingerprint is skipped without checking the
        destination. A marker is removed once no stage directory holds an accession of
        its name any more
    marker_root : Path, optional
        the directory the stage directories are in, which is searched for accessions
        before a marker is removed. Defaults to the parent of the staging directory
    recopy_dir : Path, optional
        a directory where the reclaimer asks for an accession to be copied again in
        full, with a file named after it. A request is claimed by renaming it to
        '<name>.claimed', and removed once the copy succeeds
    lock_file : Path, optional
        a lock file that is held, with ``flock``, while each accession is copied, so it
        isn't copied while another process holding the same lock writes or deletes it
    lock_wait : int
        the number of seconds to wait for the lock before skipping the accession until
        the next pass
    """

    marker_dir: Path | None = attrs.field(
        default=None, converter=attrs.converters.optional(Path)
    )
    marker_root: Path | None = attrs.field(
        default=None, converter=attrs.converters.optional(Path)
    )
    recopy_dir: Path | None = attrs.field(
        default=None, converter=attrs.converters.optional(Path)
    )
    lock_file: Path | None = attrs.field(
        default=None, converter=attrs.converters.optional(Path)
    )
    lock_wait: int = 600


def push(
    input_dir: Path,
    dest: str,
    storage_options: ty.Mapping[str, ty.Any] | None = None,
    wait_period: int = 0,
    raise_errors: bool = False,
    compatibility: Compatibility | None = None,
) -> list[str]:
    """Copies the accessions in a staging directory, as they are, to a staging
    directory on another file system, e.g. an S3 bucket.

    Each accession is copied to '<dest>/<accession-directory>/', in the same layout as
    the staging directory, metadata and manifests included, so that it can be read
    from there by the stage that comes next, e.g. ``store xnat s3://...``. A resource's
    manifest is written after its files, and the accession's metadata after
    everything else, so a reader can tell a complete copy from one that is still
    being written.

    Pushing again is cheap: a resource whose manifest at the destination matches the
    staged one, and whose files there have the staged sizes, is skipped. One that is
    missing there, left without a manifest by an interrupted copy, or changed since it
    was pushed, is copied again.

    Parameters
    ----------
    input_dir : Path
        the staging directory holding the accessions, e.g. the output of 'label' or of
        'deidentify'
    dest : str
        the staging directory to copy them to, a path or an fsspec URL, e.g.
        's3://bucket/staged' or 'sftp://host/staged'
    storage_options : Mapping[str, Any], optional
        options for the fsspec file system of the destination, e.g. credentials
    wait_period : int
        the number of seconds since anything in an accession was last modified before
        it is pushed, so one that is still being written isn't
    raise_errors : bool
        whether to raise errors instead of logging them and continuing with the next
        accession
    compatibility : Compatibility, optional
        behaviour that keeps an external reclaimer of the staged copies working (see
        :class:`Compatibility`)

    Returns
    -------
    list[str]
        the errors encountered, one per accession that couldn't be pushed

    Raises
    ------
    DestinationUnreachable
        if the destination can't be listed
    LockFailed
        if the lock file of the compatibility settings can't be opened or locked, for
        a reason other than a timeout
    """
    fs, root = open_fs(dest, storage_options)
    probe_destination(fs, root)
    compat = compatibility or Compatibility()
    if compat.recopy_dir is not None:
        _requeue_claims(compat.recopy_dir)
    errors: list[str] = []
    n_pushed = 0
    for staged_dir in list_session_dirs(input_dir):
        name = staged_dir.name
        if not _settled(staged_dir, wait_period):
            logger.info(
                "Skipping '%s' as it was modified less than %d seconds ago",
                name,
                wait_period,
            )
            continue
        if dangling := _dangling_links(staged_dir):
            msg = (
                f"Not pushing '{name}', as some of its files are links whose targets "
                f"have gone, e.g. '{dangling[0]}'"
            )
            logger.error(msg)
            errors.append(msg)
            continue
        claim = _claim_recopy(compat.recopy_dir, name)
        fingerprint = _fingerprint(staged_dir) if compat.marker_dir else None
        if claim is None and fingerprint is not None:
            marker = compat.marker_dir / name  # type: ignore[operator]
            if marker.exists() and marker.read_text().strip() == fingerprint:
                continue
        try:
            with _locked(compat.lock_file, compat.lock_wait):
                start = time.monotonic()
                pushed = push_accession(fs, root, staged_dir, force=claim is not None)
            if pushed.resources:
                n_pushed += 1
                logger.info(
                    "Pushed %d resource(s) of '%s' (%d files, %d bytes) to '%s' in "
                    "%.1f seconds",
                    pushed.resources,
                    name,
                    pushed.files,
                    pushed.bytes,
                    f"{root}/{name}",
                    time.monotonic() - start,
                )
            else:
                logger.debug("'%s' is already at the destination", name)
            if fingerprint is not None:
                compat.marker_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
                (compat.marker_dir / name).write_text(fingerprint + "\n")  # type: ignore[operator]
            if claim is not None:
                claim.unlink(missing_ok=True)
                logger.info("Copied '%s' again, as requested", name)
        except LockTimeout:
            _release_claim(claim)
            logger.info(
                "Skipping '%s' as the lock '%s' wasn't free within %d seconds",
                name,
                compat.lock_file,
                compat.lock_wait,
            )
        except LockFailed:
            _release_claim(claim)
            raise
        except Exception as e:
            _release_claim(claim)
            if raise_errors:
                raise
            msg = f"Could not push '{name}': {e}"
            logger.error(msg)
            logger.debug(traceback.format_exc())
            errors.append(msg)
    if compat.marker_dir is not None:
        _sweep_markers(compat.marker_dir, compat.marker_root or Path(input_dir).parent)
    if errors:
        logger.error("Pushing completed with %d errors", len(errors))
    else:
        logger.info("Pushing completed, %d accession(s) pushed", n_pushed)
    return errors


def check_push(
    input_dir: Path,
    dest: str,
    storage_options: ty.Mapping[str, ty.Any] | None = None,
    checksums: bool = True,
    raise_errors: bool = False,
) -> list[str]:
    """Checks the copies that ``push`` made of the accessions in a staging directory,
    and logs every resource that is missing, incomplete or different at the
    destination.

    Parameters
    ----------
    input_dir : Path
        the staging directory the accessions were pushed from
    dest : str
        the staging directory they were pushed to, a path or an fsspec URL
    storage_options : Mapping[str, Any], optional
        options for the fsspec file system of the destination, e.g. credentials
    checksums : bool
        whether to check the files' checksums, which reads every file back from the
        destination. If False, only their sizes are compared, which is much cheaper
    raise_errors : bool
        whether to raise errors instead of logging them

    Returns
    -------
    list[str]
        a description of each problem found
    """
    fs, root = open_fs(dest, storage_options)
    probe_destination(fs, root)
    problems: list[str] = []
    for staged_dir in list_session_dirs(input_dir):
        try:
            remote_dir = f"{root}/{staged_dir.name}"
            sizes = _remote_sizes(fs, remote_dir)
            for relpath, resource_dir in _resource_dirs(staged_dir):
                remote = f"{remote_dir}/{relpath}"
                manifest = _read_manifest(resource_dir)
                stored = read_remote_manifest(fs, remote)
                if stored is None:
                    problems.append(
                        f"'{remote}' is missing from the destination, or pushing it "
                        "didn't finish"
                    )
                    continue
                if stored != manifest:
                    problems.append(
                        f"'{remote}' at the destination holds different files to "
                        f"'{resource_dir}'"
                    )
                    continue
                for file_relpath, size in _local_files(resource_dir).items():
                    path = f"{remote}/{file_relpath}"
                    if path not in sizes:
                        problems.append(f"'{path}' is missing from the destination")
                    elif sizes[path] != size:
                        problems.append(
                            f"'{path}' at the destination has the wrong size"
                        )
                    elif checksums and file_relpath in manifest.get("checksums", {}):
                        if remote_md5(fs, path) != manifest["checksums"][file_relpath]:
                            problems.append(f"'{path}' at the destination is corrupted")
            if f"{remote_dir}/{Metadata.FNAME}" not in sizes:
                problems.append(
                    f"'{remote_dir}' has no metadata at the destination, so pushing it "
                    "didn't finish"
                )
        except Exception as e:
            if raise_errors:
                raise
            msg = f"Could not check '{staged_dir.name}': {e}"
            logger.debug(traceback.format_exc())
            problems.append(msg)
    for problem in problems:
        logger.error(problem)
    if not problems:
        logger.info("Everything staged is at the destination")
    return problems


@attrs.define
class Pushed:
    """What pushing an accession copied"""

    resources: int = 0
    files: int = 0
    bytes: int = 0


def push_accession(
    fs: fsspec.AbstractFileSystem, root: str, staged_dir: Path, force: bool = False
) -> Pushed:
    """Copy a staged accession to '<root>/<accession-directory>' on `fs`, skipping the
    resources that are already there unless `force` is set.

    Each resource's manifest is removed before its files are changed and written after
    them, and the accession's metadata is written after everything else.

    Returns
    -------
    Pushed
        the number of resources, files and bytes copied
    """
    remote_dir = f"{root}/{staged_dir.name}"
    sizes = _remote_sizes(fs, remote_dir)
    pushed = Pushed()
    for relpath, resource_dir in _resource_dirs(staged_dir):
        manifest = _read_manifest(resource_dir)
        files = _local_files(resource_dir)
        remote = f"{remote_dir}/{relpath}"
        if not force and _is_complete(fs, sizes, remote, files, manifest):
            continue
        manifest_path = f"{remote}/{Resource.MANIFEST_FNAME}"
        if manifest_path in sizes:
            fs.rm_file(manifest_path)
        fs.makedirs(remote, exist_ok=True)
        for file_relpath in files:
            target = f"{remote}/{file_relpath}"
            if "/" in file_relpath:
                fs.makedirs(target.rsplit("/", 1)[0], exist_ok=True)
            fs.put_file(str(resource_dir / file_relpath), target)
        # Files of an earlier copy that the resource no longer has
        prefix = remote + "/"
        for path in sizes:
            if (
                path.startswith(prefix)
                and path != manifest_path
                and path[len(prefix) :] not in files
            ):
                fs.rm_file(path)
        write_atomically(
            fs, manifest_path, Resource.manifest_fpath(resource_dir).read_bytes()
        )
        pushed.resources += 1
        pushed.files += len(files) + 1
        pushed.bytes += sum(files.values())
    # The side-cars of the acquisitions and the accession, the accession's metadata last
    side_cars = [
        acquisition / Metadata.FNAME
        for acquisition in sorted(staged_dir.iterdir())
        if acquisition.is_dir()
        and "." in acquisition.name
        and not acquisition.name.startswith(".")
    ] + [staged_dir / FIELDS_FNAME, staged_dir / Metadata.FNAME]
    for side_car in side_cars:
        if side_car.exists():
            target = f"{remote_dir}/{side_car.relative_to(staged_dir).as_posix()}"
            if _put_if_changed(fs, sizes, side_car, target):
                pushed.files += 1
                pushed.bytes += side_car.stat().st_size
    return pushed


def probe_destination(fs: fsspec.AbstractFileSystem, root: str) -> None:
    """Check the destination can be listed, so that an endpoint that is down or
    credentials that can't see it are reported once, clearly, rather than as an error
    for every accession

    Raises
    ------
    DestinationUnreachable
        if it can't be listed
    """
    try:
        fs.find(root, maxdepth=1)
    except Exception as e:
        raise DestinationUnreachable(f"Can't list the destination '{root}': {e}") from e


def _resource_dirs(staged_dir: Path) -> list[tuple[str, Path]]:
    """The resource directories of a staged accession, by their paths relative to it:
    '<acquisition>/<resource>' for the resources of acquisitions (whose directories
    have a '.' in their names), and '<resource>' for those of the accession itself"""
    resource_dirs: list[tuple[str, Path]] = []
    for item in sorted(staged_dir.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        if "." in item.name:
            resource_dirs.extend(
                (f"{item.name}/{sub.name}", sub)
                for sub in sorted(item.iterdir())
                if sub.is_dir() and not sub.name.startswith(".")
            )
        else:
            resource_dirs.append((item.name, item))
    return resource_dirs


def _read_manifest(resource_dir: Path) -> dict[str, ty.Any]:
    manifest_path = Resource.manifest_fpath(resource_dir)
    if not manifest_path.exists():
        raise ValueError(
            f"'{resource_dir}' has no manifest, so it can't be pushed (was it staged "
            "by an older version?)"
        )
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict):
        raise ValueError(f"The manifest of '{resource_dir}' can't be read")
    return manifest


def _local_files(resource_dir: Path) -> dict[str, int]:
    """The files of a staged resource to copy, besides its manifest, by their paths
    relative to it, with their sizes. Links are followed, since the staged files are
    often links to where the data came from"""
    files: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(resource_dir, followlinks=True):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fname in sorted(filenames):
            if fname.startswith(".") or (
                is_side_car(fname) and fname != Metadata.FNAME
            ):
                continue
            path = Path(dirpath) / fname
            files[path.relative_to(resource_dir).as_posix()] = path.stat().st_size
    return files


def _remote_sizes(fs: fsspec.AbstractFileSystem, remote_dir: str) -> dict[str, int]:
    """The sizes of the files under `remote_dir` on `fs`, listed in one call"""
    try:
        listing = fs.find(remote_dir, detail=True)
    except FileNotFoundError:
        return {}
    return {
        path: int(info.get("size") or 0)
        for path, info in listing.items()
        if info.get("type", "file") == "file"
    }


def _is_complete(
    fs: fsspec.AbstractFileSystem,
    sizes: ty.Mapping[str, int],
    remote: str,
    files: ty.Mapping[str, int],
    manifest: ty.Mapping[str, ty.Any],
) -> bool:
    """Whether a resource is at the destination as it is staged: its manifest matches,
    and its files are all there with the staged sizes"""
    if f"{remote}/{Resource.MANIFEST_FNAME}" not in sizes:
        return False
    if any(sizes.get(f"{remote}/{relpath}") != size for relpath, size in files.items()):
        return False
    return read_remote_manifest(fs, remote) == manifest


def _put_if_changed(
    fs: fsspec.AbstractFileSystem,
    sizes: ty.Mapping[str, int],
    local: Path,
    target: str,
) -> bool:
    """Write a small side-car to the destination, unless it is already there with the
    same contents. Returns whether it was written"""
    data = local.read_bytes()
    if sizes.get(target) == len(data):
        try:
            if fs.cat_file(target) == data:
                return False
        except FileNotFoundError:
            pass
    write_atomically(fs, target, data)
    return True


def _settled(staged_dir: Path, wait_period: int) -> bool:
    """Whether nothing in a staged accession has been modified for `wait_period`
    seconds. Links aren't followed, so that a dangling one is reported rather than
    raising"""
    if wait_period <= 0:
        return True
    cutoff = time.time() - wait_period
    if staged_dir.lstat().st_mtime > cutoff:
        return False
    for dirpath, dirnames, filenames in os.walk(staged_dir):
        for name in dirnames + filenames:
            if (Path(dirpath) / name).lstat().st_mtime > cutoff:
                return False
    return True


def _dangling_links(staged_dir: Path) -> list[Path]:
    """The links in a staged accession whose targets don't exist"""
    dangling = []
    for dirpath, dirnames, filenames in os.walk(staged_dir):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            if path.is_symlink() and not path.exists():
                dangling.append(path)
    return dangling


def _fingerprint(staged_dir: Path) -> str:
    """The fingerprint of a staged accession's files that ais-edge's s3-uploader
    recorded in its markers, and its data-policy engine computes to compare with them:
    the MD5 of the lines '<./relative-path> <size> <mtime>' of every file, following
    links, sorted, as `find -L . -type f -exec stat -c '%n %s %Y' {} + | sort | md5sum`
    gives them (with the C locale's sort order)"""
    lines = []
    for dirpath, dirnames, filenames in os.walk(staged_dir, followlinks=True):
        for fname in filenames:
            path = Path(dirpath) / fname
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            relpath = "./" + path.relative_to(staged_dir).as_posix()
            lines.append(f"{relpath} {stat.st_size} {int(stat.st_mtime)}")
    text = "".join(line + "\n" for line in sorted(lines, key=lambda s: s.encode()))
    return hashlib.md5(text.encode()).hexdigest()


def _sweep_markers(marker_dir: Path, marker_root: Path) -> None:
    """Remove the markers of accessions that no stage directory under `marker_root`
    holds any more, so none can be asked about again"""
    if not marker_dir.is_dir():
        return
    held = {
        accession.name
        for stage in marker_root.iterdir()
        if stage.is_dir()
        for accession in stage.iterdir()
        if accession.is_dir()
    }
    for marker in marker_dir.iterdir():
        if marker.is_file() and marker.name not in held:
            marker.unlink()
            logger.info(
                "Removed the push marker of '%s', as no stage holds it any more",
                marker.name,
            )


def _requeue_claims(recopy_dir: Path) -> None:
    """Put back the re-copy requests claimed by a run that didn't finish"""
    if not recopy_dir.is_dir():
        return
    for claimed in recopy_dir.glob("*.claimed"):
        request = claimed.with_suffix("")
        if request.exists():
            claimed.unlink()
        else:
            claimed.replace(request)
        logger.info("Requeued the re-copy request of '%s'", request.name)


def _claim_recopy(recopy_dir: Path | None, name: str) -> Path | None:
    """Claim the re-copy request for an accession, if there is one, by renaming it, so
    that a request made while it is being copied is served on the next pass"""
    if recopy_dir is None:
        return None
    request = recopy_dir / name
    claimed = recopy_dir / f"{name}.claimed"
    try:
        request.replace(claimed)
    except FileNotFoundError:
        return None
    logger.info("Claimed the request to copy '%s' again", name)
    return claimed


def _release_claim(claimed: Path | None) -> None:
    """Put a claimed re-copy request back, unless a newer one has been made"""
    if claimed is None or not claimed.exists():
        return
    request = claimed.with_suffix("")
    if request.exists():
        claimed.unlink()
    else:
        claimed.replace(request)


@contextlib.contextmanager
def _locked(lock_file: Path | None, wait: int) -> ty.Iterator[None]:
    """Hold an exclusive ``flock`` on `lock_file`, if one is given, waiting up to `wait`
    seconds for it"""
    if lock_file is None:
        yield
        return
    try:
        import fcntl
    except ImportError as e:  # pragma: no cover - Windows
        raise LockFailed("Lock files need fcntl, which this platform lacks") from e
    try:
        handle = open(lock_file, "a")
    except OSError as e:
        raise LockFailed(f"Can't open the lock file '{lock_file}': {e}") from e
    try:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(str(lock_file)) from None
                time.sleep(min(1.0, max(deadline - time.monotonic(), 0)))
            except OSError as e:
                raise LockFailed(f"Can't lock '{lock_file}': {e}") from e
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()
