"""Reading and writing staged accessions on any file system fsspec supports: a local
path, a mount, or a remote one such as S3 or SFTP.

Shared by the stages that copy accessions to another file system, e.g. ``push`` and
the folder store, so that they agree on what a complete copy of a resource is: one
whose manifest has been written, since it is always written after the files it lists.
"""

import hashlib
import json
import tempfile
import typing as ty
from pathlib import Path

import fsspec
from fsspec.implementations.local import LocalFileSystem

from accessionflow.helpers.logging import logger
from accessionflow.model.resource import Resource


def open_fs(
    dest: str, storage_options: ty.Mapping[str, ty.Any] | None = None
) -> tuple[fsspec.AbstractFileSystem, str]:
    """The file system at `dest` (a path or an fsspec URL, e.g. 's3://bucket/archive'),
    and the root path within it"""
    fs, root = fsspec.core.url_to_fs(str(dest), **dict(storage_options or {}))
    return fs, root.rstrip("/")


def parse_storage_options(pairs: ty.Iterable[tuple[str, str]]) -> dict[str, ty.Any]:
    """The fsspec options given by '--storage-option KEY VALUE' pairs, with values
    that are JSON (e.g. 'true', '10', '{"a": 1}') decoded, and others left as strings"""
    options: dict[str, ty.Any] = {}
    for key, value in pairs:
        try:
            options[key] = json.loads(value)
        except ValueError:
            options[key] = value
    return options


def md5(path: Path) -> str:
    """The MD5 checksum of a local file"""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(2**20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote_md5(fs: fsspec.AbstractFileSystem, path: str) -> str:
    """The MD5 checksum of a file on `fs`, read back in full"""
    digest = hashlib.md5()
    with fs.open(path, "rb") as f:
        for chunk in iter(lambda: f.read(2**20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_remote_manifest(
    fs: fsspec.AbstractFileSystem, resource_dir: str
) -> dict[str, ty.Any] | None:
    """The manifest of a resource on `fs`, or None if it has none (it hasn't been
    copied, or copying it didn't finish) or it can't be read"""
    try:
        manifest = json.loads(fs.cat_file(f"{resource_dir}/{Resource.MANIFEST_FNAME}"))
    except FileNotFoundError:
        return None
    except (ValueError, UnicodeDecodeError):
        logger.warning("The manifest of '%s' can't be read", resource_dir)
        return None
    return manifest if isinstance(manifest, dict) else None


def write_atomically(fs: fsspec.AbstractFileSystem, path: str, data: bytes) -> None:
    """Write a small file in one call, so that it is either absent or complete"""
    if isinstance(fs, LocalFileSystem):
        # A local write can be a rename, which is atomic
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=f".{target.name}.", delete=False
        ) as tmp:
            tmp.write(data)
        Path(tmp.name).replace(target)
    else:
        # Object stores publish an object only once it has been written in full
        fs.pipe_file(path, data)


def is_side_car(fname: str) -> bool:
    """Whether a file in a resource directory is one of accessionflow's own side-cars,
    rather than one of the resource's files"""
    return fname in (
        Resource.MANIFEST_FNAME,
        Resource.OLD_MANIFEST_FNAME,
        Resource.MANIFEST_TMP_FNAME,
        "__METADATA__.json",
    ) or fname.endswith(".tmp")
