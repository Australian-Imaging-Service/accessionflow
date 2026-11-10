"""Collates the DICOM studies held by an Orthanc server into accessions, by
hardlinking the files from Orthanc's storage directory"""

from accessionflow.model.source import Source

SOURCE = Source(name="orthanc", title="Orthanc")

__all__ = ["SOURCE"]
