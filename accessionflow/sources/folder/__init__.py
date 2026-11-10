"""Collates files found in folders, on a local path, a mount or in an S3 bucket,
into accessions"""

from accessionflow.model.source import Source

SOURCE = Source(name="folder", title="folder")

__all__ = ["SOURCE"]
