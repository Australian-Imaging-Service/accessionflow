"""Support for depositing accessions in nested label folders, on a local
path, a mount, or a remote file system such as S3 or SFTP (through fsspec)"""

from accessionflow.model.store import LabelLevel, Store

STORE = Store(
    name="folder",
    title="folder",
    # The levels of the folders are named when labelling, with 'label folder --level'
    labels=None,
    acquisition=LabelLevel(
        "acquisition", default="SeriesDescription", description="description"
    ),
    # An acquisition can hold several resources, e.g. the DICOM files and a NIfTI
    # conversion, each in its own folder
    multiple_resources=True,
)

__all__ = ["STORE"]
