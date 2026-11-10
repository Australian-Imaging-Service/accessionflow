"""Collates files found in folders, on a local path or a mounted file system, into
accessions"""

from accessionflow.model.source import Source

SOURCE = Source(name="folder", title="folder")

__all__ = ["SOURCE"]
