"""How staged accessions are found, and where their resources go in a folder store.

An accession is deposited in a folder per label, in level order, under the root of
the store, with a folder per acquisition (named as in the staging directory,
'<id>.<description>') holding a folder per resource:

    <root>/<label1>/<label2>/.../<acq-id>.<acq-desc>/<resource>/<files...>
                                                              /__MANIFEST__.json
    <root>/<label1>/<label2>/.../<session-resource>/<files...>
    <root>/<label1>/<label2>/.../__FIELDS__.json

The resources' manifests (the checksums of their files) are kept, and are written
after the files they list, so a resource with a manifest is a complete one, on
every kind of file system. The accession's fields are kept too, but not its
metadata.
"""

import json
import typing as ty
from pathlib import Path

import attrs
import fsspec

from accessionflow.helpers.arg_types import StoreCredentials
from accessionflow.helpers.logging import logger
from accessionflow.helpers.remote_fs import (
    is_side_car,
    md5,
    open_fs,
    read_remote_manifest,
    remote_md5,
    write_atomically,
)
from accessionflow.helpers.remotes import (
    LocalSessionListing,
    SessionListing,
    dir_older_than,
    iterate_s3_sessions,
    list_session_dirs,
)
from accessionflow.model.accession import Accession
from accessionflow.model.resource import Resource

STORE_TYPE = "folder"
FIELDS_FNAME = "__FIELDS__.json"


def open_store(
    dest: str, storage_options: ty.Mapping[str, ty.Any] | None = None
) -> tuple[fsspec.AbstractFileSystem, str]:
    """The file system of the store at `dest` (a path or an fsspec URL, e.g.
    's3://bucket/archive'), and the store's root path within it"""
    return open_fs(dest, storage_options)


def staged_sessions(
    input_dir: str | Path,
    wait_period: int = 0,
    store_credentials: StoreCredentials | None = None,
    temp_dir: Path | None = None,
    s3_max_workers: int | None = None,
) -> ty.Iterator[SessionListing]:
    """The labelled accessions in a local staging directory, or an S3 bucket, that
    haven't been modified for `wait_period` seconds"""
    if str(input_dir).startswith("s3://"):
        if store_credentials is None:
            raise ValueError(
                f"Credentials are needed to read staged accessions from '{input_dir}'"
            )
        sessions = iterate_s3_sessions(
            str(input_dir),
            store_credentials,
            temp_dir,
            wait_period=wait_period,
            max_workers=s3_max_workers,
        )
        next(sessions)  # the number of sessions comes first
        yield from sessions
        return
    for session_dir in list_session_dirs(Path(input_dir)):
        if not dir_older_than(session_dir, wait_period):
            logger.info(
                "Skipping '%s' as it was modified less than %d seconds ago",
                session_dir.name,
                wait_period,
            )
            continue
        yield LocalSessionListing(session_dir)


def load_labelled(listing: SessionListing, require_manifest: bool) -> Accession:
    """Load a staged accession, checking it was labelled for a folder store"""
    accession = Accession.load(listing.cache_path, require_manifest=require_manifest)
    if not accession.labels:
        raise ValueError(f"'{listing.name}' hasn't been labelled")
    if accession.store_type not in (None, STORE_TYPE):
        raise ValueError(
            f"'{listing.name}' was labelled for a '{accession.store_type}' data store, "
            "not a folder store. Label it with 'label folder' to deposit it in one"
        )
    return accession


@attrs.define
class StagedResource:
    """A resource of a staged accession, and where it goes in the store"""

    name: str
    staged_dir: Path
    store_dir: str
    #: file path (relative to the resource directory) -> MD5 checksum
    checksums: dict[str, str]
    datatype: str | None = None

    @property
    def manifest(self) -> dict[str, ty.Any]:
        return {"datatype": self.datatype, "checksums": self.checksums}


def staged_resources(
    accession: Accession, staged_dir: Path, root: str
) -> ty.Iterator[StagedResource]:
    """The resources of a staged accession, with their checksums and where they go in
    the store whose root is `root`"""
    store_dir = accession_dir(accession, root)
    resource_dirs = [
        (resource, f"{scan.id}.{scan.type or ''}/{resource.name}")
        for scan in accession.acquisitions.values()
        for resource in scan.resources.values()
    ] + [(resource, resource.name) for resource in accession.session_resources.values()]
    for resource, relpath in resource_dirs:
        resource_dir = staged_dir / relpath
        manifest_fpath = Resource.manifest_fpath(resource_dir)
        if manifest_fpath.exists():
            manifest = json.loads(manifest_fpath.read_text())
            checksums = manifest["checksums"]
            datatype = manifest.get("datatype")
        else:
            # Staged without a manifest (--dont-require-manifest), so work the
            # checksums out from the files
            checksums = {
                str(p.relative_to(resource_dir).as_posix()): md5(p)
                for p in sorted(resource_dir.rglob("*"))
                if p.is_file() and not is_side_car(p.name)
            }
            datatype = None
        yield StagedResource(
            name=relpath,
            staged_dir=resource_dir,
            store_dir=f"{store_dir}/{relpath}",
            checksums=checksums,
            datatype=datatype,
        )


def accession_dir(accession: Accession, root: str) -> str:
    return "/".join([root, *accession.labels.values()])


# The names the folder store's modules use
read_store_manifest = read_remote_manifest

__all__ = [
    "STORE_TYPE",
    "FIELDS_FNAME",
    "StagedResource",
    "accession_dir",
    "load_labelled",
    "md5",
    "open_store",
    "read_store_manifest",
    "remote_md5",
    "staged_resources",
    "staged_sessions",
    "write_atomically",
]
